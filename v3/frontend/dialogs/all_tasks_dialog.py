"""全部待办总览。

主面板一次只能看到当前视图（日常 / 某个项目）的一部分待办，窗口又不大，
待办一多就得反复滚动、切换。这个只读弹窗把「所有待办」摊在一个大窗口里，
按「日常待办」和各个项目分组，让用户一眼扫完心里有底，不做增删改。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.core.datetime_utils import due_label
from backend.models.task import Task
from frontend.dialogs.surface import build_surface, surface_body
from frontend.theme.palettes import Theme
from frontend.theme.qss import surface_dialog_qss

# 弹窗尺寸：够大以尽量少滚动，又不至于占满整个屏幕
_DIALOG_WIDTH = 640
_DIALOG_HEIGHT = 720
# 已完成用灰色圆点，未完成用主色空心；这里只画一个小圆点示意状态
_DOT_DONE = "●"
_DOT_TODO = "○"
_DAILY_GROUP = "日常待办"


class AllTasksDialog(QDialog):
    """所有待办的只读总览。"""

    def __init__(self, theme: Theme, tasks: list[Task], parent: Optional[QWidget] = None) -> None:
        """
        Args:
            theme: 当前配色。
            tasks: 全部有效待办（调用方从后端取好传进来）。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self.setStyleSheet(surface_dialog_qss(theme) + self._extra_qss(theme))
        self.resize(_DIALOG_WIDTH, _DIALOG_HEIGHT)

        surface = build_surface(self, theme)
        body = surface_body(surface, spacing=12)
        body.addLayout(self._build_header(tasks))
        body.addWidget(self._build_scroll(tasks), 1)
        body.addLayout(self._build_footer())

    # ------------------------------------------------------------------ 顶部
    def _build_header(self, tasks: list[Task]) -> QHBoxLayout:
        """标题 + 「未完成 x / 共 y」统计。"""
        bar = QHBoxLayout()
        bar.setSpacing(8)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("📋 全部待办总览")
        title.setObjectName("dialogTitle")
        titles.addWidget(title)

        total = len(tasks)
        undone = sum(1 for t in tasks if not t.is_done)
        subtitle = QLabel(f"未完成 {undone} 条 · 共 {total} 条")
        subtitle.setObjectName("dialogSubtitle")
        titles.addWidget(subtitle)

        bar.addLayout(titles)
        bar.addStretch()
        return bar

    # ------------------------------------------------------------------ 列表
    def _build_scroll(self, tasks: list[Task]) -> QScrollArea:
        """可滚动的分组列表区。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        holder = QWidget()
        layout = QVBoxLayout(holder)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(14)

        if not tasks:
            empty = QLabel("✓\n还没有任何待办\n享受清爽的一天")
            empty.setObjectName("allEmpty")
            empty.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty)
        else:
            for group_name, group_tasks in self._grouped(tasks):
                layout.addWidget(self._build_group(group_name, group_tasks))
        layout.addStretch()

        scroll.setWidget(holder)
        return scroll

    def _grouped(self, tasks: list[Task]) -> list[tuple[str, list[Task]]]:
        """按「日常 + 各项目」分组，日常在最前，项目按名称排序。

        组内排序：未完成在前、已完成在后，各自保持传入的原始顺序
        （调用方给的就是后端排好序的列表）。
        """
        buckets: dict[str, list[Task]] = {}
        for task in tasks:
            key = task.project.strip() or _DAILY_GROUP
            buckets.setdefault(key, []).append(task)

        ordered: list[tuple[str, list[Task]]] = []
        if _DAILY_GROUP in buckets:
            ordered.append((_DAILY_GROUP, buckets.pop(_DAILY_GROUP)))
        for name in sorted(buckets.keys()):
            ordered.append((name, buckets[name]))

        result = []
        for name, group in ordered:
            group_sorted = sorted(group, key=lambda t: t.is_done)
            result.append((name, group_sorted))
        return result

    def _build_group(self, name: str, tasks: list[Task]) -> QFrame:
        """一个分组卡片：组名（含完成计数）+ 逐条待办行。"""
        frame = QFrame()
        frame.setObjectName("allGroup")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        done = sum(1 for t in tasks if t.is_done)
        header = QLabel(f"{name}   {done}/{len(tasks)}")
        header.setObjectName("allGroupTitle")
        layout.addWidget(header)

        for task in tasks:
            layout.addWidget(self._build_row(task))
        return frame

    def _build_row(self, task: Task) -> QWidget:
        """单条待办行：状态点 + 标题 + 截止标签。"""
        row = QFrame()
        row.setObjectName("allRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(6, 5, 8, 5)
        layout.setSpacing(8)

        dot = QLabel(_DOT_DONE if task.is_done else _DOT_TODO)
        dot.setObjectName("allDotDone" if task.is_done else "allDotTodo")
        layout.addWidget(dot)

        text = QLabel(task.text or "（无标题）")
        text.setObjectName("allTextDone" if task.is_done else "allText")
        text.setWordWrap(True)
        layout.addWidget(text, 1)

        label, urgent = due_label(task.due)
        if label:
            due = QLabel(label)
            due.setObjectName("allDueUrgent" if (urgent and not task.is_done) else "allDue")
            layout.addWidget(due)
        return row

    # ------------------------------------------------------------------ 底部
    def _build_footer(self) -> QHBoxLayout:
        """底部关闭按钮。"""
        bar = QHBoxLayout()
        bar.addStretch()
        close = QPushButton("关闭")
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(self.accept)
        bar.addWidget(close)
        return bar

    # ------------------------------------------------------------------ 样式
    def _extra_qss(self, theme: Theme) -> str:
        """本弹窗特有控件的样式，叠加在通用弹窗样式之上。"""
        done_color = theme.get("done") or theme["sub"]
        return f"""
            QLabel#allEmpty {{
                color: {theme['sub']}; font-size: 14px; padding: 40px 0px;
            }}
            QFrame#allGroup {{
                background: {theme['card']}; border: 1px solid {theme['border']};
                border-radius: 12px;
            }}
            QLabel#allGroupTitle {{
                color: {theme['accent']}; font-size: 13px; font-weight: 700;
                background: transparent;
            }}
            QFrame#allRow {{ background: transparent; border: none; }}
            QLabel#allDotTodo {{ color: {theme['accent']}; font-size: 13px; }}
            QLabel#allDotDone {{ color: {done_color}; font-size: 13px; }}
            QLabel#allText {{ color: {theme['text']}; font-size: 13px; }}
            QLabel#allTextDone {{
                color: {done_color}; font-size: 13px; text-decoration: line-through;
            }}
            QLabel#allDue {{ color: {theme['sub']}; font-size: 12px; }}
            QLabel#allDueUrgent {{ color: #F0405A; font-size: 12px; font-weight: 600; }}
        """

    @classmethod
    def show_tasks(cls, parent: QWidget, theme: Theme, tasks: list[Task]) -> None:
        """便捷入口：弹出总览窗口。"""
        dialog = cls(theme, tasks, parent)
        dialog.exec()