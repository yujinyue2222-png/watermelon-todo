"""增量同步引擎。

冲突策略是**后写覆盖**（last-write-wins）：同一条待办以 ``updated_at`` 更大的
一方为准。删除通过墓碑传播，因此「A 端删除」不会被「B 端的旧副本」复活。

这不是 CRDT，极端情况下（两端离线同时改同一条待办）会丢掉较早的那次编辑。
对个人待办来说这个取舍是合适的：实现简单、行为可预期，且服务端不需要理解业务字段。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from backend.models.app_config import SyncSettings
from backend.models.task import Task, now_ms
from backend.services.task_service import TaskService
from backend.sync.client import SyncClient, SyncError

logger = logging.getLogger(__name__)

# 单次 sync_now 最多来回几轮（服务端分页时需要多轮）
MAX_ROUNDS = 20


@dataclass
class PushBatch:
    """一轮要发给服务端的数据。

    Attributes:
        stamps: ``{待办id: 推送时的 updated_at}``。合并时用它判断这条待办在
            网络请求期间有没有被用户又改一次——改过就不能清脏标记。
    """

    since: int = 0
    changes: list[dict[str, Any]] = field(default_factory=list)
    stamps: dict[str, int] = field(default_factory=dict)

    @property
    def is_empty(self) -> bool:
        """既没有要推的改动，也不是首次全量拉取。"""
        return not self.changes and self.since > 0


@dataclass
class SyncResult:
    """一次同步的结果。"""

    pushed: int = 0
    pulled: int = 0
    applied: int = 0
    rounds: int = 0
    more: bool = False
    error: str = ""

    @property
    def ok(self) -> bool:
        """是否成功（没有错误）。"""
        return not self.error

    @property
    def changed(self) -> bool:
        """本地数据是否发生了变化，决定界面要不要刷新。"""
        return self.applied > 0

    def summary(self) -> str:
        """给界面显示的一句话。"""
        if self.error:
            return f"同步失败：{self.error}"
        if not self.pushed and not self.applied:
            return "已是最新"
        parts = []
        if self.pushed:
            parts.append(f"上传 {self.pushed}")
        if self.applied:
            parts.append(f"更新 {self.applied}")
        return "同步完成（" + "，".join(parts) + "）"


class SyncEngine:
    """把本地待办与远端对齐。"""

    def __init__(
        self,
        tasks: TaskService,
        settings: SyncSettings,
        save_settings: Callable[[], Any],
    ) -> None:
        """
        Args:
            tasks: 待办服务。
            settings: 同步设置（会被就地更新游标与状态）。
            save_settings: 持久化配置的回调。
        """
        self._tasks = tasks
        self._settings = settings
        self._save_settings = save_settings

    @property
    def settings(self) -> SyncSettings:
        """当前同步设置。"""
        return self._settings

    @property
    def is_configured(self) -> bool:
        """是否已配置好可以同步。"""
        return self._settings.is_configured

    def make_client(self) -> SyncClient:
        """按当前设置创建客户端。"""
        return SyncClient(
            server_url=self._settings.server_url,
            access_token=self._settings.access_token,
        )

    # ------------------------------------------------------- 三段式同步流程
    def prepare(self) -> PushBatch:
        """挑出本地待推送的改动（主线程调用）。"""
        batch = PushBatch(since=self._settings.cursor)
        for task in self._tasks.dirty_records():
            batch.changes.append(task.to_sync_payload())
            batch.stamps[task.id] = task.updated_at
        return batch

    def exchange(self, batch: PushBatch, client: Optional[SyncClient] = None) -> dict[str, Any]:
        """发起网络请求（可在后台线程调用）。

        Args:
            batch: :meth:`prepare` 的产物。
            client: 复用的客户端；为 None 时新建。

        Returns:
            服务端响应。

        Raises:
            SyncError: 网络或服务端异常。
        """
        target = client or self.make_client()
        return target.sync(self._settings.user_id, batch.since, batch.changes)

    def apply(self, batch: PushBatch, response: dict[str, Any]) -> SyncResult:
        """合并服务端响应（主线程调用）。"""
        result = SyncResult(rounds=1)

        # rejected：服务端已有同样或更新的版本，这条推送可以就此作罢，
        #   否则它会永远保持脏状态、每次同步都重复上传。
        # refused：服务端根本没能存下（例如超出容量上限），必须保留脏标记
        #   等下次重试——当成推送成功的话这条待办就只剩本机有了，
        #   如果它还是个墓碑，删除会在墓碑被清理后彻底传不出去。
        settled = set(response.get("accepted") or []) | set(response.get("rejected") or [])
        refused = set(response.get("refused") or [])
        settled -= refused
        self._tasks.mark_synced(
            {task_id: batch.stamps[task_id] for task_id in settled if task_id in batch.stamps}
        )
        result.pushed = len(response.get("accepted") or [])

        incoming = response.get("changes") or []
        remote_tasks = []
        for item in incoming:
            if isinstance(item, dict):
                remote_tasks.append(Task.from_dict(item))
        result.pulled = len(remote_tasks)
        result.applied = self._tasks.apply_remote(remote_tasks)

        # 先把待办落盘，成功了才允许游标前进。反过来的话，写盘失败时游标已经
        # 越过这批改动，而拉取条件是 server_seq > cursor，它们再也不会下发
        if not self._tasks.save(notify=False):
            result.error = "本地数据写入失败，已保留原游标等下次重试"
            logger.error("同步拉取的数据未能落盘，游标保持在 %d", self._settings.cursor)
            self._settings.last_error = result.error
            self._save_settings()
            return result

        try:
            self._settings.cursor = max(0, int(response.get("cursor", self._settings.cursor)))
        except (TypeError, ValueError):
            logger.warning("服务端返回的游标非法，保留原值")

        # 被拒收的记录仍然是脏的，但重推只会再被拒一次，
        # 不能把它们算进「还有改动要推」，否则每次同步都空转满 MAX_ROUNDS 轮
        pending = [task for task in self._tasks.dirty_records() if task.id not in refused]
        result.more = bool(response.get("more")) or bool(pending)
        self._settings.last_sync_at = now_ms()
        if refused:
            result.error = f"服务端存储已满，{len(refused)} 条待办未能上传"
            logger.warning("服务端拒收 %d 条待办（容量上限）", len(refused))
            self._settings.last_error = result.error
        else:
            self._settings.last_error = ""
        self._save_settings()
        self._warn_on_clock_skew(response)
        return result

    def sync_now(self) -> SyncResult:
        """完整同步一次（会阻塞，适合命令行与测试）。

        Returns:
            汇总结果；未配置或失败时 ``error`` 非空。
        """
        if not self.is_configured:
            return SyncResult(error="尚未配置同步（需要服务器地址和同步码）")

        client = self.make_client()
        total = SyncResult()
        for round_index in range(MAX_ROUNDS):
            batch = self.prepare()
            try:
                response = self.exchange(batch, client)
            except SyncError as exc:
                total.error = str(exc)
                self._settings.last_error = str(exc)
                self._save_settings()
                logger.warning("同步失败：%s", exc)
                return total

            round_result = self.apply(batch, response)
            total.pushed += round_result.pushed
            total.pulled += round_result.pulled
            total.applied += round_result.applied
            total.rounds = round_index + 1
            if round_result.error:
                total.error = round_result.error
                break
            if not round_result.more:
                break
        else:
            logger.warning("同步轮次达到上限 %d，剩余改动留待下次", MAX_ROUNDS)
            total.more = True

        logger.info(
            "同步完成：上传 %d，下发 %d，本地更新 %d，共 %d 轮",
            total.pushed,
            total.pulled,
            total.applied,
            total.rounds,
        )
        return total

    def record_error(self, message: str) -> None:
        """记录一次同步失败原因（供后台线程回调使用）。"""
        self._settings.last_error = message
        self._save_settings()

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _warn_on_clock_skew(response: dict[str, Any]) -> None:
        """本机时钟与服务端差太多时告警。

        「后写覆盖」完全依赖客户端时间戳，本机时间不准会让同步结果变得诡异
        （比如旧改动盖掉新改动），所以这里主动记一条日志方便排查。
        """
        try:
            server_time = int(response.get("server_time", 0))
        except (TypeError, ValueError):
            return
        if not server_time:
            return
        skew_seconds = abs(server_time - now_ms()) / 1000
        if skew_seconds > 300:
            logger.warning(
                "本机时间与服务器相差约 %.0f 秒，可能影响同步冲突判定，建议校准系统时间",
                skew_seconds,
            )
