"""主窗口。

一个无边框圆角面板：顶部标题栏与统计，中间是「日常待办 / 项目待办」两个视图，
底部是批量操作条。窗口可拖动、可从边缘拉伸、可折叠成一条标题栏。

这个类只做三件事：把控件搭出来、把用户操作转成对后端服务的调用、把结果画回界面。
所有业务规则都在 ``backend`` 里。
"""

from __future__ import annotations

import datetime
import logging
import subprocess
from pathlib import Path
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QRect,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QGraphicsOpacityEffect,
    QStyle,
    QStyleOptionButton,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from backend.api import TodoBackend
from backend.core.constants import APP_NAME, APP_VERSION, REMINDER_INTERVAL_MS
from backend.core.platform_info import IS_LINUX, IS_MACOS, IS_WINDOWS
from backend.models.enums import CATEGORY_ALL, TaskStatus, ViewMode
from backend.models.task import Task
from backend.services.export_service import ExportError
from backend.services.reminder_service import ReminderEvent
from backend.services.task_service import TaskDraft, TaskQuery
from backend.sync.engine import SyncResult
from backend.system.autostart import is_autostart_supported
from frontend.dialogs.all_tasks_dialog import AllTasksDialog
from frontend.dialogs.batch_add_dialog import BatchAddDialog, DuplicateChoice, FormMemory
from frontend.dialogs.due_picker_dialog import DuePickerDialog, Schedule
from frontend.dialogs.export_dialog import ExportOptionsDialog
from frontend.dialogs.hotkey_dialog import HotkeyDialog
from frontend.dialogs.project_manage_dialog import ProjectManageDialog
from frontend.dialogs.reminder_popup import ReminderPopup
from frontend.dialogs.strong_remind_dialog import StrongRemindDialog
from frontend.dialogs.sync_dialog import SyncDialog
from frontend.dialogs.task_edit_dialog import TaskEditDialog
from frontend.dialogs.theme_market_dialog import ThemeMarketDialog
from frontend.native.global_hotkey import GlobalHotkey
from frontend.native.window_effects import (
    apply_no_steal_focus,
    bring_to_front_quietly,
    float_window_flags,
)
from frontend.theme.painting import fill_theme_background, parse_color
from frontend.theme.palettes import THEME_SHOWCASE_LIMIT
from frontend.sync_controller import SyncController
from frontend.theme.qss import dialog_qss, inline_editor_qss, main_window_qss, menu_qss
from frontend.theme.theme_manager import ThemeManager
from frontend.widgets.combo_box import ThemedComboBox
from frontend.widgets.icons import app_icon
from frontend.widgets.inline_task_editor import InlineTaskEditor
from frontend.widgets.task_card import TaskCard
from frontend.widgets.toast import Toast
from frontend.windows.ball_speech import nickname, random_cheer
from frontend.windows.floating_ball import FloatingBall

logger = logging.getLogger(__name__)

_COLLAPSED_HEIGHT = 48
_MIN_EXPANDED_HEIGHT = 420
_MIN_WIDTH = 300
_RESIZE_MARGIN = 6
_MAX_HEIGHT = 16_777_215
_CARD_FADE_DELAY_MS = 40
_REORDER_DELAY_MS = 280
_STRONG_POPUP_MS = 8000
# 每分钟检查一次系统日期是否翻篇：过了午夜或休眠唤醒后要重建列表，
# 否则「明天」等相对日期标签会停在昨天算出的值上（21 号设的待办到 22 号还显示「明天」）。
_DATE_WATCH_INTERVAL_MS = 60_000
_BACKGROUND_MASK_ALPHA = 150
# 启动后多久做第一次同步：等界面显示完，避免和启动抢资源
_FIRST_SYNC_DELAY_MS = 1500
_SYNC_IDLE_ICON = "☁"
_SYNC_BUSY_ICON = "⟳"
_IMAGE_FILTER = "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)"
_EXPORT_FILTER = "CSV 文件 (*.csv);;文本文件 (*.txt)"


