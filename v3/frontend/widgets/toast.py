"""底部浮动提示条。"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

from frontend.theme.palettes import Theme
from frontend.theme.qss import toast_qss

DEFAULT_DURATION_MS = 2200
_MIN_WIDTH = 220
_BOTTOM_MARGIN = 22


class Toast:
    """在某个窗口底部短暂显示一行提示。

    同一时刻只保留一条，新提示会顶掉旧的。
    """

    def __init__(self, host: QWidget) -> None:
        """
        Args:
            host: 承载提示条的窗口。
        """
        self._host = host
        self._label: Optional[QLabel] = None

    def show(
        self,
        message: str,
        theme: Theme,
        duration_ms: int = DEFAULT_DURATION_MS,
    ) -> None:
        """显示一条提示。

        Args:
            message: 提示文本。
            theme: 当前配色。
            duration_ms: 停留毫秒数。
        """
        self._dismiss()

        label = QLabel(message, self._host)
        label.setObjectName("toast")
        label.setAlignment(Qt.AlignCenter)
        label.setWordWrap(True)
        label.setMaximumWidth(max(_MIN_WIDTH, self._host.width() - 40))
        label.setStyleSheet(toast_qss(theme))
        label.adjustSize()
        label.move(
            max(12, (self._host.width() - label.width()) // 2),
            max(12, self._host.height() - label.height() - _BOTTOM_MARGIN),
        )
        label.show()
        label.raise_()
        self._label = label

        QTimer.singleShot(duration_ms, lambda: self._dismiss(label))

    def _dismiss(self, expected: Optional[QLabel] = None) -> None:
        """移除提示条。

        Args:
            expected: 只在当前提示条是它时才移除，避免定时器误删新提示。
        """
        if self._label is None:
            return
        if expected is not None and expected is not self._label:
            return
        self._label.deleteLater()
        self._label = None
