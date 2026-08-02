"""强提醒设置弹窗。

强提醒 = 在截止前的时间窗内反复提醒，适合「今天必须交」的事。
不需要单独的启用开关：只要设置了提醒参数或勾了浮窗，就视为已启用。
"""

from __future__ import annotations

from dataclasses import replace
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QWidget,
)

from backend.models.enums import StrongUnit
from backend.models.task import StrongRemind, Task
from frontend.dialogs.surface import build_surface, surface_body
from frontend.theme.palettes import Theme
from frontend.theme.qss import surface_dialog_qss
from frontend.widgets.combo_box import ThemedComboBox

_TASK_TITLE_LIMIT = 40
_FIELD_HEIGHT = 34
_MAX_SPIN_VALUE = 999


class StrongRemindDialog(QDialog):
    """配置某条待办的强提醒参数。"""

    def __init__(
        self,
        theme: Theme,
        task: Task,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            task: 目标待办（只读取，结果通过 :attr:`result_strong` 取回）。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._task = task
        # 在副本上编辑，用户点取消时原数据不受影响
        self._result: StrongRemind = replace(task.strong)

        self.setWindowTitle("强提醒设置")
        self.setMinimumWidth(400)
        self.setModal(True)
        self.setStyleSheet(surface_dialog_qss(theme))
        self._build()

    @property
    def result_strong(self) -> StrongRemind:
        """用户确认后的强提醒配置。"""
        return self._result

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        """搭出弹窗内容。"""
        surface = build_surface(self, self._theme)
        body = surface_body(surface)
        current = self._task.strong

        title = QLabel("🔔 强提醒设置")
        title.setObjectName("dialogTitle")
        body.addWidget(title)

        subtitle = QLabel("任务：" + self._task.text[:_TASK_TITLE_LIMIT])
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        body.addWidget(subtitle)

        self._before_value = self._make_spin(0, current.before_value)
        self._before_unit = self._make_unit_picker(current.before_unit)
        body.addLayout(
            self._make_row("在截止前", self._before_value, self._before_unit, "开始提醒")
        )

        self._interval_value = self._make_spin(1, current.interval_value)
        self._interval_unit = self._make_unit_picker(current.interval_unit)
        body.addLayout(
            self._make_row("每隔", self._interval_value, self._interval_unit, "提醒一次")
        )

        self._max_count = self._make_spin(0, current.max_count)
        body.addLayout(self._make_row("最多提醒", self._max_count, None, "次（0 = 不限）"))

        self._float_window = QCheckBox("用悬浮小西瓜浮窗提醒（在西瓜上弹出）")
        self._float_window.setChecked(current.float_window)
        body.addWidget(self._float_window)
        body.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确定")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

    def _make_spin(self, minimum: int, value: int) -> QSpinBox:
        """生成一个统一高度的数字输入框。"""
        spin = QSpinBox()
        spin.setRange(minimum, _MAX_SPIN_VALUE)
        spin.setValue(max(minimum, value))
        spin.setFixedHeight(_FIELD_HEIGHT)
        return spin

    def _make_unit_picker(self, unit: str) -> ThemedComboBox:
        """生成时间单位下拉框。"""
        picker = ThemedComboBox()
        picker.addItems(list(StrongUnit.ORDER))
        picker.setCurrentText(unit if unit in StrongUnit.ORDER else StrongUnit.HOUR)
        picker.setFixedHeight(_FIELD_HEIGHT)
        return picker

    @staticmethod
    def _make_row(
        prefix: str,
        spin: QSpinBox,
        unit: Optional[ThemedComboBox],
        suffix: str,
    ) -> QHBoxLayout:
        """「前缀 + 数字 + 单位 + 后缀」一行。"""
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel(prefix), 0, Qt.AlignVCenter)
        row.addWidget(spin, 0, Qt.AlignVCenter)
        if unit is not None:
            row.addWidget(unit, 0, Qt.AlignVCenter)
        row.addWidget(QLabel(suffix), 0, Qt.AlignVCenter)
        row.addStretch()
        return row

    # ------------------------------------------------------------------ 结果
    def accept(self) -> None:
        """把控件取值写进结果对象。"""
        self._result.before_value = self._before_value.value()
        self._result.before_unit = self._before_unit.currentText()
        self._result.interval_value = self._interval_value.value()
        self._result.interval_unit = self._interval_unit.currentText()
        self._result.max_count = self._max_count.value()
        self._result.float_window = self._float_window.isChecked()
        # 设置了任一提醒参数或勾了浮窗，就算启用
        self._result.enabled = bool(
            self._result.float_window
            or self._result.before_value > 0
            or self._result.interval_value > 0
        )
        super().accept()
