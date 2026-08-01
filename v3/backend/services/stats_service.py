"""统计口径。

「今日」的定义容易含糊，这里固定为：**日常待办**中截止日期在今天（含已过期）
或没填日期的任务。明天及以后的不算，项目待办也不算——日常与项目是两个独立视图。
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass
from typing import Optional

from backend.core.datetime_utils import parse_due
from backend.models.task import Task
from backend.services.task_service import TaskService


@dataclass
class TodaySummary:
    """首页「今日」统计。"""

    total: int
    done: int
    urgent: int

    @property
    def percent(self) -> int:
        """完成百分比（0-100）。"""
        return int(self.done / self.total * 100) if self.total else 0

    @property
    def remaining(self) -> int:
        """今日剩余未完成条数。"""
        return max(0, self.total - self.done)


class StatsService:
    """统计服务。"""

    def __init__(self, task_service: TaskService) -> None:
        """
        Args:
            task_service: 待办服务。
        """
        self._tasks = task_service

    def today(self, today: Optional[datetime.date] = None) -> TodaySummary:
        """今日统计。

        Args:
            today: 基准日期，便于测试注入。

        Returns:
            今日总数、已完成数与未完成的紧急数。
        """
        base = today or datetime.date.today()
        items = [task for task in self._tasks.tasks if self._counts_for_today(task, base)]
        done = sum(1 for task in items if task.is_done)
        urgent = sum(
            1 for task in items if not task.is_done and task.is_urgent_priority
        )
        return TodaySummary(total=len(items), done=done, urgent=urgent)

    @staticmethod
    def _counts_for_today(task: Task, today: datetime.date) -> bool:
        """判断一条待办是否计入今日口径。"""
        if not task.is_daily:
            return False
        due_date, _ = parse_due(task.due)
        # 没填或解析失败视为当天任务；填了则必须不晚于今天
        return due_date is None or due_date <= today
