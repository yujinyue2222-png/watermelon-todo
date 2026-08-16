"""图片预览、长文本预览与完整待办查看弹窗。

- 任务卡片上的图片默认折叠成小缩略图（仅供展示）；
- 「查看全部」弹出一个长条型完整待办窗口：完整文字 + 全部图片，
  至少完整展示第一张，图片多了可以在窗口内下滑查看；点某张图
  再弹独立预览窗口，可在该待办的多张照片间左右切换。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtGui import QKeyEvent, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.core.paths import image_path
from backend.models.task import Task
from frontend.theme.palettes import Theme
from frontend.theme.qss import dialog_qss, note_editor_qss


def open_image_viewer(
    parent,
    theme: Theme,
    images: list[str],
    index: int = 0,
    title: str = "图片预览",
) -> None:
    """打开大图预览弹窗（点击缩略图时的统一入口）。

    Args:
        parent: 父窗口。
        theme: 当前配色。
        images: 图片文件名列表（相对应用数据目录）。
        index: 初始展示第几张。
        title: 弹窗标题。
    """
    paths = [str(image_path(name)) for name in images if name]
    if not paths:
        return
    dialog = ImagePreviewDialog(theme, paths, index, title, parent)
    dialog.exec()


def _fit_pixmap(
    pix: QPixmap,
    max_w: int,
    max_h: int,
    dpr: float,
    max_upscale: float = 1.0,
) -> QPixmap:
    """把图片适配到可用区域，兼顾清晰度与完整度。

    宽高双约束：横图按宽度、竖图按高度、方图取整，保证图片在区域内
    完整可见；输出按设备像素比（Retina 为 2.0）生成物理像素，高分屏
    不糊。默认只缩小、绝不放大；传 ``max_upscale > 1`` 时允许在受限
    倍数内适度放大填满空间，避免小图显得过小，但不无限放大。
    """
    dpr = max(1.0, float(dpr))
    scale = min(max_w / pix.width(), max_h / pix.height())
    scale = min(scale, max(1.0, float(max_upscale)))
    target_w = max(1, int(pix.width() * scale * dpr))
    target_h = max(1, int(pix.height() * scale * dpr))
    display = pix.scaled(
        target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
    )
    display.setDevicePixelRatio(dpr)
    return display


class ImagePreviewDialog(QDialog):
    """大图预览：展示完整图片，支持在该待办的多张照片间左右切换。

    窗口大小变化时从原图重新采样（只缩小不放大），保证高清屏清晰；
    用 ◀ ▶ 按钮或键盘左右方向键切换照片；双击图片关闭。
    """

    def __init__(
        self,
        theme: Theme,
        paths: list[str],
        index: int = 0,
        title: str = "图片预览",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._paths = [p for p in paths if p]
        self._index = max(0, min(index, len(self._paths) - 1))
        self.setWindowTitle(title)
        self.setMinimumSize(320, 320)
        self.setStyleSheet(dialog_qss(theme))

        body = QVBoxLayout(self)
        body.setContentsMargins(12, 12, 12, 12)
        body.setSpacing(8)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setStyleSheet("background: transparent; border: none;")
        # 关键：滚动区自身的样式不会透传给 viewport，viewport 默认用系统
        # 调色板背景（深色模式下是黑/深灰），圆角照片的透明角会露出黑底，
        # 必须让它不填充背景，透出弹窗的面板底色
        self._scroll.viewport().setAutoFillBackground(False)

        self._label = QLabel()
        self._label.setAlignment(Qt.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._label.setAutoFillBackground(False)
        self._label.installEventFilter(self)
        self._scroll.setWidget(self._label)
        body.addWidget(self._scroll, 1)

        # 多图时显示切换栏：◀ 上一张 / 计数 / 下一张 ▶
        self._nav = QHBoxLayout()
        self._nav.setSpacing(12)
        self._prev_button = QPushButton("◀ 上一张")
        self._prev_button.setCursor(Qt.PointingHandCursor)
        self._prev_button.clicked.connect(self._show_prev)
        self._count_label = QLabel()
        self._count_label.setAlignment(Qt.AlignCenter)
        self._count_label.setStyleSheet(f"color: {theme['sub']}; font-size: 12px;")
        self._next_button = QPushButton("下一张 ▶")
        self._next_button.setCursor(Qt.PointingHandCursor)
        self._next_button.clicked.connect(self._show_next)
        self._nav.addStretch(1)
        self._nav.addWidget(self._prev_button)
        self._nav.addWidget(self._count_label)
        self._nav.addWidget(self._next_button)
        self._nav.addStretch(1)
        body.addLayout(self._nav)

        hint = QLabel("双击图片可关闭")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {theme['sub']}; font-size: 12px;")
        body.addWidget(hint)

        if not self._paths:
            self._label.setText("图片加载失败或文件已不存在")
            self._label.setStyleSheet(f"color: {theme['sub']}; font-size: 13px;")
            self._label.removeEventFilter(self)
            self._prev_button.setVisible(False)
            self._next_button.setVisible(False)
            self._count_label.setText("0/0")
        else:
            self._load_current()
            # 初始尺寸按屏幕 80% 且不小于第一张图自然大小
            screen = QApplication.primaryScreen()
            area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1200, 900)
            pix = self._pix
            init_w = min(pix.width() + 48, int(area.width() * 0.8))
            init_h = min(pix.height() + 120, int(area.height() * 0.8))
            self.resize(max(480, init_w), max(360, init_h))

    # ------------------------------------------------------------------ 图片
    def _load_current(self) -> None:
        """加载当前下标的图片并刷新显示。"""
        pix = QPixmap(self._paths[self._index])
        self._pix = pix
        if pix.isNull():
            self._label.setText("图片加载失败或文件已不存在")
            self._label.setStyleSheet(f"color: {self._theme['sub']}; font-size: 13px;")
            self._label.setPixmap(QPixmap())
            self._label.setCursor(Qt.ArrowCursor)
        else:
            self._label.setCursor(Qt.PointingHandCursor)
            self._refresh_preview()
        self._count_label.setText(f"{self._index + 1}/{len(self._paths)}")
        self._prev_button.setEnabled(self._index > 0)
        self._next_button.setEnabled(self._index < len(self._paths) - 1)

    def _refresh_preview(self) -> None:
        """按当前滚动区域大小重新采样原图，占满可用空间且保持清晰。"""
        pix = getattr(self, "_pix", None)
        if pix is None or pix.isNull():
            return
        viewport = self._scroll.viewport()
        margin = 8
        avail_w = max(40, viewport.width() - margin * 2)
        avail_h = max(40, viewport.height() - margin * 2)
        display = _fit_pixmap(
            pix, avail_w, avail_h, self.devicePixelRatioF(), max_upscale=1.6
        )
        self._label.setPixmap(display)

    def _show_prev(self) -> None:
        """上一张。"""
        if self._index > 0:
            self._index -= 1
            self._load_current()

    def _show_next(self) -> None:
        """下一张。"""
        if self._index < len(self._paths) - 1:
            self._index += 1
            self._load_current()

    # ------------------------------------------------------------------ 事件
    def resizeEvent(self, event) -> None:  # noqa: N802
        """窗口尺寸变化时重采样，避免放大模糊。"""
        super().resizeEvent(event)
        self._refresh_preview()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """左右方向键切换照片，Esc 关闭。"""
        if event.key() == Qt.Key_Left:
            self._show_prev()
            return
        if event.key() == Qt.Key_Right:
            self._show_next()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: QWidget, event: QEvent) -> bool:  # noqa: N802
        """双击图片关闭预览。"""
        if watched is self._label and event.type() == QEvent.MouseButtonDblClick:
            self.accept()
            return True
        return super().eventFilter(watched, event)

    @classmethod
    def show_images(
        cls,
        parent: Optional[QWidget],
        theme: Theme,
        paths: list[str],
        index: int = 0,
        title: str = "图片预览",
    ) -> None:
        """弹窗查看大图（多张可左右切换）。"""
        cls(theme, paths, index, title, parent).exec()

    @classmethod
    def show_image(
        cls,
        parent: Optional[QWidget],
        theme: Theme,
        path: str,
        title: str = "图片预览",
    ) -> None:
        """弹窗查看单张图片（兼容旧调用）。"""
        cls(theme, [path], 0, title, parent).exec()


class TextPreviewDialog(QDialog):
    """长文本预览：备注太长时展示全文。"""

    def __init__(
        self,
        theme: Theme,
        title: str,
        text: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(440, 340)
        self.setStyleSheet(dialog_qss(theme))

        body = QVBoxLayout(self)
        body.setContentsMargins(16, 16, 16, 16)
        body.setSpacing(10)

        editor = QTextEdit()
        editor.setPlainText(text)
        editor.setReadOnly(True)
        editor.setStyleSheet(note_editor_qss(theme))
        body.addWidget(editor, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

    @classmethod
    def show_text(
        cls,
        parent: Optional[QWidget],
        theme: Theme,
        title: str,
        text: str,
    ) -> None:
        """弹窗查看长文本。"""
        cls(theme, title, text, parent).exec()


class TaskDetailDialog(QDialog):
    """完整待办查看：长条型窗口，完整文字 + 全部图片，图片可点击再放大。

    用户在卡片上点「查看全部」时弹出：备注不再截断，图片至少完整
    展示第一张；图片多了时整窗可下滑继续看；点某张图弹独立预览，
    可在该待办的多张照片间左右切换。
    """

    def __init__(
        self,
        theme: Theme,
        task: Task,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self._task = task
        self.setWindowTitle(task.text or "待办详情")
        # 弹窗更大：按屏幕可用区域取 86%，让图片有充分空间完整展示
        screen = QApplication.primaryScreen()
        area = (
            screen.availableGeometry()
            if screen is not None
            else QRect(0, 0, 1280, 800)
        )
        self.resize(
            max(720, int(area.width() * 0.86)),
            max(560, int(area.height() * 0.86)),
        )
        self.setMinimumSize(560, 420)
        self.setStyleSheet(dialog_qss(theme))

        # 内容区放进滚动区：文字 + 图片整体可下滑
        self._outer_scroll = QScrollArea()
        self._outer_scroll.setWidgetResizable(True)
        self._outer_scroll.setStyleSheet("background: transparent; border: none;")
        # 同预览弹窗：viewport 默认系统调色板背景，深色模式下是黑底，
        # 圆角照片透明角会露黑块，必须透出弹窗面板底色
        self._outer_scroll.viewport().setAutoFillBackground(False)
        container = QWidget()
        container.setStyleSheet(f"background: {theme['panel']};")
        body = QVBoxLayout(container)
        body.setContentsMargins(18, 18, 18, 18)
        body.setSpacing(12)
        self._body = body

        # 完整标题
        title = QLabel(task.text or "（无标题待办）")
        title.setWordWrap(True)
        title.setStyleSheet(f"color: {theme['text']}; font-size: 16px; font-weight: 600;")
        body.addWidget(title)

        # 完整备注
        note = " ".join(task.note.split())
        if note:
            note_label = QLabel("备注")
            note_label.setStyleSheet(f"color: {theme['sub']}; font-size: 12px;")
            body.addWidget(note_label)
            editor = QTextEdit()
            editor.setPlainText(note)
            editor.setReadOnly(True)
            editor.setMinimumHeight(90)
            editor.setStyleSheet(note_editor_qss(theme))
            body.addWidget(editor)

        # 全部图片：每张完整展示（适配宽度），可下滑继续看
        self._image_labels: list[tuple[QLabel, QPixmap]] = []
        self._image_paths: list[str] = []
        self._build_images(theme, task)

        self._outer_scroll.setWidget(container)
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self._outer_scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText("关闭")
        buttons.rejected.connect(self.reject)
        main.addWidget(buttons)

        # 等布局完成后按当前宽度排第一遍
        QTimer.singleShot(0, self._refit_images)

    # ------------------------------------------------------------------ 图片
    def _build_images(self, theme: Theme, task: Task) -> None:
        """把待办的全部有效图片按顺序加进内容区。"""
        for name in task.images:
            path = image_path(name)
            if not path.is_file():
                continue
            pix = QPixmap(str(path))
            if pix.isNull():
                continue
            target = str(path)
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("background: transparent; border: none;")
            label.setAutoFillBackground(False)
            label.setCursor(Qt.PointingHandCursor)
            label.setToolTip("点击放大查看，左右键切换")
            label.mousePressEvent = (
                lambda event, p=target: ImagePreviewDialog.show_images(
                    self, theme, self._image_paths, self._image_paths.index(p)
                )
            )
            self._body.addWidget(label)
            self._image_paths.append(target)
            self._image_labels.append((label, pix))

    def _refit_images(self) -> None:
        """智能适配：横图按宽度、竖图按高度、方图取整，完整可见且不糊。

        每张图在「可视区域宽高」双约束下取能完整显示的最大尺寸：
        宽 > 高的横图宽度受限，竖图高度受限，方形图取两者较小值，
        任何方向都不被裁切；高清屏按 DPR 输出物理像素，只缩小或
        适度放大，保证清晰。
        """
        viewport = self._outer_scroll.viewport()
        avail_w = max(120, viewport.width() - 36)
        avail_h = max(120, viewport.height() - 36)
        for label, pix in self._image_labels:
            display = _fit_pixmap(
                pix, avail_w, avail_h, self.devicePixelRatioF(), max_upscale=1.6
            )
            label.setPixmap(display)

    def resizeEvent(self, event) -> None:  # noqa: N802
        """窗口尺寸变化时重新排图。"""
        super().resizeEvent(event)
        self._refit_images()

    @classmethod
    def show_detail(
        cls,
        parent: Optional[QWidget],
        theme: Theme,
        task: Task,
    ) -> None:
        """弹窗查看完整待办。"""
        cls(theme, task, parent).exec()
