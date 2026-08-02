"""列表顶部的内联新建行。

点「＋ 添加待办」后直接在列表最上方插入一行可编辑区域，输入完回车即保存，
比弹窗更轻快。日期/循环/提醒统一收进日期弹窗里，所以这一行只有两排控件。
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget

from backend.core.datetime_utils import format_due
from backend.models.enums import Priority, Recurrence, Remind
from backend.services.task_service import TaskDraft
from frontend.theme.palettes import Theme
from frontend.theme.qss import inline_editor_qss
from frontend.widgets.combo_box import ThemedComboBox

_FALLBACK_CATEGORY = "其他"
_DATE_BUTTON_MIN_WIDTH = 46
_DATE_BUTTON_MAX_WIDTH = 135


class InlineTaskEditor(QWidget):
    """内联新建待办的一行。

    Signals:
        submitted: 用户确认新建，携带一个 :class:`~backend.services.task_service.TaskDraft`。
        cancelled: 用户取消。
        due_requested: 用户点了日期按钮，请求宿主打开日期弹窗。
    """

    submitted = Signal(object)
    cancelled = Signal()
    due_requested = Signal()

    def __init__(
        self,
        theme: Theme,
        categories: Sequence[str],
        default_category: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            categories: 可选分类。
            default_category: 默认选中的分类。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setObjectName("inlinerow")

        self.due = ""
        self.recur = Recurrence.DEFAULT
        self.recur_end = ""
        self.remind = Remind.DEFAULT

        self._build(categories, default_category)
        self.setStyleSheet(inline_editor_qss(theme))

    # ------------------------------------------------------------------ 对外
    def focus_input(self) -> None:
        """把光标放到内容输入框。"""
        self._text_input.setFocus()

    def set_schedule(self, due: str, recur: str, recur_end: str, remind: str) -> None:
        """写入日期弹窗返回的排期，并刷新日期按钮文字。"""
        self.due = due
        self.recur = recur
        self.recur_end = recur_end
        self.remind = remind
        self._refresh_date_button()

    # ------------------------------------------------------------------ 内部
    def _build(self, categories: Sequence[str], default_category: str) -> None:
        """搭出两排控件。"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        first_row = QHBoxLayout()
        first_row.setSpacing(8)

        self._text_input = QLineEdit()
        self._text_input.setObjectName("inlineedit")
        self._text_input.setPlaceholderText("输入待办内容，回车保存…")
        self._text_input.returnPressed.connect(self._on_submit)
        first_row.addWidget(self._text_input, 1)

        self._date_button = QPushButton("📅")
        self._date_button.setObjectName("inlinedate")
        self._date_button.setFixedHeight(30)
        self._date_button.setFixedWidth(_DATE_BUTTON_MIN_WIDTH)
        self._date_button.setCursor(Qt.PointingHandCursor)
        self._date_button.setToolTip("设置截止时间 / 循环 / 提醒")
        self._date_button.clicked.connect(self.due_requested.emit)
        first_row.addWidget(self._date_button)

        confirm_button = QPushButton("✓")
        confirm_button.setObjectName("inlineok")
        confirm_button.setFixedSize(34, 30)
        confirm_button.setCursor(Qt.PointingHandCursor)
        confirm_button.clicked.connect(self._on_submit)
        first_row.addWidget(confirm_button)

        cancel_button = QPushButton("✕")
        cancel_button.setObjectName("inlinecancel")
        cancel_button.setFixedSize(34, 30)
        cancel_button.setCursor(Qt.PointingHandCursor)
        cancel_button.clicked.connect(self.cancelled.emit)
        first_row.addWidget(cancel_button)
        outer.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setSpacing(6)

        self._category_picker = ThemedComboBox()
        self._category_picker.setObjectName("inlinect")
        self._category_picker.addItems(list(categories))
        self._category_picker.setCurrentText(
            self._pick_default_category(categories, default_category)
        )
        self._category_picker.setFixedHeight(26)
        second_row.addWidget(self._category_picker, 1)

        self._priority_picker = ThemedComboBox()
        self._priority_picker.setObjectName("inlinepr")
        self._priority_picker.addItems(list(Priority.ORDER))
        self._priority_picker.setCurrentText(Priority.DEFAULT)
        self._priority_picker.setFixedHeight(26)
        second_row.addWidget(self._priority_picker, 1)
        outer.addLayout(second_row)

    @staticmethod
    def _pick_default_category(categories: Sequence[str], preferred: str) -> str:
        """决定默认分类：优先跟随当前筛选，其次「其他」，最后第一项。"""
        if preferred in categories:
            return preferred
        if _FALLBACK_CATEGORY in categories:
            return _FALLBACK_CATEGORY
        return categories[0] if categories else _FALLBACK_CATEGORY

    def _refresh_date_button(self) -> None:
        """按内容调整日期按钮宽度，避免日期被截断。"""
        text = f"📅 {format_due(self.due)}" if self.due else "📅"
        self._date_button.setText(text)
        content_width = self._date_button.fontMetrics().horizontalAdvance(text)
        self._date_button.setFixedWidth(
            max(_DATE_BUTTON_MIN_WIDTH, min(_DATE_BUTTON_MAX_WIDTH, content_width + 20))
        )

    def _on_submit(self) -> None:
        """校验内容并发出新建请求。"""
        text = self._text_input.text().strip()
        if not text:
            self.cancelled.emit()
            return
        self.submitted.emit(
            TaskDraft(
                text=text,
                category=self._category_picker.currentText(),
                due=self.due,
                priority=self._priority_picker.currentText(),
                recur=self.recur,
                recur_end=self.recur_end,
                remind=self.remind,
            )
        )
