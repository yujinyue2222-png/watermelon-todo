"""剪贴板图片读取：把系统剪贴板里的图像转成 PNG 字节。

桌面端常用交互：截图后直接 Cmd/Ctrl+V 粘进待办，不必先存文件再选图。
"""

from __future__ import annotations

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QGuiApplication


def clipboard_png_bytes() -> bytes:
    """剪贴板里有图像时返回 PNG 字节，否则返回空串。

    返回的字节可直接交给 ``store_image_bytes`` 入库。
    """
    mime = QGuiApplication.clipboard().mimeData()
    if mime is None or not mime.hasImage():
        return b""
    image = mime.imageData()
    if image is None:
        return b""
    # imageData 可能是 QImage 或 QPixmap，两者都支持 save(QIODevice, format)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, "PNG"):
        return b""
    return bytes(buffer.data())
