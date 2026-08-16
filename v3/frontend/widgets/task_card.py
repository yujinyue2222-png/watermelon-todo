"""任务卡片。

一条待办在列表里的样子：优先级色条 + 状态圆点 + 标题 + 备注预览 + 标签行，
悬停时右侧浮出编辑按钮，右键弹出更多操作。

卡片只负责展示与发信号，所有数据改动由主窗口交给后端处理。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QIcon, QMouseEvent, QPixmap, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from backend.core.constants import NOTE_PREVIEW_LIMIT
from backend.core.datetime_utils import due_label, format_due
from backend.core.paths import image_path
from backend.models.enums import Priority, Recurrence, Remind
from backend.models.task import Task
from frontend.dialogs.media_preview_dialog import TaskDetailDialog, open_image_viewer
from frontend.theme.palettes import (
    CATEGORY_COLORS,
    PIN_ICON,
    PRIORITY_COLORS,
    PRIORITY_ICONS,
    RECUR_ICON,
    REMIND_ICON,
    STATUS_ICONS,
    Theme,
)
from frontend.theme.qss import card_menu_qss, task_card_qss
from frontend.widgets.flow_layout import FlowLayout
from frontend.widgets.icons import pencil_icon

_CHECKED_BOX = "☑"
_UNCHECKED_BOX = "☐"
_EDIT_ICON_SIZE = 18
_THUMB_SIZE = 64

# 铅笔图标全列表共用一份：每次悬停都重绘一遍位图太浪费
_pencil_cache: Optional[QIcon] = None


def _pencil() -> QIcon:
    """取缓存的铅笔图标（首次调用时绘制）。"""
    global _pencil_cache
    if _pencil_cache is None:
        _pencil_cache = pencil_icon(_EDIT_ICON_SIZE)
    return _pencil_cache


class TaskCard(QFrame):
    """单条待办的卡片。

    Signals:
        toggled: 点击状态圆点或标题，切换完成状态。
        deleted: 请求删除。
        edited: 请求打开编辑弹窗。
        sub_toggled: 勾选某个小步骤，参数为 ``(任务 id, 小步骤下标)``。
        select_toggled: 多选模式下勾选，参数为 ``(任务 id, 是否选中)``。
        pin_toggled: 请求切换置顶。
        strong_requested: 请求打开强提醒设置。
    """

    toggled = Signal(str)
    deleted = Signal(str)
    edited = Signal(str)
    sub_toggled = Signal(str, int)
    select_toggled = Signal(str, bool)
    pin_toggled = Signal(str)
    strong_requested = Signal(str)

    def __init__(
        self,
        task: Task,
        theme: Theme,
        parent: Optional[QWidget] = None,
        select_mode: bool = False,
        selected: bool = False,
    ) -> None:
        """
        Args:
            task: 要展示的待办。
            theme: 当前配色。
            parent: 父控件。
            select_mode: 是否处于多选模式（状态圆点变复选框）。
            selected: 多选模式下是否已选中。
        """
        super().__init__(parent)
        self.task = task
        self._theme = theme
        self._select_mode = select_mode
        self._selected = selected
        self._hovered = False
        self._dot_bound = False

        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self.setMouseTracking(True)
        self._build()
        self._apply_style()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        """搭出卡片内部结构。"""
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QWidget()
        row = QHBoxLayout(top)
        row.setContentsMargins(7, 10, 10, 10)
        row.setSpacing(7)

        self._priority_bar = QFrame()
        self._priority_bar.setObjectName("pbar")
        self._priority_bar.setFixedWidth(3)
        row.addWidget(self._priority_bar)

        self._dot = QPushButton()
        self._dot.setObjectName("dot")
        self._dot.setFixedSize(22, 22)
        self._dot.setCursor(Qt.PointingHandCursor)
        self._bind_dot()
        row.addWidget(self._dot, 0, Qt.AlignVCenter)

        middle = QVBoxLayout()
        middle.setSpacing(3)

        self._title = QLabel(self.task.text)
        self._title.setObjectName("title")
        self._title.setWordWrap(True)
        middle.addWidget(self._title)

        note_preview = self._build_note_preview()
        if note_preview is not None:
            middle.addWidget(note_preview)

        image_row = self._build_image_row()
        if image_row is not None:
            middle.addWidget(image_row)

        meta = FlowLayout(horizontal_spacing=6, vertical_spacing=4)
        for widget in self._build_meta_widgets():
            meta.addWidget(widget)
        middle.addLayout(meta)
        row.addLayout(middle, 1)

        # 编辑按钮常驻布局、只切换图标显隐，避免悬停时卡片内容左右跳动。
        # 这里不能用 QGraphicsOpacityEffect：卡片本身在淡入/收起时也会挂一个效果，
        # 而 Qt 渲染不了「效果里再套效果」的子树，会刷屏报 QPainter 警告并丢帧
        self._edit_button = QPushButton()
        self._edit_button.setObjectName("edit")
        self._edit_button.setIconSize(QSize(_EDIT_ICON_SIZE, _EDIT_ICON_SIZE))
        self._edit_button.setFixedSize(27, 27)
        self._edit_button.setToolTip("编辑待办")
        self._edit_button.setCursor(Qt.PointingHandCursor)
        self._edit_button.clicked.connect(lambda: self.edited.emit(self.task.id))
        row.addWidget(self._edit_button, 0, Qt.AlignVCenter)

        outer.addWidget(top)
        outer.addWidget(self._build_subtask_panel())

        # 置顶钉子浮在右上角：绝对定位，不进布局也就不会挤压标题
        self._pin_mark = QLabel(PIN_ICON, self)
        self._pin_mark.setObjectName("pinmark")
        self._pin_mark.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._pin_mark.setVisible(self.task.pinned)
        self._place_pin_mark()

    def _build_note_preview(self) -> Optional[QLabel]:
        """备注预览标签；没有备注时返回 None。"""
        note = " ".join(self.task.note.split())
        if not note:
            return None
        text = note
        if len(text) > NOTE_PREVIEW_LIMIT:
            text = text[:NOTE_PREVIEW_LIMIT].rstrip() + "…"
        label = QLabel(f"备注 · {text}")
        label.setObjectName("notePreview")
        label.setToolTip(note)
        label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        return label

    def _build_image_row(self) -> Optional[QWidget]:
        """图片缩略图行；没有图片或文件缺失时返回 None。"""
        valid = [
            name
            for name in self.task.images
            if image_path(name).is_file() and not QPixmap(str(image_path(name))).isNull()
        ]
        if not valid:
            return None

        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 4, 0, 0)
        row.setSpacing(8)

        # 卡片上最多平铺 4 张，超出的折叠成「+N」
        # 缩略图按原图比例显示，不设固定方形框，避免圆角/横竖照片被塞进
        # 方形框后露黑底；保持照片原本形状。
        MAX_THUMBS = 4
        for idx, name in enumerate(valid[:MAX_THUMBS]):
            thumb = QLabel()
            thumb.setObjectName("thumb")
            thumb.setAlignment(Qt.AlignCenter)
            thumb.setStyleSheet("background: transparent; border: none;")
            thumb.setCursor(Qt.PointingHandCursor)
            pix = QPixmap(str(image_path(name)))
            if not pix.isNull():
                # 等比缩放进最大边长的框内，框尺寸随图自适应
                scale = min(
                    1.0, _THUMB_SIZE / pix.width(), _THUMB_SIZE / pix.height()
                )
                w = max(1, int(pix.width() * scale))
                h = max(1, int(pix.height() * scale))
                thumb.setFixedSize(w, h)
                thumb.setPixmap(
                    pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
            thumb.mousePressEvent = (
                lambda event, i=idx: open_image_viewer(
                    self, self._theme, valid, i
                )
            )
            row.addWidget(thumb, 0, Qt.AlignTop)
        extra = len(valid) - MAX_THUMBS
        if extra > 0:
            more = QLabel(f"+{extra}")
            more.setObjectName("thumbmore")
            more.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
            more.setAlignment(Qt.AlignCenter)
            row.addWidget(more, 0, Qt.AlignTop)
        row.addStretch(1)
        return box

    def _build_meta_widgets(self) -> list[QWidget]:
        """标签行：优先级、分类、截止、循环、提醒、强提醒、小步骤进度。"""
        widgets: list[QWidget] = []

        if self.task.priority != Priority.NORMAL:
            icon = PRIORITY_ICONS.get(self.task.priority, "")
            label = QLabel((icon + self.task.priority).strip())
            label.setObjectName("prio")
            widgets.append(label)

        category = QLabel(self.task.category)
        category.setObjectName("cat")
        widgets.append(category)

        due_widget = self._build_due_label()
        if due_widget is not None:
            widgets.append(due_widget)

        if Recurrence.is_repeating(self.task.recur):
            recur = QLabel(RECUR_ICON + self.task.recur)
            recur.setObjectName("recur")
            widgets.append(recur)

        # 「到期当天」是默认档、「关闭提醒」没必要展示；没有截止时间也谈不上提醒
        show_remind = self.task.remind not in (Remind.ON_TIME, Remind.OFF) and bool(
            self.task.due
        )
        if show_remind:
            remind = QLabel(REMIND_ICON + self.task.remind)
            remind.setObjectName("recur")
            widgets.append(remind)

        if self.task.strong.enabled:
            strong = QLabel("🔔强")
            strong.setObjectName("strongbadge")
            strong.setToolTip("已开启强提醒")
            widgets.append(strong)

        done_count, total = self.task.subtask_progress()
        if total:
            badge = QPushButton(f"{_CHECKED_BOX} {done_count}/{total}")
            badge.setObjectName("subbadge")
            badge.setCursor(Qt.PointingHandCursor)
            badge.clicked.connect(self.toggle_subtask_panel)
            widgets.append(badge)

        # 内容太长或带图片时给一个「查看全部」小键，点击弹长条型完整待办窗口
        note = " ".join(self.task.note.split())
        if len(note) > NOTE_PREVIEW_LIMIT or self.task.images:
            full = QPushButton("📄 查看全部")
            full.setObjectName("thumbbtn")
            full.setCursor(Qt.PointingHandCursor)
            full.setFixedHeight(24)
            full.clicked.connect(
                lambda: TaskDetailDialog.show_detail(self, self._theme, self.task)
            )
            widgets.append(full)

        return widgets

    def _build_due_label(self) -> Optional[QLabel]:
        """截止时间标签。

        已完成的待办只显示原始日期，不再标红、也不显示「已过期 X 天」——
        事情做完了就别追着催了。
        """
        if not self.task.due:
            return None
        if self.task.is_done:
            text, urgent = format_due(self.task.due), False
        else:
            text, urgent = due_label(self.task.due)
        if not text:
            return None
        label = QLabel(text)
        label.setObjectName("due_urgent" if urgent else "due")
        return label

    def _build_subtask_panel(self) -> QWidget:
        """小步骤展开区，默认收起。"""
        self._subtask_panel = QWidget()
        self._subtask_panel.setObjectName("subpanel")
        layout = QVBoxLayout(self._subtask_panel)
        layout.setContentsMargins(30, 0, 14, 10)
        layout.setSpacing(4)
        for index, subtask in enumerate(self.task.subtasks):
            mark = _CHECKED_BOX if subtask.done else _UNCHECKED_BOX
            button = QPushButton(f"{mark} {subtask.text}")
            button.setObjectName("subitem")
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, position=index: self.sub_toggled.emit(
                    self.task.id, position
                )
            )
            layout.addWidget(button)
        self._subtask_panel.setVisible(False)
        return self._subtask_panel

    # ------------------------------------------------------------------ 状态
    @property
    def select_mode(self) -> bool:
        """是否处于多选模式。"""
        return self._select_mode

    @property
    def selected(self) -> bool:
        """多选模式下是否被选中。"""
        return self._selected

    def toggle_subtask_panel(self) -> None:
        """展开/收起小步骤。"""
        self._subtask_panel.setVisible(not self._subtask_panel.isVisible())

    def set_selected(self, selected: bool) -> None:
        """原地更新选中态，避免重建卡片导致整表闪烁。"""
        self._selected = selected
        if self._select_mode:
            self._dot.setText(_CHECKED_BOX if selected else _UNCHECKED_BOX)

    def set_select_mode(self, select_mode: bool, selected: bool = False) -> None:
        """原地切换多选模式。

        Args:
            select_mode: 是否进入多选模式。
            selected: 进入多选模式时的初始选中态。
        """
        if select_mode == self._select_mode:
            if select_mode:
                self.set_selected(selected)
            return
        self._select_mode = select_mode
        self._selected = selected
        self._bind_dot()

    def refresh_status(self) -> None:
        """原地刷新完成状态与标题。"""
        if not self._select_mode:
            self._dot.setText(STATUS_ICONS.get(self.task.status, ""))
        self._title.setText(self.task.text)
        self._apply_style()

    def apply_theme(self, theme: Theme) -> None:
        """切换配色。"""
        self._theme = theme
        self._apply_style()

    # ------------------------------------------------------------------ 事件
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        """保持置顶钉子贴在右上角。"""
        self._place_pin_mark()
        super().resizeEvent(event)

    def enterEvent(self, event) -> None:  # noqa: N802
        """悬停：浮出编辑按钮并加深底色。"""
        self._hovered = True
        self._edit_button.setIcon(_pencil())
        self._apply_style()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        """离开：收起编辑按钮。"""
        self._hovered = False
        self._edit_button.setIcon(QIcon())
        self._apply_style()
        super().leaveEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """双击卡片直接进入编辑。"""
        self.edited.emit(self.task.id)
        super().mouseDoubleClickEvent(event)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:  # noqa: N802
        """右键菜单：置顶、备注、小步骤、强提醒、删除。"""
        if self._select_mode:
            return

        menu = QMenu(self)
        menu.setStyleSheet(card_menu_qss(self._theme))

        pin_action = menu.addAction(
            f"{PIN_ICON}  取消置顶" if self.task.pinned else f"{PIN_ICON}  置顶"
        )
        menu.addSeparator()
        note_action = menu.addAction("📝  编辑备注")
        subtask_action = None
        if self.task.subtasks:
            label = (
                "📂  收起小步骤"
                if self._subtask_panel.isVisible()
                else "📂  展开小步骤"
            )
            subtask_action = menu.addAction(label)
        menu.addSeparator()
        strong_action = menu.addAction("🔔  强提醒")
        menu.addSeparator()
        delete_action = menu.addAction("🗑  删除待办")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen == pin_action:
            self.pin_toggled.emit(self.task.id)
        elif chosen == note_action:
            self.edited.emit(self.task.id)
        elif subtask_action is not None and chosen == subtask_action:
            self.toggle_subtask_panel()
        elif chosen == strong_action:
            self.strong_requested.emit(self.task.id)
        elif chosen == delete_action:
            self.deleted.emit(self.task.id)

    # ------------------------------------------------------------------ 内部
    def _bind_dot(self) -> None:
        """按当前模式重新绑定状态圆点的点击行为。"""
        # 自己记状态，不靠异常兜底：PySide6 6.x 在「未连接就断开」时不再抛
        # RuntimeError，而是打一条 RuntimeWarning，每建一张卡片就刷一条
        if self._dot_bound:
            self._dot.clicked.disconnect()
        self._dot_bound = True

        if self._select_mode:
            self._dot.setText(_CHECKED_BOX if self._selected else _UNCHECKED_BOX)
            self._dot.clicked.connect(self._on_select_clicked)
        else:
            self._dot.setText(STATUS_ICONS.get(self.task.status, ""))
            self._dot.clicked.connect(lambda: self.toggled.emit(self.task.id))

    def _on_select_clicked(self) -> None:
        """多选模式下点击复选框。"""
        self._selected = not self._selected
        self._dot.setText(_CHECKED_BOX if self._selected else _UNCHECKED_BOX)
        self.select_toggled.emit(self.task.id, self._selected)

    def _place_pin_mark(self) -> None:
        """把置顶钉子摆到卡片右上角。"""
        self._pin_mark.adjustSize()
        self._pin_mark.move(self.width() - self._pin_mark.width() - 3, 2)
        self._pin_mark.raise_()

    def _apply_style(self) -> None:
        """套用当前状态对应的样式。"""
        category_color = CATEGORY_COLORS.get(self.task.category, self._theme["sub"])
        priority_color = PRIORITY_COLORS.get(self.task.priority, "#98A2B3")
        show_bar = not self.task.is_done and self.task.priority != Priority.NORMAL

        self._pin_mark.setVisible(self.task.pinned)
        self._place_pin_mark()
        self.setStyleSheet(
            task_card_qss(
                self._theme,
                category_color=category_color,
                priority_color=priority_color,
                is_done=self.task.is_done,
                is_hovered=self._hovered,
                show_priority_bar=show_bar,
            )
        )
