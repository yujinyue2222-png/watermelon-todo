"""全局快捷键设置弹窗。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from backend.core.platform_info import IS_MACOS
from backend.models.app_config import HotkeySpec
from frontend.native.global_hotkey import available_keys
from frontend.theme.palettes import Theme
from frontend.theme.qss import dialog_qss
from frontend.widgets.combo_box import ThemedComboBox

# macOS 上 ctrl 位表示 Command、alt 位表示 Option，这里只改显示文案
_MODIFIER_LABELS = {
    True: ("⌘ Command", "⌥ Option", "⇧ Shift"),
    False: ("Ctrl", "Alt", "Shift"),
}


class HotkeyDialog(QDialog):
    """设置召唤/隐藏窗口的全局快捷键。"""

    def __init__(
        self,
        theme: Theme,
        hotkey: HotkeySpec,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            hotkey: 当前快捷键配置。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._hotkey = hotkey.normalized()

        self.setWindowTitle("快捷键设置")
        self.setMinimumWidth(360)
        self.setStyleSheet(dialog_qss(theme))
        self._build()

    @classmethod
    def ask(
        cls,
        parent: QWidget,
        theme: Theme,
        hotkey: HotkeySpec,
    ) -> Optional[HotkeySpec]:
        """弹窗询问新的快捷键；取消返回 None。"""
        dialog = cls(theme, hotkey, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.result_hotkey

    @property
    def result_hotkey(self) -> HotkeySpec:
        """用户选择的快捷键（已保证至少一个修饰键）。"""
        return HotkeySpec(
            ctrl=self._ctrl_box.isChecked(),
            alt=self._alt_box.isChecked(),
            shift=self._shift_box.isChecked(),
            key=self._key_picker.currentText(),
        ).normalized()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        """搭出弹窗内容。"""
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(12)

        body.addWidget(QLabel("设置「召唤/隐藏窗口」的全局快捷键：\n（至少勾选一个修饰键）"))
        if IS_MACOS:
            tip = QLabel("macOS 使用 Command / Option / Shift 组合键；保存后立即生效。")
            tip.setWordWrap(True)
            tip.setStyleSheet(f"color: {self._theme['sub']}; font-size: 12px;")
            body.addWidget(tip)

        ctrl_label, alt_label, shift_label = _MODIFIER_LABELS[IS_MACOS]
        self._ctrl_box = QCheckBox(ctrl_label)
        self._ctrl_box.setChecked(self._hotkey.ctrl)
        self._alt_box = QCheckBox(alt_label)
        self._alt_box.setChecked(self._hotkey.alt)
        self._shift_box = QCheckBox(shift_label)
        self._shift_box.setChecked(self._hotkey.shift)

        modifier_row = QHBoxLayout()
        for box in (self._ctrl_box, self._alt_box, self._shift_box):
            modifier_row.addWidget(box)
        body.addLayout(modifier_row)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("主键："))
        self._key_picker = ThemedComboBox()
        keys = available_keys()
        self._key_picker.addItems(keys)
        if self._hotkey.key in keys:
            self._key_picker.setCurrentText(self._hotkey.key)
        key_row.addWidget(self._key_picker, 1)
        body.addLayout(key_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)
