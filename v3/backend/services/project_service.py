"""项目维度的操作。

「项目待办」与「日常待办」是两个独立视图：待办的 ``project`` 字段为空
即属于日常待办，否则归属该项目。项目本身没有独立实体，它就是待办上的一个标签，
因此重命名/删除项目 = 批量改写/删除其下的待办。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from backend.models.task import Task
from backend.services.task_service import TaskService

logger = logging.getLogger(__name__)


@dataclass
class ProjectSummary:
    """项目完成情况。"""

    name: str
    total: int
    done: int

    @property
    def percent(self) -> int:
        """完成百分比（0-100）。"""
        return int(self.done / self.total * 100) if self.total else 0


class ProjectService:
    """项目的查询、重命名与删除。"""

    def __init__(self, task_service: TaskService) -> None:
        """
        Args:
            task_service: 待办服务，项目数据由它承载。
        """
        self._tasks = task_service

    def names(self) -> list[str]:
        """全部项目名，按首次出现顺序去重。"""
        ordered: list[str] = []
        for task in self._tasks.tasks:
            if task.project and task.project not in ordered:
                ordered.append(task.project)
        return ordered

    def tasks_of(self, project: str) -> list[Task]:
        """某项目下的全部待办，未完成在前、同状态按创建时间排序。"""
        items = [task for task in self._tasks.tasks if task.project == project]
        return sorted(items, key=lambda task: (task.is_done, task.created))

    def summary(self, project: str) -> ProjectSummary:
        """某项目的完成情况。"""
        items = [task for task in self._tasks.tasks if task.project == project]
        done = sum(1 for task in items if task.is_done)
        return ProjectSummary(name=project, total=len(items), done=done)

    def rename(self, old_name: str, new_name: str) -> int:
        """重命名项目，返回受影响的待办条数。

        Args:
            old_name: 原项目名。
            new_name: 新项目名。

        Returns:
            被改写的待办条数；参数非法时返回 0。
        """
        old = (old_name or "").strip()
        new = (new_name or "").strip()
        if not old or not new or old == new:
            return 0
        changed = 0
        for task in self._tasks.tasks:
            if task.project == old:
                task.project = new
                task.touch()
                changed += 1
        if changed:
            self._tasks.save()
            logger.info("项目重命名：%s → %s（%d 条待办）", old, new, changed)
        return changed

    def delete(self, project: str) -> int:
        """删除整个项目及其下所有待办，返回删除条数。"""
        name = (project or "").strip()
        if not name:
            return 0
        target_ids = [task.id for task in self._tasks.tasks if task.project == name]
        removed = self._tasks.delete_many(target_ids)
        if removed:
            logger.info("删除项目「%s」，连带 %d 条待办", name, removed)
        return removed
