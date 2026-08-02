"""主题背景的绘制工具。

主窗口和主题预览卡片共用同一套画法，保证「预览所见 = 实际所得」。
"""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath

from frontend.theme.palettes import Theme


def parse_color(value: str) -> QColor:
    """解析 ``#RRGGBB`` 或 ``#RRGGBBAA``（透明度写在末尾）。

    Qt 的 ``QColor`` 只认 ``#AARRGGBB``，而主题里为了可读性把透明度放在末尾，
    所以这里手工拆分。

    Args:
        value: 颜色字符串。

    Returns:
        对应的 QColor。
    """
    text = str(value).lstrip("#")
    red, green, blue = (int(text[index : index + 2], 16) for index in (0, 2, 4))
    alpha = int(text[6:8], 16) if len(text) >= 8 else 255
    return QColor(red, green, blue, alpha)


def fill_theme_background(
    painter: QPainter,
    theme: Theme,
    path: QPainterPath,
    start: QPointF,
    end: QPointF,
) -> None:
    """按主题把一块圆角区域涂成渐变或纯色。

    Args:
        painter: 画笔。
        theme: 配色；含 ``gradient`` 时画线性渐变，否则用 ``bg`` 纯色。
        path: 已构造好的圆角路径。
        start: 渐变起点。
        end: 渐变终点。
    """
    stops = theme.get("gradient")
    if stops:
        gradient = QLinearGradient(start, end)
        for position, color in stops:
            gradient.setColorAt(position, QColor(color))
        painter.fillPath(path, QBrush(gradient))
        return
    painter.fillPath(path, QBrush(parse_color(theme["bg"])))
