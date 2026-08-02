"""同步调度。

把后端的三段式同步接到 Qt 的事件循环上：

- **网络**在后台线程跑，界面不卡；
- **合并**回到主线程做，不会和用户正在进行的操作同时改同一份任务列表。

自动同步默认每分钟一次；新建/修改待办后也会安排一次「稍后同步」，
把连续操作合并成一次请求。
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, QThread, QTimer, Signal

from backend.api import TodoBackend
from backend.core.constants import SYNC_INTERVAL_MS, SYNC_TIMEOUT_SECONDS
from backend.sync.client import SyncError
from backend.sync.engine import PushBatch, SyncResult

logger = logging.getLogger(__name__)

# 本地改动后延迟多久再同步，避免连续操作触发多次请求
DEBOUNCE_MS = 3000
# 服务端还有更多分页时，紧接着再来一轮
CONTINUE_MS = 500
# 退出时等待同步线程的时长，留出比 HTTP 超时多一点的余量
_SHUTDOWN_WAIT_MS = SYNC_TIMEOUT_SECONDS * 1000 + 1000


class _ExchangeWorker(QThread):
    """在后台线程里完成一次同步请求。

    Signals:
        succeeded: 请求成功，携带服务端响应字典。
        failed: 请求失败，携带原因。
    """

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, backend: TodoBackend, batch: PushBatch, parent=None) -> None:
        super().__init__(parent)
        self._backend = backend
        self._batch = batch

    def run(self) -> None:
        """只做网络，不碰本地数据。"""
        try:
            response = self._backend.sync.exchange(self._batch)
        except SyncError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            # 后台线程的兜底：异常逃出 run() 的话两个信号都不会发，
            # 界面会一直显示「同步中」而用户永远不知道出了什么事
            logger.exception("同步请求出现未预期的异常")
            self.failed.emit(f"同步异常：{exc}")
            return
        self.succeeded.emit(response)


class SyncController(QObject):
    """管理自动同步的定时器与后台线程。

    Signals:
        state_changed: 同步开始/结束，参数为「是否正在同步」。
        finished: 一轮同步结束，携带 :class:`~backend.sync.engine.SyncResult`。
    """

    state_changed = Signal(bool)
    finished = Signal(object)

    def __init__(self, backend: TodoBackend, parent: Optional[QObject] = None) -> None:
        """
        Args:
            backend: 后端门面。
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._backend = backend
        self._worker: Optional[_ExchangeWorker] = None
        self._pending_batch: Optional[PushBatch] = None
        # 同步进行中又来了手动请求：记下来，等当前这轮结束后补跑一次
        self._queued_manual = False

        self._timer = QTimer(self)
        self._timer.setInterval(SYNC_INTERVAL_MS)
        self._timer.timeout.connect(lambda: self.request_sync(manual=False))

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(lambda: self.request_sync(manual=False))

    @property
    def is_running(self) -> bool:
        """当前是否有同步在进行。"""
        return self._worker is not None and self._worker.isRunning()

    @property
    def is_configured(self) -> bool:
        """是否已配置好同步。"""
        return self._backend.sync.is_configured

    def apply_settings(self) -> None:
        """配置变化后重启自动同步。"""
        if self.is_configured:
            self._timer.start()
            logger.info("自动同步已启用，间隔 %d 秒", SYNC_INTERVAL_MS // 1000)
        else:
            self._timer.stop()
            self._debounce.stop()

    def schedule_after_change(self) -> None:
        """本地数据变化后安排一次同步（带防抖）。"""
        if not self.is_configured:
            return
        self._debounce.start(DEBOUNCE_MS)

    def request_sync(self, manual: bool = False) -> None:
        """发起一次同步。

        Args:
            manual: 是否为用户手动触发。手动触发即使未配置也会给出反馈。
        """
        if not self.is_configured:
            if manual:
                self.finished.emit(SyncResult(error="尚未配置同步，请先设置同步码"))
            return
        if self.is_running:
            # 已有同步在跑。自动同步丢掉就丢掉了（一分钟后还会再来），
            # 但手动请求是用户明确点的，必须记下来等这轮结束后补跑
            self._queued_manual = self._queued_manual or manual
            return

        self._pending_batch = self._backend.sync.prepare()
        worker = _ExchangeWorker(self._backend, self._pending_batch, self)
        worker.succeeded.connect(self._on_succeeded)
        worker.failed.connect(self._on_failed)
        worker.finished.connect(self._on_worker_finished)
        self._worker = worker
        self.state_changed.emit(True)
        worker.start()

    def stop(self) -> None:
        """停机前收尾：停掉定时器并等待线程结束。"""
        self._timer.stop()
        self._debounce.stop()
        if self._worker is not None and self._worker.isRunning():
            # 必须等得比 HTTP 超时更久：线程还在跑就析构 QThread 时，
            # Qt 会 qFatal 直接中止进程，而不是干净退出
            self._worker.wait(_SHUTDOWN_WAIT_MS)

    # ------------------------------------------------------------------ 回调
    def _on_succeeded(self, response: object) -> None:
        """主线程里合并结果。"""
        batch = self._pending_batch
        if batch is None or not isinstance(response, dict):
            return
        result = self._backend.sync.apply(batch, response)
        self.finished.emit(result)
        if result.more:
            # 还有分页或还有没推完的改动，紧接着再来一轮
            QTimer.singleShot(CONTINUE_MS, lambda: self.request_sync(manual=False))

    def _on_failed(self, message: str) -> None:
        """记录失败原因。"""
        self._backend.sync.record_error(message)
        logger.warning("同步失败：%s", message)
        self.finished.emit(SyncResult(error=message))

    def _on_worker_finished(self) -> None:
        """线程结束后清理引用，并补跑排队中的手动同步。"""
        self._pending_batch = None
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None
        queued_manual = self._queued_manual
        self._queued_manual = False
        self.state_changed.emit(False)
        if queued_manual:
            # 同步进行中收到的手动请求在这里补跑，
            # 否则「保存同步设置后立即同步」会被静默丢掉
            QTimer.singleShot(CONTINUE_MS, lambda: self.request_sync(manual=True))
