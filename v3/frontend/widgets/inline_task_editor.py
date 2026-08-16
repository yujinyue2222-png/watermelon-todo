"""列表顶部的内联新建行。

点「＋ 添加待办」后直接在列表最上方插入一行可编辑区域，输入完回车即保存，
比弹窗更轻快。日期/循环/提醒统一收进日期弹窗里，所以这一行只有两排控件。
"""

from __future__ import annotations

from typing import Optional, Sequence

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtGui import QKeyEvent, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.core.datetime_utils import format_due
from backend.core.paths import delete_image, image_path, store_image, store_image_bytes
from backend.models.enums import Priority, Recurrence, Remind
from backend.services.task_service import TaskDraft
from frontend.clipboard_image import clipboard_png_bytes
from frontend.dialogs.media_preview_dialog import open_image_viewer
from frontend.theme.palettes import Theme
from frontend.theme.qss import inline_editor_qss
from frontend.widgets.combo_box import ThemedComboBox

_IMAGE_PREVIEW_SIZE = 56

_FALLBACK_CATEGORY = "其他"
_DATE_BUTTON_MIN_WIDTH = 46
_DATE_BUTTON_MAX_WIDTH = 135
_IMAGE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"


class InlineTaskEditor(QWidget):
    """内联新建待办的一行。

    Signals:
        submitted: 用户确认新建，携带一个 :class:`~backend.services.task_service.TaskDraft`。
        cancelled: 用户取消。
        due_requested: 用户点了日期按钮，请求宿主打开日期弹窗。
    """

    submitted = Signal(object)
    cancelled = Signal()
    due_requested = Signal()

    def __init__(
        self,
        theme: Theme,
        categories: Sequence[str],
        default_category: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            categories: 可选分类。
            default_category: 默认选中的分类。
            parent: 父控件。
        """
        super().__init__(parent)
        self.setObjectName("inlinerow")
        self._theme = theme

        self.due = ""
        self.recur = Recurrence.DEFAULT
        self.recur_end = ""
        self.remind = Remind.DEFAULT
        # 已添加的图片文件名列表（选图/粘贴时即复制进应用数据目录）
        self.images: list[str] = []

        self._build(categories, default_category)
        self.setStyleSheet(inline_editor_qss(theme))

    # ------------------------------------------------------------------ 对外
    def focus_input(self) -> None:
        """把光标放到内容输入框。"""
        self._text_input.setFocus()

    def set_schedule(self, due: str, recur: str, recur_end: str, remind: str) -> None:
        """写入日期弹窗返回的排期，并刷新日期按钮文字。"""
        self.due = due
        self.recur = recur
        self.recur_end = recur_end
        self.remind = remind
        self._refresh_date_button()

    # ------------------------------------------------------------------ 内部
    def _build(self, categories: Sequence[str], default_category: str) -> None:
        """搭出输入区 + 右下角按钮 + 分类优先级三排。"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # 第一排：双倍高度多行输入框
        self._text_input = QTextEdit()
        self._text_input.setObjectName("inlineedit")
        self._text_input.setPlaceholderText("输入待办内容，回车保存…")
        self._text_input.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._text_input.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # 默认 QTextEdit 会带内边距和 frame，更清爽一些
        self._text_input.setFrameStyle(0)
        # 单行高度，整体更紧凑；限制垂直方向不拉伸
        self._text_input.setMinimumHeight(28)
        self._text_input.setMaximumHeight(28)
        self._text_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed
        )
        self._text_input.installEventFilter(self)
        outer.addWidget(self._text_input)

        # 第二排：操作按钮靠右下
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)
        buttons_row.addStretch(1)

        self._image_button = QPushButton("🖼")
        self._image_button.setObjectName("inlinedate")
        self._image_button.setFixedSize(34, 30)
        self._image_button.setCursor(Qt.PointingHandCursor)
        self._image_button.setToolTip("添加图片（可选，支持直接粘贴截图）")
        self._image_button.clicked.connect(self._on_image_button)
        buttons_row.addWidget(self._image_button)

        self._date_button = QPushButton("📅")
        self._date_button.setObjectName("inlinedate")
        self._date_button.setFixedHeight(30)
        self._date_button.setFixedWidth(_DATE_BUTTON_MIN_WIDTH)
        self._date_button.setCursor(Qt.PointingHandCursor)
        self._date_button.setToolTip("设置截止时间 / 循环 / 提醒")
        self._date_button.clicked.connect(self.due_requested.emit)
        buttons_row.addWidget(self._date_button)

        confirm_button = QPushButton("✓")
        confirm_button.setObjectName("inlineok")
        confirm_button.setFixedSize(34, 30)
        confirm_button.setCursor(Qt.PointingHandCursor)
        confirm_button.clicked.connect(self._on_submit)
        buttons_row.addWidget(confirm_button)

        cancel_button = QPushButton("✕")
        cancel_button.setObjectName("inlinecancel")
        cancel_button.setFixedSize(34, 30)
        cancel_button.setCursor(Qt.PointingHandCursor)
        cancel_button.clicked.connect(self.cancelled.emit)
        buttons_row.addWidget(cancel_button)
        outer.addLayout(buttons_row)

        # 第三排：分类 + 优先级
        second_row = QHBoxLayout()
        second_row.setSpacing(6)

        self._category_picker = ThemedComboBox()
        self._category_picker.setObjectName("inlinect")
        self._category_picker.addItems(list(categories))
        self._category_picker.setCurrentText(
            self._pick_default_category(categories, default_category)
        )
        self._category_picker.setFixedHeight(26)
        second_row.addWidget(self._category_picker, 1)

        self._priority_picker = ThemedComboBox()
        self._priority_picker.setObjectName("inlinepr")
        self._priority_picker.addItems(list(Priority.ORDER))
        self._priority_picker.setCurrentText(Priority.DEFAULT)
        self._priority_picker.setFixedHeight(26)
        second_row.addWidget(self._priority_picker, 1)
        outer.addLayout(second_row)

        # 图片预览区：粘贴/选图后并排显示缩略图，每张右上角可删除
        self._preview_box = QHBoxLayout()
        self._preview_box.setSpacing(8)
        outer.addLayout(self._preview_box)

    @staticmethod
    def _pick_default_category(categories: Sequence[str], preferred: str) -> str:
        """决定默认分类：优先跟随当前筛选，其次「其他」，最后第一项。"""
        if preferred in categories:
            return preferred
        if _FALLBACK_CATEGORY in categories:
            return _FALLBACK_CATEGORY
        return categories[0] if categories else _FALLBACK_CATEGORY

    def _refresh_date_button(self) -> None:
        """按内容调整日期按钮宽度，避免日期被截断。"""
        text = f"📅 {format_due(self.due)}" if self.due else "📅"
        self._date_button.setText(text)
        content_width = self._date_button.fontMetrics().horizontalAdvance(text)
        self._date_button.setFixedWidth(
            max(_DATE_BUTTON_MIN_WIDTH, min(_DATE_BUTTON_MAX_WIDTH, content_width + 20))
        )

    # ------------------------------------------------------------------ 事件
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """处理输入框的粘贴图片、Enter 提交、Shift+Enter 换行。"""
        if obj is not self._text_input:
            return super().eventFilter(obj, event)

        # Cmd/Ctrl+V：优先尝试粘贴为待办图片
        if event.type() == QEvent.ShortcutOverride and event.matches(
            QKeySequence.Paste
        ):
            if self._paste_image():
                event.accept()
                return True
        # macOS 上 KeyPress 阶段也可能收到粘贴，补一道
        if (
            event.type() == QEvent.KeyPress
            and (event.modifiers() & (Qt.ControlModifier | Qt.MetaModifier))
            and event.key() == Qt.Key_V
        ):
            if self._paste_image():
                return True

        # Enter/Return 提交；Shift+Enter 换行保持默认
        if event.type() == QEvent.KeyPress:
            key_event = event  # type: QKeyEvent
            if key_event.key() in (Qt.Key_Return, Qt.Key_Enter):
                if not (key_event.modifiers() & Qt.ShiftModifier):
                    self._on_submit()
                    return True
        return super().eventFilter(obj, event)

    def _paste_image(self) -> bool:
        """尝试从剪贴板粘贴图片，追加到图片列表；成功返回 True。"""
        data = clipboard_png_bytes()
        if not data:
            return False
        new_name = store_image_bytes(data)
        if not new_name:
            return False
        self.images.append(new_name)
        self._rebuild_preview()
        return True

    # ------------------------------------------------------------------ 图片
    def _on_image_button(self) -> None:
        """点图片按钮：无图直接选图；有图弹小菜单继续添加或全部移除。"""
        if not self.images:
            self._pick_image()
            return
        menu = QMenu(self)
        add_action = menu.addAction("添加图片")
        remove_action = menu.addAction("移除全部图片")
        chosen = menu.exec(self._image_button.mapToGlobal(self._image_button.rect().bottomLeft()))
        if chosen is add_action:
            self._pick_image()
        elif chosen is remove_action:
            self._remove_all_images()

    def _pick_image(self) -> None:
        """选择图片并复制进应用数据目录，追加到图片列表。"""
        src, _ = QFileDialog.getOpenFileName(self, "选择图片", "", _IMAGE_FILTER)
        if not src:
            return
        new_name = store_image(src)
        if not new_name:
            return
        self.images.append(new_name)
        self._rebuild_preview()

    def _remove_image(self, index: int) -> None:
        """移除指定下标的图片。"""
        if index < 0 or index >= len(self.images):
            return
        name = self.images.pop(index)
        delete_image(name)
        self._rebuild_preview()

    def _remove_all_images(self) -> None:
        """移除全部图片。"""
        for name in self.images:
            delete_image(name)
        self.images.clear()
        self._rebuild_preview()

    def _rebuild_preview(self) -> None:
        """按当前图片列表并排重建缩略图，每张右上角带删除叉。"""
        while self._preview_box.count():
            item = self._preview_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        if not self.images:
            self._image_button.setToolTip("添加图片（可选，支持直接粘贴截图）")
            return
        for index, name in enumerate(self.images):
            path = image_path(name)
            pix = QPixmap(str(path)) if path.is_file() else QPixmap()

            # 单张照片：图片 + 右上角叉叉，整体作为并排的一个单元
            cell = QWidget()
            cell.setObjectName("inlineimgcell")
            cell_layout = QGridLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(0)

            label = QLabel()
            label.setObjectName("inlineimg")
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet("background: transparent; border: none;")
            label.setCursor(Qt.PointingHandCursor)
            if not pix.isNull():
                scale = min(
                    1.0,
                    _IMAGE_PREVIEW_SIZE / pix.width(),
                    _IMAGE_PREVIEW_SIZE / pix.height(),
                )
                w = max(1, int(pix.width() * scale))
                h = max(1, int(pix.height() * scale))
                label.setFixedSize(w, h)
                label.setPixmap(
                    pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            label.mousePressEvent = (
                lambda event, i=index: open_image_viewer(
                    self, self._theme, self.images, i
                )
            )
            cell_layout.addWidget(label, 0, 0)

            # 右上角叉叉，叠在图片之上
            close = QPushButton("✕")
            close.setObjectName("inlineimgclose")
            close.setFixedSize(18, 18)
            close.setCursor(Qt.PointingHandCursor)
            close.clicked.connect(
                lambda checked=False, i=index: self._remove_image(i)
            )
            cell_layout.addWidget(close, 0, 0, Qt.AlignTop | Qt.AlignRight)

            self._preview_box.addWidget(cell)
        self._preview_box.addStretch(1)
        self._preview_box.setEnabled(True)
        self._image_button.setToolTip(
            f"已添加 {len(self.images)} 张图片，点击可继续添加或移除"
        )

    def _on_submit(self) -> None:
        """校验内容并发出新建请求。"""
        text = self._text_input.toPlainText().strip()
        if not text:
            self.cancelled.emit()
            return
        self.submitted.emit(
            TaskDraft(
                text=text,
                category=self._category_picker.currentText(),
                due=self.due,
                priority=self._priority_picker.currentText(),
                recur=self.recur,
                recur_end=self.recur_end,
                remind=self.remind,
                images=list(self.images),
            )
        )
