"""DIY 配色弹窗。

逐项取色 → 主界面实时预览 → 起个名字存成自己的主题。
点取消会把主界面还原成打开前的配色。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

from frontend.dialogs.surface import build_surface, surface_body
from frontend.theme.palettes import DIY_COLOR_KEYS, Theme, build_diy_theme
from frontend.theme.qss import surface_dialog_qss
from frontend.theme.theme_manager import ThemeManager
from frontend.widgets.theme_card import ThemePreview

_COLUMNS = 2
_SWATCH_SIZE = (108, 30)
_LABEL_WIDTH = 48
_PREVIEW_HEIGHT = 64
# 亮度低于这个值的色块用白字，否则用黑字，保证色值文本可读
_LIGHTNESS_THRESHOLD = 140


class DiyColorDialog(QDialog):
    """自定义配色。"""

    def __init__(self, themes: ThemeManager, parent: Optional[QWidget] = None) -> None:
        """
        Args:
            themes: 主题管理器。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._themes = themes
        self._theme: Theme = themes.current
        self._colors = {key: self._theme.get(key, "#888888") for key, _ in DIY_COLOR_KEYS}
        self._swatches: dict[str, QPushButton] = {}
        self._saved = False

        self.setWindowTitle("DIY 配色")
        self.setMinimumWidth(430)
        self.setModal(True)
        self.setStyleSheet(surface_dialog_qss(self._theme))
        self._build()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        """搭出弹窗内容。"""
        surface = build_surface(self, self._theme)
        body = surface_body(surface, spacing=12)

        title = QLabel("🎛 DIY 配色")
        title.setObjectName("dialogTitle")
        body.addWidget(title)

        subtitle = QLabel("点击色块取色，主界面会实时预览；起个名字保存成你的专属主题")
        subtitle.setObjectName("dialogSubtitle")
        body.addWidget(subtitle)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        name_row.addWidget(QLabel("名称"))
        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("例如：我的配色")
        self._name_input.setFixedHeight(32)
        # 正在用某套 DIY 主题时默认沿用其名，方便覆盖更新
        if self._themes.is_custom(self._themes.current_name):
            self._name_input.setText(self._themes.current_name)
        name_row.addWidget(self._name_input, 1)
        body.addLayout(name_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        for index, (key, label) in enumerate(DIY_COLOR_KEYS):
            row, column = divmod(index, _COLUMNS)
            grid.addLayout(self._build_color_cell(key, label), row, column)
        body.addLayout(grid)

        self._preview = ThemePreview(build_diy_theme(self._colors))
        self._preview.setFixedHeight(_PREVIEW_HEIGHT)
        body.addWidget(self._preview)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        footer.addStretch()
        cancel_button = QPushButton("取消")
        cancel_button.setObjectName("ghost")
        cancel_button.setCursor(Qt.PointingHandCursor)
        cancel_button.clicked.connect(self.reject)
        footer.addWidget(cancel_button)

        save_button = QPushButton("保存主题")
        save_button.setCursor(Qt.PointingHandCursor)
        save_button.clicked.connect(self._save)
        footer.addWidget(save_button)
        body.addLayout(footer)

    def _build_color_cell(self, key: str, label: str) -> QHBoxLayout:
        """一行「名称 + 色块按钮」。"""
        row = QHBoxLayout()
        row.setSpacing(8)

        name_label = QLabel(label)
        name_label.setFixedWidth(_LABEL_WIDTH)
        row.addWidget(name_label)

        swatch = QPushButton()
        swatch.setFixedSize(*_SWATCH_SIZE)
        swatch.setCursor(Qt.PointingHandCursor)
        swatch.clicked.connect(lambda _=False, target=key: self._pick_color(target))
        self._swatches[key] = swatch
        self._style_swatch(key)
        row.addWidget(swatch)
        row.addStretch()
        return row

    # ------------------------------------------------------------------ 交互
    def _style_swatch(self, key: str) -> None:
        """把色块刷成当前颜色，并显示色值。"""
        color = self._colors[key]
        text_color = (
            "#FFFFFF" if QColor(color).lightness() < _LIGHTNESS_THRESHOLD else "#222222"
        )
        swatch = self._swatches[key]
        swatch.setText(color.upper())
        swatch.setStyleSheet(
            f"QPushButton {{ background: {color}; color: {text_color};"
            f" border: 2px solid {self._theme['border']}; border-radius: 8px;"
            f" font-size: 11px; font-weight: 600; }}"
        )

    def _pick_color(self, key: str) -> None:
        """取色并实时预览。"""
        picked = QColorDialog.getColor(QColor(self._colors[key]), self, "选择颜色")
        if not picked.isValid():
            return
        self._colors[key] = picked.name()
        self._style_swatch(key)

        theme = build_diy_theme(self._colors)
        self._preview.theme = theme
        self._preview.update()
        self._themes.preview(theme)

    def _save(self) -> None:
        """保存为自定义主题并应用。"""
        self._saved = True
        self._themes.save_custom(self._name_input.text(), build_diy_theme(self._colors))
        self.accept()

    def reject(self) -> None:
        """取消时还原主界面配色。"""
        if not self._saved:
            self._themes.preview(None)
        super().reject()
