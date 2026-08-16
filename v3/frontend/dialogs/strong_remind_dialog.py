"""强提醒设置弹窗。

强提醒 = 在截止前的时间窗内反复提醒，适合「今天必须交」的事。

交互要点：
- 顶部有「启用 / 关闭」独立开关，解决用户找不到如何取消强提醒的痛点；
  选「关闭强提醒」时下方表单全部置灰，点确定直接清除该任务全部强提醒配置。
- 任务已过期时顶部显示灰色提示条：强提醒配置不会生效。
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.core.datetime_utils import due_datetime
from backend.models.enums import StrongUnit
from backend.models.task import StrongRemind, Task
from frontend.dialogs.surface import build_surface, surface_body
from frontend.theme.palettes import Theme
from frontend.theme.qss import surface_dialog_qss
from frontend.widgets.combo_box import ThemedComboBox

_TASK_TITLE_LIMIT = 40
_FIELD_HEIGHT = 34
_MAX_SPIN_VALUE = 999
# 过期判定宽容度：超过截止 1 分钟才算「已过期」，与提醒服务保持一致
_OVERDUE_TOLERANCE_SECONDS = 60

_DEFAULT_STRONG = StrongRemind()


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

        # 开关状态：以现有配置是否启用为准
        self._enabled = bool(task.strong.enabled)

        self.setWindowTitle("强提醒设置")
        self.setMinimumWidth(440)
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
        body = surface_body(surface, spacing=14)
        current = self._task.strong

        # 标题行：标题文字 + 角落西瓜图标
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        title = QLabel("强提醒设置")
        title.setObjectName("dialogTitle")
        title_row.addWidget(title)
        title_row.addStretch()
        watermelon = QLabel("🍉")
        watermelon.setObjectName("dialogWatermelon")
        title_row.addWidget(watermelon)
        body.addLayout(title_row)

        subtitle = QLabel("任务：" + self._task.text[:_TASK_TITLE_LIMIT])
        subtitle.setObjectName("dialogSubtitle")
        subtitle.setWordWrap(True)
        body.addWidget(subtitle)

        # 过期提示条：任务已截止则不生效
        if self._is_overdue():
            banner = QLabel("该任务已截止，强提醒配置不会生效")
            banner.setObjectName("expiredBanner")
            body.addWidget(banner)

        # 启用 / 关闭 独立开关
        self._build_switch(body)

        # 表单区（可被置灰）
        self._form = QWidget()
        self._form_grid = QGridLayout(self._form)
        self._form_grid.setContentsMargins(0, 0, 0, 0)
        self._form_grid.setHorizontalSpacing(6)
        self._form_grid.setVerticalSpacing(10)
        self._form_grid.setColumnStretch(4, 1)

        self._before_value = self._make_spin(0, current.before_value)
        self._before_value.setToolTip("提前多少开始提醒（不能小于 0）")
        self._before_unit = self._make_unit_picker(current.before_unit)
        self._add_form_row(0, "在截止前", self._before_value, self._before_unit, "开始提醒")

        self._interval_value = self._make_spin(1, current.interval_value)
        self._interval_value.setToolTip("两次提醒的最小间隔（不能小于 1）")
        self._interval_unit = self._make_unit_picker(current.interval_unit)
        self._add_form_row(1, "每隔", self._interval_value, self._interval_unit, "提醒一次")

        self._max_count = self._make_spin(0, current.max_count)
        self._max_count.setToolTip("0 代表无上限")
        self._add_form_row(2, "最多提醒", self._max_count, None, "次")

        # 对齐缩进的小字提示（与输入框左边缘对齐）
        hint = QLabel("0 代表无上限")
        hint.setObjectName("fieldHint")
        self._form_grid.addWidget(hint, 3, 1, 1, 3, Qt.AlignLeft | Qt.AlignVCenter)

        tip = QLabel("💡强提醒：循环重复告警，区别普通一次性提醒")
        tip.setObjectName("fieldHint")
        self._form_grid.addWidget(tip, 4, 1, 1, 3, Qt.AlignLeft | Qt.AlignVCenter)

        # 悬浮小西瓜浮窗提醒：单独占一整行，与上方表单拉开间距
        self._form_grid.setRowMinimumHeight(5, 18)
        self._float_window = QCheckBox("开启悬浮小西瓜浮窗提醒（桌面全局弹出提醒卡片）")
        self._float_window.setChecked(current.float_window)
        self._form_grid.addWidget(self._float_window, 6, 0, 1, 5, Qt.AlignLeft | Qt.AlignVCenter)

        body.addWidget(self._form)

        # 底部按钮：重置 / 取消 / 确定
        buttons = QDialogButtonBox()
        self._btn_reset = buttons.addButton("重置", QDialogButtonBox.ResetRole)
        self._btn_cancel = buttons.addButton("取消", QDialogButtonBox.RejectRole)
        self._btn_ok = buttons.addButton("确定", QDialogButtonBox.AcceptRole)
        self._btn_reset.setObjectName("ghost")
        self._btn_cancel.setObjectName("ghost")
        self._btn_ok.setText("确定")
        self._btn_reset.clicked.connect(self._on_reset)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

        self._apply_enabled_state()

    def _build_switch(self, body: QVBoxLayout) -> None:
        """顶部「启用 / 关闭」独立开关。"""
        switch_frame = QFrame()
        switch_frame.setObjectName("switchFrame")
        layout = QHBoxLayout(switch_frame)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self._btn_enable = QPushButton("启用强提醒")
        self._btn_enable.setObjectName("switchOn")
        self._btn_enable.setCheckable(True)
        self._btn_disable = QPushButton("关闭强提醒")
        self._btn_disable.setObjectName("switchOff")
        self._btn_disable.setCheckable(True)

        self._btn_enable.clicked.connect(lambda: self._set_enabled(True))
        self._btn_disable.clicked.connect(lambda: self._set_enabled(False))

        layout.addWidget(self._btn_enable)
        layout.addWidget(self._btn_disable)
        layout.addStretch()
        body.addWidget(switch_frame)

    # ------------------------------------------------------------------ 开关
    def _set_enabled(self, enabled: bool) -> None:
        """切换开关并同步表单可用状态。"""
        self._enabled = enabled
        self._apply_enabled_state()

    def _apply_enabled_state(self) -> None:
        """依据开关状态刷新按钮高亮与表单置灰。"""
        self._btn_enable.setChecked(self._enabled)
        self._btn_disable.setChecked(not self._enabled)
        self._form.setEnabled(self._enabled)

    def _is_overdue(self) -> bool:
        """任务截止时间已过（含宽容阈值）则视为过期。"""
        due_at = self._task.due_at
        if due_at is None:
            return False
        return datetime.now() > due_at + datetime.timedelta(
            seconds=_OVERDUE_TOLERANCE_SECONDS
        )

    # ------------------------------------------------------------------ 表单
    def _make_spin(self, minimum: int, value: int) -> QSpinBox:
        """生成一个统一高度的纯数字输入框（无上下箭头），并带占位符提示。"""
        spin = QSpinBox()
        spin.setRange(minimum, _MAX_SPIN_VALUE)
        spin.setValue(max(minimum, value))
        spin.setFixedHeight(_FIELD_HEIGHT)
        spin.setButtonSymbols(QSpinBox.NoButtons)
        spin.setSpecialValueText("0")
        spin.setSuffix("")
        spin.setAlignment(Qt.AlignCenter)
        return spin

    def _make_unit_picker(self, unit: str) -> ThemedComboBox:
        """生成时间单位下拉框。"""
        picker = ThemedComboBox()
        picker.addItems(list(StrongUnit.ORDER))
        picker.setCurrentText(unit if unit in StrongUnit.ORDER else StrongUnit.HOUR)
        picker.setFixedHeight(_FIELD_HEIGHT)
        return picker

    def _add_form_row(
        self,
        row: int,
        prefix: str,
        spin: QSpinBox,
        unit: Optional[ThemedComboBox],
        suffix: str,
    ) -> None:
        """向网格表单添加一行：前缀 | 数字 | 单位 | 后缀，剩余空间由第 4 列吸收。"""
        prefix_lbl = QLabel(prefix)
        prefix_lbl.setMinimumWidth(74)
        prefix_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._form_grid.addWidget(prefix_lbl, row, 0, Qt.AlignRight | Qt.AlignVCenter)

        spin.setFixedWidth(54)
        self._form_grid.addWidget(spin, row, 1, Qt.AlignLeft | Qt.AlignVCenter)

        if unit is not None:
            unit.setFixedWidth(82)
            self._form_grid.addWidget(unit, row, 2, Qt.AlignLeft | Qt.AlignVCenter)

        suffix_lbl = QLabel(suffix)
        self._form_grid.addWidget(suffix_lbl, row, 3, Qt.AlignLeft | Qt.AlignVCenter)

    # ------------------------------------------------------------------ 结果
    def _on_reset(self) -> None:
        """一键恢复默认参数（保留当前开关状态）。"""
        self._before_value.setValue(_DEFAULT_STRONG.before_value)
        self._before_unit.setCurrentText(_DEFAULT_STRONG.before_unit)
        self._interval_value.setValue(_DEFAULT_STRONG.interval_value)
        self._interval_unit.setCurrentText(_DEFAULT_STRONG.interval_unit)
        self._max_count.setValue(_DEFAULT_STRONG.max_count)
        self._float_window.setChecked(_DEFAULT_STRONG.float_window)

    def accept(self) -> None:
        """把控件取值写进结果对象。"""
        if self._enabled:
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
        else:
            # 关闭强提醒：清空全部配置
            self._result = StrongRemind(enabled=False)
        super().accept()
