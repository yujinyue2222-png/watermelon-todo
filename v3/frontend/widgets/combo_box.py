"""统一外观的下拉框。"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QComboBox, QStyle, QStyleOptionComboBox, QWidget


class ThemedComboBox(QComboBox):
    """自己画箭头的下拉框。

    各平台原生下拉箭头风格差异明显（macOS 是蓝色胶囊、Windows 是三角），
    样式表里把原生箭头隐藏后，这里统一画一个细线 ``∨``。
    """

    _ARROW_HALF_WIDTH = 4
    _ARROW_HALF_HEIGHT = 2
    _DISABLED_ALPHA = 90

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802 (Qt 命名)
        """先按样式表画控件，再叠一个自绘箭头。"""
        super().paintEvent(event)

        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        arrow_rect = self.style().subControlRect(
            QStyle.CC_ComboBox, option, QStyle.SC_ComboBoxArrow, self
        )
        center = arrow_rect.center()

        color = self.palette().color(self.foregroundRole())
        if not self.isEnabled():
            color.setAlpha(self._DISABLED_ALPHA)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(
            center.x() - self._ARROW_HALF_WIDTH,
            center.y() - self._ARROW_HALF_HEIGHT,
            center.x(),
            center.y() + self._ARROW_HALF_HEIGHT,
        )
        painter.drawLine(
            center.x(),
            center.y() + self._ARROW_HALF_HEIGHT,
            center.x() + self._ARROW_HALF_WIDTH,
            center.y() - self._ARROW_HALF_HEIGHT,
        )
