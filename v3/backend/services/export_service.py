"""导出待办为 CSV / TXT。

CSV 用 ``utf-8-sig`` 编码，这样 Excel 双击打开不会乱码。
"""

from __future__ import annotations

import csv
import datetime
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from backend.models.task import Task

logger = logging.getLogger(__name__)

CSV_SUFFIX = ".csv"
CSV_ENCODING = "utf-8-sig"
TXT_ENCODING = "utf-8"

_CSV_COLUMNS = ("状态", "待办内容", "分类", "优先级", "截止", "备注")
_PROJECT_COLUMN = "项目"


class ExportError(Exception):
    """导出失败（磁盘不可写、路径非法等）。"""


class StatusFilter:
    """导出时的完成状态筛选。"""

    ALL = "全部"
    UNDONE = "仅未完成"
    DONE = "仅已完成"

    ORDER = (ALL, UNDONE, DONE)


@dataclass
class DateRange:
    """导出的日期区间，两端都可留空表示不限。"""

    start: str = ""
    end: str = ""

    @property
    def label(self) -> str:
        """用于写在导出文件头部的可读描述。"""
        return f"{self.start or '不限'} ~ {self.end or '不限'}"


class ExportService:
    """把待办写成文件。"""

    def export(
        self,
        path: Path,
        tasks: Sequence[Task],
        header_lines: Optional[Sequence[str]] = None,
        with_project_column: bool = False,
    ) -> int:
        """导出待办。

        Args:
            path: 目标文件；后缀为 ``.csv`` 时导出 CSV，否则导出纯文本。
            tasks: 要导出的待办。
            header_lines: 仅 TXT 生效的头部说明行。
            with_project_column: CSV 是否额外输出「项目」列。

        Returns:
            导出的条数。

        Raises:
            ExportError: 文件无法写入时抛出。
        """
        try:
            if path.suffix.lower() == CSV_SUFFIX:
                self._write_csv(path, tasks, with_project_column)
            else:
                self._write_text(path, tasks, header_lines or ())
        except (OSError, UnicodeError) as exc:
            # UnicodeError 不是 OSError 的子类：待办文本里混进一个游离代理字符
            # （JSON 里的 \udXXX 转义）就会在编码时抛出来，漏掉的话导出对话框会直接崩
            logger.error("导出到 %s 失败：%s", path, exc)
            raise ExportError(str(exc)) from exc
        logger.info("已导出 %d 条待办到 %s", len(tasks), path)
        return len(tasks)

    @staticmethod
    def task_date(task: Task) -> str:
        """取用于日期区间过滤的日期（``YYYY-MM-DD``）。

        优先用截止日期；没填则回退到创建当日。
        """
        if task.due.strip():
            return task.due.strip()[:10]
        return task.created.strip()[:10]

    @classmethod
    def filter_tasks(
        cls,
        tasks: Iterable[Task],
        date_range: Optional[DateRange] = None,
        status: str = StatusFilter.ALL,
    ) -> list[Task]:
        """按完成状态与日期区间过滤，并按「未完成在前」排序。

        Args:
            tasks: 候选待办。
            date_range: 日期区间；为 None 表示不限。
            status: 见 :class:`StatusFilter`。

        Returns:
            过滤并排序后的待办。
        """
        span = date_range or DateRange()
        picked = []
        for task in tasks:
            if status == StatusFilter.UNDONE and task.is_done:
                continue
            if status == StatusFilter.DONE and not task.is_done:
                continue
            day = cls.task_date(task)
            if span.start and (not day or day < span.start):
                continue
            if span.end and (not day or day > span.end):
                continue
            picked.append(task)
        return sorted(picked, key=lambda task: (task.is_done, cls.task_date(task)))

    @staticmethod
    def default_file_name(prefix: str) -> str:
        """生成带日期的默认文件名。"""
        stamp = datetime.date.today().strftime("%Y%m%d")
        return f"{prefix}_{stamp}{CSV_SUFFIX}"

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _write_csv(path: Path, tasks: Sequence[Task], with_project_column: bool) -> None:
        """写 CSV。"""
        columns = list(_CSV_COLUMNS)
        if with_project_column:
            columns.insert(0, _PROJECT_COLUMN)
        # errors="replace"：单个无法编码的字符只该变成一个占位符，
        # 不该让整份导出失败
        with path.open("w", encoding=CSV_ENCODING, newline="", errors="replace") as handle:
            writer = csv.writer(handle)
            writer.writerow(columns)
            for task in tasks:
                row = [
                    "已完成" if task.is_done else "未完成",
                    task.text,
                    task.category,
                    task.priority,
                    task.due,
                    task.note.replace("\n", " "),
                ]
                if with_project_column:
                    row.insert(0, task.project)
                writer.writerow(row)

    @staticmethod
    def _write_text(path: Path, tasks: Sequence[Task], header_lines: Sequence[str]) -> None:
        """写纯文本清单。"""
        with path.open("w", encoding=TXT_ENCODING, errors="replace") as handle:
            for line in header_lines:
                handle.write(line + "\n")
            if header_lines:
                handle.write("=" * 30 + "\n")
            for task in tasks:
                mark = "[✓]" if task.is_done else "[ ]"
                line = f"{mark} {task.text}"
                if task.due:
                    line += f"  (截止 {task.due})"
                handle.write(line + "\n")
                if task.note:
                    handle.write(f"    备注：{task.note}\n")
