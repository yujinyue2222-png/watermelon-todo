"""待办任务模型。

模型负责「一条待办长什么样」以及与 JSON 字典的互转；
业务规则（排序、循环生成、提醒判定）在 ``backend/services`` 里。

多端同步相关的三个字段：

``updated_at``
    最后修改时间（UTC 毫秒）。同步冲突用它做「后写覆盖」判定。
``deleted``
    软删除标记（墓碑）。删除必须留痕，否则另一台离线设备再上线时
    会把这条待办又同步回来。
``dirty``
    本地有未推送的改动。**只存在本地**，不会上传给服务端。
"""

from __future__ import annotations

import datetime
import secrets
from dataclasses import dataclass, field
from typing import Any, Optional

from backend.core.datetime_utils import due_datetime
from backend.models.enums import Priority, Recurrence, Remind, StrongUnit, TaskStatus

# 随机后缀长度（字节）：让多台设备离线各自新建时 ID 不会撞
_ID_SUFFIX_BYTES = 3


def now_ms() -> int:
    """当前 UTC 时间的毫秒时间戳。"""
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)


def generate_task_id(offset: int = 0) -> str:
    """生成全局唯一的任务 ID。

    形如 ``1754000000123-a1b2c3``：毫秒时间戳保证大致有序、便于排查，
    随机后缀保证多台设备离线新建时不会撞 ID。

    Args:
        offset: 批量创建时的序号偏移。
    """
    return f"{now_ms() + offset}-{secrets.token_hex(_ID_SUFFIX_BYTES)}"


def _now_iso() -> str:
    """当前时间的 ISO 字符串（秒级）。"""
    return datetime.datetime.now().isoformat(timespec="seconds")


def _iso_to_ms(text: str) -> int:
    """把 ISO 时间字符串转成毫秒时间戳；解析失败返回 0。"""
    try:
        return int(datetime.datetime.fromisoformat(text).timestamp() * 1000)
    except (TypeError, ValueError):
        return 0


@dataclass
class SubTask:
    """把一条大待办拆成的小步骤。"""

    text: str
    done: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> SubTask:
        """从 JSON 字典构建。"""
        return cls(text=str(raw.get("text", "")), done=bool(raw.get("done", False)))

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 字典。"""
        return {"text": self.text, "done": self.done}


@dataclass
class StrongRemind:
    """单条待办的「强提醒」配置。

    与普通提醒的区别：强提醒会在截止前的时间窗内**反复**弹窗，
    直到任务完成或达到次数上限。
    """

    enabled: bool = False
    before_value: int = 1
    before_unit: str = StrongUnit.DAY
    interval_value: int = 2
    interval_unit: str = StrongUnit.HOUR
    max_count: int = 0  # 0 表示不限次数
    float_window: bool = False  # 是否额外用悬浮小西瓜浮窗提醒
    count: int = 0  # 已提醒次数
    last: Optional[str] = None  # 上次提醒时间（ISO 字符串）

    @property
    def before_seconds(self) -> int:
        """提前多少秒进入提醒窗口。"""
        return StrongUnit.to_seconds(self.before_value, self.before_unit)

    @property
    def interval_seconds(self) -> int:
        """两次提醒的最小间隔秒数。"""
        return StrongUnit.to_seconds(self.interval_value, self.interval_unit)

    @property
    def last_at(self) -> Optional[datetime.datetime]:
        """上次提醒时间；未提醒过或格式异常返回 None。"""
        if not self.last:
            return None
        try:
            return datetime.datetime.fromisoformat(self.last)
        except (TypeError, ValueError):
            # 数据文件里存成数字时 fromisoformat 抛的是 TypeError；
            # 漏掉它会让提醒扫描每 30 秒崩一次
            return None

    def reached_limit(self) -> bool:
        """是否已达到提醒次数上限。"""
        return self.max_count > 0 and self.count >= self.max_count

    def mark_fired(self, moment: datetime.datetime) -> None:
        """记录一次已触发的提醒。"""
        self.last = moment.isoformat(timespec="seconds")
        self.count += 1

    @classmethod
    def from_dict(cls, raw: Optional[dict[str, Any]]) -> StrongRemind:
        """从 JSON 字典构建，缺字段用默认值补齐（兼容老数据）。"""
        # 手工改坏的文件或别家客户端可能把这里写成列表/字符串，
        # 不做类型判断的话下面的 .get 会直接抛 AttributeError
        data = raw if isinstance(raw, dict) else {}
        default = cls()
        return cls(
            enabled=bool(data.get("enabled", default.enabled)),
            before_value=_as_int(data.get("before_value"), default.before_value),
            before_unit=str(data.get("before_unit") or default.before_unit),
            interval_value=_as_int(data.get("interval_value"), default.interval_value),
            interval_unit=str(data.get("interval_unit") or default.interval_unit),
            max_count=_as_int(data.get("max_count"), default.max_count),
            float_window=bool(data.get("float_window", default.float_window)),
            count=_as_int(data.get("count"), default.count),
            last=str(data["last"]) if data.get("last") else None,
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 字典。"""
        return {
            "enabled": self.enabled,
            "before_value": self.before_value,
            "before_unit": self.before_unit,
            "interval_value": self.interval_value,
            "interval_unit": self.interval_unit,
            "max_count": self.max_count,
            "float_window": self.float_window,
            "count": self.count,
            "last": self.last,
        }


