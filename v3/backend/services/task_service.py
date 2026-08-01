"""待办的增删改查、排序与循环任务生成。

**删除是软删除**：为了支持多端同步，删除只是把 ``deleted`` 置为 True（墓碑），
否则另一台离线设备再上线时会把已删的待办又同步回来。对外暴露的
:attr:`TaskService.tasks` 已经过滤掉墓碑，所以界面、统计、导出等
调用方完全感知不到它们的存在。
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Optional, Sequence

from backend.core.datetime_utils import advance_date, combine_due, due_sort_key, parse_due
from backend.models.enums import CATEGORY_ALL, Priority, Recurrence, Remind, TaskStatus, ViewMode
from backend.models.task import StrongRemind, SubTask, Task, generate_task_id, now_ms
from backend.repositories.task_repository import TaskRepository

logger = logging.getLogger(__name__)

# 墓碑本地保留天数：超过后物理清理，避免数据文件无限增长。
# 要比服务端的保留期短一些，保证清理前一定已经推送成功过。
TOMBSTONE_KEEP_DAYS = 45
_MS_PER_DAY = 24 * 3600 * 1000

# 允许通过 update() 修改的字段，防止误写出脏字段
_UPDATABLE_FIELDS = frozenset(
    {
        "text",
        "status",
        "category",
        "due",
        "priority",
        "recur",
        "recur_end",
        "remind",
        "remind_log",
        "note",
        "project",
        "subtasks",
        "strong",
        "pinned",
        "notified",
    }
)


@dataclass
class TaskDraft:
    """新建待办时传入的字段集合。"""

    text: str
    category: str = "其他"
    due: str = ""
    priority: str = Priority.DEFAULT
    recur: str = Recurrence.DEFAULT
    recur_end: str = ""
    remind: str = Remind.DEFAULT
    note: str = ""
    project: str = ""


@dataclass
class TaskQuery:
    """列表筛选条件。

    Attributes:
        view: ``daily`` 只看无项目的待办，``project`` 只看指定项目。
        category: ``全部`` 表示不按分类过滤，仅在日常视图生效。
        keyword: 标题关键字，大小写不敏感。
    """

    view: str = ViewMode.DAILY
    project: str = ""
    category: str = CATEGORY_ALL
    keyword: str = ""


@dataclass
class BatchResult:
    """批量新建的结果。"""

    created: list[Task] = field(default_factory=list)
    skipped: int = 0

    @property
    def created_count(self) -> int:
        """成功新建的数量。"""
        return len(self.created)


class TaskService:
    """待办业务逻辑。

    内存里持有全量待办（个人待办量级很小），每次写操作后立即落盘，
    保证异常退出也不丢数据。
    """

    def __init__(
        self,
        repository: TaskRepository,
        on_local_change: Optional[Callable[[], None]] = None,
    ) -> None:
        """
        Args:
            repository: 数据仓库。
            on_local_change: 本地数据被用户改动后的回调，桌面端用它来安排一次同步。
                合并远端数据、清理墓碑等「非用户操作」不会触发它，
                否则同步完又触发同步会自己转起来。
        """
        self._repository = repository
        self._on_local_change = on_local_change
        self._tasks: list[Task] = repository.load()
        self._purge_stale_tombstones()

    def set_change_listener(self, listener: Optional[Callable[[], None]]) -> None:
        """设置本地改动回调。"""
        self._on_local_change = listener

    # ------------------------------------------------------------------ 读取
    @property
    def tasks(self) -> list[Task]:
        """全部有效待办（已排除软删除的墓碑）。"""
        return [task for task in self._tasks if not task.deleted]

    def all_records(self) -> list[Task]:
        """含墓碑的全部记录，仅供同步使用。"""
        return list(self._tasks)

    def reload(self) -> None:
        """从磁盘重新载入。"""
        self._tasks = self._repository.load()
        self._purge_stale_tombstones()

    def save(self, notify: bool = True) -> bool:
        """把当前内存数据写回磁盘。

        Args:
            notify: 是否触发本地改动回调。合并远端结果时传 False。
        """
        saved = self._repository.save(self._tasks)
        if notify and self._on_local_change is not None:
            self._on_local_change()
        return saved

    def get(self, task_id: str) -> Optional[Task]:
        """按 ID 查找有效待办；不存在或已删除返回 None。"""
        task = self._find(task_id)
        return None if task is None or task.deleted else task

    def _find(self, task_id: str) -> Optional[Task]:
        """按 ID 查找记录，包含墓碑。"""
        for task in self._tasks:
            if task.id == task_id:
                return task
        return None

    def query(self, query: TaskQuery) -> list[Task]:
        """按条件筛选并排序。

        排序规则：未完成在前 → 置顶在前 → 优先级高在前 →
        截止时间早在前 → 状态 → 创建时间。

        Args:
            query: 筛选条件。

        Returns:
            排序后的待办列表。
        """
        keyword = (query.keyword or "").strip().lower()
        result = []
        for task in self._tasks:
            if not self._matches(task, query, keyword):
                continue
            result.append(task)
        return sorted(result, key=self._sort_key)

    def visible_ids(self, query: TaskQuery) -> list[str]:
        """当前筛选条件下可见的待办 ID，供「全选」使用。"""
        return [task.id for task in self.query(query)]

    def texts_of_project(self, project: str) -> set[str]:
        """某项目下已有的待办标题集合，用于重复检测。"""
        return {task.text.strip() for task in self.tasks if task.project == project}

    # ------------------------------------------------------------------ 写入
    def create(self, draft: TaskDraft) -> Task:
        """新建一条待办。

        Args:
            draft: 待办字段。

        Returns:
            新建的待办。
        """
        task = Task(
            id=generate_task_id(),
            text=draft.text.strip(),
            category=draft.category,
            due=draft.due,
            priority=draft.priority,
            recur=draft.recur,
            recur_end=draft.recur_end,
            remind=draft.remind,
            note=draft.note,
            project=draft.project,
        )
        task.touch()
        self._tasks.append(task)
        self.save()
        logger.info("新建待办：%s（项目=%s）", task.text, task.project or "日常")
        return task

    def create_many(
        self,
        drafts: Sequence[TaskDraft],
        skip_duplicates: bool = True,
    ) -> BatchResult:
        """批量新建待办。

        Args:
            drafts: 待办字段列表。
            skip_duplicates: 为 True 时跳过与同项目内已有待办同名的条目；
                为 False 时即使重名也照常新增（用户明确选择「继续新增」）。

        Returns:
            新建结果，含成功列表与跳过数量。
        """
        result = BatchResult()
        existing = {(task.project, task.text.strip()) for task in self.tasks}
        for index, draft in enumerate(drafts):
            text = draft.text.strip()
            if not text:
                continue
            key = (draft.project, text)
            if skip_duplicates and key in existing:
                result.skipped += 1
                continue
            existing.add(key)
            task = Task(
                id=generate_task_id(index),
                text=text,
                category=draft.category,
                due=draft.due,
                priority=draft.priority,
                recur=draft.recur,
                recur_end=draft.recur_end,
                remind=draft.remind,
                note=draft.note,
                project=draft.project,
            )
            task.touch()
            self._tasks.append(task)
            result.created.append(task)
        if result.created:
            self.save()
            logger.info("批量新建 %d 条待办，跳过 %d 条", result.created_count, result.skipped)
        return result

    def update(self, task_id: str, **fields: Any) -> Optional[Task]:
        """按字段名更新待办。

        Args:
            task_id: 待办 ID。
            **fields: 需要更新的字段，未知字段会被忽略并记录警告。

        Returns:
            更新后的待办；ID 不存在返回 None。
        """
        task = self.get(task_id)
        if task is None:
            logger.warning("更新失败，待办不存在：%s", task_id)
            return None
        due_changed = "due" in fields and fields["due"] != task.due
        for name, value in fields.items():
            if name not in _UPDATABLE_FIELDS:
                logger.warning("忽略不可更新的字段：%s", name)
                continue
            setattr(task, name, value)
        if due_changed:
            self._reset_deadline_state(task, fields)
        task.touch()
        self.save()
        return task

    @staticmethod
    def _reset_deadline_state(task: Task, fields: Mapping[str, Any]) -> None:
        """改了截止时间后，清掉所有按「上一个截止时间」记的账。

        这些计数器都是针对某一个具体截止时刻的：不清的话，改期后普通提醒会因为
        「已提醒过」而不再响，强提醒也会因为次数用尽或间隔未到而彻底哑火。

        Args:
            task: 已经写入新字段的待办。
            fields: 本次调用传入的字段，调用方显式给了值的就不覆盖。
        """
        if "remind_log" not in fields:
            task.remind_log = []
        task.notified = False
        task.strong.count = 0
        task.strong.last = None
        # 锚定日跟着新的截止日重新推断
        task.recur_anchor = 0

    def delete(self, task_id: str) -> bool:
        """删除一条待办（软删除），返回是否真的删掉了。"""
        task = self.get(task_id)
        if task is None:
            return False
        task.deleted = True
        task.touch()
        self.save()
        return True

    def delete_many(self, task_ids: Iterable[str]) -> int:
        """批量删除（软删除），返回删除条数。"""
        targets = set(task_ids)
        if not targets:
            return 0
        removed = 0
        for task in self._tasks:
            if task.id in targets and not task.deleted:
                task.deleted = True
                task.touch()
                removed += 1
        if removed:
            self.save()
        return removed

    def clear_completed(self) -> int:
        """清除所有已完成待办（软删除），返回清除条数。"""
        removed = 0
        for task in self._tasks:
            if task.is_done and not task.deleted:
                task.deleted = True
                task.touch()
                removed += 1
        if removed:
            self.save()
            logger.info("清除已完成待办 %d 条", removed)
        return removed

    def toggle_status(self, task_id: str) -> Optional[Task]:
        """在「未完成」与「已完成」间切换。

        完成一条循环待办时会自动生成下一期。

        Args:
            task_id: 待办 ID。

        Returns:
            被切换的待办；ID 不存在返回 None。
        """
        task = self.get(task_id)
        if task is None:
            return None
        was_done = task.is_done
        task.status = TaskStatus.TODO if was_done else TaskStatus.DONE
        task.touch()
        if task.is_done and not was_done:
            self._spawn_next_occurrence(task)
        self.save()
        return task

    def set_status_many(self, task_ids: Iterable[str], status: str) -> int:
        """批量设置状态，返回影响条数。"""
        targets = set(task_ids)
        changed = 0
        for task in self.tasks:
            if task.id in targets and task.status != status:
                task.status = status
                task.touch()
                changed += 1
        if changed:
            self.save()
        return changed

    def set_category_many(self, task_ids: Iterable[str], category: str) -> int:
        """批量改分类，返回影响条数。"""
        targets = set(task_ids)
        changed = 0
        for task in self.tasks:
            if task.id in targets and task.category != category:
                task.category = category
                task.touch()
                changed += 1
        if changed:
            self.save()
        return changed

    def set_pinned(self, task_id: str, pinned: Optional[bool] = None) -> Optional[Task]:
        """设置或翻转置顶状态。

        Args:
            task_id: 待办 ID。
            pinned: 目标状态；为 None 时表示翻转当前状态。

        Returns:
            更新后的待办；ID 不存在返回 None。
        """
        task = self.get(task_id)
        if task is None:
            return None
        task.pinned = (not task.pinned) if pinned is None else bool(pinned)
        task.touch()
        self.save()
        return task

    def toggle_subtask(self, task_id: str, index: int) -> Optional[Task]:
        """切换某条待办下第 ``index`` 个小步骤的完成状态。"""
        task = self.get(task_id)
        if task is None:
            return None
        if not 0 <= index < len(task.subtasks):
            logger.warning("小步骤下标越界：task=%s index=%s", task_id, index)
            return task
        task.subtasks[index].done = not task.subtasks[index].done
        task.touch()
        self.save()
        return task

    def replace_subtasks(self, task_id: str, subtasks: Sequence[SubTask]) -> Optional[Task]:
        """整体替换小步骤列表。"""
        return self.update(task_id, subtasks=list(subtasks))

    def set_strong_remind(self, task_id: str, strong: StrongRemind) -> Optional[Task]:
        """写入强提醒配置。"""
        return self.update(task_id, strong=strong)

    # -------------------------------------------------------------- 同步支持
    def dirty_records(self) -> list[Task]:
        """本地有未推送改动的记录（含墓碑）。"""
        return [task for task in self._tasks if task.dirty]

    def mark_synced(self, stamps: Mapping[str, int]) -> None:
        """清除已推送记录的脏标记。

        只清「时间戳没再变过」的记录：如果推送期间用户又改了同一条待办，
        它的 ``updated_at`` 已经变了，必须保留脏标记等下一轮再推，
        否则这次编辑会永远留在本地。

        Args:
            stamps: ``{待办id: 推送时的 updated_at}``。
        """
        for task in self._tasks:
            pushed_at = stamps.get(task.id)
            if pushed_at is not None and task.updated_at == pushed_at:
                task.dirty = False

    def apply_remote(self, records: Sequence[Task]) -> int:
        """把服务端下发的记录合并进本地。

        冲突规则是「后写覆盖」：``updated_at`` 更大的一方胜出。本地较新时
        保留本地版本，它的脏标记会让它在下一轮被推上去。

        时间戳**打平时以远端为准**，这必须和服务端的判定方向一致
        （服务端在相等时拒绝上传、保留自己那份）。两边都偏袒自己的话，
        同一毫秒内改同一条待办的两台设备会各执己见、永久分叉且无人察觉。

        Args:
            records: 服务端下发的待办。

        Returns:
            实际发生变化的条数。
        """
        changed = 0
        index = {task.id: position for position, task in enumerate(self._tasks)}
        for remote in records:
            position = index.get(remote.id)
            if position is None:
                remote.dirty = False
                self._tasks.append(remote)
                index[remote.id] = len(self._tasks) - 1
                changed += 1
                continue
            local = self._tasks[position]
            if remote.updated_at < local.updated_at:
                continue
            if (
                remote.updated_at == local.updated_at
                and remote.to_sync_payload() == local.to_sync_payload()
            ):
                continue  # 服务端回发的就是本机刚推上去的那份，不必当成变化去刷界面
            remote.dirty = False
            self._tasks[position] = remote
            changed += 1
        if changed:
            self.save(notify=False)
        return changed

    def _purge_stale_tombstones(self) -> None:
        """物理清理早已推送过的老墓碑，避免数据文件无限增长。"""
        deadline = now_ms() - TOMBSTONE_KEEP_DAYS * _MS_PER_DAY
        keep = [
            task
            for task in self._tasks
            if not (task.deleted and not task.dirty and task.updated_at < deadline)
        ]
        removed = len(self._tasks) - len(keep)
        if removed:
            self._tasks = keep
            self.save(notify=False)
            logger.info("清理过期删除记录 %d 条", removed)

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _matches(task: Task, query: TaskQuery, keyword: str) -> bool:
        """判断单条待办是否命中筛选条件。"""
        if task.deleted:
            return False
        if query.view == ViewMode.PROJECT:
            if not query.project or task.project != query.project:
                return False
        else:
            if task.project:
                return False
            if query.category != CATEGORY_ALL and task.category != query.category:
                return False
        if keyword and keyword not in task.text.lower():
            return False
        return True

    @staticmethod
    def _sort_key(task: Task) -> tuple[int, int, int, datetime.datetime, int, str]:
        """列表排序权重。"""
        return (
            1 if task.is_done else 0,
            0 if task.pinned else 1,
            Priority.RANK.get(task.priority, Priority.RANK[Priority.NORMAL]),
            due_sort_key(task.due),
            TaskStatus.RANK.get(task.status, 0),
            task.created,
        )

    def _spawn_next_occurrence(self, task: Task) -> Optional[Task]:
        """为循环待办生成下一期。

        Args:
            task: 刚被标记完成的循环待办。

        Returns:
            新生成的待办；不需要生成时返回 None。
        """
        if not Recurrence.is_repeating(task.recur):
            return None

        base_date, base_time = parse_due(task.due)
        # 锚定日只在第一期推断一次，之后一路传下去：否则 1 月 31 日的每月循环
        # 在 2 月被压到 28 日后，后面每一期都会跟着钉死在 28 日
        anchor_day = task.recur_anchor or (base_date.day if base_date else 0)
        next_date = advance_date(
            base_date or datetime.date.today(),
            task.recur,
            anchor_day or None,
        )
        if next_date is None:
            return None

        if task.recur_end:
            end_date, _ = parse_due(task.recur_end)
            if end_date is not None and next_date > end_date:
                logger.debug("循环待办已到结束日期，不再生成：%s", task.text)
                return None

        next_due = combine_due(next_date, base_time)
        # 同一期只生成一次：文本/截止/周期都相同且尚未完成，说明已经存在
        for existing in self.tasks:
            if (
                existing.text == task.text
                and existing.due == next_due
                and existing.recur == task.recur
                and not existing.is_done
            ):
                return None

        spawned = Task(
            id=generate_task_id(1),
            text=task.text,
            category=task.category,
            due=next_due,
            priority=task.priority,
            recur=task.recur,
            recur_end=task.recur_end,
            recur_anchor=anchor_day,
            remind=task.remind,
            note=task.note,
            project=task.project,
        )
        spawned.touch()
        self._tasks.append(spawned)
        logger.info("循环待办生成下一期：%s → %s", task.text, next_due)
        return spawned
