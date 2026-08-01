"""图标生成与加载。"""

import logging
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap, QTransform
from PySide6.QtWidgets import QApplication

from backend.core.constants import LOGO_FILE_NAME
from backend.core.paths import asset_path
from backend.core.platform_info import IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)

_DEFAULT_PIXEL_RATIO = 2
_EMOJI_FONTS = {"darwin": "Apple Color Emoji", "win32": "Segoe UI Emoji"}


def app_icon() -> QIcon:
    """应用图标（托盘、任务栏、窗口）。"""
    logo = asset_path(LOGO_FILE_NAME)
    if logo.is_file():
        return QIcon(str(logo))
    logger.warning("找不到应用图标：%s", logo)
    return QIcon()


def pencil_icon(size: int = 18) -> QIcon:
    """绘制「编辑」铅笔图标。

    macOS 系统字体里 ✏️ 的朝向与设计稿相反，所以渲染成位图后做一次水平镜像；
    Windows 上朝向本来就对，保持原样。用位图承载可保证跨平台方向一致。

    Args:
        size: 逻辑像素边长。
    """
    ratio = _device_pixel_ratio()
    pixmap = QPixmap(size * ratio, size * ratio)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
    font = QFont()
    if IS_MACOS:
        font.setFamily(_EMOJI_FONTS["darwin"])
    elif IS_WINDOWS:
        font.setFamily(_EMOJI_FONTS["win32"])
    # 字号要按设备像素算：位图是 size*ratio 大的，用逻辑像素画的话
    # Retina 屏上图形只会填满位图的 1/ratio，看着明显偏小
    font.setPixelSize(int(size * ratio * 0.95))
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "✏️")
    painter.end()

    pixmap.setDevicePixelRatio(ratio)
    if IS_MACOS:
        pixmap = pixmap.transformed(QTransform.fromScale(-1, 1), Qt.SmoothTransformation)
        pixmap.setDevicePixelRatio(ratio)
    return QIcon(pixmap)


def _device_pixel_ratio() -> int:
    """当前主屏的像素比，取不到时按 2 倍图处理。"""
    screen: Optional[object] = None
    app = QApplication.instance()
    if app is not None:
        screen = QApplication.primaryScreen()
    if screen is None:
        return _DEFAULT_PIXEL_RATIO
    return max(1, int(screen.devicePixelRatio()))