@dataclass
class Task:
    """一条待办。

    Attributes:
        project: 所属项目；空串表示「日常待办」，与项目待办是两个独立视图。
        remind_log: 已发过的提醒种类（``ahead`` / ``due``），避免重复打扰。
        recur_anchor: 每月/每年循环最初锚定的「几号」；0 表示按当前 ``due`` 推断。
        updated_at: 最后修改时间（UTC 毫秒），同步冲突判定用。
        deleted: 软删除墓碑标记。
        dirty: 本地有未推送的改动，只存本地、不上传。
    """

    id: str
    text: str
    status: str = TaskStatus.TODO
    category: str = "其他"
    due: str = ""
    priority: str = Priority.DEFAULT
    recur: str = Recurrence.DEFAULT
    recur_end: str = ""
    recur_anchor: int = 0
    remind: str = Remind.DEFAULT
    remind_log: list[str] = field(default_factory=list)
    note: str = ""
    images: list[str] = field(default_factory=list)  # 待办图片文件名列表（存于用户数据目录 images/ 下）
    project: str = ""
    subtasks: list[SubTask] = field(default_factory=list)
    strong: StrongRemind = field(default_factory=StrongRemind)
    pinned: bool = False
    notified: bool = False
    created: str = field(default_factory=_now_iso)
    updated_at: int = field(default_factory=now_ms)
    deleted: bool = False
    dirty: bool = False

    def touch(self) -> None:
        """标记「本地刚改过」：更新时间戳并置脏，等待下次同步推送。

        时间戳保证严格递增：毫秒精度下连续两次编辑很可能落在同一毫秒，
        而服务端按「不比我新就拒绝」判定，时间戳不推进的话第二次编辑
        会被当成陈旧数据丢掉。
        """
        self.updated_at = max(now_ms(), self.updated_at + 1)
        self.dirty = True

    @property
    def image(self) -> str:
        """第一张图片的文件名；没有图片返回空串。

        兼容旧版单图时期的代码（卡片缩略图、删除清理等）。
        """
        return self.images[0] if self.images else ""

    @property
    def is_done(self) -> bool:
        """是否已完成。"""
        return self.status == TaskStatus.DONE

    @property
    def is_daily(self) -> bool:
        """是否属于「日常待办」（不归属任何项目）。"""
        return not self.project

    @property
    def due_at(self) -> Optional[datetime.datetime]:
        """截止时刻；未填或无法解析返回 None。"""
        return due_datetime(self.due)

    @property
    def is_urgent_priority(self) -> bool:
        """紧急程度是否属于 P0/P1/P2。"""
        return self.priority in Priority.URGENT

    def subtask_progress(self) -> tuple[int, int]:
        """返回 ``(已完成小步骤数, 小步骤总数)``。"""
        return sum(1 for item in self.subtasks if item.done), len(self.subtasks)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Task:
        """从 JSON 字典构建，并顺带完成历史数据的取值迁移。

        迁移内容：
        - 旧的「紧急」优先级并入 P1；
        - 缺失或为空的提醒档位补成默认「到期当天」；
        - ``note`` / ``project`` / ``strong`` 等新增字段补默认值；
        - 没有 ``updated_at`` 的老数据用创建时间兜底，保证同步比较有依据。
        """
        priority = str(raw.get("priority") or Priority.DEFAULT)
        priority = Priority.LEGACY_MAP.get(priority, priority)

        remind = str(raw.get("remind") or Remind.DEFAULT)
        if remind not in Remind.LEAD_MINUTES:
            remind = Remind.DEFAULT

        # 这两个字段必须判类型再遍历：存成数字会抛 TypeError，
        # 存成字符串更糟——会被逐字符拆成列表且不报错
        subtasks_raw = raw.get("subtasks")
        subtasks = [
            SubTask.from_dict(item)
            for item in (subtasks_raw if isinstance(subtasks_raw, list) else [])
            if isinstance(item, dict)
        ]

        log_raw = raw.get("remind_log")
        remind_log = [str(item) for item in log_raw] if isinstance(log_raw, list) else []

        # 图片兼容迁移：新版存 images 数组；老数据只有 image 字符串，
        # 迁移成单元素列表；两者都没有则保持空列表
        images_raw = raw.get("images")
        if isinstance(images_raw, list):
            images = [str(name) for name in images_raw if name]
        else:
            legacy = str(raw.get("image") or "")
            images = [legacy] if legacy else []

        created = str(raw.get("created") or _now_iso())
        updated_at = _as_int(raw.get("updated_at"), 0) or _iso_to_ms(created)

        return cls(
            id=str(raw.get("id") or generate_task_id()),
            text=str(raw.get("text", "")),
            status=str(raw.get("status") or TaskStatus.TODO),
            category=str(raw.get("category") or "其他"),
            due=str(raw.get("due") or ""),
            priority=priority,
            recur=str(raw.get("recur") or Recurrence.DEFAULT),
            recur_end=str(raw.get("recur_end") or ""),
            recur_anchor=_as_int(raw.get("recur_anchor"), 0),
            remind=remind,
            remind_log=remind_log,
            note=str(raw.get("note") or ""),
            images=images,
            project=str(raw.get("project") or ""),
            subtasks=subtasks,
            strong=StrongRemind.from_dict(raw.get("strong")),
            pinned=bool(raw.get("pinned", False)),
            notified=bool(raw.get("notified", False)),
            created=created,
            updated_at=updated_at,
            deleted=bool(raw.get("deleted", False)),
            dirty=bool(raw.get("dirty", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为本地 JSON 字典（字段顺序与 v2 数据文件保持一致）。"""
        return {
            "id": self.id,
            "text": self.text,
            "status": self.status,
            "category": self.category,
            "due": self.due,
            "priority": self.priority,
            "recur": self.recur,
            "recur_end": self.recur_end,
            "recur_anchor": self.recur_anchor,
            "subtasks": [item.to_dict() for item in self.subtasks],
            "remind": self.remind,
            "remind_log": list(self.remind_log),
            "note": self.note,
            "images": list(self.images),
            "image": self.image,  # 兼容旧版单图字段与旧同步服务端
            "project": self.project,
            "created": self.created,
            "notified": self.notified,
            "pinned": self.pinned,
            "strong": self.strong.to_dict(),
            "updated_at": self.updated_at,
            "deleted": self.deleted,
            "dirty": self.dirty,
        }

    def to_sync_payload(self) -> dict[str, Any]:
        """序列化为上传给服务端的字典。

        与 :meth:`to_dict` 的唯一区别是去掉 ``dirty``——它描述的是
        「本机还没推送」，对其他设备毫无意义，传上去反而会污染对端状态。
        """
        payload = self.to_dict()
        payload.pop("dirty", None)
        return payload


def _as_int(value: Any, fallback: int) -> int:
    """尽力把值转成 int，失败时返回 fallback。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
