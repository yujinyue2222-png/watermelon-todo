"""主题市场里的配色预览卡片。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from frontend.theme.painting import fill_theme_background
from frontend.theme.palettes import Theme

_CARD_SIZE = (186, 184)
_SHADOW_ALPHA = 70


class ThemePreview(QFrame):
    """主题预览的背景层，如实绘制该主题的渐变或底色。"""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        """
        Args:
            theme: 要预览的配色。
            parent: 父控件。
        """
        super().__init__(parent)
        self.theme = theme

    def paintEvent(self, event) -> None:  # noqa: N802
        """画圆角背景 + 细边框。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        fill_theme_background(painter, self.theme, path, rect.topLeft(), rect.bottomRight())
        painter.setPen(QPen(QColor(self.theme["border"]), 1))
        painter.drawPath(path)
        painter.end()


class ThemeCard(QFrame):
    """一张可点击的主题卡片：背景预览 + 迷你待办 + 选中角标。

    Signals:
        clicked: 点击卡片，参数为主题名。
    """

    clicked = Signal(str)

    def __init__(
        self,
        name: str,
        theme: Theme,
        selected: bool,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            name: 主题名。
            theme: 该主题的配色。
            selected: 是否为当前主题。
            parent: 父控件。
        """
        super().__init__(parent)
        self.name = name
        self.theme = theme
        self.setObjectName("themecard")
        self.setFixedSize(*_CARD_SIZE)
        self.setCursor(Qt.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow_color = QColor(theme.get("shadow") or theme["border"])
        shadow_color.setAlpha(_SHADOW_ALPHA)
        shadow.setColor(shadow_color)
        self.setGraphicsEffect(shadow)

        self._badge = QLabel("✓", self)
        self._build()
        self.set_selected(selected)

    def set_selected(self, selected: bool) -> None:
        """更新选中态（边框高亮 + 右上角对勾）。"""
        border_color = self.theme["accent"] if selected else "transparent"
        border_width = "2px" if selected else "1px"
        self.setStyleSheet(
            f"#themecard {{ background: transparent;"
            f" border: {border_width} solid {border_color}; border-radius: 14px; }}"
            f"#themecard:hover {{ border: 2px solid {self.theme['accent']}; }}"
        )
        self._badge.setVisible(selected)

    def resizeEvent(self, event) -> None:  # noqa: N802
        """把角标固定在右上角。"""
        super().resizeEvent(event)
        self._badge.move(self.width() - self._badge.width() - 7, 7)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """左键点击即选用该主题。"""
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.name)
        super().mousePressEvent(event)

    # ------------------------------------------------------------------ 内部
    def _build(self) -> None:
        """搭出预览区与名称 chip。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        preview = ThemePreview(self.theme)
        preview_layout = QVBoxLayout(preview)
        preview_layout.setContentsMargins(9, 9, 9, 9)
        preview_layout.setSpacing(6)
        preview_layout.addWidget(
            self._mock_task(48, 5, self.theme["accent"], self.theme["text"])
        )
        preview_layout.addWidget(
            self._mock_task(36, 4, self.theme["done"], self.theme["sub"])
        )
        preview_layout.addStretch()

        button_row = QHBoxLayout()
        button_row.setContentsMargins(0, 0, 0, 0)
        button_row.addStretch()
        mock_button = QFrame()
        mock_button.setFixedSize(32, 10)
        mock_button.setStyleSheet(
            f"background: {self.theme['accent']}; border-radius: 5px;"
        )
        button_row.addWidget(mock_button)
        preview_layout.addLayout(button_row)
        layout.addWidget(preview, 1)

        # 名称用该主题的面板色做底，保证深色主题下也读得清
        name_label = QLabel(self.name)
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setStyleSheet(
            f"color: {self.theme['text']}; background: {self.theme['panel']};"
            f" border: 1px solid {self.theme['border']}; border-radius: 9px;"
            f" padding: 3px 10px; font-size: 12px; font-weight: bold;"
        )
        layout.addWidget(name_label, 0, Qt.AlignHCenter)

        self._badge.setFixedSize(22, 22)
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setStyleSheet(
            f"color: #FFFFFF; background: {self.theme['accent']}; border-radius: 11px;"
            f" font-size: 12px; font-weight: bold;"
            f" border: 2px solid {self.theme['panel']};"
        )

    def _mock_task(
        self,
        bar_width: int,
        bar_height: int,
        dot_color: str,
        bar_color: str,
    ) -> QFrame:
        """一条迷你待办：圆点 + 文本条，模拟卡片浮在背景上的效果。"""
        row = QFrame()
        row.setFixedHeight(24)
        row.setStyleSheet(
            f"background: {self.theme['card']};"
            f" border: 1px solid {self.theme['border']}; border-radius: 6px;"
        )
        layout = QHBoxLayout(row)
        layout.setContentsMargins(7, 6, 7, 6)
        layout.setSpacing(6)

        dot = QFrame()
        dot.setFixedSize(9, 9)
        dot.setStyleSheet(f"background: {dot_color}; border-radius: 4px;")
        layout.addWidget(dot, 0, Qt.AlignVCenter)

        bar = QFrame()
        bar.setFixedSize(bar_width, bar_height)
        bar.setStyleSheet(f"background: {bar_color}; border-radius: 2px;")
        layout.addWidget(bar, 0, Qt.AlignVCenter)
        layout.addStretch()
        return row