class _TitleIconButton(QPushButton):
    """标题栏图标按钮：用 QPainter 直接绘制，不依赖字体字形，避免乱码。"""

    def __init__(self, kind: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._kind = kind

    def paintEvent(self, event):  # noqa: N802
        """先用 QSS/Style 绘制按钮背景（含 hover），再叠画图标。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 让 Qt 样式引擎画出 titlebtn 背景和高亮，保证和其他按钮一致
        opt = QStyleOptionButton()
        self.initStyleOption(opt)
        self.style().drawControl(QStyle.CE_PushButton, opt, painter, self)

        w, h = self.width(), self.height()
        color = QColor("#9aa0a6")
        if self.underMouse():
            color = QColor("#ffffff")
        painter.setPen(color)
        painter.setBrush(color)
        if self._kind == "minimize":
            bar_w, bar_h = max(10, int(w * 0.35)), 2
            x = (w - bar_w) // 2
            y = (h - bar_h) // 2
            painter.drawRect(x, y, bar_w, bar_h)
        else:
            painter.drawText(self.rect(), Qt.AlignCenter, "-")
        painter.end()


class MainWindow(QWidget):
    """待办主面板。"""

    def __init__(self, backend: TodoBackend) -> None:
        """
        Args:
            backend: 后端门面。
        """
        super().__init__()
        self._backend = backend
        self._themes = ThemeManager(backend, self)
        self._themes.changed.connect(self._on_theme_changed)
        self._toast = Toast(self)
        self._hotkey = GlobalHotkey()

        config = backend.config
        self._view_mode = ViewMode.DAILY
        self._active_category = CATEGORY_ALL
        self._active_project = ""
        self._select_mode = False
        self._selected_ids: set[str] = set()
        self._collapsed = False
        self._expanded_height = config.expanded_height
        self._nickname = nickname()
        self._add_form_memory = FormMemory()

        self._inline_editor: Optional[InlineTaskEditor] = None
        self._floating_ball: Optional[FloatingBall] = None
        self._tray: Optional[QSystemTrayIcon] = None
        self._background: Optional[QPixmap] = None
        self._exiting = False
        self._delete_animations: list[QPropertyAnimation] = []
        self._progress_animation: Optional[QPropertyAnimation] = None

        self._drag_offset = None
        self._resizing = False
        self._resize_edges = ""
        self._resize_start_geometry: Optional[QRect] = None
        self._resize_start_pos = None

        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(float_window_flags(topmost=config.topmost))
        apply_no_steal_focus(self, accept_focus=True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumWidth(_MIN_WIDTH)

        self._load_background()
        self._restore_geometry()
        self._build_ui()
        self.refresh()
        self._setup_tray()

        self._reminder_timer = QTimer(self)
        self._reminder_timer.timeout.connect(self._check_reminders)
        self._reminder_timer.start(REMINDER_INTERVAL_MS)

        # 监视日期翻篇：卡片上的「今天/明天/N 天后」是在构建卡片那一刻算好的，
        # 程序常驻不动时不会自己更新。这里每分钟看一眼日期，一旦跨天就重建列表，
        # 让相对日期标签跟上真实的今天。
        self._last_seen_date = datetime.date.today()
        self._date_watch_timer = QTimer(self)
        self._date_watch_timer.timeout.connect(self._check_date_rollover)
        self._date_watch_timer.start(_DATE_WATCH_INTERVAL_MS)

        self._sync = SyncController(backend, self)
        self._sync.state_changed.connect(self._on_sync_state_changed)
        self._sync.finished.connect(self._on_sync_finished)
        # 用户一改数据就安排一次同步（带防抖），不必等到下一个定时周期
        backend.tasks.set_change_listener(self._sync.schedule_after_change)
        self._sync.apply_settings()
        if self._sync.is_configured:
            QTimer.singleShot(_FIRST_SYNC_DELAY_MS, lambda: self._sync.request_sync())

        if config.floating_ball:
            self.show_floating_ball()

        # 运行中拔副屏、改分辨率或 DPI 变化后，上次坐标可能落到屏幕之外，
        # 窗口和悬浮球就会「莫名不见了」但进程还在。监听屏幕变化，自动拉回可见区。
        self._connect_screen_guard()

    def _connect_screen_guard(self) -> None:
        """监听屏幕增删/几何变化，变化后把窗口与悬浮球拉回可见区域。"""
        app = QApplication.instance()
        if app is None:
            return
        app.screenAdded.connect(self._on_screens_changed)
        app.screenRemoved.connect(self._on_screens_changed)
        app.primaryScreenChanged.connect(self._on_screens_changed)
        for screen in app.screens():
            screen.geometryChanged.connect(self._on_screens_changed)
            screen.availableGeometryChanged.connect(self._on_screens_changed)

    def _on_screens_changed(self, *args) -> None:
        """屏幕布局变化：延迟一拍等系统稳定，再把窗口/悬浮球夹回可见区。"""
        QTimer.singleShot(300, self._ensure_on_screen)

    def _ensure_on_screen(self) -> None:
        """把主窗口和悬浮球都夹回当前可见区域，避免留在屏幕外看不见。"""
        if self.isVisible():
            self._restore_geometry()
        if self._floating_ball is not None:
            self._floating_ball.clamp_into_screen()

    # ================================================================ 生命周期
    @property
    def theme(self):
        """当前配色。"""
        return self._themes.current

    def register_hotkey(self) -> bool:
        """按配置注册全局快捷键。"""
        return self._hotkey.register(self._backend.config.hotkey, self.toggle_visibility)

    def toggle_visibility(self) -> None:
        """全局快捷键：可见就隐藏，隐藏就以完整界面召回。"""
        if self.isVisible() and not self.isMinimized():
            self.hide()
            return
        self.summon_to_front()

    def summon_to_front(self) -> None:
        """把窗口召回前台。"""
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def quit_application(self) -> None:
        """彻底退出程序（不再驻留后台）。"""
        self._exiting = True
        self._save_config()
        self._release_resources()
        QApplication.quit()

    def sync_now(self) -> None:
        """手动触发一次同步。"""
        self._sync.request_sync(manual=True)

    def closeEvent(self, event) -> None:  # noqa: N802
        """点关闭按钮只隐藏到后台；真正退出走 :meth:`quit_application`。"""
        if self._exiting:
            self._release_resources()
            super().closeEvent(event)
            return
        self._save_config()
        event.ignore()
        self.hide()

    def _release_resources(self) -> None:
        """退出前释放托盘、悬浮球、同步线程与全局热键，避免进程残留。"""
        if self._tray is not None:
            self._tray.hide()
            self._tray = None
        self.hide_floating_ball()
        self._sync.stop()
        self._hotkey.unregister()

    # ==================================================================== 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        """画圆角背景（渐变/纯色/背景图）与细边框。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        radius = 14 if self._collapsed else 20
        path.addRoundedRect(rect, radius, radius)

        theme = self.theme
        fill_theme_background(painter, theme, path, rect.topLeft(), rect.bottomRight())

        if self._background is not None and not self._background.isNull():
            painter.save()
            painter.setClipPath(path)
            scaled = self._background.scaled(
                rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            painter.drawPixmap(
                rect.x() + (rect.width() - scaled.width()) // 2,
                rect.y() + (rect.height() - scaled.height()) // 2,
                scaled,
            )
            # 叠一层半透明遮罩，保证文字仍然读得清
            mask = parse_color(theme["bg"])
            mask.setAlpha(_BACKGROUND_MASK_ALPHA)
            painter.fillPath(path, QBrush(mask))
            painter.restore()

        pen = painter.pen()
        pen.setColor(QColor(theme["border"]))
        painter.setPen(pen)
        painter.drawPath(path)

    # ==================================================================== 构建
    def _build_ui(self) -> None:
        """搭出窗口结构。"""
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(11)

        root.addLayout(self._build_title_bar())
        self._stats_box = self._build_stats()
        root.addWidget(self._stats_box)
        root.addLayout(self._build_tab_bar())
        root.addWidget(self._build_add_button())
        root.addWidget(self._build_project_bar())
        root.addWidget(self._build_category_bar())

        self._scroll = QScrollArea()
        self._scroll.setObjectName("scroll")
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        list_holder = QWidget()
        self._list_layout = QVBoxLayout(list_holder)
        self._list_layout.setContentsMargins(0, 2, 0, 2)
        self._list_layout.setSpacing(7)
        self._list_layout.addStretch()
        self._scroll.setWidget(list_holder)
        root.addWidget(self._scroll, 1)

        self._batch_bar = self._build_batch_bar()
        self._batch_bar.setVisible(False)
        root.addWidget(self._batch_bar)

        self.setStyleSheet(main_window_qss(self.theme))
        self._apply_view_mode()
        self._apply_collapsed()

    def _build_title_bar(self) -> QHBoxLayout:
        """标题 + 鼓励语 + 右侧四个小按钮。"""
        bar = QHBoxLayout()
        bar.setSpacing(8)

        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel(f"🍉 {APP_NAME}")
        title.setObjectName("apptitle")
        title.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        titles.addWidget(title)

        self._cheer_label = QLabel(random_cheer(self._nickname))
        self._cheer_label.setObjectName("cheer")
        self._cheer_label.setCursor(Qt.PointingHandCursor)
        self._cheer_label.setToolTip("点一下换一句")
        self._cheer_label.mousePressEvent = self._reroll_cheer
        titles.addWidget(self._cheer_label)
        bar.addLayout(titles)
        bar.addStretch()

        self._sync_button = QPushButton(_SYNC_IDLE_ICON)
        self._theme_button = QPushButton("🎨")
        self._theme_button.setToolTip("主题与背景")
        self._menu_button = QPushButton("⋮")
        self._menu_button.setToolTip("更多设置")
        self._collapse_button = _TitleIconButton("minimize")
        self._collapse_button.setToolTip("隐藏窗口（缩小到后台）")
        self._collapse_button.setObjectName("titlebtn")
        self._collapse_button.clicked.connect(self._toggle_collapse)
        close_button = QPushButton("✕")
        close_button.setObjectName("closebtn")
        close_button.setToolTip("隐藏到后台（彻底退出请点 ⋮ 菜单）")

        title_font = QFont("PingFang SC", 14)
        title_font.setWeight(QFont.Weight.Medium)

        # 统一设置标题栏按钮样式/尺寸；最小化按钮放在关闭按钮左边
        title_buttons = [
            self._sync_button,
            self._theme_button,
            self._menu_button,
            self._collapse_button,
            close_button,
        ]
        for button in title_buttons:
            if button.objectName() != "closebtn":
                button.setObjectName("titlebtn")
            button.setFixedSize(30, 30)
            button.setCursor(Qt.PointingHandCursor)
            button.setFont(title_font)
            bar.addWidget(button)

        self._sync_button.clicked.connect(self._show_sync_menu)
        self._theme_button.clicked.connect(self._show_theme_menu)
        self._menu_button.clicked.connect(self._show_main_menu)
        self._collapse_button.clicked.connect(self._toggle_collapse)
        close_button.clicked.connect(self.hide)
        self._refresh_sync_button()
        return bar

    def _build_stats(self) -> QFrame:
        """统计区：文案 + 百分比 + 进度条。"""
        box = QFrame()
        box.setObjectName("stats")
        layout = QVBoxLayout(box)
        layout.setContentsMargins(14, 12, 14, 13)
        layout.setSpacing(9)

        top = QHBoxLayout()
        self._stats_text = QLabel("今日 0/0")
        self._stats_text.setObjectName("statstext")
        top.addWidget(self._stats_text)
        top.addStretch()
        self._stats_percent = QLabel("0%")
        self._stats_percent.setObjectName("statspct")
        top.addWidget(self._stats_percent)
        layout.addLayout(top)

        self._progress_track = QFrame()
        self._progress_track.setObjectName("barbg")
        self._progress_track.setFixedHeight(8)
        self._progress_fill = QFrame(self._progress_track)
        self._progress_fill.setObjectName("barfg")
        self._progress_fill.setGeometry(0, 0, 0, 8)
        layout.addWidget(self._progress_track)
        return box

    def _build_tab_bar(self) -> QHBoxLayout:
        """日常待办 / 项目待办 切换。"""
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self._tab_buttons: dict[str, QPushButton] = {}
        for mode, label in (
            (ViewMode.DAILY, "📋 日常待办"),
            (ViewMode.PROJECT, "📁 项目待办"),
        ):
            button = QPushButton(label)
            button.setObjectName("tabbtn")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setChecked(mode == self._view_mode)
            button.clicked.connect(lambda _=False, target=mode: self._switch_view(target))
            self._tab_buttons[mode] = button
            bar.addWidget(button, 1)
        return bar

    def _build_add_button(self) -> QWidget:
        """日常视图的「＋ 添加待办」。"""
        self._add_button = QPushButton("＋ 添加待办")
        self._add_button.setObjectName("addbtn")
        self._add_button.setFixedHeight(40)
        self._add_button.setCursor(Qt.PointingHandCursor)
        self._add_button.clicked.connect(self._open_inline_editor)
        return self._add_button

    def _build_project_bar(self) -> QFrame:
        """项目视图的工具栏：项目下拉 + 添加/导出/多选。"""
        bar = QFrame()
        bar.setObjectName("projbar")
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)

        first_row = QHBoxLayout()
        first_row.setSpacing(6)
        self._project_picker = ThemedComboBox(self)
        self._project_picker.setObjectName("projpick")
        self._project_picker.setMinimumHeight(34)
        self._project_picker.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._project_picker.activated.connect(self._on_project_picked)
        first_row.addWidget(self._project_picker, 1)

        manage_button = QPushButton("⚙")
        manage_button.setObjectName("secondarybtn")
        manage_button.setFixedSize(34, 34)
        manage_button.setToolTip("管理项目（重命名 / 删除）")
        manage_button.setCursor(Qt.PointingHandCursor)
        manage_button.clicked.connect(self._open_project_manager)
        first_row.addWidget(manage_button)
        outer.addLayout(first_row)

        second_row = QHBoxLayout()
        second_row.setSpacing(8)
        add_button = QPushButton("＋ 添加待办")
        add_button.setObjectName("secondarybtn")
        add_button.setFixedHeight(36)
        add_button.setCursor(Qt.PointingHandCursor)
        add_button.clicked.connect(self._open_batch_add)
        second_row.addWidget(add_button, 3)

        export_button = QPushButton("⬇ 导出")
        export_button.setObjectName("secondarybtn")
        export_button.setFixedHeight(36)
        export_button.setCursor(Qt.PointingHandCursor)
        export_button.clicked.connect(self._export_project)
        second_row.addWidget(export_button, 1)

        self._project_multi_button = QPushButton("多选")
        self._project_multi_button.setObjectName("secondarybtn")
        self._project_multi_button.setFixedHeight(36)
        self._project_multi_button.setCursor(Qt.PointingHandCursor)
        self._project_multi_button.clicked.connect(self._toggle_select_mode)
        second_row.addWidget(self._project_multi_button, 1)

        self._project_select_all_button = QPushButton("全选")
        self._project_select_all_button.setObjectName("selallbtn")
        self._project_select_all_button.setFixedHeight(36)
        self._project_select_all_button.setCursor(Qt.PointingHandCursor)
        self._project_select_all_button.clicked.connect(self._select_all_visible)
        self._project_select_all_button.setVisible(False)
        second_row.addWidget(self._project_select_all_button, 1)
        outer.addLayout(second_row)

        self._project_bar = bar
        bar.setVisible(False)
        return bar

    def _build_category_bar(self) -> QFrame:
        """日常视图的分类筛选栏 + 导出/多选按钮。"""
        self._category_bar = QFrame()
        self._category_bar.setObjectName("catbar")
        outer = QHBoxLayout(self._category_bar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        outer.setAlignment(Qt.AlignVCenter)

        self._category_scroll = QScrollArea()
        self._category_scroll.setObjectName("catscroll")
        self._category_scroll.setWidgetResizable(True)
        self._category_scroll.setFrameShape(QFrame.NoFrame)
        self._category_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._category_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._category_scroll.setFixedHeight(30)
        self._category_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # 普通鼠标没有横向滚轮，这里把竖直滚轮转成横向滚动
        self._category_scroll.viewport().installEventFilter(self)

        chips_holder = QWidget()
        self._chips_layout = QHBoxLayout(chips_holder)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(6)
        self._chips_layout.setAlignment(Qt.AlignVCenter)

        self._category_buttons: dict[str, QPushButton] = {}
        for name in [CATEGORY_ALL] + list(self._backend.config.categories):
            self._chips_layout.addWidget(self._make_category_chip(name))

        self._new_category_button = QPushButton("＋ 标签")
        self._new_category_button.setObjectName("chip")
        self._new_category_button.setFixedHeight(28)
        self._new_category_button.setCursor(Qt.PointingHandCursor)
        self._new_category_button.setToolTip("新建标签")
        self._new_category_button.clicked.connect(self._create_category)
        self._chips_layout.addWidget(self._new_category_button)
        self._chips_layout.addStretch()

        self._category_scroll.setWidget(chips_holder)
        outer.addWidget(self._category_scroll, 1)

        export_button = QPushButton("导出")
        export_button.setObjectName("chip")
        export_button.setCursor(Qt.PointingHandCursor)
        export_button.setToolTip("导出待办（按日期区间 / 完成状态）")
        export_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        export_button.setFixedHeight(28)
        export_button.clicked.connect(self._export_daily)
        outer.addWidget(export_button)

        self._multi_button = QPushButton("☑")
        self._multi_button.setObjectName("chip")
        self._multi_button.setCursor(Qt.PointingHandCursor)
        self._multi_button.setToolTip("多选")
        self._multi_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._multi_button.setFixedHeight(28)
        self._multi_button.clicked.connect(self._toggle_select_mode)
        outer.addWidget(self._multi_button)

        self._select_all_button = QPushButton("全选")
        self._select_all_button.setObjectName("chip")
        self._select_all_button.setCursor(Qt.PointingHandCursor)
        self._select_all_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._select_all_button.setFixedHeight(28)
        self._select_all_button.clicked.connect(self._select_all_visible)
        self._select_all_button.setVisible(False)
        outer.addWidget(self._select_all_button)
        return self._category_bar

    def _make_category_chip(self, name: str) -> QPushButton:
        """生成一个分类筛选 chip。"""
        button = QPushButton(name)
        button.setObjectName("chip")
        button.setCheckable(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setChecked(name == self._active_category)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.setFixedHeight(28)
        button.clicked.connect(lambda _=False, target=name: self._set_category(target))
        self._category_buttons[name] = button
        return button

    def _build_batch_bar(self) -> QFrame:
        """批量操作条。"""
        bar = QFrame()
        bar.setObjectName("batchbar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        self._batch_label = QLabel("已选 0")
        self._batch_label.setObjectName("batchlbl")
        layout.addWidget(self._batch_label)
        layout.addStretch()

        done_button = QPushButton("✓完成")
        done_button.setObjectName("batchbtn")
        done_button.setCursor(Qt.PointingHandCursor)
        done_button.clicked.connect(self._batch_mark_done)
        layout.addWidget(done_button)

        self._batch_category_button = QPushButton("改分类")
        self._batch_category_button.setObjectName("batchbtn")
        self._batch_category_button.setCursor(Qt.PointingHandCursor)
        self._batch_category_button.clicked.connect(self._batch_change_category)
        layout.addWidget(self._batch_category_button)

        delete_button = QPushButton("✕删除")
        delete_button.setObjectName("batchdanger")
        delete_button.setCursor(Qt.PointingHandCursor)
        delete_button.clicked.connect(self._batch_delete)
        layout.addWidget(delete_button)
        return bar

    # ================================================================ 列表渲染
    def _current_query(self) -> TaskQuery:
        """当前视图对应的筛选条件。"""
        return TaskQuery(
            view=self._view_mode,
            project=self._active_project,
            category=self._active_category,
        )

    def refresh(self, animate: bool = True) -> None:
        """重建任务列表。

        Args:
            animate: 是否播放卡片淡入动画。
        """
        self._close_inline_editor(silent=True)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        tasks = self._backend.tasks.query(self._current_query())
        if not tasks:
            placeholder = QLabel("✓\n暂无待办\n享受清爽的一天")
            placeholder.setObjectName("emptyState")
            placeholder.setAlignment(Qt.AlignCenter)
            self._list_layout.insertWidget(0, placeholder)
        else:
            for index, task in enumerate(tasks):
                card = self._make_card(task)
                self._list_layout.insertWidget(index, card)
                if animate:
                    self._fade_in(card, index)

        self._update_stats()

    def _make_card(self, task: Task) -> TaskCard:
        """创建一张任务卡片并接好信号。"""
        card = TaskCard(
            task=task,
            theme=self.theme,
            select_mode=self._select_mode,
            selected=task.id in self._selected_ids,
        )
        card.toggled.connect(self._on_task_toggled)
        card.deleted.connect(self._on_task_deleted)
        card.edited.connect(self._on_task_edit)
        card.pin_toggled.connect(self._on_task_pin)
        card.sub_toggled.connect(self._on_subtask_toggled)
        card.select_toggled.connect(self._on_card_selected)
        card.strong_requested.connect(self._on_strong_remind)
        return card

    def _cards(self) -> list[TaskCard]:
        """列表中现存的卡片。"""
        cards = []
        for index in range(self._list_layout.count()):
            widget = self._list_layout.itemAt(index).widget()
            if isinstance(widget, TaskCard):
                cards.append(widget)
        return cards

    def _fade_in(self, widget: QWidget, index: int) -> None:
        """卡片依次淡入。"""
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        # 动画的父对象设成卡片而不是窗口：卡片销毁时动画会跟着走，
        # 挂在窗口下的话每刷新一次列表就多留一批，永远不会释放
        animation = QPropertyAnimation(effect, b"opacity", widget)
        animation.setDuration(260)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        # 结束后撤掉透明度效果：留着会和卡片自身的效果嵌套，
        # 而 Qt 渲染不了「效果里再套效果」的子树
        animation.finished.connect(lambda: self._clear_fade(widget))
        QTimer.singleShot(index * _CARD_FADE_DELAY_MS, animation.start)
        # 挂在控件上防止动画对象被 Python 侧回收
        widget._fade_animation = animation  # noqa: SLF001

    @staticmethod
    def _clear_fade(widget: QWidget) -> None:
        """淡入结束后撤掉临时的透明度效果。"""
        try:
            widget.setGraphicsEffect(None)
            widget._fade_animation = None  # noqa: SLF001
        except RuntimeError:
            pass  # 卡片已被删除（列表在动画期间刷新过）

    def _update_stats(self) -> None:
        """刷新统计文案与进度条。"""
        if self._view_mode == ViewMode.PROJECT and not self._active_project:
            # 一个项目都没有时不能去查空项目名：日常待办的 project 也是空串，
            # 会把它们全算进来，出现「列表空着、统计却显示 2/5」的自相矛盾
            self._stats_text.setText("项目 0/0")
            percent = 0
        elif self._view_mode == ViewMode.PROJECT:
            summary = self._backend.projects.summary(self._active_project)
            self._stats_text.setText(f"{self._active_project} {summary.done}/{summary.total}")
            percent = summary.percent
        else:
            today = self._backend.stats.today()
            text = f"今日 {today.done}/{today.total}"
            if today.urgent:
                text += f"   🔥紧急 {today.urgent}"
            self._stats_text.setText(text)
            percent = today.percent

        self._stats_percent.setText(f"{percent}%")
        target_width = int(self._progress_track.width() * percent / 100)
        # 复用同一个动画对象：每次都新建的话，动画挂在窗口下不会自动销毁，
        # 而这个方法在每次刷新、每次切换状态、每次缩放窗口时都会跑，
        # 常驻托盘一天下来能攒出成百上千个
        if self._progress_animation is None:
            self._progress_animation = QPropertyAnimation(self._progress_fill, b"geometry", self)
            self._progress_animation.setDuration(400)
            self._progress_animation.setEasingCurve(QEasingCurve.OutCubic)
        self._progress_animation.stop()
        self._progress_animation.setStartValue(self._progress_fill.geometry())
        self._progress_animation.setEndValue(QRect(0, 0, target_width, 8))
        self._progress_animation.start()

    def resizeEvent(self, event) -> None:  # noqa: N802
        """窗口尺寸变化后重算进度条宽度。"""
        super().resizeEvent(event)
        QTimer.singleShot(0, self._update_stats)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802
        """把分类栏上的竖直滚轮转成横向滚动。"""
        # 过滤的是 viewport 而不是 QScrollArea 本身：滚轮事件落在 viewport 上，
        # QAbstractScrollArea 会就地消化掉，根本传不到滚动区对象
        if watched is self._category_scroll.viewport() and event.type() == QEvent.Wheel:
            scroll_bar = self._category_scroll.horizontalScrollBar()
            delta = event.angleDelta().y() or event.angleDelta().x()
            scroll_bar.setValue(scroll_bar.value() - delta)
            return True
        return super().eventFilter(watched, event)

    # ================================================================ 视图切换
    def _switch_view(self, mode: str) -> None:
        """切换日常/项目视图。"""
        if mode == self._view_mode:
            return
        self._view_mode = mode
        if self._select_mode:
            self._toggle_select_mode()  # 切视图时退出多选，避免选中态错乱
        for key, button in self._tab_buttons.items():
            button.setChecked(key == mode)
        self._apply_view_mode()
        self.refresh()

    def _apply_view_mode(self) -> None:
        """按当前视图显示/隐藏对应工具栏。"""
        is_project = self._view_mode == ViewMode.PROJECT
        self._project_bar.setVisible(is_project)
        self._add_button.setVisible(not is_project)
        self._category_bar.setVisible(not is_project)
        self._multi_button.setVisible(not is_project)
        self._project_multi_button.setVisible(is_project)
        self._project_select_all_button.setVisible(is_project and self._select_mode)
        if is_project:
            self._refresh_project_picker()

    def _refresh_project_picker(self) -> None:
        """刷新项目下拉框。"""
        projects = self._backend.projects.names()
        self._project_picker.blockSignals(True)
        self._project_picker.clear()
        if projects:
            self._project_picker.addItems(projects)
            if self._active_project not in projects:
                self._active_project = projects[0]
            self._project_picker.setCurrentText(self._active_project)
        else:
            self._project_picker.addItem("（暂无项目，点击添加待办新建）")
            self._active_project = ""
        self._project_picker.blockSignals(False)

    def _on_project_picked(self, index: int) -> None:
        """切换当前项目。"""
        projects = self._backend.projects.names()
        if not 0 <= index < len(projects):
            return
        self._active_project = projects[index]
        if self._select_mode:
            self._selected_ids.clear()
            self._update_batch_label()
        self.refresh()

    def _set_category(self, name: str) -> None:
        """切换分类筛选。"""
        self._active_category = name
        for key, button in self._category_buttons.items():
            button.setChecked(key == name)
        self.refresh()

    def _create_category(self) -> None:
        """新建分类标签。"""
        dialog = QInputDialog(self)
        dialog.setWindowTitle("新建分类")
        dialog.setLabelText("分类名称")
        dialog.setOkButtonText("创建")
        dialog.setCancelButtonText("取消")
        dialog.setStyleSheet(dialog_qss(self.theme))
        if dialog.exec() != QInputDialog.Accepted:
            return

        name = dialog.textValue().strip()
        if not name:
            return
        if self._backend.config.add_category(name):
            self._backend.save_config()
            chip = self._make_category_chip(name)
            self._chips_layout.insertWidget(
                self._chips_layout.indexOf(self._new_category_button), chip
            )
        self._set_category(name)

    # ================================================================ 任务操作
    def _open_inline_editor(self) -> None:
        """在列表顶部插入内联新建行。"""
        if self._inline_editor is not None:
            self._inline_editor.focus_input()
            return

        editor = InlineTaskEditor(
            theme=self.theme,
            categories=self._backend.config.categories,
            default_category=self._active_category,
        )
        editor.submitted.connect(self._on_inline_submitted)
        editor.cancelled.connect(self._close_inline_editor)
        editor.due_requested.connect(self._on_inline_due_requested)
        self._inline_editor = editor
        self._list_layout.insertWidget(0, editor)
        editor.focus_input()

    def _on_inline_due_requested(self) -> None:
        """内联行请求打开日期弹窗。"""
        editor = self._inline_editor
        if editor is None:
            return
        picked = DuePickerDialog.pick(
            self,
            self.theme,
            Schedule(
                due=editor.due,
                recur=editor.recur,
                recur_end=editor.recur_end,
                remind=editor.remind,
            ),
        )
        if picked is None:
            return
        editor.set_schedule(picked.due, picked.recur, picked.recur_end, picked.remind)

    def _on_inline_submitted(self, draft: TaskDraft) -> None:
        """保存内联行内容。"""
        self._backend.tasks.create(draft)
        self._close_inline_editor(silent=True)
        self.refresh()

    def _close_inline_editor(self, silent: bool = False) -> None:
        """移除内联新建行。

        Args:
            silent: 为 True 时只清引用（列表即将整体重建，控件会被一起删掉）。
        """
        editor = self._inline_editor
        self._inline_editor = None
        if editor is None or silent:
            return
        editor.setParent(None)
        editor.deleteLater()

    def _on_task_toggled(self, task_id: str) -> None:
        """切换完成状态。"""
        task = self._backend.tasks.toggle_status(task_id)
        if task is None:
            return
        # 原地刷新这张卡片，避免整表重建导致闪烁
        for card in self._cards():
            if card.task.id == task_id:
                card.refresh_status()
                break
        self._update_stats()
        # 循环任务会生成新的一期，且完成项要沉底，延迟做一次静默重排
        QTimer.singleShot(_REORDER_DELAY_MS, lambda: self.refresh(animate=False))

    def _on_task_deleted(self, task_id: str) -> None:
        """删除待办，并让下方卡片平滑上移。"""
        if not self._backend.tasks.delete(task_id):
            return
        target = None
        for card in self._cards():
            if card.task.id == task_id:
                target = card
                break
        if target is None:
            self.refresh(animate=False)
            return
        self._collapse_and_remove(target)
        self._update_stats()

    def _collapse_and_remove(self, card: TaskCard) -> None:
        """卡片淡出 + 高度收缩后销毁。"""
        effect = QGraphicsOpacityEffect(card)
        card.setGraphicsEffect(effect)
        fade = QPropertyAnimation(effect, b"opacity", self)
        fade.setDuration(160)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)

        shrink = QPropertyAnimation(card, b"maximumHeight", self)
        shrink.setDuration(200)
        shrink.setStartValue(card.sizeHint().height())
        shrink.setEndValue(0)
        shrink.setEasingCurve(QEasingCurve.OutCubic)

        self._delete_animations.extend((fade, shrink))

        def finish() -> None:
            self._list_layout.removeWidget(card)
            card.deleteLater()
            for animation in (fade, shrink):
                if animation in self._delete_animations:
                    self._delete_animations.remove(animation)

        shrink.finished.connect(finish)
        fade.start()
        shrink.start()

    def _on_task_edit(self, task_id: str) -> None:
        """打开编辑弹窗。"""
        task = self._backend.tasks.get(task_id)
        if task is None:
            return
        result = TaskEditDialog.edit(
            self, self.theme, task, self._backend.config.categories
        )
        if result is None:
            return
        self._backend.tasks.update(
            task_id,
            text=result.text,
            category=result.category,
            priority=result.priority,
            due=result.schedule.due,
            recur=result.schedule.recur,
            recur_end=result.schedule.recur_end,
            remind=result.schedule.remind,
            remind_log=[],  # 排期变了，之前发过的提醒记录作废
            note=result.note,
            subtasks=result.subtasks,
        )
        self.refresh()

    def _on_task_pin(self, task_id: str) -> None:
        """切换置顶。"""
        self._backend.tasks.set_pinned(task_id)
        self.refresh(animate=False)

    def _on_subtask_toggled(self, task_id: str, index: int) -> None:
        """勾选小步骤。"""
        self._backend.tasks.toggle_subtask(task_id, index)
        self.refresh(animate=False)

    def _on_strong_remind(self, task_id: str) -> None:
        """打开强提醒设置。"""
        task = self._backend.tasks.get(task_id)
        if task is None:
            return
        dialog = StrongRemindDialog(self.theme, task, self)
        if dialog.exec() != StrongRemindDialog.Accepted:
            return
        self._backend.tasks.set_strong_remind(task_id, dialog.result_strong)
        self.refresh(animate=False)

    # ================================================================ 批量操作
    def _toggle_select_mode(self) -> None:
        """进入/退出多选模式。"""
        self._select_mode = not self._select_mode
        if not self._select_mode:
            self._selected_ids.clear()

        is_project = self._view_mode == ViewMode.PROJECT
        self._batch_bar.setVisible(self._select_mode)
        self._select_all_button.setVisible(self._select_mode and not is_project)
        self._project_select_all_button.setVisible(self._select_mode and is_project)
        self._multi_button.setText("✕" if self._select_mode else "☑")
        self._project_multi_button.setText("取消" if self._select_mode else "多选")
        self._batch_category_button.setVisible(not is_project)
        self._update_batch_label()

        # 原地切换每张卡片的模式，避免重建整表导致闪烁
        for card in self._cards():
            card.set_select_mode(
                self._select_mode, selected=card.task.id in self._selected_ids
            )

    def _on_card_selected(self, task_id: str, selected: bool) -> None:
        """记录勾选。"""
        if selected:
            self._selected_ids.add(task_id)
        else:
            self._selected_ids.discard(task_id)
        self._update_batch_label()

    def _update_batch_label(self) -> None:
        """更新「已选 N」。"""
        self._batch_label.setText(f"已选 {len(self._selected_ids)}")

    def _select_all_visible(self) -> None:
        """全选/取消全选当前可见待办。"""
        visible = self._backend.tasks.visible_ids(self._current_query())
        if self._selected_ids.issuperset(visible):
            self._selected_ids.clear()
        else:
            self._selected_ids.update(visible)
        self._update_batch_label()
        for card in self._cards():
            card.set_selected(card.task.id in self._selected_ids)

    def _batch_mark_done(self) -> None:
        """批量标记完成。"""
        if not self._selected_ids:
            self._show_toast("请先选择待办")
            return
        count = self._backend.tasks.set_status_many(self._selected_ids, TaskStatus.DONE)
        self._selected_ids.clear()
        self._update_batch_label()
        self.refresh()
        self._show_toast(f"已完成 {count} 条 🎉")

    def _batch_delete(self) -> None:
        """批量删除。"""
        if not self._selected_ids:
            self._show_toast("请先选择待办")
            return
        count = self._backend.tasks.delete_many(self._selected_ids)
        self._selected_ids.clear()
        self._update_batch_label()
        self.refresh()
        self._show_toast(f"已删除 {count} 条")

    def _batch_change_category(self) -> None:
        """批量改分类。"""
        if not self._selected_ids:
            self._show_toast("请先选择待办")
            return
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss(self.theme))
        menu.addAction("改为分类").setEnabled(False)
        menu.addSeparator()
        for name in self._backend.config.categories:
            action = menu.addAction(name)
            action.triggered.connect(
                lambda _=False, target=name: self._apply_batch_category(target)
            )
        menu.exec(
            self._batch_category_button.mapToGlobal(
                self._batch_category_button.rect().bottomLeft()
            )
        )

    def _apply_batch_category(self, name: str) -> None:
        """执行批量改分类。"""
        count = self._backend.tasks.set_category_many(self._selected_ids, name)
        self._selected_ids.clear()
        self._update_batch_label()
        self.refresh()
        self._show_toast(f"已把 {count} 条改为「{name}」")

    # ==================================================================== 项目
    def _open_batch_add(self) -> None:
        """打开项目待办的添加弹窗。"""
        dialog = BatchAddDialog(
            theme=self.theme,
            categories=self._backend.config.categories,
            existing_projects=self._backend.projects.names(),
            active_project=self._active_project,
            memory=self._add_form_memory,
            parent=self,
        )
        if dialog.exec() != BatchAddDialog.Accepted:
            return

        result = dialog.collect()
        if not result.project:
            self._show_toast("请填写或选择项目名称")
            return
        if not result.drafts:
            self._show_toast("没有可添加的内容")
            return

        skip_duplicates = True
        existing = self._backend.tasks.texts_of_project(result.project)
        duplicates = [draft for draft in result.drafts if draft.text.strip() in existing]
        if duplicates:
            choice = DuplicateChoice.ask(self, self.theme, len(duplicates))
            if choice == DuplicateChoice.CANCEL:
                return
            skip_duplicates = choice == DuplicateChoice.SKIP

        outcome = self._backend.tasks.create_many(
            result.drafts, skip_duplicates=skip_duplicates
        )
        if outcome.created_count == 0:
            self._show_toast("没有新增内容")
            return

        self._add_form_memory = dialog.memory
        self._active_project = result.project
        self._view_mode = ViewMode.PROJECT
        for key, button in self._tab_buttons.items():
            button.setChecked(key == ViewMode.PROJECT)
        self._apply_view_mode()
        self.refresh()

        message = f"已添加 {outcome.created_count} 条到「{result.project}」"
        if outcome.skipped:
            message += f"，跳过 {outcome.skipped} 条重复"
        self._show_toast(message)

    def _open_project_manager(self) -> None:
        """打开项目管理弹窗。"""
        dialog = ProjectManageDialog(self.theme, self._backend.projects, self)
        dialog.exec()
        if not dialog.changed:
            return
        renamed = dialog.renamed
        if self._active_project in renamed:
            self._active_project = renamed[self._active_project]
        if self._active_project in dialog.deleted:
            self._active_project = ""
        self._refresh_project_picker()
        self.refresh()

    # ==================================================================== 导出
    def _export_project(self) -> None:
        """导出当前项目的完成情况。"""
        if self._view_mode != ViewMode.PROJECT or not self._active_project:
            self._show_toast("请先选择一个项目")
            return
        tasks = self._backend.projects.tasks_of(self._active_project)
        if not tasks:
            self._show_toast("该项目暂无待办")
            return

        summary = self._backend.projects.summary(self._active_project)
        target = self._ask_save_path(f"{self._active_project}_完成情况.csv", "导出项目完成情况")
        if target is None:
            return
        self._write_export(
            target,
            tasks,
            header_lines=[
                f"项目：{self._active_project}",
                f"完成情况：{summary.done}/{summary.total}",
            ],
        )

    def _export_daily(self) -> None:
        """按日期区间与完成状态导出日常待办。"""
        options = ExportOptionsDialog.ask(self, self.theme)
        if options is None:
            return

        daily = [task for task in self._backend.tasks.tasks if task.is_daily]
        picked = self._backend.exporter.filter_tasks(
            daily, date_range=options.date_range, status=options.status
        )
        if not picked:
            self._show_toast("没有符合条件的待办")
            return

        target = self._ask_save_path("待办导出.csv", "导出待办")
        if target is None:
            return
        self._write_export(
            target,
            picked,
            header_lines=[
                f"导出范围：{options.date_range.label}",
                f"完成状态：{options.status}",
                f"共 {len(picked)} 条",
            ],
        )

    def _ask_save_path(self, default_name: str, title: str) -> Optional[Path]:
        """弹出保存对话框。"""
        chosen, _ = QFileDialog.getSaveFileName(self, title, default_name, _EXPORT_FILTER)
        return Path(chosen) if chosen else None

    def _write_export(
        self,
        target: Path,
        tasks: list[Task],
        header_lines: list[str],
    ) -> None:
        """写导出文件并提示结果。"""
        try:
            count = self._backend.exporter.export(target, tasks, header_lines=header_lines)
        except ExportError as exc:
            self._show_toast(f"导出失败：{exc}")
            return
        self._show_toast(f"已导出 {count} 条：{target.name}")

    # ==================================================================== 主题
    def _show_theme_menu(self) -> None:
        """主题快捷菜单 + 主题市场入口。"""
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss(self.theme))
        menu.addAction("选择主题").setEnabled(False)
        menu.addSeparator()
        for name in self._themes.showcase_names()[:THEME_SHOWCASE_LIMIT]:
            selected = name == self._themes.current_name
            action = menu.addAction(("● " if selected else "○ ") + name)
            action.setCheckable(True)
            action.setChecked(selected)
            action.triggered.connect(
                lambda _=False, target=name: self._themes.apply(target)
            )
        menu.addSeparator()
        market = menu.addAction("🎨  主题商店与 DIY…")
        market.triggered.connect(self._open_theme_market)
        menu.addSeparator()
        menu.addAction("背景图片").setEnabled(False)
        upload = menu.addAction("上传背景图片…")
        upload.triggered.connect(self._pick_background_image)
        if self._themes.background_image:
            clear = menu.addAction("清除背景图片")
            clear.triggered.connect(self._themes.clear_background_image)
        menu.exec(self._theme_button.mapToGlobal(self._theme_button.rect().bottomLeft()))

    def _open_theme_market(self) -> None:
        """打开主题市场。

        悬浮球是置顶窗口，会盖住模态弹窗（正好压在按钮上时点不动），
        因此打开期间先把它藏起来，关闭后恢复。
        """
        ball_visible = self._floating_ball is not None and self._floating_ball.isVisible()
        if ball_visible:
            self._floating_ball.hide()
        try:
            ThemeMarketDialog(
                themes=self._themes,
                pick_background=self._pick_background_image,
                clear_background=self._themes.clear_background_image,
                parent=self,
            ).exec()
        finally:
            if ball_visible and self._floating_ball is not None:
                self._floating_ball.show()
                bring_to_front_quietly(self._floating_ball)

    def _pick_background_image(self) -> None:
        """选择窗口背景图。"""
        chosen, _ = QFileDialog.getOpenFileName(self, "选择背景图片", "", _IMAGE_FILTER)
        if not chosen:
            return
        self._themes.set_background_image(chosen)

    def _load_background(self) -> None:
        """把配置里的背景图读成位图。"""
        path = self._themes.background_image
        if not path:
            self._background = None
            return
        if not Path(path).is_file():
            logger.warning("背景图不存在：%s", path)
            self._background = None
            return
        pixmap = QPixmap(path)
        self._background = None if pixmap.isNull() else pixmap

    def _on_theme_changed(self) -> None:
        """配色变化后刷新整窗样式。"""
        self._load_background()
        self.setStyleSheet(main_window_qss(self.theme))
        for card in self._cards():
            card.apply_theme(self.theme)
        if self._inline_editor is not None:
            self._inline_editor.setStyleSheet(inline_editor_qss(self.theme))
        self.update()

    def _reroll_cheer(self, event=None) -> None:
        """换一句鼓励语。"""
        del event  # 作为 mousePressEvent 使用时会带入事件对象
        self._cheer_label.setText(random_cheer(self._nickname))

    def _show_toast(self, message: str) -> None:
        """底部提示。"""
        self._toast.show(message, self.theme)

    # ================================================================ 多端同步
    def _show_sync_menu(self) -> None:
        """☁ 按钮的菜单：立即同步 / 设置。"""
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss(self.theme))
        menu.addAction(self._sync_status_text()).setEnabled(False)
        menu.addSeparator()
        sync_now = menu.addAction("↻  立即同步")
        sync_now.setEnabled(self._sync.is_configured and not self._sync.is_running)
        sync_now.triggered.connect(self.sync_now)
        settings = menu.addAction("⚙  同步设置…")
        settings.triggered.connect(self._open_sync_dialog)
        menu.exec(self._sync_button.mapToGlobal(self._sync_button.rect().bottomLeft()))

    def _open_sync_dialog(self) -> None:
        """打开同步设置。"""
        # 首次打开时先备好一个同步码，用户不用自己想
        self._backend.ensure_sync_code()

        result = SyncDialog.edit(self, self.theme, self._backend.config.sync)
        if result is None:
            return

        self._backend.update_sync_settings(result.settings)
        self._sync.apply_settings()
        self._refresh_sync_button()

        if not result.settings.enabled:
            self._show_toast("已关闭多端同步")
            return
        if result.should_sync_now:
            self.sync_now()

    def _on_sync_state_changed(self, running: bool) -> None:
        """同步开始/结束时更新按钮图标。"""
        self._refresh_sync_button(busy=running)

    def _on_sync_finished(self, result: object) -> None:
        """一轮同步结束。"""
        self._refresh_sync_button()
        if not isinstance(result, SyncResult):
            return
        if result.changed:
            self.refresh(animate=False)
        # 只在失败或确有变化时打扰用户，定时同步的「已是最新」不弹提示
        if not result.ok or result.changed or result.pushed:
            self._show_toast(result.summary())

    def _refresh_sync_button(self, busy: bool = False) -> None:
        """更新 ☁ 按钮的图标与提示。"""
        self._sync_button.setText(_SYNC_BUSY_ICON if busy else _SYNC_IDLE_ICON)
        self._sync_button.setToolTip(self._sync_status_text())

    def _sync_status_text(self) -> str:
        """同步状态的一句话描述。"""
        settings = self._backend.config.sync
        if not settings.is_configured:
            return "多端同步未开启（点此设置）"
        if settings.last_error:
            return f"同步失败：{settings.last_error}"
        if not settings.last_sync_at:
            return "多端同步已开启，尚未同步"
        moment = datetime.datetime.fromtimestamp(settings.last_sync_at / 1000)
        return f"上次同步 {moment:%m-%d %H:%M}"

    # ==================================================================== 菜单
    def _show_main_menu(self) -> None:
        """⋮ 菜单：置顶、自启、快捷键、悬浮球、数据目录、退出等。"""
        config = self._backend.config
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss(self.theme))
        menu.addAction(f"🍉 {APP_NAME} v{APP_VERSION}").setEnabled(False)
        menu.addSeparator()
        menu.addAction(f"主题：{self._themes.current_name}（点🎨选择）").setEnabled(False)
        menu.addSeparator()

        topmost = menu.addAction("取消置顶" if config.topmost else "窗口置顶")
        topmost.triggered.connect(self._toggle_topmost)

        if is_autostart_supported():
            autostart = menu.addAction("关闭开机自启" if config.autostart else "开机自启")
            autostart.triggered.connect(self._toggle_autostart)

        hotkey_label = config.hotkey.label(mac_style=IS_MACOS)
        hotkey = menu.addAction(f"快捷键设置（当前 {hotkey_label}）")
        hotkey.triggered.connect(self._open_hotkey_dialog)
        menu.addSeparator()

        ball = menu.addAction(
            "收起悬浮西瓜" if self._floating_ball is not None else "🍉 悬浮桌面小西瓜"
        )
        ball.triggered.connect(self._toggle_floating_ball)
        menu.addSeparator()

        all_tasks = menu.addAction("📋 查看全部待办")
        all_tasks.triggered.connect(self._show_all_tasks)
        menu.addSeparator()

        open_folder = menu.addAction("📂 打开数据文件夹")
        open_folder.triggered.connect(self._open_data_folder)
        menu.addSeparator()

        clear_done = menu.addAction("清除已完成")
        clear_done.triggered.connect(self._clear_completed)
        menu.addSeparator()

        hide_action = menu.addAction("隐藏到后台")
        hide_action.triggered.connect(self.hide)
        quit_action = menu.addAction("彻底退出程序")
        quit_action.triggered.connect(self.quit_application)
        menu.exec(QCursor.pos())

    def _show_all_tasks(self) -> None:
        """打开全部待办总览（只读）。"""
        AllTasksDialog.show_tasks(self, self.theme, self._backend.tasks.tasks)

    def _clear_completed(self) -> None:
        """清除已完成待办。"""
        count = self._backend.tasks.clear_completed()
        self.refresh()
        self._show_toast(f"已清除 {count} 条已完成" if count else "没有已完成的待办")

    def _toggle_topmost(self) -> None:
        """切换窗口置顶。"""
        config = self._backend.config
        config.topmost = not config.topmost
        self.setWindowFlags(float_window_flags(topmost=config.topmost))
        apply_no_steal_focus(self, accept_focus=True)
        self.show()
        self._save_config()

    def _toggle_autostart(self) -> None:
        """切换开机自启。"""
        enable = not self._backend.config.autostart
        if self._backend.apply_autostart(enable):
            self._show_toast("已设置开机自启" if enable else "已关闭开机自启")
        else:
            self._show_toast("设置开机自启失败")

    def _open_hotkey_dialog(self) -> None:
        """修改全局快捷键。"""
        picked = HotkeyDialog.ask(self, self.theme, self._backend.config.hotkey)
        if picked is None:
            return
        self._backend.config.hotkey = picked
        self._save_config()
        if not self.register_hotkey() and self._hotkey.is_supported:
            QMessageBox.warning(
                self,
                "快捷键注册失败",
                "该快捷键可能已被其他应用占用，请换一个组合后重试。",
            )

    def _open_data_folder(self) -> None:
        """在文件管理器里打开数据目录。"""
        folder = self._backend.data_dir
        if not folder.is_dir():
            self._show_toast("数据文件夹不存在")
            return
        if IS_WINDOWS:
            command = ["explorer", str(folder)]
        elif IS_MACOS:
            command = ["open", str(folder)]
        else:
            command = ["xdg-open", str(folder)]
        try:
            subprocess.run(command, check=False)
        except OSError as exc:
            logger.error("打开数据文件夹失败：%s", exc)
            self._show_toast("打开数据文件夹失败")

    # ================================================================ 悬浮小球
    def _toggle_floating_ball(self) -> None:
        """开关悬浮小西瓜。"""
        if self._floating_ball is None:
            self.show_floating_ball()
        else:
            self.hide_floating_ball()
        self._backend.config.floating_ball = self._floating_ball is not None
        self._save_config()

    def show_floating_ball(self) -> None:
        """显示悬浮小西瓜。"""
        if self._floating_ball is None:
            self._floating_ball = FloatingBall(self._backend, self._themes, self)
        self._floating_ball.show()
        # 延迟一帧再置顶，确保主窗口 show 之后小西瓜仍在最前
        QTimer.singleShot(0, lambda: bring_to_front_quietly(self._floating_ball))

    def hide_floating_ball(self) -> None:
        """收起悬浮小西瓜。"""
        if self._floating_ball is None:
            return
        self._floating_ball.close()
        self._floating_ball = None

    # ==================================================================== 提醒
    def _check_date_rollover(self) -> None:
        """日期翻篇时重建列表，让「今天/明天/N 天后」等相对标签跟上真实日期。

        用「记录上次看到的日期，和现在比对」的方式，既能覆盖过了午夜的正常翻篇，
        也能覆盖电脑休眠好几天后唤醒、日期一次跳过多天的情况。
        """
        today = datetime.date.today()
        if today != self._last_seen_date:
            self._last_seen_date = today
            self.refresh(animate=False)

    def _check_reminders(self) -> None:
        """定时检查提醒并弹窗。"""
        for event in self._backend.reminders.collect():
            self._notify(event)

    def _notify(self, event: ReminderEvent) -> None:
        """弹出一条提醒。

        强提醒不阻塞操作（自动关闭），普通提醒模态等待用户确认。
        强提醒若未勾选「悬浮小西瓜浮窗提醒/桌面全局弹出卡片」，则只走悬浮球
        气泡，不弹桌面提醒卡片。
        """
        if event.float_window and self._floating_ball is not None:
            self._floating_ball.force_bubble(f"记得{event.task.text}哦～")

        if event.is_strong and not event.float_window:
            return

        popup = ReminderPopup(
            theme=self.theme,
            task_text=event.task.text or "未命名待办",
            phrase=event.phrase,
            due=event.task.due,
            urgent=event.urgent,
            parent=self,
        )
        if event.is_strong:
            popup.show()
            QTimer.singleShot(_STRONG_POPUP_MS, popup.close)
            return
        popup.exec_modal()

    # ==================================================================== 托盘
    def _setup_tray(self) -> None:
        """在系统托盘放一个图标，让用户知道程序在后台运行。"""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.info("系统托盘不可用，跳过托盘图标")
            return

        icon = app_icon()
        if icon.isNull():
            icon = QApplication.windowIcon()
        self._tray = QSystemTrayIcon(icon, self)
        self._tray.setToolTip(f"{APP_NAME} 正在运行")

        menu = QMenu()
        show_action = QAction("显示 / 隐藏窗口", self)
        show_action.triggered.connect(self._toggle_window_from_tray)
        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self.quit_application)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()
        self._show_tray_tip_once()

    def _show_tray_tip_once(self) -> None:
        """首次运行提示托盘位置（不同系统位置不同）。"""
        config = self._backend.config
        if config.tray_tip_shown or self._tray is None:
            return
        if IS_MACOS:
            where = "屏幕右上角菜单栏"
        elif IS_LINUX:
            where = "系统托盘"
        else:
            where = "屏幕右下角托盘"
        self._tray.showMessage(
            f"{APP_NAME} 已启动",
            f"窗口在桌面上；关闭窗口后可在{where}的小西瓜里重新打开。",
            QSystemTrayIcon.Information,
            5000,
        )
        config.tray_tip_shown = True
        self._save_config()

    def _on_tray_activated(self, reason) -> None:
        """单击或双击托盘图标都唤起窗口。"""
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.summon_to_front()

    def _toggle_window_from_tray(self) -> None:
        """托盘菜单里的显示/隐藏。"""
        if self.isVisible():
            self.hide()
        else:
            self.summon_to_front()

    # ============================================================== 折叠与拖拽
    def _restore_geometry(self) -> None:
        """恢复窗口位置，并把越界坐标夹回可见区域。

        拔掉副屏或改分辨率后，上次保存的坐标可能落在所有屏幕之外，
        窗口就会「打开了但看不见」。
        """
        geometry = self._backend.config.geometry
        x, y = geometry.x, geometry.y
        width = max(geometry.width, _MIN_WIDTH)
        height = max(self._expanded_height, _MIN_EXPANDED_HEIGHT)

        # 先按窗口中心找它当前所在屏；找不到（落在所有屏幕之外）再退回主屏。
        center = QPoint(int(x + width / 2), int(y + height / 2))
        screen = QApplication.screenAt(center) or QApplication.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            width = min(width, available.width())
            height = min(height, available.height())
            x = min(max(x, available.left()), available.right() - width)
            y = min(max(y, available.top()), available.bottom() - height)

        self._expanded_height = height
        self.setGeometry(x, y, width, height)

    def _apply_collapsed(self) -> None:
        """应用折叠/展开状态（已废弃，保持展开）。"""
        self._set_body_visible(True)
        layout = self.layout()
        layout.setContentsMargins(14, 12, 14, 14)
        self.setMaximumHeight(_MAX_HEIGHT)
        self.setMinimumHeight(_MIN_EXPANDED_HEIGHT)
        self.resize(self.width(), self._expanded_height)

    def _toggle_collapse(self) -> None:
        """折叠功能已废弃，改为隐藏窗口。"""
        self.hide()

    def _set_body_visible(self, visible: bool) -> None:
        """折叠时只留标题栏与折叠/关闭按钮。"""
        is_project = self._view_mode == ViewMode.PROJECT
        self._stats_box.setVisible(visible)
        self._scroll.setVisible(visible)
        self._add_button.setVisible(visible and not is_project)
        self._project_bar.setVisible(visible and is_project)
        self._category_bar.setVisible(visible and not is_project)
        self._multi_button.setVisible(visible and not is_project)
        self._project_multi_button.setVisible(visible and is_project)
        self._select_all_button.setVisible(
            visible and self._select_mode and not is_project
        )
        self._project_select_all_button.setVisible(
            visible and self._select_mode and is_project
        )
        self._batch_bar.setVisible(visible and self._select_mode)
        self._cheer_label.setVisible(visible)
        self._sync_button.setVisible(visible)
        self._theme_button.setVisible(visible)
        self._menu_button.setVisible(visible)

    def _edge_at(self, position) -> str:
        """判断鼠标处于哪条边缘，返回如 ``topleft`` 的组合。"""
        if self._collapsed:
            return ""  # 折叠态不允许拉伸
        rect = self.rect()
        edges = ""
        if position.y() <= _RESIZE_MARGIN:
            edges += "top"
        elif position.y() >= rect.height() - _RESIZE_MARGIN:
            edges += "bottom"
        if position.x() <= _RESIZE_MARGIN:
            edges += "left"
        elif position.x() >= rect.width() - _RESIZE_MARGIN:
            edges += "right"
        return edges

    @staticmethod
    def _cursor_for_edge(edges: str):
        """边缘对应的光标形状。"""
        if edges in ("left", "right"):
            return Qt.SizeHorCursor
        if edges in ("top", "bottom"):
            return Qt.SizeVerCursor
        if edges in ("topleft", "bottomright"):
            return Qt.SizeFDiagCursor
        if edges in ("topright", "bottomleft"):
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def mousePressEvent(self, event) -> None:  # noqa: N802
        """按住边缘拉伸，按住空白处拖动窗口。"""
        if event.button() != Qt.LeftButton:
            return
        edges = self._edge_at(event.position().toPoint())
        if edges:
            self._resizing = True
            self._resize_edges = edges
            self._resize_start_geometry = self.geometry()
            self._resize_start_pos = event.globalPosition().toPoint()
        else:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
        event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """拉伸 / 拖动 / 更新光标。"""
        pressed = bool(event.buttons() & Qt.LeftButton)
        if self._resizing and pressed:
            self._resize_to(event.globalPosition().toPoint())
            event.accept()
            return
        if self._drag_offset is not None and pressed:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()
            return
        self.setCursor(self._cursor_for_edge(self._edge_at(event.position().toPoint())))

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """结束拖动/拉伸并记住尺寸。"""
        if self._resizing:
            self._resizing = False
            self._resize_edges = ""
            if not self._collapsed:
                self._expanded_height = self.height()
        self._drag_offset = None
        self.setCursor(Qt.ArrowCursor)
        self._save_config()

    def _resize_to(self, global_position) -> None:
        """按命中的边缘调整窗口几何。"""
        if self._resize_start_geometry is None or self._resize_start_pos is None:
            return
        delta = global_position - self._resize_start_pos
        geometry = QRect(self._resize_start_geometry)
        min_width = self.minimumWidth() or _MIN_WIDTH
        min_height = self.minimumHeight() or _MIN_EXPANDED_HEIGHT

        if "left" in self._resize_edges:
            new_left = geometry.left() + delta.x()
            if geometry.right() - new_left + 1 < min_width:
                new_left = geometry.right() - min_width + 1
            geometry.setLeft(new_left)
        if "right" in self._resize_edges:
            new_right = geometry.right() + delta.x()
            if new_right - geometry.left() + 1 < min_width:
                new_right = geometry.left() + min_width - 1
            geometry.setRight(new_right)
        if "top" in self._resize_edges:
            new_top = geometry.top() + delta.y()
            if geometry.bottom() - new_top + 1 < min_height:
                new_top = geometry.bottom() - min_height + 1
            geometry.setTop(new_top)
        if "bottom" in self._resize_edges:
            new_bottom = geometry.bottom() + delta.y()
            if new_bottom - geometry.top() + 1 < min_height:
                new_bottom = geometry.top() + min_height - 1
            geometry.setBottom(new_bottom)
        self.setGeometry(geometry)

    # ==================================================================== 配置
    def _save_config(self) -> None:
        """把窗口状态写回配置。"""
        geometry = self.geometry()
        self._expanded_height = geometry.height()

        config = self._backend.config
        config.geometry.x = geometry.x()
        config.geometry.y = geometry.y()
        config.geometry.width = geometry.width()
        config.geometry.height = self._expanded_height
        config.expanded_height = self._expanded_height
        config.collapsed = False
        config.theme = self._themes.current_name
        self._backend.save_config()
