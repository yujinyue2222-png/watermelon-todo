"""编辑待办弹窗。

内容 / 分类 / 紧急程度 / 截止（含循环与提醒）/ 备注 / 小步骤 六块。
循环与提醒折叠进日期弹窗，所以这里只有一个「截止日期」按钮。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.core.paths import delete_image, image_path, store_image, store_image_bytes
from frontend.clipboard_image import clipboard_png_bytes
from backend.models.enums import Priority
from backend.models.task import SubTask, Task
from frontend.dialogs.due_picker_dialog import DuePickerDialog, Schedule
from frontend.dialogs.media_preview_dialog import open_image_viewer
from frontend.theme.palettes import Theme
from frontend.theme.qss import dialog_qss, note_editor_qss
from frontend.widgets.combo_box import ThemedComboBox

_DONE_STYLE = "text-decoration: line-through; color: #98A2B3;"
_NOTE_HEIGHT = 70
_CHECKED_BOX = "☑"
_UNCHECKED_BOX = "☐"
_IMAGE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
_THUMB_SIZE = 96


@dataclass
class TaskEditResult:
    """编辑结果。"""

    text: str
    category: str
    priority: str
    schedule: Schedule
    note: str
    images: list[str]
    subtasks: list[SubTask]


class _SubtaskRow:
    """小步骤编辑行：勾选框 + 输入框 + 删除按钮。"""

    def __init__(self, text: str, done: bool) -> None:
        self.done = done
        self.check_button = QPushButton(_CHECKED_BOX if done else _UNCHECKED_BOX)
        self.check_button.setCursor(Qt.PointingHandCursor)
        self.check_button.setFixedWidth(28)
        self.text_input = QLineEdit(text)
        self.text_input.setPlaceholderText("这一步要做什么？")
        self.delete_button = QPushButton("✕")
        self.delete_button.setCursor(Qt.PointingHandCursor)
        self.delete_button.setFixedWidth(28)

        self.check_button.clicked.connect(self._toggle)
        self._sync_style()

    @property
    def widgets(self) -> tuple[QWidget, ...]:
        """本行的三个控件。"""
        return (self.check_button, self.text_input, self.delete_button)

    def to_subtask(self) -> Optional[SubTask]:
        """转成模型；内容为空返回 None。"""
        text = self.text_input.text().strip()
        return SubTask(text=text, done=self.done) if text else None

    def _toggle(self) -> None:
        """切换完成态。"""
        self.done = not self.done
        self.check_button.setText(_CHECKED_BOX if self.done else _UNCHECKED_BOX)
        self._sync_style()

    def _sync_style(self) -> None:
        """已完成的小步骤加删除线。"""
        self.text_input.setStyleSheet(_DONE_STYLE if self.done else "")


class TaskEditDialog(QDialog):
    """编辑一条已有待办。"""

    def __init__(
        self,
        theme: Theme,
        task: Task,
        categories: Sequence[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            task: 待编辑的待办（不会被直接修改）。
            categories: 可选分类。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._task = task
        self._schedule = Schedule(
            due=task.due,
            recur=task.recur,
            recur_end=task.recur_end,
            remind=task.remind,
        )
        self._subtask_rows: list[_SubtaskRow] = []
        # 图片：_saved 是已保存的文件名列表；_added 是本次新增尚未入库的
        # (源文件路径, 内存字节)，保存时才真正写进应用数据目录
        self._saved: list[str] = list(task.images)
        self._added: list[tuple[Optional[str], Optional[bytes]]] = []

        self.setWindowTitle("编辑待办")
        self.setMinimumWidth(360)
        self.setStyleSheet(dialog_qss(theme))
        self._build(categories)

    @classmethod
    def edit(
        cls,
        parent: Optional[QWidget],
        theme: Theme,
        task: Task,
        categories: Sequence[str],
    ) -> Optional[TaskEditResult]:
        """弹出编辑窗，返回结果；取消或内容为空时返回 None。"""
        dialog = cls(theme, task, categories, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.result_value

    @property
    def result_value(self) -> Optional[TaskEditResult]:
        """收集当前界面上的编辑结果。"""
        text = self._text_input.text().strip()
        if not text:
            return None
        subtasks = []
        for row in self._subtask_rows:
            subtask = row.to_subtask()
            if subtask is not None:
                subtasks.append(subtask)
        return TaskEditResult(
            text=text,
            category=self._category_picker.currentText(),
            priority=self._priority_picker.currentText(),
            schedule=self._schedule,
            note=self._note_input.toPlainText().strip(),
            images=self._resolve_images(),
            subtasks=subtasks,
        )

    # ------------------------------------------------------------------ 构建
    def _build(self, categories: Sequence[str]) -> None:
        """搭出弹窗内容。"""
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(10)

        body.addWidget(QLabel("内容"))
        self._text_input = QLineEdit(self._task.text)
        self._text_input.setPlaceholderText("这条待办要做什么？")
        self._text_input.installEventFilter(self)
        body.addWidget(self._text_input)

        body.addLayout(self._build_pickers(categories))

        body.addWidget(QLabel("截止日期"))
        body.addLayout(self._build_due_row())

        body.addWidget(QLabel("备注（可选）"))
        self._note_input = QTextEdit()
        self._note_input.setPlaceholderText("记录进行中的注意事项…")
        self._note_input.setPlainText(self._task.note)
        self._note_input.setFixedHeight(_NOTE_HEIGHT)
        self._note_input.setStyleSheet(note_editor_qss(self._theme))
        self._note_input.installEventFilter(self)
        body.addWidget(self._note_input)

        body.addWidget(QLabel("图片（可选，可添加多张，支持直接粘贴截图）"))
        body.addLayout(self._build_image_section())

        body.addWidget(QLabel("小步骤（可选，把这条待办拆成几步）"))
        self._subtask_container = QWidget()
        self._subtask_layout = QVBoxLayout(self._subtask_container)
        self._subtask_layout.setContentsMargins(0, 0, 0, 0)
        self._subtask_layout.setSpacing(6)
        body.addWidget(self._subtask_container)
        for subtask in self._task.subtasks:
            self._add_subtask_row(subtask.text, subtask.done)

        add_subtask_button = QPushButton("＋ 添加一步")
        add_subtask_button.setCursor(Qt.PointingHandCursor)
        add_subtask_button.clicked.connect(lambda: self._add_subtask_row())
        body.addWidget(add_subtask_button)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

    def _build_pickers(self, categories: Sequence[str]) -> QHBoxLayout:
        """分类 + 紧急程度。"""
        row = QHBoxLayout()
        row.setSpacing(10)

        category_column = QVBoxLayout()
        category_column.setSpacing(4)
        category_column.addWidget(QLabel("分类"))
        self._category_picker = ThemedComboBox()
        self._category_picker.addItems(list(categories))
        self._category_picker.setCurrentText(self._task.category)
        category_column.addWidget(self._category_picker)
        row.addLayout(category_column, 1)

        priority_column = QVBoxLayout()
        priority_column.setSpacing(4)
        priority_column.addWidget(QLabel("紧急程度"))
        self._priority_picker = ThemedComboBox()
        self._priority_picker.addItems(list(Priority.ORDER))
        self._priority_picker.setCurrentText(self._task.priority)
        priority_column.addWidget(self._priority_picker)
        row.addLayout(priority_column, 1)
        return row

    def _build_due_row(self) -> QHBoxLayout:
        """截止日期按钮 + 清除。"""
        row = QHBoxLayout()
        row.setSpacing(8)

        self._due_button = QPushButton()
        self._due_button.setCursor(Qt.PointingHandCursor)
        self._due_button.clicked.connect(self._pick_schedule)
        self._refresh_due_button()
        row.addWidget(self._due_button, 1)

        clear_button = QPushButton("清除")
        clear_button.setCursor(Qt.PointingHandCursor)
        clear_button.clicked.connect(self._clear_due)
        row.addWidget(clear_button)
        return row

    # ------------------------------------------------------------------ 交互
    def _pick_schedule(self) -> None:
        """打开日期弹窗。"""
        picked = DuePickerDialog.pick(self, self._theme, self._schedule)
        if picked is None:
            return
        self._schedule = picked
        self._refresh_due_button()

    def _clear_due(self) -> None:
        """只清空截止日期，循环与提醒设置保留。"""
        self._schedule.due = ""
        self._refresh_due_button()

    def _refresh_due_button(self) -> None:
        """刷新截止日期按钮文字。"""
        self._due_button.setText(
            f"📅  {self._schedule.due}" if self._schedule.due else "📅  点击选择日期"
        )

    # ------------------------------------------------------------------ 事件
    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        """内容框/备注框里按 Cmd/Ctrl+V 时，若剪贴板有图片则作为待办图片。"""
        if (
            (obj is self._text_input or obj is self._note_input)
            and event.type() == QEvent.ShortcutOverride
            and event.matches(QKeySequence.Paste)
            and self._paste_image()
        ):
            event.accept()
            return True
        return super().eventFilter(obj, event)

    def _paste_image(self) -> bool:
        """从剪贴板读图并追加到图片列表；成功返回 True。"""
        data = clipboard_png_bytes()
        if not data:
            return False
        self._added.append((None, data))
        self._rebuild_preview()
        return True

    # ------------------------------------------------------------------ 图片
    def _build_image_section(self) -> QVBoxLayout:
        """图片区：并排缩略图（点击放大、右上角叉移除）+ 添加按钮。"""
        section = QVBoxLayout()
        section.setSpacing(6)

        self._preview_box = QHBoxLayout()
        self._preview_box.setSpacing(8)
        section.addLayout(self._preview_box)

        add_button = QPushButton("＋ 添加图片")
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(self._pick_image)
        section.addWidget(add_button, 0, Qt.AlignLeft)

        self._rebuild_preview()
        return section

    def _rebuild_preview(self) -> None:
        """按当前已保存 + 新增的图片列表并排重建缩略图。"""
        while self._preview_box.count():
            item = self._preview_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        total = len(self._saved) + len(self._added)
        if total == 0:
            return
        index = 0
        # 已保存的图片
        for name in self._saved:
            self._append_preview_cell(index, self._load_thumb_pix(name))
            index += 1
        # 新增待入库的图片
        for src, data in self._added:
            pix = QPixmap()
            if data:
                pix.loadFromData(data)
            elif src:
                pix = QPixmap(src)
            self._append_preview_cell(index, pix)
            index += 1
        self._preview_box.addStretch(1)

    def _append_preview_cell(self, index: int, pix: QPixmap) -> None:
        """追加一个并排缩略图单元：图片 + 右上角叉，点击放大。"""
        cell = QWidget()
        cell_layout = QGridLayout(cell)
        cell_layout.setContentsMargins(0, 0, 0, 0)
        cell_layout.setSpacing(0)

        thumb = QLabel()
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("background: transparent; border: none;")
        thumb.setCursor(Qt.PointingHandCursor)
        if pix.isNull():
            thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
            thumb.setStyleSheet(
                f"border: 1px dashed {self._theme['border']}; border-radius: 8px;"
                f" color: {self._theme['sub']}; background: {self._theme['panel']};"
            )
            thumb.setText("🖼")
        else:
            scale = min(1.0, _THUMB_SIZE / pix.width(), _THUMB_SIZE / pix.height())
            w = max(1, int(pix.width() * scale))
            h = max(1, int(pix.height() * scale))
            thumb.setFixedSize(w, h)
            thumb.setPixmap(
                pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        cell_layout.addWidget(thumb, 0, 0)

        close = QPushButton("✕")
        close.setObjectName("inlineimgclose")
        close.setFixedSize(18, 18)
        close.setCursor(Qt.PointingHandCursor)
        close.clicked.connect(
            lambda checked=False, i=index: self._remove_image(i)
        )
        cell_layout.addWidget(close, 0, 0, Qt.AlignTop | Qt.AlignRight)

        # 点击缩略图放大查看
        thumb.mousePressEvent = (
            lambda event, i=index: self._open_viewer(i)
        )
        self._preview_box.addWidget(cell)

    def _open_viewer(self, index: int) -> None:
        """打开大图预览，已保存 + 本次新增的图片都能看。"""
        import tempfile

        paths: list[str] = []
        for name in self._saved:
            p = image_path(name)
            if p.is_file():
                paths.append(str(p))
        for src, data in self._added:
            if src:
                paths.append(src)
            elif data:
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(data)
                tmp.close()
                paths.append(tmp.name)
        if not paths:
            return
        # 预览接收文件名列表（会经 image_path 解析），新增图片已是绝对路径，
        # 直接用绝对路径也能被 image_path 原样返回
        open_image_viewer(self, self._theme, paths, index)

    def _load_thumb_pix(self, name: str) -> QPixmap:
        """加载已保存图片文件的缩略图源图。"""
        path = image_path(name)
        return QPixmap(str(path)) if path.is_file() else QPixmap()

    def _pick_image(self) -> None:
        """选择一张图片加入列表（保存时才复制进应用数据目录）。"""
        src, _ = QFileDialog.getOpenFileName(self, "选择图片", "", _IMAGE_FILTER)
        if not src:
            return
        self._added.append((src, None))
        self._rebuild_preview()

    def _remove_image(self, index: int) -> None:
        """移除指定下标的图片（保存时清理被删的旧文件）。"""
        saved_len = len(self._saved)
        if index < saved_len:
            self._saved.pop(index)
        else:
            self._added.pop(index - saved_len)
        self._rebuild_preview()

    def _resolve_images(self) -> list[str]:
        """决定保存后的图片文件名列表，并清理不再需要的旧文件。"""
        result = list(self._saved)
        for src, data in self._added:
            new_name = ""
            if data:
                new_name = store_image_bytes(data)
            elif src:
                new_name = store_image(src)
            if new_name:
                result.append(new_name)
        # 删除本次编辑中被移除的旧图片文件
        kept = set(result)
        for old in self._task.images:
            if old not in kept:
                delete_image(old)
        return result

    def _add_subtask_row(self, text: str = "", done: bool = False) -> None:
        """追加一行小步骤。"""
        row = _SubtaskRow(text, done)
        layout = QHBoxLayout()
        layout.setSpacing(6)
        layout.addWidget(row.check_button)
        layout.addWidget(row.text_input, 1)
        layout.addWidget(row.delete_button)
        self._subtask_layout.addLayout(layout)
        self._subtask_rows.append(row)

        def remove() -> None:
            for widget in row.widgets:
                widget.setParent(None)
            self._subtask_layout.removeItem(layout)
            if row in self._subtask_rows:
                self._subtask_rows.remove(row)

        row.delete_button.clicked.connect(remove)
