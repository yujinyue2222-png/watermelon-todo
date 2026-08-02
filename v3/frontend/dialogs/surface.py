"""无边框弹窗的公共外壳。

直接把控件画在「无边框 + 半透明」的窗口上，在 macOS 与 Windows 上都可能出现
错位或重影。稳妥的做法是：窗口本身完全透明，只承载一个不透明的圆角面板，
所有内容都放进这个面板里。
"""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QVBoxLayout,
    QWidget,
)

from frontend.theme.palettes import Theme

_SHADOW_BLUR = 34
_SHADOW_OFFSET_Y = 8
_SHADOW_ALPHA = 60


def build_surface(dialog: QDialog, theme: Theme) -> QFrame:
    """把弹窗设置成透明外壳，并返回内部的圆角面板。

    Args:
        dialog: 目标弹窗。
        theme: 当前配色，用于阴影颜色。

    Returns:
        已加入弹窗布局的面板，调用方在其上继续布局。
    """
    dialog.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
    dialog.setAttribute(Qt.WA_TranslucentBackground)

    shell = QVBoxLayout(dialog)
    shell.setContentsMargins(18, 18, 18, 18)

    surface = QFrame()
    surface.setObjectName("dialogSurface")

    shadow = QGraphicsDropShadowEffect(surface)
    shadow.setBlurRadius(_SHADOW_BLUR)
    shadow.setOffset(0, _SHADOW_OFFSET_Y)
    shadow_color = QColor(theme.get("shadow") or theme["text"])
    shadow_color.setAlpha(_SHADOW_ALPHA)
    shadow.setColor(shadow_color)
    surface.setGraphicsEffect(shadow)

    shell.addWidget(surface)
    return surface


def surface_body(surface: QFrame, spacing: int = 13) -> QVBoxLayout:
    """在面板内建立主布局。

    Args:
        surface: :func:`build_surface` 返回的面板。
        spacing: 子项间距。
    """
    body = QVBoxLayout(surface)
    body.setContentsMargins(22, 20, 22, 18)
    body.setSpacing(spacing)
    return body


def make_card(parent: Optional[QWidget] = None) -> QFrame:
    """生成一个次级卡片容器（用于日期弹窗里的时间/循环/提醒分区）。

    外观由弹窗级样式表的 ``QFrame#timeCard`` 规则统一提供。

    Args:
        parent: 父控件。
    """
    card = QFrame(parent)
    card.setObjectName("timeCard")
    return card
