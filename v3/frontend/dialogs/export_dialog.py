"""导出选项弹窗（日期区间 + 完成状态）。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.services.export_service import DateRange, StatusFilter
from frontend.dialogs.due_picker_dialog import DuePickerDialog, Schedule
from frontend.theme.palettes import Theme
from frontend.theme.qss import dialog_qss
from frontend.widgets.combo_box import ThemedComboBox

_START_LABEL = "开始日期"
_END_LABEL = "结束日期"


@dataclass
class ExportOptions:
    """用户选择的导出条件。"""

    date_range: DateRange
    status: str = StatusFilter.ALL


class ExportOptionsDialog(QDialog):
    """选择导出范围。"""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        """
        Args:
            theme: 当前配色。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._start = ""
        self._end = ""

        self.setWindowTitle("导出待办")
        self.setMinimumWidth(340)
        self.setStyleSheet(dialog_qss(theme))
        self._build()

    @classmethod
    def ask(cls, parent: QWidget, theme: Theme) -> Optional[ExportOptions]:
        """弹窗询问导出条件；取消返回 None。"""
        dialog = cls(theme, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.options

    @property
    def options(self) -> ExportOptions:
        """当前选择的导出条件。"""
        return ExportOptions(
            date_range=DateRange(start=self._start, end=self._end),
            status=self._status_picker.currentText(),
        )

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        """搭出弹窗内容。"""
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(10)

        hint = QLabel("按日期区间与完成状态筛选后导出（无截止日期的按创建当日计算）")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self._theme['sub']}; font-weight: normal;")
        body.addWidget(hint)

        body.addWidget(QLabel("日期区间（可留空表示不限）"))
        row = QHBoxLayout()
        row.setSpacing(8)
        self._start_button = QPushButton(f"📅  {_START_LABEL}")
        self._start_button.setCursor(Qt.PointingHandCursor)
        self._start_button.clicked.connect(lambda: self._pick_date(is_start=True))
        row.addWidget(self._start_button, 1)

        self._end_button = QPushButton(f"📅  {_END_LABEL}")
        self._end_button.setCursor(Qt.PointingHandCursor)
        self._end_button.clicked.connect(lambda: self._pick_date(is_start=False))
        row.addWidget(self._end_button, 1)
        body.addLayout(row)

        body.addWidget(QLabel("完成状态"))
        self._status_picker = ThemedComboBox()
        self._status_picker.addItems(list(StatusFilter.ORDER))
        body.addWidget(self._status_picker)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("导出")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

    # ------------------------------------------------------------------ 交互
    def _pick_date(self, is_start: bool) -> None:
        """复用日期弹窗选区间端点（不需要循环与提醒）。"""
        current = self._start if is_start else self._end
        picked = DuePickerDialog.pick(
            self,
            self._theme,
            Schedule(due=current),
            show_recurrence=False,
            show_remind=False,
            title=_START_LABEL if is_start else _END_LABEL,
            subtitle="留空表示不限",
        )
        if picked is None:
            return

        day = picked.due[:10]
        label = _START_LABEL if is_start else _END_LABEL
        button = self._start_button if is_start else self._end_button
        if is_start:
            self._start = day
        else:
            self._end = day
        button.setText(f"📅  {day}" if day else f"📅  {label}")
