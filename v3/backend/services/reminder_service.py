"""提醒判定。

本服务只回答「现在该提醒哪些待办」，不负责怎么弹窗——弹什么样的窗口是前端的事。
这样提醒逻辑可以脱离 GUI 单独测试。

两类提醒：

- **普通提醒**：按档位提前 N 分钟提醒一次，到期/过期再提醒一次，各只发一次；
- **强提醒**：在「截止前 N 单位」到截止之间，每隔 M 单位反复提醒，受次数上限约束。

「已提醒过」这类记账信息刻意**不参与多端同步**（不调用 ``Task.touch()``）：
每台设备各自负责提醒自己的主人，手机上弹过不代表电脑上就不该弹。
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Optional

from backend.core.datetime_utils import parse_due
from backend.models.enums import Remind
from backend.models.task import Task
from backend.services.task_service import TaskService

logger = logging.getLogger(__name__)

# 过期判定的宽容度：超过截止 1 分钟才算「已过期」，避免整点抖动
_OVERDUE_TOLERANCE = datetime.timedelta(minutes=1)

# 只填了日期、没填具体时间点时，「到期当天」在这个时刻提醒。
# 不这么处理的话它会落在当天 23:59（date-only 的默认到期时刻），
# 白天一整天都不吭声，等于这个档位形同虚设。
ON_DAY_REMIND_TIME = datetime.time(9, 0)


class ReminderKind:
    """提醒类型。"""

    AHEAD = "ahead"
    DUE = "due"
    STRONG = "strong"


@dataclass
class ReminderEvent:
    """一条待发送的提醒。"""

    task: Task
    kind: str
    phrase: str
    urgent: bool = False
    float_window: bool = False

    @property
    def is_strong(self) -> bool:
        """是否为强提醒。"""
        return self.kind == ReminderKind.STRONG


class ReminderService:
    """扫描全部待办，产出当前需要发出的提醒。"""

    def __init__(self, task_service: TaskService) -> None:
        """
        Args:
            task_service: 待办服务。
        """
        self._tasks = task_service

    def collect(self, now: Optional[datetime.datetime] = None) -> list[ReminderEvent]:
        """收集当前需要弹出的提醒，并记录「已提醒」状态。

        调用方每次拿到的事件都是新的，不会重复；状态变更会立即落盘。

        Args:
            now: 当前时间，便于测试注入。

        Returns:
            需要提醒的事件列表。
        """
        current = now or datetime.datetime.now()
        events: list[ReminderEvent] = []
        changed = False

        for task in self._tasks.tasks:
            if task.is_done:
                continue
            normal_events, normal_changed = self._collect_normal(task, current)
            strong_event, strong_changed = self._collect_strong(task, current)
            events.extend(normal_events)
            if strong_event is not None:
                events.append(strong_event)
            changed = changed or normal_changed or strong_changed

        if changed:
            # notify=False：「已提醒过」是每台设备各自的记账，刻意不参与同步
            # （上面也没有调 touch()），通知出去只会安排一次无事可推的同步
            self._tasks.save(notify=False)
        return events

    # ------------------------------------------------------------------ 内部
    def _collect_normal(
        self,
        task: Task,
        now: datetime.datetime,
    ) -> tuple[list[ReminderEvent], bool]:
        """普通提醒：提前提醒 + 到期提醒，各只发一次。"""
        due_at = task.due_at
        if due_at is None:
            return [], False
        lead = Remind.lead_minutes(task.remind)
        if lead is None:  # 关闭提醒
            return [], False

        events: list[ReminderEvent] = []
        changed = False

        remind_at = self._ahead_moment(task, due_at, lead)
        if remind_at is not None and ReminderKind.AHEAD not in task.remind_log:
            if remind_at <= now < due_at:
                events.append(
                    ReminderEvent(
                        task=task,
                        kind=ReminderKind.AHEAD,
                        phrase=self.lead_phrase(lead) if lead > 0 else "今天到期",
                    )
                )
                task.remind_log.append(ReminderKind.AHEAD)
                changed = True

        if now >= due_at and ReminderKind.DUE not in task.remind_log:
            overdue = now > due_at + _OVERDUE_TOLERANCE
            events.append(
                ReminderEvent(
                    task=task,
                    kind=ReminderKind.DUE,
                    phrase="已过期" if overdue else "现在到期啦",
                    urgent=True,
                )
            )
            task.remind_log.append(ReminderKind.DUE)
            task.notified = True
            changed = True

        return events, changed

    @staticmethod
    def _ahead_moment(
        task: Task,
        due_at: datetime.datetime,
        lead: int,
    ) -> Optional[datetime.datetime]:
        """算出「提前提醒」该在哪一刻发出；不需要提前提醒时返回 None。

        Args:
            task: 待办。
            due_at: 解析好的截止时刻。
            lead: 提前分钟数，0 表示「到期当天」档。
        """
        if lead > 0:
            return due_at - datetime.timedelta(minutes=lead)
        _, moment = parse_due(task.due)
        if moment is not None:
            return None  # 填了具体时间点，到点提醒就够了
        return datetime.datetime.combine(due_at.date(), ON_DAY_REMIND_TIME)

    @staticmethod
    def _collect_strong(
        task: Task,
        now: datetime.datetime,
    ) -> tuple[Optional[ReminderEvent], bool]:
        """强提醒：时间窗内按间隔反复提醒。

        未勾选「悬浮小西瓜浮窗/桌面全局弹出卡片」时，强提醒没有可见输出，
        直接跳过，避免空跑并导致计数/last_at 提前消耗。
        """
        strong = task.strong
        if not strong.enabled or not strong.float_window:
            return None, False
        due_at = task.due_at
        if due_at is None:
            return None, False

        # before_value 为 0 表示「从现在起就开始提醒」
        if strong.before_value <= 0:
            window_start = datetime.datetime.min
        else:
            window_start = due_at - datetime.timedelta(seconds=strong.before_seconds)
        if now < window_start or now >= due_at:
            return None, False

        last_at = strong.last_at
        if last_at is not None and (now - last_at).total_seconds() < strong.interval_seconds:
            return None, False
        if strong.reached_limit():
            return None, False

        strong.mark_fired(now)
        logger.debug("强提醒触发：%s（第 %d 次）", task.text, strong.count)
        return (
            ReminderEvent(
                task=task,
                kind=ReminderKind.STRONG,
                phrase="强提醒",
                urgent=True,
                float_window=strong.float_window,
            ),
            True,
        )

    @staticmethod
    def lead_phrase(minutes: int) -> str:
        """把提前分钟数转成友好话术。"""
        if minutes >= 1440:
            return f"还有 {minutes // 1440} 天到期"
        if minutes >= 60:
            return f"还有 {minutes // 60} 小时到期"
        return f"还有 {minutes} 分钟到期"
