"""悬浮小西瓜的表情位图。

做法是「改 SVG 文本再渲染」：读 ``watermelon_ball.svg``，把「左眼」和「嘴巴」
两段替换成不同形状，再用 QSvgRenderer 渲染成位图。右眼始终保持原来的眨眼造型
（这是角色特征）。任一步失败就返回空字典，绘制时自动回退成 🍉 emoji。
"""

from __future__ import annotations

import logging
import re

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from backend.core.constants import BALL_FILE_NAME, LOGO_FILE_NAME
from backend.core.paths import asset_path

logger = logging.getLogger(__name__)

# 表情名
NORMAL = "normal"
BLINK = "blink"
CHEERFUL = "cheerful"
SURPRISED = "surprised"
SLEEPY = "sleepy"
LOVE = "love"
DIZZY = "dizzy"
CHEER = "cheer"

# SVG 里两段可替换区域的定位（viewBox 为 1024）
_LEFT_EYE_PATTERN = re.compile(r"<!-- Open eye -->.*?(?=<!-- Winking eye -->)", re.S)
_MOUTH_PATTERN = re.compile(r"<!-- Happy mouth -->.*?(?=</svg>)", re.S)

# ---- 左眼各形态 ----
_EYE_CLOSED = (
    '<path d="M339 506 Q392 461 445 506" fill="none" '
    'stroke="#211A1C" stroke-width="19" stroke-linecap="round"/>'
)
_EYE_HAPPY = (
    '<path d="M335 520 Q392 466 449 520" fill="none" '
    'stroke="#211A1C" stroke-width="19" stroke-linecap="round"/>'
)
_EYE_SURPRISED = (
    '<ellipse cx="384" cy="494" rx="82" ry="82" fill="#FFFFFF" '
    'stroke="#F6E7E4" stroke-width="10"/>\n'
    '  <ellipse cx="384" cy="500" rx="50" ry="56" fill="#261D20"/>\n'
    '  <ellipse cx="366" cy="478" rx="18" ry="22" fill="#FFFFFF"/>'
)
_EYE_SLEEPY = (
    '<path d="M312 495 Q384 475 456 495 L456 512 Q384 532 312 512 Z" '
    'fill="#FFFFFF" stroke="#211A1C" stroke-width="8" stroke-linejoin="round"/>\n'
    '  <ellipse cx="392" cy="506" rx="40" ry="16" fill="#261D20"/>'
)
_EYE_LOVE = (
    '<path d="M384 548 C360 520 330 500 330 472 C330 452 348 440 364 440 '
    "C374 440 380 446 384 454 C388 446 394 440 404 440 C420 440 438 452 "
    '438 472 C438 500 408 520 384 548 Z" fill="#FF5C7A" '
    'stroke="#D63554" stroke-width="5"/>'
)
_EYE_DIZZY = (
    '<path d="M348 470 L420 540 M420 470 L348 540" fill="none" '
    'stroke="#211A1C" stroke-width="16" stroke-linecap="round"/>'
)
_EYE_STAR = (
    '<path d="M384 448 C392 488 392 488 434 498 C392 508 392 508 384 548 '
    'C376 508 376 508 334 498 C376 488 376 488 384 448 Z" '
    'fill="#FFD23F" stroke="#E8A900" stroke-width="4"/>'
)

# ---- 嘴巴各形态 ----
_MOUTH_SMILE = (
    '<path d="M438 605 Q512 655 586 605" fill="none" '
    'stroke="#7B1831" stroke-width="16" stroke-linecap="round"/>'
)
_MOUTH_OPEN = (
    '<ellipse cx="512" cy="628" rx="32" ry="42" fill="url(#mouth)" '
    'stroke="#7B1831" stroke-width="8"/>'
)


def build_faces(size_px: int, pixel_ratio: float) -> dict[str, QPixmap]:
    """预渲染全部表情位图。

    Args:
        size_px: 逻辑边长（西瓜本体直径）。
        pixel_ratio: 屏幕像素比，用于高清渲染。

    Returns:
        ``{表情名: 位图}``；资源缺失或 SVG 非法时返回空字典。
    """
    source = asset_path(BALL_FILE_NAME)
    if not source.is_file():
        source = asset_path(LOGO_FILE_NAME)
    if not source.is_file():
        logger.warning("找不到小西瓜素材，将回退成 emoji")
        return {}

    try:
        svg_text = source.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("读取 %s 失败：%s", source, exc)
        return {}

    render_size = max(1, int(size_px * pixel_ratio))

    def render(text: str) -> QPixmap:
        """把一段 SVG 文本渲染成位图。"""
        renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
        if not renderer.isValid():
            return QPixmap()
        pixmap = QPixmap(render_size, render_size)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(pixel_ratio)
        return pixmap

    def variant(left_eye: str, mouth: str = "") -> QPixmap:
        """替换左眼（可选替换嘴巴）后渲染。"""
        text = _LEFT_EYE_PATTERN.sub(
            f"<!-- Open eye -->\n  {left_eye}\n", svg_text, count=1
        )
        if mouth:
            text = _MOUTH_PATTERN.sub(f"<!-- Happy mouth -->\n  {mouth}\n", text, count=1)
        return render(text)

    faces = {
        NORMAL: render(svg_text),  # 原图即常态：左眼睁开 + 右眼笑 + 开心嘴
        BLINK: variant(_EYE_CLOSED),
        CHEERFUL: variant(_EYE_HAPPY),
        SURPRISED: variant(_EYE_SURPRISED, _MOUTH_OPEN),
        SLEEPY: variant(_EYE_SLEEPY, _MOUTH_SMILE),
        LOVE: variant(_EYE_LOVE),
        DIZZY: variant(_EYE_DIZZY, _MOUTH_OPEN),
        CHEER: variant(_EYE_STAR),
    }
    return {name: pixmap for name, pixmap in faces.items() if not pixmap.isNull()}
