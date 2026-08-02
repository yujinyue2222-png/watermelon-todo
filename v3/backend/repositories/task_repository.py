"""待办数据仓库。"""

import logging
from pathlib import Path
from typing import Sequence

from backend.models.task import Task
from backend.repositories.json_store import read_json, write_json

logger = logging.getLogger(__name__)


class TaskRepository:
    """把待办列表读写到一个 JSON 文件。

    数据文件格式与 v2 一致：顶层是一个任务对象数组。
    """

    def __init__(self, path: Path) -> None:
        """
        Args:
            path: 数据文件路径。
        """
        self._path = path

    @property
    def path(self) -> Path:
        """数据文件路径。"""
        return self._path

    def load(self) -> list[Task]:
        """读取全部待办。

        文件不存在或内容损坏时返回空列表，保证程序总能启动。
        """
        raw = read_json(self._path)
        if not isinstance(raw, list):
            if raw is not None:
                logger.error("%s 顶层不是数组，按空数据处理", self._path)
            return []

        tasks: list[Task] = []
        for item in raw:
            if not isinstance(item, dict):
                logger.warning("跳过非法待办记录：%r", item)
                continue
            try:
                tasks.append(Task.from_dict(item))
            except (AttributeError, TypeError, ValueError) as exc:
                # 只判断元素是不是 dict 还不够：字段值的类型也可能是坏的
                # （比如 subtasks 存成了数字）。一条坏记录不该让程序开不了
                logger.error("跳过无法解析的待办记录 %r：%s", item.get("id"), exc)
        logger.debug("已载入 %d 条待办", len(tasks))
        return tasks

    def save(self, tasks: Sequence[Task]) -> bool:
        """写回全部待办。

        Args:
            tasks: 待保存的待办列表。

        Returns:
            是否保存成功。
        """
        return write_json(self._path, [task.to_dict() for task in tasks])
