"""截止时间 / 循环 / 提醒 的合并选择弹窗。

把「循环重复」和「提醒时间」折叠进日期弹窗，是为了让待办卡片和编辑窗上少几个按钮：
用户设置日期时顺手就能把排期规则一起定完。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QDate, QLocale, Qt, QTime
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from backend.core.datetime_utils import parse_due
from backend.models.enums import Recurrence, Remind
from frontend.dialogs.surface import build_surface, make_card, surface_body
from frontend.theme.palettes import Theme
from frontend.theme.qss import calendar_qss, surface_dialog_qss
from frontend.widgets.calendar_widget import ThemedCalendar
from frontend.widgets.combo_box import ThemedComboBox

_DEFAULT_TIME = QTime(18, 0)
_QT_DATE_FORMAT = "yyyy-MM-dd"


@dataclass
class Schedule:
    """一条待办的排期设置。"""

    due: str = ""
    recur: str = Recurrence.DEFAULT
    recur_end: str = ""
    remind: str = Remind.DEFAULT


class DuePickerDialog(QDialog):
    """日历 + 时间点 + 循环 + 提醒的组合弹窗。"""

    def __init__(
        self,
        theme: Theme,
        schedule: Schedule,
        show_recurrence: bool = True,
        show_remind: bool = True,
        title: str = "选择截止时间",
        subtitle: str = "为待办安排一个明确的完成节点",
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            schedule: 初始排期。
            show_recurrence: 是否显示循环设置。
            show_remind: 是否显示提醒设置。
            title: 标题。
            subtitle: 副标题。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._schedule = Schedule(
            due=schedule.due,
            recur=schedule.recur,
            recur_end=schedule.recur_end,
            remind=schedule.remind,
        )
        self._show_recurrence = show_recurrence
        self._show_remind = show_remind
        self._recurrence_picker: Optional[ThemedComboBox] = None
        self._recur_end_picker: Optional[QDateEdit] = None
        self._recur_end_toggle: Optional[QCheckBox] = None
        self._recur_end_label: Optional[QLabel] = None
        self._remind_picker: Optional[ThemedComboBox] = None

        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self.setModal(True)
        self.setStyleSheet(surface_dialog_qss(theme) + calendar_qss(theme))
        self._build(title, subtitle)

    @classmethod
    def pick(
        cls,
        parent: Optional[QWidget],
        theme: Theme,
        schedule: Optional[Schedule] = None,
        show_recurrence: bool = True,
        show_remind: bool = True,
        title: str = "选择截止时间",
        subtitle: str = "为待办安排一个明确的完成节点",
    ) -> Optional[Schedule]:
        """弹出对话框并返回用户选择。

        Args:
            parent: 父窗口。
            theme: 当前配色。
            schedule: 初始排期；为 None 时用默认值。
            show_recurrence: 是否显示循环设置。
            show_remind: 是否显示提醒设置。
            title: 标题。
            subtitle: 副标题。

        Returns:
            用户确认后的排期；点「取消」返回 None。点「清除」返回
            ``due`` 为空串的排期。
        """
        dialog = cls(
            theme=theme,
            schedule=schedule or Schedule(),
            show_recurrence=show_recurrence,
            show_remind=show_remind,
            title=title,
            subtitle=subtitle,
            parent=parent,
        )
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.schedule

    @property
    def schedule(self) -> Schedule:
        """当前排期结果。"""
        return self._schedule

    # ------------------------------------------------------------------ 构建
    def _build(self, title: str, subtitle: str) -> None:
        """搭出弹窗内容。"""
        surface = build_surface(self, self._theme)
        body = surface_body(surface, spacing=14)

        body.addLayout(self._build_header(title, subtitle))
        body.addWidget(self._build_calendar_card())
        body.addWidget(self._build_time_card())
        if self._show_recurrence:
            body.addWidget(self._build_recurrence_card())
        if self._show_remind:
            body.addWidget(self._build_remind_card())
        body.addLayout(self._build_footer())

        self._sync_selected_label()

    def _build_header(self, title: str, subtitle: str) -> QHBoxLayout:
        """标题区 + 当前选中日期的 chip。"""
        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)

        title_label = QLabel(title)
        title_label.setObjectName("dialogTitle")
        subtitle_label = QLabel(subtitle)
        subtitle_label.setObjectName("dialogSubtitle")
        titles.addWidget(title_label)
        titles.addWidget(subtitle_label)

        header.addLayout(titles)
        header.addStretch()
        self._selected_label = QLabel()
        self._selected_label.setObjectName("selectedDate")
        header.addWidget(self._selected_label, 0, Qt.AlignVCenter)
        return header

    def _build_calendar_card(self) -> QWidget:
        """日历区。"""
        card = make_card()
        card.setObjectName("calendarCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)

        self._calendar = ThemedCalendar(self._theme)
        self._calendar.setLocale(QLocale(QLocale.Chinese, QLocale.China))
        self._calendar.selectionChanged.connect(self._sync_selected_label)

        current_date, _ = parse_due(self._schedule.due)
        if current_date is not None:
            self._calendar.setSelectedDate(
                QDate(current_date.year, current_date.month, current_date.day)
            )
        layout.addWidget(self._calendar)
        return card

    def _build_time_card(self) -> QWidget:
        """具体时间点。"""
        _, current_time = parse_due(self._schedule.due)
        card = make_card()
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)

        self._time_toggle = QCheckBox("指定具体时间点")
        self._time_toggle.setChecked(current_time is not None)
        row.addWidget(self._time_toggle)
        row.addStretch()

        self._time_edit = QTimeEdit()
        self._time_edit.setObjectName("timeEdit")
        self._time_edit.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(
            QTime(current_time.hour, current_time.minute)
            if current_time is not None
            else _DEFAULT_TIME
        )
        self._time_edit.setEnabled(current_time is not None)
        self._time_toggle.toggled.connect(self._time_edit.setEnabled)
        row.addWidget(self._time_edit)
        return card

    def _build_recurrence_card(self) -> QWidget:
        """循环周期 + 循环结束日期。"""
        card = make_card()
        column = QVBoxLayout(card)
        column.setContentsMargins(12, 9, 12, 9)
        column.setSpacing(8)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(QLabel("循环重复"))
        top_row.addStretch()
        self._recurrence_picker = ThemedComboBox()
        self._recurrence_picker.setObjectName("timeEdit")
        self._recurrence_picker.addItems(list(Recurrence.ORDER))
        self._recurrence_picker.setCurrentText(
            self._schedule.recur or Recurrence.DEFAULT
        )
        self._recurrence_picker.setMinimumWidth(120)
        top_row.addWidget(self._recurrence_picker)
        column.addLayout(top_row)

        has_end = bool(self._schedule.recur_end)
        self._recur_end_toggle = QCheckBox("设置循环结束日期")
        self._recur_end_toggle.setChecked(has_end)

        self._recur_end_picker = QDateEdit()
        self._recur_end_picker.setObjectName("timeEdit")
        self._recur_end_picker.setCalendarPopup(True)
        self._recur_end_picker.setDisplayFormat(_QT_DATE_FORMAT)
        self._recur_end_picker.setMinimumWidth(140)
        end_date = QDate.fromString(self._schedule.recur_end[:10], _QT_DATE_FORMAT)
        self._recur_end_picker.setDate(
            end_date if end_date.isValid() else QDate.currentDate()
        )
        self._recur_end_picker.setEnabled(has_end)
        self._recur_end_toggle.toggled.connect(self._recur_end_picker.setEnabled)

        toggle_row = QHBoxLayout()
        toggle_row.addWidget(self._recur_end_toggle)
        toggle_row.addStretch()
        column.addLayout(toggle_row)

        end_row = QHBoxLayout()
        end_row.setSpacing(10)
        # 留个引用：这个标签也要跟着一起隐藏，否则不循环时
        # 卡片上会孤零零挂着一个「循环截止」四个字
        self._recur_end_label = QLabel("循环截止")
        end_row.addWidget(self._recur_end_label)
        end_row.addStretch()
        end_row.addWidget(self._recur_end_picker)
        column.addLayout(end_row)

        self._recurrence_picker.currentTextChanged.connect(
            lambda _=None: self._sync_recur_end_visibility()
        )
        self._sync_recur_end_visibility()
        return card

    def _build_remind_card(self) -> QWidget:
        """提醒档位。"""
        card = make_card()
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(10)
        row.addWidget(QLabel("提醒时间"))
        row.addStretch()

        self._remind_picker = ThemedComboBox()
        self._remind_picker.setObjectName("timeEdit")
        self._remind_picker.addItems(list(Remind.ORDER))
        self._remind_picker.setCurrentText(self._schedule.remind or Remind.DEFAULT)
        self._remind_picker.setMinimumWidth(120)
        row.addWidget(self._remind_picker)
        return card

    def _build_footer(self) -> QHBoxLayout:
        """清除 + 确定/取消。"""
        footer = QHBoxLayout()
        clear_button = QPushButton("清除")
        clear_button.setObjectName("dangerGhost")
        clear_button.setCursor(Qt.PointingHandCursor)
        clear_button.clicked.connect(self._on_clear)
        footer.addWidget(clear_button)
        footer.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        footer.addWidget(buttons)
        return footer

    # ------------------------------------------------------------------ 交互
    def _sync_selected_label(self) -> None:
        """更新右上角的日期 chip。"""
        self._selected_label.setText(
            self._calendar.selectedDate().toString("MM月dd日  ddd")
        )

    def _sync_recur_end_visibility(self) -> None:
        """只有选了循环周期，「循环结束日期」才有意义。"""
        if self._recurrence_picker is None:
            return
        enabled = self._recurrence_picker.currentText() != Recurrence.NONE
        if self._recur_end_toggle is not None:
            self._recur_end_toggle.setVisible(enabled)
        if self._recur_end_picker is not None:
            self._recur_end_picker.setVisible(enabled)
        if self._recur_end_label is not None:
            self._recur_end_label.setVisible(enabled)

    def _on_clear(self) -> None:
        """清除截止时间：日期留空，其余设置保持不变。"""
        self._schedule.due = ""
        super().accept()

    def accept(self) -> None:
        """收集控件取值写回排期。"""
        due = self._calendar.selectedDate().toString(_QT_DATE_FORMAT)
        if self._time_toggle.isChecked():
            due += " " + self._time_edit.time().toString("HH:mm")
        self._schedule.due = due

        if self._recurrence_picker is not None:
            self._schedule.recur = self._recurrence_picker.currentText()
            keep_end = (
                self._schedule.recur != Recurrence.NONE
                and self._recur_end_toggle is not None
                and self._recur_end_toggle.isChecked()
                and self._recur_end_picker is not None
            )
            self._schedule.recur_end = (
                self._recur_end_picker.date().toString(_QT_DATE_FORMAT)
                if keep_end
                else ""
            )

        if self._remind_picker is not None:
            self._schedule.remind = self._remind_picker.currentText()

        super().accept()
