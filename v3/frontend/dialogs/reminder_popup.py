"""到期提醒弹窗。

铺满整屏的半透明遮罩 + 屏幕正中的圆角卡片，把注意力强行拉回到这条待办上。
遮罩本身可点击关闭，避免用户找不到关闭按钮。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEventLoop, QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from frontend.native.window_effects import apply_no_steal_focus, float_window_flags
from frontend.theme.palettes import URGENT_COLOR, Theme
from frontend.theme.qss import reminder_card_qss

_CARD_WIDTH = 340
_MASK_ALPHA = 90
_FALLBACK_SCREEN = QRect(0, 0, 1280, 800)


class ReminderPopup(QWidget):
    """居中的提醒卡片。

    既可以用 :meth:`exec_modal` 阻塞等待用户确认（普通提醒），
    也可以直接 ``show()`` 后由调用方定时关闭（强提醒，不打断操作）。
    """

    def __init__(
        self,
        theme: Theme,
        task_text: str,
        phrase: str,
        due: str = "",
        urgent: bool = False,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            task_text: 待办标题。
            phrase: 提醒话术，例如「还有 30 分钟到期」。
            due: 截止时间文本，为空则不显示。
            urgent: 是否为紧急提醒（换成警示红 + 时钟图标）。
            parent: 仅用于生命周期管理，弹窗自身是独立顶层窗口。
        """
        super().__init__(None)
        self._owner = parent
        self._theme = theme
        self._loop: Optional[QEventLoop] = None

        self.setWindowFlags(float_window_flags(topmost=True))
        apply_no_steal_focus(self, accept_focus=True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setGeometry(self._screen_geometry())
        self._build(task_text, phrase, due, urgent)

    def exec_modal(self) -> None:
        """模态显示，阻塞到用户关闭。"""
        self.show()
        self.raise_()
        self.activateWindow()
        self._loop = QEventLoop()
        self._loop.exec()

    def paintEvent(self, event) -> None:  # noqa: N802
        """画半透明遮罩。"""
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, _MASK_ALPHA))

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """点遮罩空白处也能关闭。"""
        self._dismiss()

    # ------------------------------------------------------------------ 内部
    def _build(self, task_text: str, phrase: str, due: str, urgent: bool) -> None:
        """搭出中央卡片。"""
        accent = URGENT_COLOR if urgent else self._theme["accent"]

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addStretch()

        row = QHBoxLayout()
        row.addStretch()

        card = QFrame()
        card.setObjectName("reminderCard")
        card.setFixedWidth(_CARD_WIDTH)
        card.setStyleSheet(reminder_card_qss(self._theme, accent))

        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(40)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 10)
        card.setGraphicsEffect(shadow)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)

        icon = QLabel("⏰" if urgent else "🔔")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 40px;")
        layout.addWidget(icon)

        heading = QLabel("待办到期提醒" if urgent else "待办提醒")
        heading.setAlignment(Qt.AlignCenter)
        heading.setStyleSheet(f"color: {accent}; font-size: 16px; font-weight: bold;")
        layout.addWidget(heading)

        title = QLabel(task_text)
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color: {self._theme['text']}; font-size: 15px; font-weight: bold;"
        )
        layout.addWidget(title)

        detail = QLabel(phrase + (f"\n截止 {due}" if due else ""))
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignCenter)
        detail.setStyleSheet(f"color: {self._theme['sub']}; font-size: 12px;")
        layout.addWidget(detail)

        confirm = QPushButton("知道啦")
        confirm.setObjectName("reminderOk")
        confirm.setFixedHeight(38)
        confirm.setCursor(Qt.PointingHandCursor)
        confirm.clicked.connect(self._dismiss)
        layout.addWidget(confirm)

        row.addWidget(card)
        row.addStretch()
        root.addLayout(row)
        root.addStretch()

    @staticmethod
    def _screen_geometry() -> QRect:
        """主屏几何；取不到时给一个保守的默认值。"""
        screen = QApplication.primaryScreen()
        return screen.geometry() if screen is not None else _FALLBACK_SCREEN

    def _dismiss(self) -> None:
        """关闭弹窗并退出模态循环。"""
        if self._loop is not None:
            self._loop.quit()
            self._loop = None
        self.close()
