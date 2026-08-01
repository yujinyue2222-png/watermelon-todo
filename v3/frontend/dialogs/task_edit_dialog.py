"""编辑待办弹窗。

内容 / 分类 / 紧急程度 / 截止（含循环与提醒）/ 备注 / 小步骤 六块。
循环与提醒折叠进日期弹窗，所以这里只有一个「截止日期」按钮。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.models.enums import Priority
from backend.models.task import SubTask, Task
from frontend.dialogs.due_picker_dialog import DuePickerDialog, Schedule
from frontend.theme.palettes import Theme
from frontend.theme.qss import dialog_qss, note_editor_qss
from frontend.widgets.combo_box import ThemedComboBox

_DONE_STYLE = "text-decoration: line-through; color: #98A2B3;"
_NOTE_HEIGHT = 70
_CHECKED_BOX = "☑"
_UNCHECKED_BOX = "☐"


@dataclass
class TaskEditResult:
    """编辑结果。"""

    text: str
    category: str
    priority: str
    schedule: Schedule
    note: str
    subtasks: list[SubTask]


class _SubtaskRow:
    """小步骤编辑行：勾选框 + 输入框 + 删除按钮。"""

    def __init__(self, text: str, done: bool) -> None:
        self.done = done
        self.check_button = QPushButton(_CHECKED_BOX if done else _UNCHECKED_BOX)
        self.check_button.setCursor(Qt.PointingHandCursor)
        self.check_button.setFixedWidth(28)
        self.text_input = QLineEdit(text)
        self.text_input.setPlaceholderText("这一步要做什么？")
        self.delete_button = QPushButton("✕")
        self.delete_button.setCursor(Qt.PointingHandCursor)
        self.delete_button.setFixedWidth(28)

        self.check_button.clicked.connect(self._toggle)
        self._sync_style()

    @property
    def widgets(self) -> tuple[QWidget, ...]:
        """本行的三个控件。"""
        return (self.check_button, self.text_input, self.delete_button)

    def to_subtask(self) -> Optional[SubTask]:
        """转成模型；内容为空返回 None。"""
        text = self.text_input.text().strip()
        return SubTask(text=text, done=self.done) if text else None

    def _toggle(self) -> None:
        """切换完成态。"""
        self.done = not self.done
        self.check_button.setText(_CHECKED_BOX if self.done else _UNCHECKED_BOX)
        self._sync_style()

    def _sync_style(self) -> None:
        """已完成的小步骤加删除线。"""
        self.text_input.setStyleSheet(_DONE_STYLE if self.done else "")


class TaskEditDialog(QDialog):
    """编辑一条已有待办。"""

    def __init__(
        self,
        theme: Theme,
        task: Task,
        categories: Sequence[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            task: 待编辑的待办（不会被直接修改）。
            categories: 可选分类。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._task = task
        self._schedule = Schedule(
            due=task.due,
            recur=task.recur,
            recur_end=task.recur_end,
            remind=task.remind,
        )
        self._subtask_rows: list[_SubtaskRow] = []

        self.setWindowTitle("编辑待办")
        self.setMinimumWidth(360)
        self.setStyleSheet(dialog_qss(theme))
        self._build(categories)

    @classmethod
    def edit(
        cls,
        parent: Optional[QWidget],
        theme: Theme,
        task: Task,
        categories: Sequence[str],
    ) -> Optional[TaskEditResult]:
        """弹出编辑窗，返回结果；取消或内容为空时返回 None。"""
        dialog = cls(theme, task, categories, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.result_value

    @property
    def result_value(self) -> Optional[TaskEditResult]:
        """收集当前界面上的编辑结果。"""
        text = self._text_input.text().strip()
        if not text:
            return None
        subtasks = []
        for row in self._subtask_rows:
            subtask = row.to_subtask()
            if subtask is not None:
                subtasks.append(subtask)
        return TaskEditResult(
            text=text,
            category=self._category_picker.currentText(),
            priority=self._priority_picker.currentText(),
            schedule=self._schedule,
            note=self._note_input.toPlainText().strip(),
            subtasks=subtasks,
        )

    # ------------------------------------------------------------------ 构建
    def _build(self, categories: Sequence[str]) -> None:
        """搭出弹窗内容。"""
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(10)

        body.addWidget(QLabel("内容"))
        self._text_input = QLineEdit(self._task.text)
        self._text_input.setPlaceholderText("这条待办要做什么？")
        body.addWidget(self._text_input)

        body.addLayout(self._build_pickers(categories))

        body.addWidget(QLabel("截止日期"))
        body.addLayout(self._build_due_row())

        body.addWidget(QLabel("备注（可选）"))
        self._note_input = QTextEdit()
        self._note_input.setPlaceholderText("记录进行中的注意事项…")
        self._note_input.setPlainText(self._task.note)
        self._note_input.setFixedHeight(_NOTE_HEIGHT)
        self._note_input.setStyleSheet(note_editor_qss(self._theme))
        body.addWidget(self._note_input)

        body.addWidget(QLabel("小步骤（可选，把这条待办拆成几步）"))
        self._subtask_container = QWidget()
        self._subtask_layout = QVBoxLayout(self._subtask_container)
        self._subtask_layout.setContentsMargins(0, 0, 0, 0)
        self._subtask_layout.setSpacing(6)
        body.addWidget(self._subtask_container)
        for subtask in self._task.subtasks:
            self._add_subtask_row(subtask.text, subtask.done)

        add_subtask_button = QPushButton("＋ 添加一步")
        add_subtask_button.setCursor(Qt.PointingHandCursor)
        add_subtask_button.clicked.connect(lambda: self._add_subtask_row())
        body.addWidget(add_subtask_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

    def _build_pickers(self, categories: Sequence[str]) -> QHBoxLayout:
        """分类 + 紧急程度。"""
        row = QHBoxLayout()
        row.setSpacing(10)

        category_column = QVBoxLayout()
        category_column.setSpacing(4)
        category_column.addWidget(QLabel("分类"))
        self._category_picker = ThemedComboBox()
        self._category_picker.addItems(list(categories))
        self._category_picker.setCurrentText(self._task.category)
        category_column.addWidget(self._category_picker)
        row.addLayout(category_column, 1)

        priority_column = QVBoxLayout()
        priority_column.setSpacing(4)
        priority_column.addWidget(QLabel("紧急程度"))
        self._priority_picker = ThemedComboBox()
        self._priority_picker.addItems(list(Priority.ORDER))
        self._priority_picker.setCurrentText(self._task.priority)
        priority_column.addWidget(self._priority_picker)
        row.addLayout(priority_column, 1)
        return row

    def _build_due_row(self) -> QHBoxLayout:
        """截止日期按钮 + 清除。"""
        row = QHBoxLayout()
        row.setSpacing(8)

        self._due_button = QPushButton()
        self._due_button.setCursor(Qt.PointingHandCursor)
        self._due_button.clicked.connect(self._pick_schedule)
        self._refresh_due_button()
        row.addWidget(self._due_button, 1)

        clear_button = QPushButton("清除")
        clear_button.setCursor(Qt.PointingHandCursor)
        clear_button.clicked.connect(self._clear_due)
        row.addWidget(clear_button)
        return row

    # ------------------------------------------------------------------ 交互
    def _pick_schedule(self) -> None:
        """打开日期弹窗。"""
        picked = DuePickerDialog.pick(self, self._theme, self._schedule)
        if picked is None:
            return
        self._schedule = picked
        self._refresh_due_button()

    def _clear_due(self) -> None:
        """只清空截止日期，循环与提醒设置保留。"""
        self._schedule.due = ""
        self._refresh_due_button()

    def _refresh_due_button(self) -> None:
        """刷新截止日期按钮文字。"""
        self._due_button.setText(
            f"📅  {self._schedule.due}" if self._schedule.due else "📅  点击选择日期"
        )

    def _add_subtask_row(self, text: str = "", done: bool = False) -> None:
        """追加一行小步骤。"""
        row = _SubtaskRow(text, done)
        layout = QHBoxLayout()
        layout.setSpacing(6)
        layout.addWidget(row.check_button)
        layout.addWidget(row.text_input, 1)
        layout.addWidget(row.delete_button)
        self._subtask_layout.addLayout(layout)
        self._subtask_rows.append(row)

        def remove() -> None:
            for widget in row.widgets:
                widget.setParent(None)
            self._subtask_layout.removeItem(layout)
            if row in self._subtask_rows:
                self._subtask_rows.remove(row)

        row.delete_button.clicked.connect(remove)
