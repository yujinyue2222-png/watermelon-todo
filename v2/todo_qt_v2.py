# -*- coding: utf-8 -*-
"""
桌面待办插件 · PySide6 高颜值版  (v2.0)
- 无边框 / 圆角 / 半透明毛玻璃质感
- 精致任务卡片 + 微交互动效
- 多套精品主题
- JSON 本地持久化 / 定时提醒 / 开机自启
- 全局快捷键可自定义

版本历史：
  v1.0  (2026-07-13) 首个正式版：分条小步骤、时间点截止、%APPDATA% 数据隔离、
                      单文件 exe 分发、可配置全局快捷键
  v2.0  (2026-07-21) 重大更新：智能统计面板、批量操作模式、个性化鼓励系统、
                      流式布局标签、跨平台统一代码、打开数据文件夹功能
  v2.3  (2026-07-27) 新增：启动自动检查更新，有新版本弹窗提示并可一键打开下载页
  v2.5  (2026-07-27) 优化：再次双击程序时自动把已运行窗口召回前台（不再静默无反应）
  v2.6  (2026-07-28) 优化：桌面悬浮小西瓜腿部黑色描边（白底可见、连接处自然）；
                      置顶待办卡片外观与普通待办一致，仅保留右上角钉子标记
  v2.7  (2026-07-28) 新增：悬浮小西瓜跑动速度随未完成待办数量变化（越多跑越快）；
                      修复 macOS 端悬浮西瓜未打包透明 SVG 导致的"没抠图"问题
  v2.10 (2026-07-29) 修复：macOS 端悬浮窗口鼠标滑过会抢走其他 app 键盘焦点的问题；
                      优化：首页"今日"统计只计入日常待办（排除项目待办）且仅算今天/过期/无日期的；
                      优化：项目待办 tab 顶部统计改为显示该项目"完成/总计"
  v2.11 (2026-07-30) 新增：首页导出按钮（可按日期区间+完成状态筛选后导出）；
                      优化：编辑待办窗把循环/提醒折叠进"选截止日期"，按钮更少；
                      优化：备注加主题色高亮排版；右键菜单新增"编辑备注/展开小步骤"；
                      优化：项目页"批量导入"改为"添加待办"，支持批量粘贴或单个填写
  v2.12 (2026-07-30) 优化：批量添加改用"内容|优先级|日期|备注"竖线分列语法，
                      支持单条设优先级/日期(07-31/明天/周五等)、实时解析预览、
                      同项目同名待办自动去重、Tab切换焦点、精简弹窗标题
  v2.13 (2026-07-30) 优化：添加待办弹窗改 Tab 分页(批量/单个数据隔离不丢失)；
                      项目名改二选一(下拉选已有 / ➕新建才展开输入框)；
                      记忆上次分类/紧急度；重复检测升级为三选一弹窗(继续/跳过/取消)；
                      支持从 Excel 直接粘贴(Tab 分列自动映射)
                      修复：去掉导出/管理项目/编辑待办弹窗内与标题栏重复的大标题
"""

APP_VERSION = "3.7"
# 检查更新用：GitHub 仓库最新 Release 接口 + 下载页地址
UPDATE_API = "https://api.github.com/repos/yujinyue2222-png/watermelon-todo/releases/latest"
RELEASE_PAGE = "https://github.com/yujinyue2222-png/watermelon-todo/releases/latest"
import ctypes
import sys
import os
import json
import random
import getpass
import datetime
from pathlib import Path
# 平台判断：Windows 才使用 Win32 相关能力（ctypes / 全局热键 / 启动文件夹）
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
# 单实例锁服务（在 main() 中赋值；模块级预声明便于 closeEvent 安全引用）
_single_server = None
if IS_WIN:
    import ctypes.wintypes

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QFrame, QGraphicsDropShadowEffect,
    QComboBox as QtComboBox, QMenu, QSizePolicy, QGraphicsOpacityEffect,
    QLayout, QTextEdit, QFileDialog, QCalendarWidget, QStyle,
    QStyleOptionComboBox, QSystemTrayIcon, QDialog, QDialogButtonBox,
    QCheckBox, QSpinBox,
)
from PySide6.QtCore import (
    Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, QRect, QSize, Signal,
    QAbstractNativeEventFilter, QDate, QThread, QUrl,
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QBrush, QCursor, QIcon, QFontDatabase,
    QLinearGradient, QPaintEvent, QPen, QDesktopServices, QPixmap, QTransform,
)

# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _float_window_flags(topmost: bool = False):
    """桌面悬浮窗口的窗口标志。

    Windows/Linux 使用 Qt.Tool 以隐藏任务栏图标；
    macOS 上 Qt.Tool 会被映射成 NSPanel —— 鼠标滑过窗口即自动成为
    key window，抢走其他应用正在输入的键盘焦点，因此 macOS 改用
    普通 Qt.Window（NSWindow），配合 _apply_no_steal_focus 阻止抢焦点。
    """
    flags = Qt.FramelessWindowHint
    flags |= Qt.Window if IS_MAC else Qt.Tool
    if topmost:
        flags |= Qt.WindowStaysOnTopHint
    return flags


def _apply_no_steal_focus(widget, accept_focus: bool = True):
    """让悬浮窗口显示时不主动激活、鼠标滑过不抢键盘焦点（主要针对 macOS）。

    - WA_ShowWithoutActivating：show() 时不把窗口设为激活窗口；
    - WA_MacAlwaysShowToolWindow：macOS 上即使非激活也保持可见；
    - accept_focus=False 时进一步禁止窗口接收键盘焦点（用于纯展示/点击的
      悬浮小西瓜；主面板与输入弹窗需要输入，保持 True）。
    """
    try:
        widget.setAttribute(Qt.WA_ShowWithoutActivating, True)
        if IS_MAC:
            try:
                widget.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
            except Exception:
                pass
        if not accept_focus:
            widget.setFocusPolicy(Qt.NoFocus)
    except Exception:
        pass


def _mac_bring_to_front(widget):
    """macOS：把窗口提到最前但**绝不**激活本 App（不抢其它 App 焦点）。

    用 NSWindow 的 orderFrontRegardless —— 只调整窗口层级，不会让本 App
    成为活跃 App，因此不会抢走微信等前台 App 的键盘/输入法焦点。用于让悬浮
    小西瓜浮在主窗口之上（否则两个置顶窗口中，后激活的主窗口会盖住它）。
    """
    if not IS_MAC:
        return
    try:
        from ctypes.util import find_library
        objc = ctypes.cdll.LoadLibrary(find_library("objc") or "/usr/lib/libobjc.dylib")
        sr = objc.sel_registerName
        sr.restype = ctypes.c_void_p
        sr.argtypes = [ctypes.c_char_p]
        msg = objc.objc_msgSend
        msg.restype = ctypes.c_void_p
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        view = ctypes.c_void_p(int(widget.winId()))
        window = ctypes.c_void_p(msg(view, sr(b"window")))
        if window:
            msg(window, sr(b"orderFrontRegardless"))
    except Exception:
        pass


def _mac_make_window_truly_transparent(widget):
    """macOS：关闭悬浮窗阴影并把背景设为完全透明。

    frameless + WA_TranslucentBackground 的窗口在 macOS 上仍可能被系统加上一层
    浅色阴影/半透明背景，在浅色桌面下显出“白色重影”。关闭阴影、背景设 clearColor
    即可消除。仅做属性设置（不改变窗口类型），风险极低；全程 try/except 兜底。
    """
    if not IS_MAC:
        return
    try:
        from ctypes.util import find_library
        objc = ctypes.cdll.LoadLibrary(find_library("objc") or "/usr/lib/libobjc.dylib")
        sr = objc.sel_registerName
        sr.restype = ctypes.c_void_p
        sr.argtypes = [ctypes.c_char_p]
        msg = objc.objc_msgSend
        msg.restype = ctypes.c_void_p
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        view = ctypes.c_void_p(int(widget.winId()))
        window = ctypes.c_void_p(msg(view, sr(b"window")))
        if not window:
            return
        # 1) 关闭窗口阴影（drop shadow），浅色桌面下这层光晕最像“白色重影”
        msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        msg(window, sr(b"setHasShadow:"), ctypes.c_int(0))
        # 2) 背景设为完全透明 clearColor
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        NSColor = objc.objc_getClass(b"NSColor")
        if NSColor:
            msg.restype = ctypes.c_void_p
            msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
            clear = ctypes.c_void_p(msg(NSColor, sr(b"clearColor")))
            if clear:
                msg.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
                msg(window, sr(b"setBackgroundColor:"), clear)
    except Exception:
        pass


def _resource_path(name: str) -> Path:
    """返回源码运行或 PyInstaller 打包后的资源路径。"""
    bundle_dir = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    return bundle_dir / name


# 数据/配置统一存到用户目录 %APPDATA%\DesktopTodo\ ，与程序文件分离
# 这样打包分发时不会带上个人待办数据
def _user_data_dir():
    # 跨平台数据目录：
    #   Windows → %APPDATA%\DesktopTodo
    #   macOS   → ~/Library/Application Support/DesktopTodo
    #   Linux   → ~/.local/share/DesktopTodo（或 $XDG_DATA_HOME）
    if IS_WIN:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif IS_MAC:
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share")
    d = os.path.join(base, "DesktopTodo")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        d = BASE_DIR  # 兜底：无法创建时退回程序目录
    return d

USER_DIR = _user_data_dir()
DATA_FILE = os.path.join(USER_DIR, "todo_data.json")
CONFIG_FILE = os.path.join(USER_DIR, "todo_config.json")

# 首次运行迁移：若用户目录还没有数据，但程序目录旁有旧数据，则搬过来一次
def _migrate_old_data():
    import shutil
    for name in ("todo_data.json", "todo_config.json"):
        old = os.path.join(BASE_DIR, name)
        new = os.path.join(USER_DIR, name)
        if os.path.exists(old) and not os.path.exists(new) and old != new:
            try:
                shutil.copy2(old, new)
            except Exception:
                pass

_migrate_old_data()

CATEGORIES = ["工作", "生活", "学习", "其他"]
NOTE_PREVIEW_LIMIT = 32

# ----------------------------------------------------------------------------
# 主题系统：每套主题定义完整配色
# ----------------------------------------------------------------------------
THEMES = {
    "极光白": {
        "bg": "#FBFCFEE6", "panel": "#FFFFFF", "card": "#F5F7FB",
        "card_hover": "#EEF2F9", "text": "#1F2733", "sub": "#8A94A6",
        "accent": "#4C6FFF", "accent2": "#6E8BFF", "border": "#E6EAF2",
        "shadow": "#20324D", "done": "#B4BCCB",
    },
    "奶油极光": {
        "bg": "#FFF9F4F2", "panel": "#FFFDF9", "card": "#FFFBF7",
        "card_hover": "#F8F1EC", "text": "#181716", "sub": "#77716C",
        "accent": "#6C5CE7", "accent2": "#8478EA", "border": "#EDE6DF",
        "shadow": "#53473D", "done": "#BDB6AF",
        "gradient": [
            (0.0, "#F8D6E5"),
            (0.38, "#FFF5E2"),
            (0.68, "#F5F6C9"),
            (1.0, "#C9F1EA"),
        ],
    },
    "曜石黑": {
        "bg": "#151A22F2", "panel": "#1C2129", "card": "#232A34",
        "card_hover": "#2A3340", "text": "#EAEEF5", "sub": "#8791A0",
        "accent": "#5B7FFF", "accent2": "#7C97FF", "border": "#2E3742",
        "shadow": "#000000", "done": "#5A6472",
    },
    "薄雾蓝": {
        "bg": "#E3EEFBE6", "panel": "#EDF4FE", "card": "#FFFFFF",
        "card_hover": "#E1ECFB", "text": "#1E3A5F", "sub": "#6E86A6",
        "accent": "#4A90E2", "accent2": "#78B4F0", "border": "#CFE0F5",
        "shadow": "#2C5A8F", "done": "#A7BCD6",
    },
    "抹茶绿": {
        "bg": "#F0F7F1E6", "panel": "#F9FCF9", "card": "#FFFFFF",
        "card_hover": "#EAF4EC", "text": "#233529", "sub": "#7A9083",
        "accent": "#2FA96B", "accent2": "#4FC186", "border": "#DBEBE0",
        "shadow": "#1C4A32", "done": "#AECBB7",
    },
    "落日橘": {
        "bg": "#FEF4EEE6", "panel": "#FFF9F5", "card": "#FFFFFF",
        "card_hover": "#FCEEE3", "text": "#3A2A22", "sub": "#A88E7F",
        "accent": "#F2751F", "accent2": "#FB9450", "border": "#F5E2D4",
        "shadow": "#6B3A18", "done": "#D9C2B3",
    },
    "暗夜紫": {
        "bg": "#1A1626F2", "panel": "#221D33", "card": "#2A2440",
        "card_hover": "#332C4D", "text": "#EEE9F7", "sub": "#9A90B4",
        "accent": "#9B6BFF", "accent2": "#B48CFF", "border": "#382F52",
        "shadow": "#000000", "done": "#6C6284",
    },
    "西瓜红": {
        "bg": "#FFF0F1E6", "panel": "#FFF6F6", "card": "#FFFFFF",
        "card_hover": "#FCE6E8", "text": "#3A1F24", "sub": "#B08890",
        "accent": "#F0405A", "accent2": "#FF6E82", "border": "#F6D9DD",
        "shadow": "#7A1F2C", "done": "#E0B7BD",
    },
    "樱花粉": {
        "bg": "#FDEFF5E6", "panel": "#FEF6FA", "card": "#FFFFFF",
        "card_hover": "#FBE6EF", "text": "#3E2733", "sub": "#B58AA0",
        "accent": "#F06AAE", "accent2": "#FB93C6", "border": "#F6DCE8",
        "shadow": "#7A2B57", "done": "#E4BCD2",
    },
    "海洋青": {
        "bg": "#E9F7F6E6", "panel": "#F2FBFA", "card": "#FFFFFF",
        "card_hover": "#DFF3F1", "text": "#173234", "sub": "#6E9896",
        "accent": "#0FB5AE", "accent2": "#3FD0C9", "border": "#CFEAE8",
        "shadow": "#0A4B47", "done": "#A9D3D0",
    },
    "深邃蓝": {
        "bg": "#0E1726F2", "panel": "#152033", "card": "#1B283E",
        "card_hover": "#233150", "text": "#E6EDF7", "sub": "#7E8DA6",
        "accent": "#3DA9FC", "accent2": "#6BC0FF", "border": "#27324A",
        "shadow": "#000000", "done": "#4A5A75",
    },
    "薄荷青": {
        "bg": "#E8F8F4E6", "panel": "#F2FBF8", "card": "#FFFFFF",
        "card_hover": "#DFF3EE", "text": "#1E3A33", "sub": "#6E9A8E",
        "accent": "#16BFA0", "accent2": "#3FD8BC", "border": "#CDEAE2",
        "shadow": "#0A4A3C", "done": "#A5D5CB",
    },
    "焦糖棕": {
        "bg": "#F7EFE6E6", "panel": "#FBF5EE", "card": "#FFFFFF",
        "card_hover": "#F2E6D8", "text": "#3A2A1E", "sub": "#9C8270",
        "accent": "#B07B4E", "accent2": "#D29B6B", "border": "#ECDDCD",
        "shadow": "#5A3A1E", "done": "#D2BCA4",
    },
    "玫瑰金": {
        "bg": "#FCEEEDE6", "panel": "#FEF5F4", "card": "#FFFFFF",
        "card_hover": "#FBE7E5", "text": "#3E2A2C", "sub": "#B08E92",
        "accent": "#E08A8E", "accent2": "#F0AEB1", "border": "#F4D9D8",
        "shadow": "#7A3A42", "done": "#E2BCBE",
    },
    "蜜桃汽水": {
        "bg": "#FFEEE7E6", "panel": "#FFF6F1", "card": "#FFFFFF",
        "card_hover": "#FFE7DE", "text": "#3D2A24", "sub": "#A07C70",
        "accent": "#FF7A59", "accent2": "#FFA07E", "border": "#F5DCD0",
        "shadow": "#7A3A22", "done": "#E0BFB5",
        "gradient": [(0.0, "#FFD9C2"), (0.38, "#FFB3C6"), (0.7, "#E2C2F5"), (1.0, "#BFE3FF")],
    },
    "晚霞": {
        "bg": "#FFF1E8E6", "panel": "#FFF7F2", "card": "#FFFFFF",
        "card_hover": "#FCE7DF", "text": "#3A2433", "sub": "#9E7892",
        "accent": "#F25C7A", "accent2": "#FF8AA5", "border": "#F5D8DE",
        "shadow": "#7A2A44", "done": "#E0BBC6",
        "gradient": [(0.0, "#FF9D8B"), (0.4, "#FF6A88"), (0.72, "#FF99AC"), (1.0, "#8E7AE6")],
    },
    "极光夜": {
        "bg": "#0B1220F2", "panel": "#101A2E", "card": "#172238",
        "card_hover": "#1F2C48", "text": "#E6EEF8", "sub": "#7E8DA6",
        "accent": "#3FE0C0", "accent2": "#6BE8D0", "border": "#243150",
        "shadow": "#000000", "done": "#4A5A75",
        "gradient": [(0.0, "#08182A"), (0.4, "#0E2A3C"), (0.72, "#1A2052"), (1.0, "#2C154A")],
    },
    "棉花糖": {
        "bg": "#FCF0F5E6", "panel": "#FEF6FA", "card": "#FFFFFF",
        "card_hover": "#FBE7EF", "text": "#3A2740", "sub": "#A988A0",
        "accent": "#C56AC0", "accent2": "#E094DC", "border": "#F3D9E8",
        "shadow": "#6A2A5C", "done": "#DDBED2",
        "gradient": [(0.0, "#FFD1E8"), (0.35, "#D7E4FF"), (0.7, "#D6F5E6"), (1.0, "#EADDFF")],
    },
    "莫兰迪晨雾": {
        "bg": "#EDEAE5E6", "panel": "#F4F1EC", "card": "#FFFFFF",
        "card_hover": "#EAE5DE", "text": "#3A352F", "sub": "#8C857B",
        "accent": "#B08968", "accent2": "#C9A384", "border": "#E0DAD0",
        "shadow": "#5A5048", "done": "#C2BAAF",
        "gradient": [(0.0, "#D8CFC2"), (0.5, "#C9B6AE"), (1.0, "#A8B5AE")],
    },
}
THEME_ORDER = list(THEMES.keys())
# 仅内置示例主题（不含运行时 DIY 追加的主题），用作“展示前 8 个例子”的基准
BUILTIN_THEME_ORDER = list(THEME_ORDER)

CAT_COLORS = {
    "工作": "#4C6FFF", "生活": "#2FA96B",
    "学习": "#F2751F", "其他": "#8A94A6",
}


def _qss_alpha(color, alpha):
    """将 #RRGGBB 转为 Qt 样式表使用的 #AARRGGBB。"""
    rgb = str(color).lstrip("#")[:6]
    return f"#{max(0, min(255, int(alpha))):02X}{rgb}"


class QComboBox(QtComboBox):
    """使用统一细线箭头的下拉框，避免各平台原生箭头风格不一致。"""

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        arrow_rect = self.style().subControlRect(
            QStyle.CC_ComboBox,
            option,
            QStyle.SC_ComboBoxArrow,
            self,
        )
        center = arrow_rect.center()
        color = self.palette().color(self.foregroundRole())
        if not self.isEnabled():
            color.setAlpha(90)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(color, 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.drawLine(center.x() - 4, center.y() - 2, center.x(), center.y() + 2)
        painter.drawLine(center.x(), center.y() + 2, center.x() + 4, center.y() - 2)


class _StyledCalendarWidget(QCalendarWidget):
    """跟随应用主题绘制带阴影的日期选中态。"""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        # 月份按钮默认带下拉箭头（˅），会让「七月」文字上下错落；
        # 设为纯文字样式并去掉箭头，让月/年文字水平居中不错位。
        try:
            from PySide6.QtWidgets import QToolButton
            for btn in self.findChildren(QToolButton):
                name = btn.objectName()
                if name in ("qt_calendar_monthbutton", "qt_calendar_yearbutton"):
                    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
                    btn.setPopupMode(QToolButton.InstantPopup)
                    btn.setArrowType(Qt.NoArrow)
        except Exception:
            pass

    def paintCell(self, painter: QPainter, rect: QRect, date: QDate) -> None:
        if date != self.selectedDate():
            super().paintCell(painter, rect, date)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        accent = QColor(self._theme["accent"])

        shadow = QColor(accent)
        shadow.setAlpha(105)
        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(rect.adjusted(2, 4, -2, -1), 9, 9)

        painter.setBrush(accent)
        painter.drawRoundedRect(rect.adjusted(3, 1, -3, -4), 8, 8)
        painter.setPen(QColor("#FFFFFF"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect.adjusted(3, 0, -3, -3), Qt.AlignCenter, str(date.day()))
        painter.restore()


# ----------------------------------------------------------------------------
# 昵称 & 随机鼓励语
# ----------------------------------------------------------------------------
def get_nickname():
    """从配置读昵称，否则取系统用户名"""
    try:
        name = getpass.getuser()
    except Exception:
        name = os.environ.get("USERNAME") or os.environ.get("USER") or "亲爱的"
    return name or "亲爱的"


CHEER_QUOTES = [
    "{name}，加油啦！✨",
    "{name}，今天也要元气满满哦~ 🌸",
    "{name}，一件一件来，你可以的！💪",
    "{name}，慢慢来，会更快 🍀",
    "{name}，完成的每一件都值得鼓励 🎉",
    "{name}，别忘了对自己好一点 ☕",
    "{name}，前进一小步也是胜利 🚀",
    "{name}，你比想象中更棒💖",
    "{name}，把大事拆小，就不难啦📌",
    "{name}，深呼吸，开始行动吧🌈",
    "{name}，今天的努力都算数⭐",
    "{name}，冲鸭，好运在路上🍭",
    "{name}，你已经很努力了，别太苛责自己🫶",
    "{name}，做完一件就奖励自己一下吧🍰",
    "{name}，星光不问赶路人，加油🌟",
    "{name}，先完成，再完美✍️",
    "{name}，休息也是效率的一部分😴",
    "{name}，你今天的样子超级可爱🐻",
    "{name}，再坚持一下下就好啦🐣",
    "{name}，把焦虑写进清单，它就变小了📝",
    "{name}，今天也是被期待的一天呀🌤️",
    "{name}，稳住，我们能赢🎮",
    "{name}，一步一步，风景都在路上🚶",
    "{name}，别急，好事正在发生🌷",
    "{name}，你值得所有的好运气🍀",
    "{name}，喝口水，继续发光吧💡",
    "{name}，完成度 > 完美度，先动起来⚡",
    "{name}，今天的你也在悄悄变强🌱",
    "{name}，累了就抱抱西瓜再出发🍉",
    "{name}，把注意力放在下一小步就好🎯",
    "{name}，你的坚持终会开花🌸",
]


def random_cheer(name):
    return random.choice(CHEER_QUOTES).format(name=name)





# ----------------------------------------------------------------------------
# 数据层
# ----------------------------------------------------------------------------
class Store:
    def __init__(self):
        self.tasks = []
        self.load()

    def load(self):
        if os.path.exists(DATA_FILE):
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    self.tasks = json.load(f)
            except Exception:
                self.tasks = []
        else:
            self.tasks = []
        # 旧数据迁移：老版本的“紧急”优先级 -> P1
        for t in self.tasks:
            p = t.get("priority")
            if p in PRIORITY_MIGRATE:
                t["priority"] = PRIORITY_MIGRATE[p]
            # 旧数据提醒字段迁移/补全
            rm = t.get("remind")
            if rm is None or rm == "":
                t["remind"] = "到期当天"
            elif rm in REMIND_MIGRATE:
                t["remind"] = REMIND_MIGRATE[rm]
            t.setdefault("remind_log", [])
            # 新增字段：备注、所属项目（空串表示日常待办）
            t.setdefault("note", "")
            t.setdefault("project", "")
            # 强提醒配置：与默认值合并，兼容老数据缺字段
            t["strong"] = {**_default_strong(), **(t.get("strong") or {})}

    def save(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, text, category="其他", due="", priority="普通",
            recur="不循环", recur_end="", remind="到期当天",
            note="", project=""):
        tid = str(int(datetime.datetime.now().timestamp() * 1000))
        self.tasks.append({
            "id": tid, "text": text, "status": "todo",
            "category": category, "due": due, "priority": priority,
            "recur": recur, "recur_end": recur_end, "subtasks": [],
            "remind": remind, "remind_log": [],
            "note": note, "project": project,
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "notified": False,
            "strong": _default_strong(),
        })
        self.save()
        return tid

    def add_batch(
        self,
        lines: list[str],
        project: str = "",
        category: str = "其他",
        priority: str = "普通",
    ) -> int:
        """批量导入待办，可用竖线或 Tab 分隔每条待办的备注。

        Args:
            lines: 多行文本拆出的待办，格式为 ``待办内容 | 备注``。
            project: 所属项目。
            category: 默认分类。
            priority: 默认优先级。

        Returns:
            成功新建的待办数量。
        """
        n = 0
        base_ts = int(datetime.datetime.now().timestamp() * 1000)
        now_iso = datetime.datetime.now().isoformat(timespec="seconds")
        # 已存在的（项目, 待办内容）集合，用于重复检测
        existing = {
            (t.get("project", ""), (t.get("text", "") or "").strip())
            for t in self.tasks
        }
        for i, raw in enumerate(lines):
            parsed = self._parse_batch_line(raw)
            if not parsed:
                continue
            text = parsed["text"]
            key = (project, text)
            if key in existing:
                continue  # 同项目内同名待办跳过
            existing.add(key)
            tid = str(base_ts + i)
            self.tasks.append({
                "id": tid, "text": text, "status": "todo",
                "category": category,
                "due": parsed["due"],
                "priority": parsed["priority"] or priority,
                "recur": "不循环", "recur_end": "", "subtasks": [],
                "remind": "到期当天", "remind_log": [],
                "note": parsed["note"], "project": project,
                "created": now_iso, "notified": False,
                "strong": _default_strong(),
            })
            n += 1
        if n:
            self.save()
        return n

    @staticmethod
    def _split_batch_note(text: str) -> tuple[str, str]:
        """拆分批量导入行中的待办内容与备注。"""
        for separator in ("\t", "｜", "|"):
            if separator in text:
                task_text, note = text.split(separator, 1)
                return task_text.strip(), note.strip()
        return text.strip(), ""

    @staticmethod
    def _strip_bullet(text):
        """剥离行首常见的列表符号：- * • ·  以及  1.  1、  (1)  等编号"""
        import re
        return re.sub(r"^\s*(?:[-*•·]|\(?\d+[\.\)、])\s*", "", text).strip()

    @staticmethod
    def _norm_batch_date(token: str) -> str:
        """把日期片段归一化成 YYYY-MM-DD；无法识别返回空串。

        支持：2026-07-31 / 07-31 / 07/31 / 明天 / 后天 / 今天 /
        本周五 / 周五 / 下周一 等。
        """
        import re
        s = (token or "").strip()
        if not s:
            return ""
        today = datetime.date.today()
        # 相对词
        rel = {"今天": 0, "今日": 0, "明天": 1, "明日": 1, "后天": 2, "大后天": 3}
        if s in rel:
            return (today + datetime.timedelta(days=rel[s])).isoformat()
        # 周几：周一~周日 / 星期x / 下周x
        wk = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5,
              "日": 6, "天": 6}
        m = re.match(r"^(下)?(?:周|星期|礼拜)([一二三四五六日天])$", s)
        if m:
            target = wk[m.group(2)]
            delta = (target - today.weekday()) % 7
            if m.group(1):  # 下周
                delta += 7
            elif delta == 0:  # 本周同一天且就是今天 -> 取今天
                delta = 0
            return (today + datetime.timedelta(days=delta)).isoformat()
        # 完整日期 YYYY-MM-DD 或 YYYY/MM/DD
        m = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$", s)
        if m:
            try:
                return datetime.date(
                    int(m.group(1)), int(m.group(2)), int(m.group(3))
                ).isoformat()
            except ValueError:
                return ""
        # 简写 MM-DD 或 MM/DD -> 补当前年份
        m = re.match(r"^(\d{1,2})[-/](\d{1,2})$", s)
        if m:
            try:
                return datetime.date(
                    today.year, int(m.group(1)), int(m.group(2))
                ).isoformat()
            except ValueError:
                return ""
        return ""

    @classmethod
    def _parse_batch_line(cls, raw: str):
        """解析批量粘贴的一行，返回 dict 或 None（空行）。

        竖线分列：内容 | 优先级 | 日期 | 备注
        - 第1列＝内容（必填）
        - 第2列＝智能识别：是优先级词则为优先级，否则视为备注
        - 第3列＝日期（可识别才生效，否则并入备注）
        - 第4列及之后＝备注（多列用空格拼回）

        兼容老习惯：``内容 | 备注`` 里第2列不是优先级词时仍当备注。
        """
        cleaned = (raw or "").strip()
        if not cleaned:
            return None
        cleaned = cls._strip_bullet(cleaned)
        if not cleaned:
            return None
        # 统一全角竖线/Tab 为半角竖线后分列
        norm = cleaned.replace("｜", "|").replace("\t", "|")
        parts = [p.strip() for p in norm.split("|")]
        text = parts[0].strip()
        if not text:
            return None
        priority = ""
        due = ""
        note = ""
        rest = parts[1:]
        # 第2列：优先级词判定
        if rest and rest[0] in PRIORITIES:
            priority = rest[0]
            rest = rest[1:]
        # 下一列：日期判定
        if rest:
            d = cls._norm_batch_date(rest[0])
            if d:
                due = d
                rest = rest[1:]
        # 剩余列拼成备注
        if rest:
            note = " ".join(p for p in rest if p).strip()
        return {"text": text, "priority": priority, "due": due, "note": note}

    def projects(self):
        """返回当前所有项目名（去重、按出现顺序）"""
        seen = []
        for t in self.tasks:
            p = t.get("project", "")
            if p and p not in seen:
                seen.append(p)
        return seen

    def project_stats(self, project):
        """某项目的 (总数, 完成数)"""
        items = [t for t in self.tasks if t.get("project", "") == project]
        total = len(items)
        done = sum(1 for t in items if t.get("status") == "done")
        return total, done

    def toggle_sub(self, tid, idx):
        """切换某任务下第 idx 个子任务的完成状态"""
        for t in self.tasks:
            if t["id"] == tid:
                subs = t.get("subtasks", [])
                if 0 <= idx < len(subs):
                    subs[idx]["done"] = not subs[idx].get("done", False)
                break
        self.save()

    def update(self, tid, **kw):
        for t in self.tasks:
            if t["id"] == tid:
                t.update(kw)
                break
        self.save()

    def delete(self, tid):
        self.tasks = [t for t in self.tasks if t["id"] != tid]
        self.save()

    def delete_project(self, project):
        """删除整个项目：移除该项目下所有待办"""
        if not project:
            return
        self.tasks = [t for t in self.tasks if t.get("project", "") != project]
        self.save()

    def rename_project(self, old, new):
        """重命名项目：把该项目下所有待办的 project 字段改名"""
        if not old or not new or old == new:
            return
        for t in self.tasks:
            if t.get("project", "") == old:
                t["project"] = new
        self.save()

    def toggle(self, tid):
        for t in self.tasks:
            if t["id"] == tid:
                was_done = t["status"] == "done"
                # 单击直接在 未完成 <-> 完成 间切换
                t["status"] = "todo" if was_done else "done"
                if t["status"] == "done" and not was_done:
                    self._spawn_next(t)
                break
        self.save()

    def _spawn_next(self, t):
        recur = t.get("recur", "不循环")
        if recur == "不循环" or recur not in RECUR_TYPES:
            return
        nxt = self._next_due(t.get("due", ""), recur)
        if not nxt:
            return
        # 超过结束日期则停止
        end = t.get("recur_end", "")
        if end:
            try:
                if nxt > datetime.datetime.strptime(end, "%Y-%m-%d").date():
                    return
            except Exception:
                pass
        # 避免重复生成同一期（保留原截止时间点）
        _, orig_tm = parse_due(t.get("due", ""))
        due_str = nxt.strftime("%Y-%m-%d")
        if orig_tm:
            due_str += orig_tm.strftime(" %H:%M")
        for x in self.tasks:
            if (x.get("text") == t.get("text") and x.get("due") == due_str
                    and x.get("recur") == recur and x["status"] != "done"):
                return
        self.add(t.get("text", ""), t.get("category", "其他"), due_str,
                 t.get("priority", "普通"), recur, end)

    @staticmethod
    def _next_due(due, recur):
        base = None
        if due:
            base, _ = parse_due(due)
        if base is None:
            base = datetime.date.today()
        if recur == "每日":
            return base + datetime.timedelta(days=1)
        if recur == "工作日":
            d = base + datetime.timedelta(days=1)
            while d.weekday() >= 5:  # 5=周六 6=周日
                d += datetime.timedelta(days=1)
            return d
        if recur == "每周":
            return base + datetime.timedelta(days=7)
        if recur == "每月":
            m = base.month + 1
            y = base.year + (m - 1) // 12
            m = (m - 1) % 12 + 1
            import calendar
            day = min(base.day, calendar.monthrange(y, m)[1])
            return datetime.date(y, m, day)
        if recur == "每年":
            try:
                return base.replace(year=base.year + 1)
            except ValueError:  # 2/29
                return base.replace(year=base.year + 1, day=28)
        return None

    def clear_done(self):
        self.tasks = [t for t in self.tasks if t["status"]!= "done"]
        self.save()

    def stats(self):
        """首页「今日」统计口径：只算【日常待办】(project 为空) 中，
        截止日期在今天(含已过期)或没填日期的任务；未来日期(明天及以后)
        不计入，项目待办的任务也不计入——日常/项目是两个独立 tab。"""
        today = datetime.date.today()

        def _is_today_daily(t):
            if t.get("project", ""):          # 属于项目待办，排除
                return False
            d, _ = parse_due(t.get("due", ""))
            # 没填/解析失败 视为当天任务；已填则须 <= 今天
            return d is None or d <= today

        today_tasks = [t for t in self.tasks if _is_today_daily(t)]
        total = len(today_tasks)
        done = sum(1 for t in today_tasks if t["status"] == "done")
        urgent = sum(1 for t in today_tasks
                     if t["status"] != "done"
                     and t.get("priority") in URGENT_PRIORITIES)
        return total, done, urgent


def load_config():
    default = {"theme": "极光白", "topmost": True,
               "geometry": [140, 120, 340, 500], "collapsed": False,
               "autostart": False, "categories": list(CATEGORIES),
               "floating_ball": True,
               "bubble_speak": True,
               "hotkey": {"ctrl": True, "alt": True, "shift": False, "key": "T"}}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            default.update(cfg)
        except Exception:
            pass
    return default


def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ----------------------------------------------------------------------------
# 辅助函数：截止时间解析（兼容纯日期与日期+时间点两种格式）
# ----------------------------------------------------------------------------
def parse_due(due):
    """把 due 字符串解析为 (date, time_or_None)。
    支持 "YYYY-MM-DD" 与 "YYYY-MM-DD HH:MM"。解析失败返回 (None, None)。"""
    if not due:
        return None, None
    due = due.strip()
    for fmt, has_t in (("%Y-%m-%d %H:%M", True), ("%Y-%m-%d", False)):
        try:
            dt = datetime.datetime.strptime(due, fmt)
            return dt.date(), (dt.time() if has_t else None)
        except Exception:
            continue
    return None, None


def due_datetime(due):
    """把 due 解析为 datetime（无时间点时按当天 23:59 计），失败返回 None。"""
    d, tm = parse_due(due)
    if d is None:
        return None
    if tm is None:
        return datetime.datetime.combine(d, datetime.time(23, 59))
    return datetime.datetime.combine(d, tm)


# ----------------------------------------------------------------------------
# 辅助函数：截止时间标签
# ----------------------------------------------------------------------------
def due_label(due):
    """返回 (文字, 是否紧急/过期)"""
    if not due:
        return "", False
    d, tm = parse_due(due)
    if d is None:
        return due, False
    hm = tm.strftime(" %H:%M") if tm else ""
    now = datetime.datetime.now()
    today = now.date()
    delta = (d - today).days
    if delta < 0:
        return f"已过期 {-delta} 天", True
    if delta == 0:
        # 当天：若有时间点且已过，显示已过期
        if tm and datetime.datetime.combine(d, tm) < now:
            return f"今天{hm} 已过", True
        return f"今天{hm}", True
    if delta == 1:
        return f"明天{hm}", True
    if delta <= 7:
        return f"{delta} 天后{hm}", False
    return d.strftime("%m-%d") + hm, False


def due_sort_key(due):
    """无截止时间视为「当天任务」（逻辑 due = 今天 23:59），
    而非排到最后。这样没填时间的默认当天，与填了远期日期的任务
    在同一优先级下按逻辑 due 早晚排序。"""
    dt = due_datetime(due)
    if dt is None:
        return datetime.datetime.combine(datetime.date.today(), datetime.time(23, 59))
    return dt


def set_autostart(enable):
    """开机自启（跨平台）"""
    if IS_WIN:
        return _set_autostart_win(enable)
    if IS_MAC:
        return _set_autostart_mac(enable)
    return False  # 其他平台暂不支持


def _set_autostart_win(enable):
    """Windows：通过启动文件夹快捷方式实现开机自启"""
    try:
        startup = os.path.join(
            os.environ["APPDATA"],
            r"Microsoft\Windows\Start Menu\Programs\Startup")
        link = os.path.join(startup, "桌面待办.lnk")
        if enable:
            pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            target = os.path.join(BASE_DIR, "todo_qt.py")
            ps = (
                f'$w=New-Object -ComObject WScript.Shell;'
                f'$s=$w.CreateShortcut("{link}");'
                f'$s.TargetPath="{pythonw}";'
                f'$s.Arguments="""{target}""";'
                f'$s.WorkingDirectory="{BASE_DIR}";$s.Save()'
            )
            os.system(f'powershell -NoProfile -Command "{ps}"')
        else:
            if os.path.exists(link):
                os.remove(link)
        return True
    except Exception:
        return False


def _launch_command():
    """返回用于自启的启动命令数组：
    - 已打包(.app/exe)：直接用当前可执行文件
    - 源码运行：用当前 python 解释器 + 脚本路径
    """
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, os.path.join(BASE_DIR, "todo_qt.py")]


def _set_autostart_mac(enable):
    """macOS：通过 ~/Library/LaunchAgents 的 plist 实现登录自启"""
    try:
        label = "com.watermelon.desktoptodo"
        agents = os.path.join(os.path.expanduser("~"), "Library", "LaunchAgents")
        os.makedirs(agents, exist_ok=True)
        plist = os.path.join(agents, f"{label}.plist")
        if enable:
            args = _launch_command()
            args_xml = "".join(f"        <string>{a}</string>\n" for a in args)
            content = (
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
                '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
                '<plist version="1.0">\n'
                '<dict>\n'
                f'    <key>Label</key>\n    <string>{label}</string>\n'
                '    <key>ProgramArguments</key>\n    <array>\n'
                f'{args_xml}'
                '    </array>\n'
                '    <key>RunAtLoad</key>\n    <true/>\n'
                '</dict>\n'
                '</plist>\n'
            )
            with open(plist, "w", encoding="utf-8") as f:
                f.write(content)
        else:
            if os.path.exists(plist):
                os.remove(plist)
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------------
# 精致任务卡片
# ----------------------------------------------------------------------------
STATUS_ICON = {"todo": "○", "doing": "◐", "done": "●"}

# 优先级体系：P0/P1/P2（紧急，由重到轻）> 重要黄 > 普通灰
PRIORITIES = ["P0", "P1", "P2", "重要", "普通"]
PRIORITY_COLORS = {
    "P0": "#D92D20", "P1": "#F2564B", "P2": "#F58C4B",
    "重要": "#F5A623", "普通": "#98A2B3",
}
PRIORITY_RANK = {"P0": 0, "P1": 1, "P2": 2, "重要": 3, "普通": 4}
PRIORITY_ICON = {"P0": "🔥", "P1": "", "P2": "", "重要": "⭐", "普通": ""}
# 属于“紧急”类的优先级（用于统计与显示判断）
URGENT_PRIORITIES = ("P0", "P1", "P2")
# 旧数据迁移映射：老版本的“紧急” -> P1
PRIORITY_MIGRATE = {"紧急": "P1"}

# 循环/重复：周期类型
RECUR_TYPES = ["不循环", "每日", "工作日", "每周", "每月", "每年"]
RECUR_ICON = "🔁"
# 提醒层级：文字 -> 提前分钟数（None=不提醒，0=到期当刻/当天）
# 分钟级提醒需截止时间带具体时间点才精确生效；纯日期按当天 00:00 触发“到期当天”
REMIND_TYPES = {
    "关闭提醒": None,
    "到期当天": 0,
    "结束前10分钟": 10,
    "结束前30分钟": 30,
    "结束前2小时": 120,
    "提前1天": 1440,
    "提前3天": 4320,
}
REMIND_ICON = "🔔"
# 旧数据迁移：老版本提醒值（曾以“天”为单位）-> 新的分钟制文字
REMIND_MIGRATE = {"提前1天": "提前1天", "提前3天": "提前3天"}

# 强提醒：时间单位
STRONG_UNITS = ["天", "小时", "分钟"]
STRONG_UNIT_SECONDS = {"天": 86400, "小时": 3600, "分钟": 60}


def _default_strong():
    """单条待办的“强提醒”配置默认值。"""
    return {
        "enabled": False,        # 是否启用强提醒
        "before_value": 1,       # 截止前 N
        "before_unit": "天",     # 天/小时/分钟
        "interval_value": 2,     # 每 N
        "interval_unit": "小时", # 天/小时/分钟
        "max_count": 0,          # 最多提醒次数（0 = 不限）
        "float_window": False,   # 是否用悬浮小西瓜浮窗提醒
        "count": 0,              # 已提醒次数（运行时累计）
        "last": None,            # 上次提醒时间（ISO 字符串）
    }


def _strong_seconds(value, unit):
    """把“数值+单位”换算成秒，做最小值保护，避免过于频繁的强提醒。"""
    try:
        sec = int(value) * STRONG_UNIT_SECONDS.get(unit, 3600)
    except Exception:
        sec = 3600
    return max(60, sec)  # 下限 60 秒，防止刷屏


class ReminderPopup(QWidget):
    """居中显示的高颜值提醒弹窗：无边框、圆角、阴影、跟随主题配色。
    自带一层半透明遮罩铺满屏幕，把注意力聚焦到中央卡片上。"""

    def __init__(self, theme, task_text, phrase, due="", urgent=False, parent=None):
        super().__init__(None)
        self.theme = theme
        self._result_loop = None
        self.setWindowFlags(_float_window_flags(topmost=True))
        _apply_no_steal_focus(self, accept_focus=True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 铺满当前屏幕，做居中的遮罩效果
        try:
            scr = QApplication.primaryScreen().geometry()
        except Exception:
            scr = QRect(0, 0, 1280, 800)
        self.setGeometry(scr)
        self._build(task_text, phrase, due, urgent)

    def _build(self, task_text, phrase, due, urgent):
        t = self.theme
        accent = "#F2564B" if urgent else t["accent"]
        # 外层铺满，用于绘制半透明遮罩
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addStretch()
        line = QHBoxLayout()
        line.addStretch()

        card = QFrame()
        card.setObjectName("rmcard")
        card.setFixedWidth(340)
        eff = QGraphicsDropShadowEffect(card)
        eff.setBlurRadius(40)
        eff.setColor(QColor(0, 0, 0, 120))
        eff.setOffset(0, 10)
        card.setGraphicsEffect(eff)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(24, 22, 24, 20)
        cl.setSpacing(12)

        icon = QLabel("⏰" if urgent else "🔔")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size:40px;")
        cl.addWidget(icon)

        head = QLabel("待办到期提醒" if urgent else "待办提醒")
        head.setAlignment(Qt.AlignCenter)
        head.setStyleSheet(
            f"color:{accent};font-size:16px;font-weight:bold;")
        cl.addWidget(head)

        body = QLabel(task_text)
        body.setWordWrap(True)
        body.setAlignment(Qt.AlignCenter)
        body.setStyleSheet(
            f"color:{t['text']};font-size:15px;font-weight:bold;")
        cl.addWidget(body)

        sub = QLabel(phrase + (f"\n截止 {due}" if due else ""))
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignCenter)
        sub.setStyleSheet(f"color:{t['sub']};font-size:12px;")
        cl.addWidget(sub)

        btn = QPushButton("知道啦")
        btn.setObjectName("rmok")
        btn.setFixedHeight(38)
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._on_ok)
        cl.addWidget(btn)

        card.setStyleSheet(f"""
            QFrame#rmcard {{
                background: {t['panel']};
                border: 1px solid {t['border']};
                border-radius: 18px;
            }}
            QPushButton#rmok {{
                background: {accent}; color: #FFFFFF; border: none;
                border-radius: 11px; font-size: 14px; font-weight: bold;
            }}
            QPushButton#rmok:hover {{ background: {t['accent2']}; }}
        """)

        line.addWidget(card)
        line.addStretch()
        root.addLayout(line)
        root.addStretch()

    def paintEvent(self, e):
        # 半透明遮罩铺满整个屏幕
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 90))

    def _on_ok(self):
        if self._result_loop is not None:
            self._result_loop.quit()
        self.close()

    def mousePressEvent(self, e):
        # 点击遮罩空白区域也可关闭
        self._on_ok()

    def exec(self):
        """模态显示：阻塞到用户关闭"""
        from PySide6.QtCore import QEventLoop
        self.show()
        self.raise_()
        self.activateWindow()
        self._result_loop = QEventLoop()
        self._result_loop.exec()


class StrongRemindDialog(QDialog):
    """强提醒设置窗口：与主题一致。设置“截止前多久开始 / 每多久一次 / 最多几次 /
    是否用悬浮小西瓜浮窗提醒”，写回到任务数据的 strong 字段。

    enabled 不再需要单独勾选：只要设置了提醒参数或勾选了浮窗，就视为已启用强提醒。
    窗口采用「透明无边框外壳 + 不透明圆角面板(surface)」结构，跨平台（macOS/Windows）
    渲染一致，避免直接把控件画在透明无边框窗口上导致的错位与重影。
    """

    def __init__(self, theme, task, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.task = task
        self.setWindowTitle("强提醒设置")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(400)
        self.setModal(True)
        self._build()

    def _build(self):
        t = self.theme
        s = self.task.get("strong") or _default_strong()

        # 透明外壳，仅承载一个不透明圆角面板
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)

        surface = QFrame()
        surface.setObjectName("dialogSurface")
        shadow = QGraphicsDropShadowEffect(surface)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow_color = QColor(t["text"])
        shadow_color.setAlpha(55)
        shadow.setColor(shadow_color)
        surface.setGraphicsEffect(shadow)
        shell.addWidget(surface)

        root = QVBoxLayout(surface)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(13)

        title = QLabel("🔔 强提醒设置")
        title.setStyleSheet(f"color:{t['text']};font-size:17px;font-weight:bold;")
        root.addWidget(title)

        sub = QLabel("任务：" + (self.task.get("text") or "")[:40])
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{t['sub']};font-size:12px;")
        root.addWidget(sub)

        # 截止前 N 单位 开始提醒
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(QLabel("在截止前"), 0, Qt.AlignVCenter)
        self.spin_before = QSpinBox()
        self.spin_before.setRange(0, 999)
        self.spin_before.setValue(int(s.get("before_value", 1)))
        self.combo_before = QComboBox()
        self.combo_before.addItems(STRONG_UNITS)
        self.combo_before.setCurrentText(s.get("before_unit", "天"))
        row1.addWidget(self.spin_before, 0, Qt.AlignVCenter)
        row1.addWidget(self.combo_before, 0, Qt.AlignVCenter)
        row1.addWidget(QLabel("开始提醒"), 0, Qt.AlignVCenter)
        row1.addStretch()
        root.addLayout(row1)

        # 每隔 N 单位 提醒一次
        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(QLabel("每隔"), 0, Qt.AlignVCenter)
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 999)
        self.spin_interval.setValue(int(s.get("interval_value", 2)))
        self.combo_interval = QComboBox()
        self.combo_interval.addItems(STRONG_UNITS)
        self.combo_interval.setCurrentText(s.get("interval_unit", "小时"))
        row2.addWidget(self.spin_interval, 0, Qt.AlignVCenter)
        row2.addWidget(self.combo_interval, 0, Qt.AlignVCenter)
        row2.addWidget(QLabel("提醒一次"), 0, Qt.AlignVCenter)
        row2.addStretch()
        root.addLayout(row2)

        # 最多提醒 N 次
        row3 = QHBoxLayout()
        row3.setSpacing(8)
        row3.addWidget(QLabel("最多提醒"), 0, Qt.AlignVCenter)
        self.spin_max = QSpinBox()
        self.spin_max.setRange(0, 999)
        self.spin_max.setValue(int(s.get("max_count", 0)))
        row3.addWidget(self.spin_max, 0, Qt.AlignVCenter)
        row3.addWidget(QLabel("次（0 = 不限）"), 0, Qt.AlignVCenter)
        row3.addStretch()
        root.addLayout(row3)

        # 浮窗提醒（勾选即视为启用强提醒）
        self.chk_float = QCheckBox("用悬浮小西瓜浮窗提醒（在西瓜上弹出）")
        self.chk_float.setChecked(bool(s.get("float_window")))
        root.addWidget(self.chk_float)

        root.addStretch()

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("确定")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        root.addWidget(bb)

        # 统一的输入框高度，保证上下对齐
        for w in (self.spin_before, self.combo_before,
                  self.spin_interval, self.combo_interval, self.spin_max):
            w.setFixedHeight(34)

        self.setStyleSheet(self._dlg_style())

    def _dlg_style(self):
        t = self.theme
        return f"""
        QDialog {{ background: transparent; }}
        QFrame#dialogSurface {{
            background: {t['panel']}; border: 1px solid {t['border']};
            border-radius: 17px;
        }}
        QLabel {{ color: {t['text']}; font-size: 13px; }}
        QSpinBox, QComboBox {{
            background: {t['card']}; color: {t['text']};
            border: 1px solid {t['border']}; border-radius: 10px;
            padding: 4px 10px; font-size: 13px;
        }}
        QSpinBox:hover, QComboBox:hover {{ border-color: {_qss_alpha(t['accent'], 0x80)}; }}
        QSpinBox:focus, QComboBox:focus {{ border: 1px solid {t['accent']}; }}
        QComboBox::drop-down {{ border: none; width: 28px; background: transparent; }}
        QComboBox::down-arrow {{ image: none; width: 0; height: 0; border: none; }}
        QComboBox QAbstractItemView {{
            background: {t['panel']}; color: {t['text']};
            selection-background-color: {t['accent']}; selection-color: #FFFFFF;
            border: 1px solid {t['border']}; border-radius: 9px;
            outline: none; padding: 4px;
        }}
        QCheckBox {{
            color: {t['text']}; font-size: 13px; spacing: 7px;
        }}
        QCheckBox::indicator {{
            width: 17px; height: 17px; border-radius: 5px;
            border: 1px solid {t['border']}; background: {t['card']};
        }}
        QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
        QCheckBox::indicator:checked {{
            background: {t['accent']}; border-color: {t['accent']};
        }}
        QPushButton {{
            background: {t['accent']}; color: #FFFFFF; border: none;
            border-radius: 10px; padding: 9px 18px; font-size: 13px; font-weight: bold;
        }}
        QPushButton:hover {{ background: {t['accent2']}; }}
        """

    def accept(self):
        s = self.task.setdefault("strong", _default_strong())
        # 只要设置了提醒参数或勾选了浮窗，即视为已启用强提醒（无需单独勾选框）
        s["enabled"] = bool(
            self.chk_float.isChecked()
            or self.spin_before.value() > 0
            or self.spin_interval.value() > 0
        )
        s["before_value"] = self.spin_before.value()
        s["before_unit"] = STRONG_UNITS[self.combo_before.currentIndex()]
        s["interval_value"] = self.spin_interval.value()
        s["interval_unit"] = STRONG_UNITS[self.combo_interval.currentIndex()]
        s["max_count"] = self.spin_max.value()
        s["float_window"] = self.chk_float.isChecked()
        super().accept()


class FlowLayout(QLayout):
    """自动换行的流式布局：标签放不下时自动换到下一行，避免撑爆父容器。"""
    def __init__(self, parent=None, margin=0, hspacing=6, vspacing=4):
        super().__init__(parent)
        self._items = []
        self._hspace = hspacing
        self._vspace = vspacing
        self.setContentsMargins(margin, margin, margin, margin)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        size += QSize(m.left() + m.right(), m.top() + m.bottom())
        return size

    def _do_layout(self, rect, test_only):
        x = rect.x()
        y = rect.y()
        line_height = 0
        for item in self._items:
            w = item.sizeHint().width()
            h = item.sizeHint().height()
            next_x = x + w + self._hspace
            if next_x - self._hspace > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + self._vspace
                next_x = x + w + self._hspace
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), QSize(w, h)))
            x = next_x
            line_height = max(line_height, h)
        return y + line_height - rect.y()


def _hexa_color(s):
    """把 #RRGGBBAA（alpha 在后）解析成 QColor，兼容 #RRGGBB。"""
    s = s.lstrip("#")
    r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
    a = int(s[6:8], 16) if len(s) >= 8 else 255
    return QColor(r, g, b, a)


class _ThemePreview(QFrame):
    """主题预览的背景层：如实绘制该主题的渐变/底色（与主窗口同款画法）。"""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        gs = self.theme.get("gradient")
        if gs:
            g = QLinearGradient(rect.topLeft(), rect.bottomRight())
            for pos, col in gs:
                g.setColorAt(pos, QColor(col))
            p.fillPath(path, QBrush(g))
        else:
            bg = self.theme["bg"]
            c = QColor(bg) if len(bg) <= 7 else _hexa_color(bg)
            p.fillPath(path, QBrush(c))
        p.setPen(QPen(QColor(self.theme["border"]), 1))
        p.drawPath(path)
        p.end()


class _ThemeCard(QFrame):
    """主题市场卡片：背景渐变预览 + 迷你待办 + 选中角标，点击即应用。"""
    clicked = Signal(str)   # 主题名

    def __init__(self, name, theme, selected, parent=None):
        super().__init__(parent)
        self.name = name
        self.theme = theme
        self.setFixedSize(186, 184)
        self.setCursor(Qt.PointingHandCursor)
        self.setObjectName("themecard")

        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(20)
        sh.setOffset(0, 4)
        sc = QColor(theme.get("shadow") or theme["border"])
        sc.setAlpha(70)
        sh.setColor(sc)
        self.setGraphicsEffect(sh)

        v = QVBoxLayout(self)
        v.setContentsMargins(10, 10, 10, 10)
        v.setSpacing(8)

        # ---- 预览：真实绘制背景渐变，上面摆迷你待办 ----
        prev = _ThemePreview(theme)
        ph = QVBoxLayout(prev)
        ph.setContentsMargins(9, 9, 9, 9)
        ph.setSpacing(6)
        ph.addWidget(self._mock_item(theme, 48, 5, theme["accent"], theme["text"]))
        ph.addWidget(self._mock_item(theme, 36, 4, theme["done"], theme["sub"]))
        ph.addStretch()
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch()
        ab = QFrame()
        ab.setFixedSize(32, 10)
        ab.setStyleSheet(f"background:{theme['accent']}; border-radius:5px;")
        row.addWidget(ab)
        ph.addLayout(row)
        v.addWidget(prev, 1)

        # ---- 名称（用该主题 panel 做底色 chip，保证可读）----
        lbl = QLabel(name)
        lbl.setAlignment(Qt.AlignHCenter)
        lbl.setStyleSheet(
            f"color:{theme['text']}; background:{theme['panel']};"
            f" border:1px solid {theme['border']}; border-radius:9px;"
            f" padding:3px 10px; font-size:12px; font-weight:bold;")
        v.addWidget(lbl, 0, Qt.AlignHCenter)

        # ---- 选中角标 ----
        self._badge = QLabel("✓", self)
        self._badge.setFixedSize(22, 22)
        self._badge.setAlignment(Qt.AlignCenter)
        self._badge.setStyleSheet(
            f"color:#FFFFFF; background:{theme['accent']}; border-radius:11px;"
            f" font-size:12px; font-weight:bold;"
            f" border:2px solid {theme['panel']};")

        self._refresh(selected)

    def _mock_item(self, theme, bar_w, bar_h, dot_color, bar_color):
        """一条迷你待办：圆点 + 文本条（模拟卡片浮在背景上）。"""
        f = QFrame()
        f.setFixedHeight(24)
        f.setStyleSheet(
            f"background:{theme['card']}; border:1px solid {theme['border']};"
            f" border-radius:6px;")
        h = QHBoxLayout(f)
        h.setContentsMargins(7, 6, 7, 6)
        h.setSpacing(6)
        dot = QFrame()
        dot.setFixedSize(9, 9)
        dot.setStyleSheet(f"background:{dot_color}; border-radius:4px;")
        h.addWidget(dot, 0, Qt.AlignVCenter)
        bar = QFrame()
        bar.setFixedSize(bar_w, bar_h)
        bar.setStyleSheet(f"background:{bar_color}; border-radius:2px;")
        h.addWidget(bar, 0, Qt.AlignVCenter)
        h.addStretch()
        return f

    def _refresh(self, selected):
        t = self.theme
        bord = t["accent"] if selected else "transparent"
        w = "2px" if selected else "1px"
        self.setStyleSheet(
            f"_ThemeCard#themecard{{background:transparent;"
            f" border:{w} solid {bord}; border-radius:14px;}}"
            f"_ThemeCard#themecard:hover{{ border:2px solid {t['accent']};}}")
        self._badge.setVisible(selected)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._badge.move(self.width() - self._badge.width() - 7, 7)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.name)
        super().mousePressEvent(e)


# DIY 配色可编辑的颜色项：(主题键, 中文名)
_DIY_KEYS = [
    ("accent", "主色"), ("accent2", "副色"), ("panel", "面板"),
    ("card", "卡片"), ("text", "文字"), ("sub", "副文字"), ("border", "边框"),
]


class DIYColorDialog(QDialog):
    """DIY 配色专属弹窗：逐项取色 → 主窗口实时预览 → 取名保存为自定义主题。
    取消则把主窗口还原到打开前的配色。结构沿用透明外壳 + 圆角面板。"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.setWindowTitle("DIY 配色")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        # 打开前的配色快照：取消/关闭时用它还原
        self._orig_theme = dict(self.main.theme)
        self._diy = {k: self.main.theme.get(k, "#888888") for k, _ in _DIY_KEYS}
        self._saved = False
        self._build()

    # ---- 配色 → 完整主题 dict ----
    def _theme_dict(self):
        d = self._diy
        return {
            "bg": d["panel"], "panel": d["panel"], "card": d["card"],
            "card_hover": d["card"], "text": d["text"], "sub": d["sub"],
            "accent": d["accent"], "accent2": d["accent2"],
            "border": d["border"], "shadow": "#000000", "done": d["sub"],
        }

    def _build(self):
        t = self.main.theme
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)

        surface = QFrame()
        surface.setObjectName("dialogSurface")
        shadow = QGraphicsDropShadowEffect(surface)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 8)
        sc = QColor(t["text"]); sc.setAlpha(55)
        shadow.setColor(sc)
        surface.setGraphicsEffect(shadow)
        shell.addWidget(surface)

        root = QVBoxLayout(surface)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        title = QLabel("🎛 DIY 配色")
        title.setStyleSheet(f"color:{t['text']};font-size:16px;font-weight:bold;")
        root.addWidget(title)
        sub = QLabel("点击色块取色，主界面会实时预览；起个名字保存成你的专属主题")
        sub.setStyleSheet(f"color:{t['sub']};font-size:11px;")
        root.addWidget(sub)

        # ---- 名称 ----
        nrow = QHBoxLayout()
        nrow.setSpacing(8)
        nlbl = QLabel("名称")
        nlbl.setStyleSheet(f"color:{t['text']};font-size:13px;font-weight:600;")
        nrow.addWidget(nlbl)
        self.ed_name = QLineEdit()
        self.ed_name.setPlaceholderText("例如：我的配色")
        # 当前若正处在某套自定义主题上，默认沿用其名，方便覆盖更新
        cur = self.main.theme_name
        if cur in (self.main.cfg.get("custom_themes") or {}):
            self.ed_name.setText(cur)
        self.ed_name.setFixedHeight(32)
        nrow.addWidget(self.ed_name, 1)
        root.addLayout(nrow)

        # ---- 颜色项（两列网格：标签 + 色块按钮）----
        from PySide6.QtWidgets import QGridLayout
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(10)
        self._swatches = {}
        for i, (key, label) in enumerate(_DIY_KEYS):
            r, c = divmod(i, 2)
            lbl = QLabel(label)
            lbl.setStyleSheet(f"color:{t['text']};font-size:13px;")
            lbl.setFixedWidth(48)
            btn = QPushButton()
            btn.setFixedSize(108, 30)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, k=key: self._pick_color(k))
            self._swatches[key] = btn
            self._style_swatch(key)
            cell = QHBoxLayout()
            cell.setSpacing(8)
            cell.addWidget(lbl)
            cell.addWidget(btn)
            cell.addStretch()
            grid.addLayout(cell, r, c)
        root.addLayout(grid)

        # ---- 迷你预览条 ----
        self._preview = _ThemePreview(self._theme_dict())
        self._preview.setFixedHeight(64)
        root.addWidget(self._preview)

        # ---- 底部按钮 ----
        foot = QHBoxLayout()
        foot.setSpacing(8)
        foot.addStretch()
        btn_cancel = QPushButton("取消")
        btn_cancel.setObjectName("ghost")
        btn_cancel.setCursor(Qt.PointingHandCursor)
        btn_cancel.clicked.connect(self.reject)
        foot.addWidget(btn_cancel)
        btn_save = QPushButton("保存主题")
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._save)
        foot.addWidget(btn_save)
        root.addLayout(foot)

        self.setMinimumWidth(430)
        self.setStyleSheet(self._dlg_style())

    def _style_swatch(self, key):
        color = self._diy[key]
        tc = "#FFFFFF" if QColor(color).lightness() < 140 else "#222222"
        btn = self._swatches[key]
        btn.setText(color.upper())
        btn.setStyleSheet(
            f"QPushButton{{background:{color}; color:{tc};"
            f" border:2px solid {self.main.theme['border']};"
            f" border-radius:8px; font-size:11px; font-weight:600;}}")

    def _pick_color(self, key):
        from PySide6.QtWidgets import QColorDialog
        c = QColorDialog.getColor(QColor(self._diy[key]), self, "选择颜色")
        if not c.isValid():
            return
        self._diy[key] = c.name()
        self._style_swatch(key)
        th = self._theme_dict()
        self._preview.theme = th
        self._preview.update()
        # 主窗口实时预览（不落盘）
        self.main._preview_theme(th)

    def _save(self):
        name = self.ed_name.text().strip() or "我的配色"
        customs = self.main.cfg.setdefault("custom_themes", {})
        # 与内置主题重名时自动加后缀，避免覆盖内置配色
        if name in THEMES and name not in customs:
            name += "·DIY"
        theme = self._theme_dict()
        customs[name] = theme
        THEMES[name] = theme
        if name not in THEME_ORDER:
            THEME_ORDER.append(name)
        self._saved = True
        self.main._set_theme(name)   # 内部会 _save_cfg，连同 custom_themes 持久化
        self.accept()

    def reject(self):
        # 取消：把主窗口还原到打开前的配色
        if not self._saved:
            self.main._preview_theme(self._orig_theme)
        super().reject()

    def _dlg_style(self):
        t = self.main.theme
        return f"""
        QDialog {{ background: transparent; }}
        QFrame#dialogSurface {{
            background: {t['panel']}; border: 1px solid {t['border']};
            border-radius: 18px;
        }}
        QLineEdit {{
            background: {t['card']}; color: {t['text']};
            border: 1px solid {t['border']}; border-radius: 8px;
            padding: 4px 10px; font-size: 13px;
        }}
        QLineEdit:focus {{ border: 1px solid {t['accent']}; }}
        QPushButton {{ background: {t['accent']}; color: #FFFFFF; border: none;
            border-radius: 9px; padding: 8px 16px; font-size: 13px; font-weight: bold; }}
        QPushButton:hover {{ background: {t['accent2']}; }}
        QPushButton#ghost {{ background: transparent; color: {t['sub']};
            border: 1px solid {t['border']}; font-weight: 600; }}
        QPushButton#ghost:hover {{ color: {t['accent']}; border-color: {t['accent']}; }}
        """


class ThemeMarketDialog(QDialog):
    """主题市场：以卡片网格浏览所有主题，点击即时应用（实时预览）。
    结构与强提醒弹窗一致——透明外壳 + 不透明圆角面板，跨平台渲染稳定。"""

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main = main_window
        self.setWindowTitle("主题市场")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumWidth(560)
        self.setMinimumHeight(480)
        self.setModal(True)
        self._cards = []
        self._build()

    def _build(self):
        t = self.main.theme
        shell = QVBoxLayout(self)
        shell.setContentsMargins(0, 0, 0, 0)

        surface = QFrame()
        surface.setObjectName("dialogSurface")
        shadow = QGraphicsDropShadowEffect(surface)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        sc = QColor(t["text"]); sc.setAlpha(55)
        shadow.setColor(sc)
        surface.setGraphicsEffect(shadow)
        shell.addWidget(surface)

        root = QVBoxLayout(surface)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("🎨 主题市场")
        title.setStyleSheet(f"color:{t['text']};font-size:17px;font-weight:bold;")
        subtitle = QLabel("点击卡片即时预览，选中后点“完成”即可")
        subtitle.setStyleSheet(f"color:{t['sub']};font-size:11px;")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        head.addLayout(title_col)
        head.addStretch()
        self._sub = QLabel()
        self._sub.setStyleSheet(f"color:{t['accent']};font-size:12px;font-weight:bold;")
        head.addWidget(self._sub, 0, Qt.AlignVCenter)
        root.addLayout(head)

        # ---- 主题卡片网格（可滚动）----
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._scroll.setObjectName("scroll")
        self._rebuild_grid()
        root.addWidget(self._scroll, 1)

        # 底部：DIY 配色 + 背景图片 + 完成
        foot = QHBoxLayout()
        foot.setSpacing(8)
        btn_diy = QPushButton("🎛  DIY 配色…")
        btn_diy.setObjectName("ghost")
        btn_diy.setCursor(Qt.PointingHandCursor)
        btn_diy.clicked.connect(self._open_diy)
        foot.addWidget(btn_diy)
        btn_bg = QPushButton("🖼  上传背景图片…")
        btn_bg.setObjectName("ghost")
        btn_bg.setCursor(Qt.PointingHandCursor)
        btn_bg.clicked.connect(lambda: (self.main._pick_bg_image(), self._sync_bg_btn(btn_clr)))
        foot.addWidget(btn_bg)
        btn_clr = QPushButton("🗑  清除背景图片")
        btn_clr.setObjectName("ghost")
        btn_clr.setCursor(Qt.PointingHandCursor)
        btn_clr.clicked.connect(lambda: (self.main._clear_bg_image(), self._sync_bg_btn(btn_clr)))
        foot.addWidget(btn_clr)
        foot.addStretch()
        btn_done = QPushButton("完成")
        btn_done.setCursor(Qt.PointingHandCursor)
        btn_done.clicked.connect(self.accept)
        foot.addWidget(btn_done)
        root.addLayout(foot)

        self._sync_bg_btn(btn_clr)
        self.setStyleSheet(self._dlg_style())

    def _sync_bg_btn(self, btn_clr):
        has = bool(self.main.cfg.get("bg_image"))
        btn_clr.setEnabled(has)

    def _apply(self, name):
        self.main._set_theme(name)
        # 同步卡片选中态 + 配色（主题切换后面板色也变了，刷新样式）
        cur = self.main.theme_name
        for c in self._cards:
            c._refresh(c.name == cur)
        self._sub.setText("当前：" + cur)
        self.setStyleSheet(self._dlg_style())

    # ---- DIY 配色 ----
    def _open_diy(self):
        """打开 DIY 配色专属弹窗；关闭后刷新卡片网格与自身样式。"""
        dlg = DIYColorDialog(self.main, self)
        dlg.exec()
        self._rebuild_grid()
        self._sub.setText("当前：" + self.main.theme_name)
        self.setStyleSheet(self._dlg_style())

    def _rebuild_grid(self):
        old = self._scroll.widget()
        inner = QWidget()
        inner.setObjectName("inner")
        flow = FlowLayout(inner, margin=6, hspacing=14, vspacing=14)
        self._cards = []
        # 只展示前 8 个内置示例主题，但确保当前正在使用的主题始终可见
        shown = BUILTIN_THEME_ORDER[:8]
        if self.main.theme_name not in shown and self.main.theme_name in THEME_ORDER:
            shown = shown[:-1] + [self.main.theme_name]
        for name in shown:
            th = THEMES[name]
            card = _ThemeCard(name, th, name == self.main.theme_name)
            card.clicked.connect(self._apply)
            self._cards.append(card)
            flow.addWidget(card)
        self._scroll.setWidget(inner)
        if old is not None:
            old.deleteLater()

    def _dlg_style(self):
        t = self.main.theme
        return f"""
        QDialog {{ background: transparent; }}
        QFrame#dialogSurface {{
            background: {t['panel']}; border: 1px solid {t['border']};
            border-radius: 18px;
        }}
        QScrollArea {{ background: transparent; border: none; }}
        QWidget#inner {{ background: transparent; }}
        QLabel {{ color: {t['text']}; font-size: 13px; }}
        QPushButton {{ background: {t['accent']}; color: #FFFFFF; border: none;
            border-radius: 9px; padding: 8px 16px; font-size: 13px; font-weight: bold; }}
        QPushButton:hover {{ background: {t['accent2']}; }}
        QPushButton#ghost {{ background: transparent; color: {t['sub']};
            border: 1px solid {t['border']}; font-weight: 600; }}
        QPushButton#ghost:hover {{ color: {t['accent']}; border-color: {t['accent']}; }}
        QPushButton#ghost:disabled {{ color: {t['done']}; border-color: {t['border']}; }}
        """


def _pencil_icon(px: int = 18) -> QIcon:
    """绘制“编辑”铅笔图标。

    macOS 上系统字体的 ✏️ 朝向与期望相反，故渲染为位图后做一次水平镜像；
    Windows 上 ✏️ 本就朝向正确，保持原样。用位图承载可保证跨平台方向一致。
    """
    dpr = 2
    try:
        screen = QApplication.primaryScreen()
        if screen:
            dpr = max(1, int(screen.devicePixelRatio()))
    except Exception:
        pass
    pm = QPixmap(px * dpr, px * dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    f = QFont()
    if IS_MAC:
        f.setFamily("Apple Color Emoji")
    elif IS_WIN:
        f.setFamily("Segoe UI Emoji")
    f.setPixelSize(int(px * 0.95))
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "✏️")
    p.end()
    pm.setDevicePixelRatio(dpr)
    if IS_MAC:
        pm = pm.transformed(QTransform.fromScale(-1, 1), Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


class TaskCard(QFrame):
    toggled = Signal(str)
    deleted = Signal(str)
    edited = Signal(str)
    sub_toggled = Signal(str, int)   # (任务id, 子任务索引)
    select_toggled = Signal(str, bool)   # (任务id, 是否选中)
    pinned = Signal(str)   # (任务id) 切换置顶
    configure_strong = Signal(str)   # (任务id) 打开强提醒设置
    def __init__(self, task, theme, parent=None, select_mode=False, selected=False):
        super().__init__(parent)
        self.task = task
        self.theme = theme
        self.select_mode = select_mode
        self.selected = selected
        self.setObjectName("card")
        self.setCursor(Qt.PointingHandCursor)
        self._hover = False
        self.setMouseTracking(True)
        self._build()
        self._apply_style()

    def _build(self):
        self.is_pinned = bool(self.task.get("pinned", False))
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QWidget()
        lay = QHBoxLayout(top)
        lay.setContentsMargins(7, 10, 10, 10)
        lay.setSpacing(7)

        # 优先级左侧色条
        self.pbar = QFrame()
        self.pbar.setObjectName("pbar")
        self.pbar.setFixedWidth(3)
        lay.addWidget(self.pbar)

        # 状态圆点按钮（选择模式下变为复选框）
        self.dot = QPushButton()
        self.dot.setObjectName("dot")
        self.dot.setFixedSize(22, 22)
        self.dot.setCursor(Qt.PointingHandCursor)
        if self.select_mode:
            self.dot.setText("☑" if self.selected else "☐")
            self.dot.clicked.connect(self._on_select_click)
        else:
            self.dot.setText(STATUS_ICON[self.task["status"]])
            self.dot.clicked.connect(lambda: self.toggled.emit(self.task["id"]))
        lay.addWidget(self.dot, 0, Qt.AlignVCenter)

        # 中部文字区
        mid = QVBoxLayout()
        mid.setSpacing(3)
        self.title = QLabel(self.task["text"])
        self.title.setObjectName("title")
        self.title.setWordWrap(True)
        mid.addWidget(self.title)

        note_full = " ".join(self.task.get("note", "").split())
        if note_full:
            note_text = note_full
            if len(note_text) > NOTE_PREVIEW_LIMIT:
                note_text = note_text[:NOTE_PREVIEW_LIMIT].rstrip() + "…"
            self.note_preview = QLabel(f"备注 · {note_text}")
            self.note_preview.setObjectName("notePreview")
            self.note_preview.setToolTip(note_full)
            self.note_preview.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            mid.addWidget(self.note_preview)

        meta = FlowLayout(hspacing=6, vspacing=4)
        # 优先级标签（普通不显示，减少干扰）
        pr = self.task.get("priority", "普通")
        if pr != "普通":
            self.pr_lbl = QLabel((PRIORITY_ICON.get(pr, "") + pr).strip())
            self.pr_lbl.setObjectName("prio")
            meta.addWidget(self.pr_lbl)
        cat = self.task.get("category", "其他")
        self.cat = QLabel(cat)
        self.cat.setObjectName("cat")
        meta.addWidget(self.cat)
        dtxt, urgent = due_label(self.task.get("due", ""))
        # 已完成任务：截止时间标签不再标红（去掉过期紧急样式），
        # 且不显示“已过期 X 天”这类催促文字，直接展示原始截止日期
        is_done = self.task.get("status") == "done"
        if is_done:
            urgent = False
            raw_due = self.task.get("due", "")
            if raw_due:
                d, tm = parse_due(raw_due)
                if d is not None:
                    dtxt = d.strftime("%m-%d") + (tm.strftime(" %H:%M") if tm else "")
                else:
                    dtxt = raw_due
        if dtxt:
            self.due = QLabel(dtxt)
            self.due.setObjectName("due_urgent" if urgent else "due")
            meta.addWidget(self.due)
        rc = self.task.get("recur", "不循环")
        if rc and rc != "不循环":
            self.recur_lbl = QLabel(RECUR_ICON + rc)
            self.recur_lbl.setObjectName("recur")
            meta.addWidget(self.recur_lbl)
        rm = self.task.get("remind", "到期当天")
        if rm and rm not in ("到期当天", "关闭提醒") and self.task.get("due"):
            self.remind_lbl = QLabel(REMIND_ICON + rm)
            self.remind_lbl.setObjectName("recur")
            meta.addWidget(self.remind_lbl)
        # 强提醒标识：启用时显示 🔔（带“强”字），提示该待办有强提醒
        if self.task.get("strong", {}).get("enabled"):
            self.strong_badge = QLabel("🔔强")
            self.strong_badge.setObjectName("strongbadge")
            self.strong_badge.setToolTip("已开启强提醒")
            meta.addWidget(self.strong_badge)
        # 子任务进度徽章（可点击展开/收起）
        subs = self.task.get("subtasks", [])
        if subs:
            done_n = sum(1 for s in subs if s.get("done"))
            self.sub_badge = QPushButton(f"☑ {done_n}/{len(subs)}")
            self.sub_badge.setObjectName("subbadge")
            self.sub_badge.setCursor(Qt.PointingHandCursor)
            self.sub_badge.clicked.connect(self._toggle_subs)
            meta.addWidget(self.sub_badge)
        mid.addLayout(meta)
        lay.addLayout(mid, 1)

        # 编辑按钮（悬浮显示，唯一保留在卡片上的按钮）
        # 用透明度控制显隐而非 setVisible，避免布局宽度突变导致卡片内容“跳动”
        self.edit_btn = QPushButton()
        self.edit_btn.setIcon(_pencil_icon(18))
        self.edit_btn.setIconSize(QSize(18, 18))
        self.edit_btn.setObjectName("edit")
        self.edit_btn.setFixedSize(27, 27)
        self.edit_btn.setToolTip("编辑待办")
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.clicked.connect(lambda: self.edited.emit(self.task["id"]))
        self._edit_opacity = QGraphicsOpacityEffect(self.edit_btn)
        self._edit_opacity.setOpacity(0.0)
        self.edit_btn.setGraphicsEffect(self._edit_opacity)
        lay.addWidget(self.edit_btn, 0, Qt.AlignVCenter)

        outer.addWidget(top)

        # 子任务展开区（默认收起）
        self.sub_panel = QWidget()
        self.sub_panel.setObjectName("subpanel")
        sp = QVBoxLayout(self.sub_panel)
        sp.setContentsMargins(30, 0, 14, 10)
        sp.setSpacing(4)
        self.sub_checks = []
        for i, s in enumerate(self.task.get("subtasks", [])):
            cb = QPushButton(("☑ " if s.get("done") else "☐ ") + s.get("text", ""))
            cb.setObjectName("subitem")
            cb.setCursor(Qt.PointingHandCursor)
            cb.clicked.connect(lambda _=False, idx=i: self.sub_toggled.emit(self.task["id"], idx))
            sp.addWidget(cb)
            self.sub_checks.append(cb)
        self.sub_panel.setVisible(False)
        outer.addWidget(self.sub_panel)

        # 置顶钉子：浮在卡片右上角（绝对定位，不进布局、不占标题位置）
        self.pin_mark = QLabel("📌", self)
        self.pin_mark.setObjectName("pinmark")
        self.pin_mark.adjustSize()
        self.pin_mark.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.pin_mark.setVisible(self.is_pinned)
        self._place_pin_mark()

    def _place_pin_mark(self):
        """把置顶钉子固定在卡片右上角"""
        if not hasattr(self, "pin_mark"):
            return
        self.pin_mark.adjustSize()
        w = self.pin_mark.width()
        self.pin_mark.move(self.width() - w - 3, 2)
        self.pin_mark.raise_()

    def resizeEvent(self, e):
        self._place_pin_mark()
        super().resizeEvent(e)

    def _toggle_subs(self):
        self.sub_panel.setVisible(not self.sub_panel.isVisible())

    def _on_select_click(self):
        self.selected = not self.selected
        self.dot.setText("☑" if self.selected else "☐")
        self.select_toggled.emit(self.task["id"], self.selected)

    def set_selected(self, sel):
        """原地更新选中态（不重建卡片，避免全选时整表闪烁）"""
        self.selected = sel
        if self.select_mode:
            self.dot.setText("☑" if sel else "☐")

    def set_select_mode(self, mode, selected=False):
        """原地切换多选模式（不重建卡片，避免进入/退出选择模式时整表闪烁）"""
        if mode == self.select_mode:
            # 模式未变，仅同步选中态
            if mode:
                self.set_selected(selected)
            return
        self.select_mode = mode
        self.selected = selected
        # 重新绑定 dot 的点击行为
        try:
            self.dot.clicked.disconnect()
        except (RuntimeError, TypeError):
            pass
        if mode:
            self.dot.setText("☑" if selected else "☐")
            self.dot.clicked.connect(self._on_select_click)
        else:
            self.dot.setText(STATUS_ICON[self.task["status"]])
            self.dot.clicked.connect(lambda: self.toggled.emit(self.task["id"]))

    def refresh_status(self):
        """原地刷新完成状态（不重建卡片，避免整表闪烁）"""
        if not self.select_mode:
            self.dot.setText(STATUS_ICON[self.task["status"]])
        self.title.setText(self.task["text"])
        self._apply_style()

    def _apply_style(self):
        t = self.theme
        c = CAT_COLORS.get(self.task.get("category", "其他"), t["sub"])
        done = self.task["status"] == "done"
        pr = self.task.get("priority", "普通")
        pc = PRIORITY_COLORS.get(pr, "#98A2B3")
        title_color = t["done"] if done else t["text"]
        deco = "line-through" if done else "none"
        card_bg = t["card_hover"] if self._hover else t["card"]
        # 已置顶：仅靠右上角钉子标记，卡片外观与普通待办完全一致（无边框高亮、无底色微染）
        pinned = getattr(self, "is_pinned", False)
        if hasattr(self, "pin_mark"):
            self.pin_mark.setVisible(pinned)
            self._place_pin_mark()
        card_border = f"1px solid {t['border']}"
        card_left = f"1px solid {t['border']}"
        self.setStyleSheet(f"""
            QFrame#card {{
                background: {card_bg};
                border-radius: 12px;
                border: {card_border};
                border-left: {card_left};
            }}
            QFrame#pbar {{
                background: {'transparent' if (done or pr == '普通') else pc};
                border-radius: 1px;
            }}
            QLabel#prio {{
                color: {'#FFFFFF' if not done else t['done']}; font-size: 11px; font-weight: bold;
                background: {pc if not done else _qss_alpha(pc, 0x22)};
                border-radius: 8px; padding: 3px 8px;
            }}
            QPushButton#dot {{
                background: {_qss_alpha(t['accent'], 0x10)};
                border: 1px solid {_qss_alpha(t['accent'], 0x30)};
                border-radius: 11px; color: {t['accent']};
                font-size: 14px; font-weight: bold;
            }}
            QPushButton#dot:hover {{
                background: {_qss_alpha(t['accent'], 0x22)};
                border-color: {t['accent']};
            }}
            QPushButton#dot:pressed {{
                background: {_qss_alpha(t['accent'], 0x35)};
            }}
            QLabel#pinmark {{
                font-size: 10px;
                background: transparent;
                padding: 0px;
            }}
            QLabel#title {{
                color: {title_color}; font-size: 14px; font-weight: 500;
                text-decoration: {deco};
            }}
            QLabel#notePreview {{
                color: {c if not done else t['done']}; font-size: 11px; font-weight: 500;
                background: {_qss_alpha(c, 0x14 if not done else 0x0A)};
                border-left: 3px solid {_qss_alpha(c, 0xCC if not done else 0x55)};
                border-radius: 6px; padding: 2px 6px;
            }}
            QLabel#cat {{
                color: {c if not done else t['done']}; font-size: 11px; font-weight: bold;
                background: {_qss_alpha(c, 0x18 if not done else 0x0C)};
                border: 1px solid {_qss_alpha(c, 0x28 if not done else 0x14)};
                border-radius: 8px; padding: 3px 8px;
            }}
            QLabel#due {{
                color: {t['sub'] if not done else t['done']}; font-size: 11px;
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 8px; padding: 3px 8px;
            }}
            QLabel#due_urgent {{
                color: #FFFFFF; font-size: 11px; font-weight: bold;
                background: #F2564B; border: 1px solid #F2564B;
                border-radius: 8px; padding: 3px 8px;
            }}
            QLabel#recur {{
                color: {t['accent'] if not done else t['done']}; font-size: 11px; font-weight: bold;
                background: {_qss_alpha(t['accent'], 0x14 if not done else 0x0A)};
                border: 1px solid {_qss_alpha(t['accent'], 0x25 if not done else 0x12)};
                border-radius: 8px; padding: 3px 8px;
            }}
            QLabel#strongbadge {{
                color: #FFFFFF; font-size: 11px; font-weight: bold;
                background: {t['accent']}; border: 1px solid {t['accent']};
                border-radius: 8px; padding: 3px 8px;
            }}
            QPushButton#del, QPushButton#edit {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 8px; color: {t['sub']}; font-size: 13px;
            }}
            QPushButton#del:hover {{
                color: #FFFFFF; background: #E5484D; border-color: #E5484D;
            }}
            QPushButton#edit:hover {{
                color: #FFFFFF; background: {t['accent']};
                border-color: {t['accent']};
            }}
            QPushButton#del:pressed, QPushButton#edit:pressed {{ padding-top: 2px; }}
            QPushButton#subbadge {{
                color: {t['accent']}; font-size: 11px; font-weight: bold;
                background: {_qss_alpha(t['accent'], 0x14)};
                border: 1px solid {_qss_alpha(t['accent'], 0x25)};
                border-radius: 8px; padding: 3px 8px;
            }}
            QPushButton#subbadge:hover {{
                background: {_qss_alpha(t['accent'], 0x25)};
            }}
            QWidget#subpanel {{ background: transparent; }}
            QPushButton#subitem {{
                color: {t['sub']}; font-size: 12px; text-align: left;
                background: transparent; border: none; border-radius: 7px;
                padding: 4px 7px;
            }}
            QPushButton#subitem:hover {{
                color: {t['accent']};
                background: {_qss_alpha(t['accent'], 0x10)};
            }}
        """)

    def enterEvent(self, e):
        self._hover = True
        self._edit_opacity.setOpacity(1.0)
        self._apply_style()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._edit_opacity.setOpacity(0.0)
        self._apply_style()
        super().leaveEvent(e)

    def contextMenuEvent(self, e):
        """右键卡片弹出菜单：置顶/取消置顶、删除"""
        if self.select_mode:
            return
        menu = QMenu(self)
        t = self.theme
        menu.setStyleSheet(f"""
            QMenu {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 10px; padding: 6px;
            }}
            QMenu::item {{
                color: {t['text']}; font-size: 13px;
                padding: 7px 22px 7px 14px; border-radius: 7px;
            }}
            QMenu::item:selected {{
                background: {_qss_alpha(t['accent'], 0x22)}; color: {t['accent']};
            }}
            QMenu::separator {{ height: 1px; background: {t['border']}; margin: 5px 8px; }}
        """)
        if self.is_pinned:
            act_pin = menu.addAction("📌  取消置顶")
        else:
            act_pin = menu.addAction("📌  置顶")
        menu.addSeparator()
        act_note = menu.addAction("📝  编辑备注")
        act_subs = None
        if self.task.get("subtasks"):
            label = "📂  收起小步骤" if self.sub_panel.isVisible() else "📂  展开小步骤"
            act_subs = menu.addAction(label)
        menu.addSeparator()
        act_strong = menu.addAction("🔔  强提醒")
        menu.addSeparator()
        act_del = menu.addAction("🗑  删除待办")
        chosen = menu.exec(e.globalPos())
        if chosen == act_pin:
            self.pinned.emit(self.task["id"])
        elif chosen == act_note:
            self.edited.emit(self.task["id"])
        elif act_subs is not None and chosen == act_subs:
            self._toggle_subs()
        elif chosen == act_strong:
            self.configure_strong.emit(self.task["id"])
        elif chosen == act_del:
            self.deleted.emit(self.task["id"])

    def mouseDoubleClickEvent(self, e):
        self.edited.emit(self.task["id"])
        super().mouseDoubleClickEvent(e)


# ----------------------------------------------------------------------------
# 桌面悬浮小西瓜
# ----------------------------------------------------------------------------
_BALL_SPEECH = [
    # —— 陪伴 · 打气 ——
    "抱抱西瓜，歇会儿吧～",
    "今天也要元气满满 🍉",
    "待办再多，慢慢来不急",
    "你辛苦啦，奖励自己一口西瓜",
    "别绷太紧，西瓜都替你放松啦",
    "一步一步来，你已经很棒啦",
    "累了就靠一会儿，我陪着你 🍉",
    "慢一点没关系，方向对就行",
    "你比自己想象中更能扛哦",
    "今天的你，已经足够努力啦",
    "不用赶，稳稳的就很好",
    "西瓜给你打气：冲鸭，但别硬撑～",
    "做完一件就少一件，加油 💪",
    "情绪也要按时清空哦",
    "你值得被温柔对待，先从自己开始",
    # —— 身体 · 提醒 ——
    "记得喝水哦 💧",
    "久坐啦，起来动动肩膀吧",
    "眼睛酸了就看看远处 👀",
    "深呼吸，世界不会崩塌",
    "别忘了好好吃饭呀 🍚",
    "该起来伸个懒腰啦～",
    "护好颈椎，别一直低头哦",
    "困了就眯一会儿，效率更高",
    # —— 心情 · 治愈 ——
    "坏心情？扔给西瓜吧 🍉",
    "今天也有好好爱自己吗？",
    "不开心的话，先暂停一下下",
    "把焦虑放一放，先做眼前这件",
    "你已经处理了好多事，了不起",
    "允许自己偶尔摆烂一小会儿",
    "生活是长跑，不必事事争先",
    "西瓜相信你，会越来越顺的",
]



# 完成待办后的庆祝文案（{n}=今日已完成数）
_BALL_CELEBRATE = [
    "哇你太棒了！今天已完成 {n} 个待办 🎉",
    "厉害！今天 {n} 个待办搞定啦 ✨",
    "牛！{n} 个完成，继续冲 💪",
    "太赞了～今天 {n} 个待办收工 🍉",
    "你超棒的，今天 {n} 个待办拿下！🌟",
]


class HoverBubble(QWidget):
    """悬浮小西瓜的悬停气泡：鼠标移到西瓜上时，从它右上方“冒出”一句话。"""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)      # 显示但不激活，不抢微信焦点
        self.setAttribute(Qt.WA_TransparentForMouseEvents)  # 鼠标穿透，不影响西瓜的 hover 检测
        self._label = QLabel("", self)
        self._label.setWordWrap(True)
        # 舒适阅读宽度：约 15~16 个中文/行；由 _position_bubble 在贴右缘时才临时收窄
        self._label.setMaximumWidth(240)
        self._label.setStyleSheet(
            "QLabel{color:#2b2b2b;"
            "font:14px/1.5 'PingFang SC','Microsoft YaHei',sans-serif;}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(15, 11, 15, 11)
        lay.addWidget(self._label)
        self.adjustSize()

    def set_text(self, text):
        self._label.setText(text)
        self.adjustSize()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.rect().adjusted(1, 1, -1, -1)
        p.setBrush(QColor(255, 255, 255, 240))
        p.setPen(QColor(0, 0, 0, 25))
        p.drawRoundedRect(r, 14, 14)

    def showEvent(self, e):
        super().showEvent(e)
        _mac_make_window_truly_transparent(self)


class FloatingBall(QWidget):
    """桌面悬浮小西瓜：无边框、置顶、小圆形，可拖动。
    左键单击（非拖动）→ 唤起主界面；右键 → 菜单（退出）。"""

    SIZE = 56  # 西瓜本体直径
    PAD_X = 14  # 左右留白（给手臂+摆动）
    PAD_TOP = 6  # 顶部留白（给弹跳）
    PAD_BOTTOM = 20  # 底部留白（给腿+脚）

    def __init__(self, main_window):
        super().__init__(None)
        self.main = main_window
        self._drag_pos = None
        self._moved = False
        # 控件比西瓜本体大一圈，容纳摆动/弹跳/腿的空间
        self.W = self.SIZE + self.PAD_X * 2
        self.H = self.SIZE + self.PAD_TOP + self.PAD_BOTTOM
        self.setWindowFlags(_float_window_flags(topmost=True))
        _apply_no_steal_focus(self, accept_focus=False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 主动开启 hover 事件投递 + 鼠标跟踪：不依赖窗口激活状态，
        # 否则 macOS 上「不抢焦点」的窗口要先点一下才会收到 enter/leave。
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setFixedSize(self.W, self.H)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("西瓜todo · 点击打开 / 右键退出")
        # 悬停气泡防抖：进入西瓜本体才弹，且同一次悬停内不重复换台词
        self._hover_in = False        # 当前光标是否在“西瓜本体”判定区内
        self._hover_poll = QTimer(self)
        self._hover_poll.setInterval(120)
        self._hover_poll.timeout.connect(self._check_hover)
        self._hover_poll.start()
        # ---- 动画状态 ----
        self._t = 0.0          # 累计时间（秒）
        self._blinking = 0.0     # 眨眼进度（>0 表示正在眨）
        import random as _rnd
        self._rnd = _rnd
        self._anim = QTimer(self)
        self._anim.setInterval(30)  # ~33fps
        self._anim.timeout.connect(self._on_anim_tick)
        self._anim.start()
        # ---- 表情 / 动作状态 ----
        self._face = "normal"        # 当前表情名（normal/blink/cheerful/surprised/sleepy）
        self._face_left = 0.0        # 非常态表情剩余秒数（归零则回到 normal）
        self._dir = -1               # 行进方向：固定 -1（不再来回翻转，避免脚朝向怪异）
        self._hop = 0.0              # 蹦跳能量（触发后衰减，叠加到弹跳高度上）
        self._turn = 0.0             # 转身剩余秒数（>0 时绕竖直轴做 3D 转身，非 2D 翻跟头）
        self._turn_dur = 1.0         # 单次转身时长（秒），用于算转身进度
        self._particles = []         # 粒子（花瓣/星星/爱心），tick 更新、paintEvent 绘制
        # 完成待办庆祝：轮询今日完成数，增加时撒花+弹庆祝气泡
        self._done_today = None      # 上次见到的“今日已完成”数（None=尚未基线）
        self._stat_tick = 0          # 轮询计数
        self._celeb_cooldown = 0.0   # 庆祝冷却（秒），避免快速批量完成时刷屏
        # 载入西瓜图标并预生成多套表情（睁眼/闭眼/开心/惊讶/犯困），高清渲染；失败回退 emoji
        self._faces = self._build_faces()
        self._pixmap = self._faces.get("normal")
        self._pixmap_blink = self._faces.get("blink")
        # 初始位置：屏幕右下角上方一点
        try:
            scr = QApplication.primaryScreen().availableGeometry()
            pos = self.main.cfg.get("floating_ball_pos")
            if (isinstance(pos, list) and len(pos) == 2
                    and all(isinstance(v, int) for v in pos)):
                x = min(max(pos[0], scr.left()), scr.right() - self.W)
                y = min(max(pos[1], scr.top()), scr.bottom() - self.H)
            else:
                x = scr.right() - self.W - 24
                y = scr.bottom() - self.H - 120
            self.move(x, y)
        except Exception:
            self.move(1000, 600)

    def _build_faces(self):
        """预渲染多套表情位图：normal/blink/cheerful/surprised/sleepy。

        沿用既有“改 SVG 文本再渲染”的标准：读 watermelon_ball.svg 文本，按表情替换
        “左眼”与“嘴巴”两段 SVG，用 QSvgRenderer 渲染成位图。右眼维持原 wink（角色特征）。
        任一步失败返回空 dict，paintEvent 自动回退 emoji。"""
        import re as _re
        from PySide6.QtSvg import QSvgRenderer
        from PySide6.QtCore import QByteArray
        from PySide6.QtGui import QPainter as _QP, QPixmap
        faces = {}
        try:
            ball_path = _resource_path("watermelon_ball.svg")
            svg_path = ball_path if ball_path.exists() else _resource_path("watermelon_logo.svg")
            if not svg_path.exists():
                return faces
            svg_txt = svg_path.read_text(encoding="utf-8")
            dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
            px = int(self.SIZE * dpr)

            def _render(txt):
                r = QSvgRenderer(QByteArray(txt.encode("utf-8")))
                if not r.isValid():
                    return None
                pm = QPixmap(px, px)
                pm.fill(Qt.transparent)
                pp = _QP(pm)
                pp.setRenderHint(_QP.Antialiasing, True)
                r.render(pp)
                pp.end()
                pm.setDevicePixelRatio(dpr)
                return pm if not pm.isNull() else None

            # 原图即“常态”：左眼睁开 + 右眼笑 + 开心嘴
            faces["normal"] = _render(svg_txt)

            # 左眼 / 嘴巴 两段互不重叠，可先后替换
            left_re = _re.compile(r'<!-- Open eye -->.*?(?=<!-- Winking eye -->)', _re.S)
            mouth_re = _re.compile(r'<!-- Happy mouth -->.*?(?=</svg>)', _re.S)

            def _face(left_eye_svg, mouth_svg=None):
                """换左眼；mouth_svg 为 None 则保留原开心嘴。"""
                txt = left_re.sub(
                    f'<!-- Open eye -->\n  {left_eye_svg}\n', svg_txt, count=1)
                if mouth_svg is not None:
                    txt = mouth_re.sub(
                        f'<!-- Happy mouth -->\n  {mouth_svg}\n', txt, count=1)
                return _render(txt)

            # ---- 左眼各形态（SVG 坐标，viewBox 1024）----
            EYE_CLOSED = ('<path d="M339 506 Q392 461 445 506" fill="none" '
                          'stroke="#211A1C" stroke-width="19" stroke-linecap="round"/>')
            EYE_HAPPY = ('<path d="M335 520 Q392 466 449 520" fill="none" '
                         'stroke="#211A1C" stroke-width="19" stroke-linecap="round"/>')
            EYE_SURPRISED = (
                '<ellipse cx="384" cy="494" rx="82" ry="82" fill="#FFFFFF" '
                'stroke="#F6E7E4" stroke-width="10"/>\n'
                '  <ellipse cx="384" cy="500" rx="50" ry="56" fill="#261D20"/>\n'
                '  <ellipse cx="366" cy="478" rx="18" ry="22" fill="#FFFFFF"/>'
            )
            EYE_SLEEPY = (
                '<path d="M312 495 Q384 475 456 495 L456 512 Q384 532 312 512 Z" '
                'fill="#FFFFFF" stroke="#211A1C" stroke-width="8" stroke-linejoin="round"/>\n'
                '  <ellipse cx="392" cy="506" rx="40" ry="16" fill="#261D20"/>'
            )
            # ---- 嘴巴各形态 ----
            MOUTH_SMILE = ('<path d="M438 605 Q512 655 586 605" fill="none" '
                           'stroke="#7B1831" stroke-width="16" stroke-linecap="round"/>')
            MOUTH_O = ('<ellipse cx="512" cy="628" rx="32" ry="42" fill="url(#mouth)" '
                       'stroke="#7B1831" stroke-width="8"/>')

            # blink/cheerful 保留原“开心嘴”，只换左眼
            faces["blink"] = _face(EYE_CLOSED)
            faces["cheerful"] = _face(EYE_HAPPY)
            faces["surprised"] = _face(EYE_SURPRISED, MOUTH_O)
            faces["sleepy"] = _face(EYE_SLEEPY, MOUTH_SMILE)

            # ---- 扩展表情：心形眼(爱)/晕眩眼(转圈)/星星眼(加油) ----
            EYE_LOVE = (
                '<path d="M384 548 C360 520 330 500 330 472 C330 452 348 440 364 440 '
                'C374 440 380 446 384 454 C388 446 394 440 404 440 C420 440 438 452 '
                '438 472 C438 500 408 520 384 548 Z" fill="#FF5C7A" '
                'stroke="#D63554" stroke-width="5"/>'
            )
            EYE_DIZZY = (
                '<path d="M348 470 L420 540 M420 470 L348 540" fill="none" '
                'stroke="#211A1C" stroke-width="16" stroke-linecap="round"/>'
            )
            EYE_STAR = (
                '<path d="M384 448 C392 488 392 488 434 498 C392 508 392 508 384 548 '
                'C376 508 376 508 334 498 C376 488 376 488 384 448 Z" '
                'fill="#FFD23F" stroke="#E8A900" stroke-width="4"/>'
            )
            faces["love"] = _face(EYE_LOVE)            # 心形眼 + 开心嘴（庆祝）
            faces["dizzy"] = _face(EYE_DIZZY, MOUTH_O)  # 晕眩眼 + O 嘴（转圈）
            faces["cheer"] = _face(EYE_STAR)            # 星星眼 + 开心嘴（加油）
        except Exception:
            pass
        return faces

    def showEvent(self, e):
        """首次显示时关闭 macOS 窗口阴影并让背景完全透明，消除浅色背景下的白色重影。"""
        super().showEvent(e)
        _mac_make_window_truly_transparent(self)

    def _body_rect(self):
        """西瓜本体的判定区（不含给弹跳/手臂/腿预留的透明留白）。

        控件是矩形且比西瓜大一圈，气泡又故意压在右上角，
        若用整个控件当悬停区，光标停在角落会和气泡反复互相触发 enter/leave。
        因此只把本体范围（放宽 1px）算作悬停区——必须比气泡的 2px 间隙更小，
        这样气泡永远落在判定区之外，不会互相触发。"""
        return QRect(self.PAD_X - 1, self.PAD_TOP - 1,
                     self.SIZE + 2, self.SIZE + 2)

    def _check_hover(self):
        """定时轮询光标是否在西瓜本体内，用状态跳变来驱动气泡显隐。

        比 enterEvent/leaveEvent 可靠：既不受「窗口未激活收不到事件」影响，
        也不会因气泡尺寸变化导致的抖动而重复触发。"""
        if not self.isVisible():
            if self._hover_in:
                self._hover_in = False
                self._hide_bubble()
            return
        if self._drag_pos is not None:
            return          # 拖动中：不打扰
        try:
            inside = self._body_rect().contains(self.mapFromGlobal(QCursor.pos()))
        except Exception:
            return
        if inside == self._hover_in:
            return          # 状态没变 → 不换台词，杜绝“飞快切换文字”
        self._hover_in = inside
        if inside:
            self._show_bubble()
        elif not self._forced_bubble_active():
            # 强提醒/庆祝气泡有自己的定时器，别被鼠标移开顺手关掉
            self._hide_bubble()

    def enterEvent(self, e):
        """鼠标移入控件：交由 _check_hover 依据本体判定区决定是否弹气泡。"""
        self._check_hover()
        super().enterEvent(e)

    def leaveEvent(self, e):
        """鼠标移出控件：确保气泡收起。"""
        if self._hover_in:
            self._hover_in = False
            self._hide_bubble()
        super().leaveEvent(e)

    def _show_bubble(self):
        # 「西瓜说话」总开关关闭时，悬停闲聊气泡静音（任务强提醒不受此限）
        if not self.main.cfg.get("bubble_speak", True):
            return
        if getattr(self, "_bubble", None) is None:
            self._bubble = HoverBubble()
        # 悬停气泡由鼠标控制显隐：若此前是“强提醒”自动气泡在显示，停掉自动隐藏计时器
        if getattr(self, "_bubble_hide_timer", None) is not None:
            self._bubble_hide_timer.stop()
        # 悬停只说陪伴/鼓励语，不再随机拎出待办念叨（任务提醒交给“强提醒”负责）
        msg = random.choice(_BALL_SPEECH)
        self._bubble.set_text(msg)
        self._position_bubble()

    def _position_bubble(self):
        """气泡【永远】从西瓜右上方冒出，macOS / Windows 完全一致，绝不强翻到左侧。

        规则（简单、无平台差异、不移动西瓜本体）：
        - 始终放在西瓜本体右侧（body_right + 2）。
        - 不采用“哪边空间大放哪边”的自适应，也不临时挪动西瓜去腾位置。
        - 只有当西瓜贴着屏幕右缘、气泡右侧会顶出屏幕时，才把气泡右缘贴住屏幕右缘
          往左收一点——气泡仍在西瓜右上方，绝不翻到西瓜左边。
        - 找屏幕用“西瓜中心点在哪块屏”(QApplication.screenAt)，避免 Windows 上
          Qt.Tool 无边框窗口 self.screen() 返回错误屏幕导致的左右判定差异。
        """
        # 跨平台稳健地定位西瓜真实所在屏幕：Windows 上无边框/Qt.Tool 窗口的
        # self.screen() 可能返回 None 或错误屏幕，会让“右侧空间”算错、气泡误翻左。
        # 改用西瓜中心点落在哪块屏来判定，杜绝系统差异。
        screen = QApplication.screenAt(self.geometry().center())
        if screen is None:
            screen = self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        sg = screen.availableGeometry() if screen is not None else None

        body_right = self.x() + self.PAD_X + self.SIZE

        # 宽度上限：固定舒适阅读宽度 240px（约 15~16 中文/行），排版稳定不随位置抖动。
        # 只有当西瓜贴屏幕右缘、右侧空间不足时，才临时收窄（下限 180px）保证不顶出屏幕。
        PREF_W = 240
        if sg is not None:
            right_space = sg.right() - (body_right + 2) - 16
            max_w = max(180, min(PREF_W, int(right_space)))
        else:
            max_w = PREF_W
        self._bubble._label.setMaximumWidth(max_w)
        self._bubble.adjustSize()
        bw, bh = self._bubble.width(), self._bubble.height()

        # 默认放右侧：紧贴西瓜本体外沿右 2px（不会盖住本体，不触发 enter/leave 抖动）
        x = body_right + 2
        # 若会顶出屏幕右缘（西瓜贴右边缘时），把气泡右缘贴屏幕右缘往左收，仍在右侧
        if sg is not None and x + bw > sg.right() - 4:
            x = sg.right() - 4 - bw
        # 纵向压到本体顶部上方 2px（盖住本体才会触发 enter/leave 抖动，故不压本体）
        y = self.y() + self.PAD_TOP - bh - 2
        if sg is not None:
            x = max(sg.left() + 4, min(x, sg.right() - bw - 4))
            y = max(sg.top() + 4, min(y, sg.bottom() - bh - 4))
        self._bubble.move(x, y)
        self._bubble.show()
        if IS_MAC:
            _mac_bring_to_front(self._bubble)

    def force_bubble(self, text, ms=6000):
        """强提醒：用指定文案强制弹出气泡，ms 毫秒后自动消失（不抢微信焦点）。"""
        self._show_forced_bubble(text, ms)
        # 强提醒触发时露个惊讶脸 + 蹦一下，吸引注意
        if "surprised" in self._faces:
            self._face = "surprised"
            self._face_left = 2.0
        if self._hop <= 0:
            self._hop = 1.0

    def _show_forced_bubble(self, text, ms=6000):
        """只负责把气泡强行显示并在 ms 毫秒后自动隐藏（不抢焦点），不改表情/动作。"""
        if getattr(self, "_bubble", None) is None:
            self._bubble = HoverBubble()
        self._bubble.set_text(text)
        self._position_bubble()
        if getattr(self, "_bubble_hide_timer", None) is None:
            self._bubble_hide_timer = QTimer(self)
            self._bubble_hide_timer.setSingleShot(True)
            self._bubble_hide_timer.timeout.connect(self._hide_bubble)
        self._bubble_hide_timer.start(max(1000, int(ms)))

    def _celebrate(self, done_today):
        """完成待办后的庆祝：撒花/爱心 + 庆祝脸 + 弹一句庆祝气泡。"""
        n = int(done_today) if done_today else 0
        # 「西瓜说话」关闭时，庆祝气泡静音（撒花/表情照常，只是不说话）
        if self.main.cfg.get("bubble_speak", True):
            msg = self._rnd.choice(_BALL_CELEBRATE).format(n=n)
            self._show_forced_bubble(msg, 5000)
        face = self._rnd.choice(["love", "cheer"])
        if face in self._faces:
            self._face = face
            self._face_left = 2.5
        self._emit_burst()

    def _emit_burst(self):
        """庆祝爆发：混合撒出花瓣/星星/爱心粒子。"""
        import math as _m
        cx = self.W / 2.0
        cy = self.PAD_TOP + self.SIZE / 2.0
        for _ in range(14):
            ang = self._rnd.uniform(0, 2 * _m.pi)
            spd = self._rnd.uniform(40, 110)
            kind = self._rnd.choice(["petal", "star", "heart"])
            self._particles.append({
                "x": cx, "y": cy,
                "vx": _m.cos(ang) * spd,
                "vy": _m.sin(ang) * spd - 60,   # 略向上
                "g": 80.0,                       # 重力
                "life": self._rnd.uniform(0.9, 1.6),
                "max": 1.6,
                "size": self._rnd.uniform(5, 9),
                "rot": self._rnd.uniform(0, 360),
                "vr": self._rnd.uniform(-220, 220),
                "kind": kind,
            })

    def _forced_bubble_active(self):
        """是否正有一条强提醒/庆祝气泡在自动倒计时显示中。"""
        tmr = getattr(self, "_bubble_hide_timer", None)
        return tmr is not None and tmr.isActive()

    def _hide_bubble(self):
        if getattr(self, "_bubble", None) is not None:
            self._bubble.hide()

    def _current_speed(self):
        """根据未完成待办数量算出跑动速度倍率：待办越多跑越快（有上下限）。
        0 个 → 0.5（悠闲散步）；每多 1 个 +0.1；封顶 1.6（快步走，不至于太夸张）。"""
        try:
            total, done, _urgent = self.main.store.stats()
            todo_n = max(0, total - done)
        except Exception:
            todo_n = 0
        return max(0.5, min(1.6, 0.5 + todo_n * 0.1))

    def _on_anim_tick(self):
        # 窗口不可见时不重绘，省 CPU（被完全遮挡/隐藏时避免空转 33fps）
        if not self.isVisible():
            return
        # 每 20 帧刷新一次速度倍率（依据未完成待办数量），避免每帧都算
        self._speed_tick = getattr(self, "_speed_tick", 0) + 1
        if self._speed_tick >= 20 or not hasattr(self, "_speed"):
            self._speed_tick = 0
            self._speed = self._current_speed()
        # 每约 2 秒（60 帧）维护一次置顶状态。
        # 关键修复：macOS 上**绝不**调用会激活本 App 的 QWidget.raise_()
        # （raise_() 会把本 App 提到前台，周期性抢走微信等 App 的键盘/输入法焦点，
        # 导致“有悬浮小西瓜就微信打字失调”）。macOS 分支改为空操作，仅依赖
        # WindowStaysOnTopHint 保持置顶；其它平台保留原 raise_()。
        self._top_tick = getattr(self, "_top_tick", 0) + 1
        if self._top_tick >= 60:
            self._top_tick = 0
            try:
                if IS_MAC:
                    _mac_bring_to_front(self)  # 当前为安全空操作
                else:
                    self.raise_()
            except Exception:
                pass
        # 走路计时：速度越快，时间推进越快 → 步频/弹跳都更快
        dt = 0.03
        self._t += dt * self._speed
        # 随机眨眼：正在眨则递减，否则按概率触发一次眨眼
        if self._blinking > 0:
            self._blinking -= 0.08
            if self._blinking < 0:
                self._blinking = 0.0
        else:
            if self._rnd.random() < 0.012:
                self._blinking = 1.0

        # ---- 动作：偶尔蹦跳一下（跑得快时更爱蹦）----
        if self._hop > 0:
            self._hop = max(0.0, self._hop - 0.06)
        elif self._rnd.random() < 0.004 * (0.6 + 0.8 * (self._speed - 0.5)):
            self._hop = 1.0
        # ---- 动作：偶尔 3D 转身（绕竖直轴转一圈，非 2D 翻跟头；悠闲时爱臭美）----
        if self._turn > 0:
            self._turn -= dt
        elif self._speed <= 0.7 and self._rnd.random() < 0.0015:
            self._turn = self._turn_dur
        # ---- 粒子更新（花瓣/星星/爱心）----
        if self._particles:
            alive = []
            for pt in self._particles:
                pt["x"] += pt["vx"] * dt
                pt["y"] += pt["vy"] * dt
                pt["vy"] += pt["g"] * dt
                pt["rot"] += pt["vr"] * dt
                pt["life"] -= dt
                if pt["life"] > 0:
                    alive.append(pt)
            self._particles = alive
        # ---- 庆祝轮询：每约 2 秒查一次“今日已完成”，增多则庆祝 ----
        if self._celeb_cooldown > 0:
            self._celeb_cooldown -= dt
        self._stat_tick += 1
        if self._stat_tick >= 60:
            self._stat_tick = 0
            try:
                _done = self.main.store.stats()[1]
            except Exception:
                _done = None
            if _done is not None:
                if self._done_today is None:
                    self._done_today = _done
                elif _done > self._done_today and self._celeb_cooldown <= 0:
                    self._celebrate(_done)
                    self._celeb_cooldown = 8.0
                self._done_today = _done

        # ---- 表情调度：眨眼 > 庆祝/心情 > 常态 ----
        if self._blinking > 0.35 and "blink" in self._faces:
            self._face = "blink"
        elif self._face_left > 0:
            self._face_left -= dt
            if self._face_left <= 0:
                self._face = "normal"
        else:
            if self._rnd.random() < 0.006:
                if self._speed <= 0.6:        # 悠闲：犯困/满足
                    self._face = self._rnd.choice(["sleepy", "cheerful"])
                elif self._speed >= 1.3:      # 忙碌：惊讶/打鸡血
                    self._face = self._rnd.choice(["surprised", "cheerful"])
                else:
                    self._face = self._rnd.choice(["cheerful", "surprised"])
                if self._face not in self._faces:
                    self._face = "normal"
                else:
                    self._face_left = self._rnd.uniform(1.6, 3.0)
            else:
                self._face = "normal"
        self.update()

    def paintEvent(self, e):
        import math
        from PySide6.QtGui import (QPainter, QColor, QFont, QPen, QBrush,
                                   QPainterPath, QPixmap)
        from PySide6.QtCore import QPointF, QRectF
        # 离屏缓冲：每帧在全新、绝对干净的透明 pixmap 上绘制，再用 Source 模式整体
        # 替换到窗口（透明区也会一并覆盖窗口旧像素），彻底消除 macOS 上的白色残影/重影。
        _dpr = self.devicePixelRatioF() if hasattr(self, "devicePixelRatioF") else 1.0
        _off = QPixmap(int(self.width() * _dpr), int(self.height() * _dpr))
        _off.setDevicePixelRatio(_dpr)
        _off.fill(QColor(0, 0, 0, 0))
        p = QPainter(_off)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)

        s = self.SIZE
        cx = self.W / 2.0                       # 控件水平中心
        body_x = self.PAD_X
        body_y = self.PAD_TOP
        body_bottom = body_y + s                # 西瓜本体底边

        # 走路相位（speed 越大：步频已由 _t 加速，这里再放大摆幅/弹跳，跑得更有劲）
        spd = getattr(self, "_speed", 1.0)
        vigor = min(1.0, max(0.0, (spd - 0.5) / 1.1))  # 0(悠闲)~1(快步) 的活力系数
        walk = math.sin(self._t * 5.0)          # -1..1
        swing = walk * (5.0 + vigor * 4.0)       # 身体左右摆动角度（度）：越快摆越大
        bob = abs(math.sin(self._t * 5.0)) * (2.0 + vigor * 4.0)  # 上下弹跳：越快颠得越高
        # 蹦跳：触发后能量衰减，叠加一记更高的起跳
        bob += self._hop * (s * 0.22)

        # ===== 依据 watermelon_ball.svg 真实几何（viewBox 1024，三角形西瓜）=====
        # 顶点(512,100)；底边圆弧 Q512 888 813 827，最低点在正中央(512,888)；
        # 左斜边 (443,152)->(135,679)，右斜边 (581,152)->(889,679)。
        def sx(u):  # SVG x(1024) -> 本体局部
            return body_x + s * (u / 1024.0)
        def sy(v):  # SVG y(1024) -> 本体局部
            return body_y + s * (v / 1024.0)
        cx_body = sx(512.0)
        melon_bottom = sy(878.0)   # 底部圆弧中央附近（腿从这里长出）

        limb_color = QColor("#FFFFFF")
        limb = QPen(limb_color, 3)
        limb.setCapStyle(Qt.RoundCap)
        limb.setJoinStyle(Qt.RoundJoin)
        # 黑色描边画笔：比白线更粗，先画它打底，白线盖上去 → 白腿带黑边，白底下也看得见
        limb_edge = QPen(QColor("#222222"), 5)
        limb_edge.setCapStyle(Qt.RoundCap)
        limb_edge.setJoinStyle(Qt.RoundJoin)

        # ================= 统一坐标系：本体 + 眨眼 + 双腿 + 双臂 =================
        # 全部画在同一套 translate(pivot)+rotate(swing) 变换内，
        # 让四肢永远吸附在西瓜身上，一起摇晃/弹跳，绝不脱节。
        p.save()
        pivot_x = cx
        pivot_y = body_bottom
        p.translate(pivot_x, pivot_y - bob)   # 弹跳
        p.rotate(swing)                        # 走路左右摇摆
        p.translate(-pivot_x, -pivot_y)
        # 3D 转身：绕竖直轴转一圈——用水平方向 cos 收缩(1→0→-1→0→1)模拟立体转身，
        # 正→侧→背(镜像)→侧→正，绝非 2D 翻跟头；腿和身体一起转，保持整体感。
        if self._turn > 0:
            prog = 1.0 - max(0.0, min(1.0, self._turn / self._turn_dur))
            turn_sx = math.cos(prog * 2.0 * math.pi)   # 1→0→-1→0→1
            if abs(turn_sx) < 0.06:                     # 侧脸时保留一条薄边，更“立体”
                turn_sx = 0.06 if turn_sx >= 0 else -0.06
            bcx = body_x + s / 2.0
            bcy = body_y + s / 2.0
            p.translate(bcx, bcy)
            p.scale(turn_sx, 1.0)
            p.translate(-bcx, -bcy)

        # ---- 画西瓜本体（按当前表情 _face 切换整脸位图，颜色纹路一致不脱离）----
        target = QRectF(body_x, body_y, s, s)
        face_pm = self._faces.get(self._face) or self._faces.get("normal") or self._pixmap
        if face_pm is not None:
            p.drawPixmap(target, face_pm, QRectF(face_pm.rect()))
        else:
            f = QFont()
            f.setPointSize(int(s * 0.7))
            p.setFont(f)
            p.setPen(QColor("#000000"))
            p.drawText(target, Qt.AlignCenter, "🍉")

        # ---- 两条腿：朝当前行进方向行走，一前一后交替迈步 ----
        DIR = self._dir                              # 行进方向：+1 向右，-1 向左（定时翻转）
        leg_len = s * 0.10
        for i, sign in enumerate((-1, 1)):
            hip_x = sx(512.0 + sign * 62.0)       # 两腿根靠中央
            hip_y = melon_bottom
            # 两条腿相位相差半个周期（一前一后），沿行进方向前后摆
            phase = math.sin(self._t * 5.0 + (0 if i == 0 else math.pi))
            stride = 0.06 + vigor * 0.05              # 迈步幅度：越快甩得越开
            foot_x = hip_x + DIR * phase * s * stride   # 沿行进方向前后迈
            foot_y = hip_y + leg_len
            toe_x = foot_x + DIR * s * 0.05           # 小脚掌：统一朝行进方向
            leg_a = QPointF(hip_x, hip_y)
            leg_b = QPointF(foot_x, foot_y)
            toe_b = QPointF(toe_x, foot_y)
            # 描边起点从大腿根往下偏一点，让连接身体处不描边、自然融入，越往脚黑边越明显
            edge_a = QPointF(
                hip_x + (foot_x - hip_x) * 0.35,
                hip_y + (foot_y - hip_y) * 0.35,
            )
            # 先画黑色描边（粗）打底，再画白线盖上 → 白腿带黑边（根部无边更自然）
            p.setPen(limb_edge)
            p.drawLine(edge_a, leg_b)
            p.drawLine(leg_b, toe_b)
            p.setPen(limb)
            p.drawLine(leg_a, leg_b)
            p.drawLine(leg_b, toe_b)

        # ---- 两条手臂：已按用户要求删除（只保留腿 + 眨眼）----
        # ---- 眨眼由本体 pixmap 整脸切换实现（见上方 face_pm），此处无需再叠加 ----

        p.restore()
        # ---- 粒子（花瓣/星星/爱心），在窗口坐标系内独立飘浮 ----
        if self._particles:
            self._draw_particles(p)
        p.end()
        # 离屏结果整体替换到窗口（Source 模式：透明区也会覆盖窗口旧像素，杜绝残影）
        _wp = QPainter(self)
        _wp.setCompositionMode(QPainter.CompositionMode_Source)
        _wp.drawPixmap(0, 0, _off)
        _wp.end()

    def _draw_particles(self, p):
        """绘制花瓣/星星/爱心粒子（带淡出）。"""
        from PySide6.QtGui import QColor, QBrush, QPainterPath
        from PySide6.QtCore import QPointF
        for pt in self._particles:
            a = max(0.0, min(1.0, pt["life"] / pt["max"]))
            sz = pt["size"]
            p.save()
            p.translate(pt["x"], pt["y"])
            p.rotate(pt["rot"])
            kind = pt["kind"]
            if kind == "petal":
                c = QColor("#FFC2D1"); c.setAlpha(int(255 * a))
                p.setBrush(QBrush(c)); p.setPen(Qt.NoPen)
                p.drawEllipse(QPointF(0, 0), sz, sz * 0.6)
            elif kind == "star":
                path = QPainterPath()
                path.moveTo(0, -sz)
                path.cubicTo(sz * 0.25, -sz * 0.25, sz * 0.25, -sz * 0.25, sz, 0)
                path.cubicTo(sz * 0.25, sz * 0.25, sz * 0.25, sz * 0.25, 0, sz)
                path.cubicTo(-sz * 0.25, sz * 0.25, -sz * 0.25, sz * 0.25, -sz, 0)
                path.cubicTo(-sz * 0.25, -sz * 0.25, -sz * 0.25, -sz * 0.25, 0, -sz)
                c = QColor("#FFD23F"); c.setAlpha(int(255 * a))
                p.setBrush(QBrush(c)); p.setPen(Qt.NoPen)
                p.drawPath(path)
            else:  # heart
                path = QPainterPath()
                path.moveTo(0, sz * 0.6)
                path.cubicTo(-sz * 1.1, -sz * 0.1, -sz * 0.5, -sz * 0.9, 0, -sz * 0.3)
                path.cubicTo(sz * 0.5, -sz * 0.9, sz * 1.1, -sz * 0.1, 0, sz * 0.6)
                c = QColor("#FF5C7A"); c.setAlpha(int(255 * a))
                p.setBrush(QBrush(c)); p.setPen(Qt.NoPen)
                p.drawPath(path)
            p.restore()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self._moved = False
            e.accept()

    def mouseMoveEvent(self, e):
        if self._drag_pos is not None and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            self._moved = True
            e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            if not self._moved:
                # 纯单击（未拖动）→ 唤起主界面
                self.main.summon_to_front()
                # 唤起后主窗口 raise_() 会盖住置顶的小西瓜，这里把西瓜再提到最前
                # （_mac_bring_to_front 不抢前台 App 焦点；非 mac 用 raise_）
                try:
                    if IS_MAC:
                        _mac_bring_to_front(self)
                    else:
                        self.raise_()
                except Exception:
                    pass
            else:
                # 拖动结束：记住位置
                try:
                    g = self.geometry()
                    self.main.cfg["floating_ball_pos"] = [g.x(), g.y()]
                    save_config(self.main.cfg)
                except Exception:
                    pass
            self._drag_pos = None
            e.accept()

    def contextMenuEvent(self, e):
        t = self.main.theme
        m = QMenu(self)
        m.setStyleSheet(f"""
            QMenu {{
                background: {t['panel']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 10px; padding: 6px;
            }}
            QMenu::item {{ padding: 8px 22px; border-radius: 8px; }}
            QMenu::item:selected {{ background: {t['accent']}; color: #FFFFFF; }}
            QMenu::separator {{ height: 1px; background: {t['border']}; margin: 5px 8px; }}
        """)
        act_open = m.addAction("打开主界面")
        m.addSeparator()
        _speak_on = self.main.cfg.get("bubble_speak", True)
        act_speak = m.addAction("关闭西瓜说话" if _speak_on else "开启西瓜说话")
        act_hide = m.addAction("收起悬浮西瓜")
        act_quit = m.addAction("退出程序")
        chosen = m.exec(e.globalPos())
        if chosen == act_open:
            self.main.summon_to_front()
        elif chosen == act_speak:
            self.main.cfg["bubble_speak"] = not _speak_on
            save_config(self.main.cfg)
            if _speak_on:
                # 由开→关：立刻把当前悬停闲聊气泡收起（强提醒不受影响）
                if not self._forced_bubble_active():
                    self._hide_bubble()
        elif chosen == act_hide:
            self.main._toggle_floating_ball()
        elif chosen == act_quit:
            self.main._real_quit()


# ----------------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------------
class TodoWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.store = Store()
        self.cfg = load_config()
        # 注入持久化的自定义主题（DIY 配色，可多套具名），使启动时能直接恢复
        _cts = self.cfg.get("custom_themes")
        if not isinstance(_cts, dict):
            _cts = {}
        _old = self.cfg.get("custom_theme")  # 兼容旧版单套「自定义」
        if isinstance(_old, dict) and _old and "自定义" not in _cts:
            _cts["自定义"] = _old
        self.cfg["custom_themes"] = _cts
        for _nm, _th in _cts.items():
            if isinstance(_th, dict) and _th:
                THEMES[_nm] = _th
                if _nm not in THEME_ORDER:
                    THEME_ORDER.append(_nm)
        self.theme_name = self.cfg.get("theme", "极光白")
        if self.theme_name not in THEMES:
            self.theme_name = "极光白"
        self.theme = THEMES[self.theme_name]
        self.active_cat = "全部"
        self.keyword = ""
        self._drag_pos = None
        self.collapsed = self.cfg.get("collapsed", False)
        self.select_mode = False
        self.selected_ids = set()
        # 视图模式："daily" 日常待办 / "project" 项目待办
        self.view_mode = "daily"
        self.active_project = ""
        self.categories = self.cfg.get("categories") or list(CATEGORIES)
        self._bg_pixmap = None
        self._load_bg_image()

        self.setWindowFlags(
            _float_window_flags(topmost=self.cfg.get("topmost", False)))
        _apply_no_steal_focus(self, accept_focus=True)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setWindowTitle("西瓜todo")

        g = self.cfg.get("geometry", [140, 120, 340, 500])
        if not (isinstance(g, list) and len(g) == 4
                and all(isinstance(v, int) for v in g)):
            g = [140, 120, 340, 500]
        # 展开态高度：至少 420，避免被折叠高度污染
        self.expanded_height = self.cfg.get("expanded_height", g[3])
        if not isinstance(self.expanded_height, int) or self.expanded_height < 420:
            self.expanded_height = 500
        # 防越界：若上次保存的位置落在所有屏幕可见区域之外（例如拔掉副屏、
        # 分辨率变化导致坐标为负或超出边界），窗口会“看不见”像是打不开。
        # 这里把坐标夹回当前主屏可见范围内，保证窗口一定可见。
        try:
            from PySide6.QtWidgets import QApplication as _QApp
            _scr = _QApp.primaryScreen()
            _av = _scr.availableGeometry() if _scr else None
            if _av is not None:
                _w = min(max(g[2], 300), _av.width())
                _h = min(max(self.expanded_height, 420), _av.height())
                _x = min(max(g[0], _av.left()), _av.right() - _w)
                _y = min(max(g[1], _av.top()), _av.bottom() - _h)
                g = [_x, _y, _w, g[3]]
                self.expanded_height = _h
        except Exception:
            pass
        self.cfg["geometry"] = [g[0], g[1], g[2], self.expanded_height]
        self.setGeometry(g[0], g[1], g[2], self.expanded_height)
        self.setMinimumWidth(300)

        # 边缘拖拽调整窗口大小相关状态
        self._resize_margin = 6          # 边缘可触发拉伸的像素范围
        self._resizing = False           # 是否正在拉伸
        self._resize_edges = ""          # 当前命中的边缘（组合：left/right/top/bottom）
        self._resize_start_geo = None    # 拉伸起始时的窗口几何
        self._resize_start_pos = None    # 拉伸起始时的全局鼠标位置
        self.setMouseTracking(True)      # 开启鼠标追踪，实时更新光标形状

        self._build_ui()
        self.refresh()

        # 系统托盘图标（让用户在右下角看到程序正在运行）
        self._setup_tray()

        # 定时提醒
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_reminders)
        self.timer.start(30000)

        # 恢复桌面悬浮小西瓜状态（默认开启：首次打开即显示悬浮西瓜；
        # 曾手动收起的用户会保存 False，仍尊重其选择）
        self.floating_ball = None
        if self.cfg.get("floating_ball", True):
            self._show_floating_ball()

    # -- 圆角背景绘制 --
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        radius = 14 if getattr(self, "collapsed", False) else 20
        path.addRoundedRect(rect, radius, radius)
        bg = self.theme["bg"]
        col = QColor(bg) if len(bg) <= 7 else self._hexa(bg)
        gradient_stops = self.theme.get("gradient")
        if gradient_stops:
            gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
            for position, color in gradient_stops:
                gradient.setColorAt(position, QColor(color))
            p.fillPath(path, QBrush(gradient))
        else:
            p.fillPath(path, QBrush(col))
        # 自定义背景图片（若已上传）：等比裁剪填充窗口，圆角裁剪
        pm = getattr(self, "_bg_pixmap", None)
        if pm is not None and not pm.isNull():
            p.save()
            p.setClipPath(path)
            scaled = pm.scaled(rect.size(), Qt.KeepAspectRatioByExpanding,
                               Qt.SmoothTransformation)
            x = rect.x() + (rect.width() - scaled.width()) // 2
            y = rect.y() + (rect.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
            # 叠加半透明遮罩，保证文字可读
            mask = QColor(col)
            mask.setAlpha(150)
            p.fillPath(path, QBrush(mask))
            p.restore()
        # 细边框
        pen = p.pen()
        pen.setColor(QColor(self.theme["border"]))
        p.setPen(pen)
        p.drawPath(path)

    @staticmethod
    def _hexa(s):
        s = s.lstrip("#")
        r, g, b = int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)
        a = int(s[6:8], 16) if len(s) >= 8 else 255
        return QColor(r, g, b, a)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 14)
        root.setSpacing(11)

        root.addLayout(self._build_titlebar())
        self.stats_box = self._build_stats()
        root.addWidget(self.stats_box)
        root.addLayout(self._build_tabbar())
        root.addLayout(self._build_input())
        root.addWidget(self._build_project_bar())
        root.addWidget(self._build_catbar())

        # 任务列表滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("scroll")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_holder = QWidget()
        self.list_lay = QVBoxLayout(self.list_holder)
        self.list_lay.setContentsMargins(0, 2, 0, 2)
        self.list_lay.setSpacing(7)
        self.list_lay.addStretch()
        self.scroll.setWidget(self.list_holder)
        root.addWidget(self.scroll, 1)

        # 批量操作条（多选模式时显示）
        self.batch_bar = self._build_batch_bar()
        root.addWidget(self.batch_bar)
        self.batch_bar.setVisible(False)

        self._apply_window_style()
        self._apply_view_mode()
        self._apply_collapsed()

    def _build_titlebar(self):
        bar = QHBoxLayout()
        bar.setSpacing(8)

        # 左侧标题 + 随机鼓励语（两行）
        title_col = QVBoxLayout()
        title_col.setSpacing(1)
        self.title_lbl = QLabel("🍉 西瓜todo")
        self.title_lbl.setObjectName("apptitle")
        self.title_lbl.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        title_col.addWidget(self.title_lbl)
        self.nickname = get_nickname()
        self.cheer_lbl = QLabel(random_cheer(self.nickname))
        self.cheer_lbl.setObjectName("cheer")
        self.cheer_lbl.setCursor(Qt.PointingHandCursor)
        # 点击鼓励语可换一句
        self.cheer_lbl.mousePressEvent = self._reroll_cheer
        title_col.addWidget(self.cheer_lbl)
        self.title_col = title_col
        bar.addLayout(title_col)
        bar.addStretch()

        # 多选按钮已移到分类标签行；标题栏保留：主题、菜单在左，折叠/关闭固定最右
        self.btn_theme = QPushButton("🎨")
        self.btn_menu = QPushButton("⋮")
        self.btn_collapse = QPushButton("–")
        self.btn_close = QPushButton("✕")
        for b in (self.btn_theme, self.btn_menu, self.btn_collapse, self.btn_close):
            b.setObjectName("titlebtn")
            b.setFixedSize(30, 30)
            b.setCursor(Qt.PointingHandCursor)
            bar.addWidget(b)
        self.btn_theme.clicked.connect(self._pick_theme)
        self.btn_menu.clicked.connect(self._show_menu)
        self.btn_collapse.clicked.connect(self.hide)
        self.btn_close.clicked.connect(self.hide)  # ✕ 只隐藏到后台，彻底退出请用三个点菜单
        self.btn_close.setToolTip("隐藏到后台（彻底退出请点 ⋮ 菜单）")
        self.btn_close.setObjectName("closebtn")
        return bar

    def _reroll_cheer(self, event=None):
        """点击鼓励语换一句"""
        if hasattr(self, "cheer_lbl"):
            self.cheer_lbl.setText(random_cheer(self.nickname))

    def _show_toast(self, message: str) -> None:
        """在窗口底部短暂显示操作结果。"""
        old_toast = getattr(self, "_toast", None)
        if old_toast is not None:
            old_toast.deleteLater()

        toast = QLabel(message, self)
        toast.setObjectName("toast")
        toast.setAlignment(Qt.AlignCenter)
        toast.setWordWrap(True)
        toast.setMaximumWidth(max(220, self.width() - 40))
        toast.setStyleSheet(f"""
            QLabel#toast {{
                background: {self.theme['text']};
                color: {self.theme['panel']};
                border-radius: 10px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }}
        """)
        toast.adjustSize()
        toast.move(
            max(12, (self.width() - toast.width()) // 2),
            max(12, self.height() - toast.height() - 22),
        )
        toast.show()
        toast.raise_()
        self._toast = toast

        def _remove_toast() -> None:
            if getattr(self, "_toast", None) is toast:
                self._toast = None
            toast.deleteLater()

        QTimer.singleShot(2200, _remove_toast)

    def _build_stats(self):
        box = QFrame()
        box.setObjectName("stats")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 12, 14, 13)
        lay.setSpacing(9)
        top = QHBoxLayout()
        self.stats_text = QLabel("今日 0/0")
        self.stats_text.setObjectName("statstext")
        top.addWidget(self.stats_text)
        top.addStretch()
        self.stats_pct = QLabel("0%")
        self.stats_pct.setObjectName("statspct")
        top.addWidget(self.stats_pct)
        lay.addLayout(top)
        # 进度条
        self.bar_bg = QFrame()
        self.bar_bg.setObjectName("barbg")
        self.bar_bg.setFixedHeight(8)
        self.bar_fg = QFrame(self.bar_bg)
        self.bar_fg.setObjectName("barfg")
        self.bar_fg.setGeometry(0, 0, 0, 8)
        lay.addWidget(self.bar_bg)
        return box

    def _build_tabbar(self):
        """日常待办 / 项目待办 两个视图切换标签"""
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.tab_btns = {}
        for key, label in (("daily", "📋 日常待办"), ("project", "📁 项目待办")):
            b = QPushButton(label)
            b.setObjectName("tabbtn")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(key == self.view_mode)
            b.clicked.connect(lambda _=False, k=key: self._switch_view(k))
            self.tab_btns[key] = b
            bar.addWidget(b, 1)
        return bar

    def _switch_view(self, mode):
        if mode == self.view_mode:
            return
        self.view_mode = mode
        # 切换视图时退出多选，避免选中态错乱
        if self.select_mode:
            self._toggle_select_mode()
        for k, b in self.tab_btns.items():
            b.setChecked(k == mode)
        self._apply_view_mode()
        self.refresh()

    def _apply_view_mode(self):
        """根据当前视图模式显示/隐藏对应工具栏"""
        is_proj = self.view_mode == "project"
        # 日常待办用分类栏 + 添加按钮；项目待办用项目栏
        if hasattr(self, "project_bar"):
            self.project_bar.setVisible(is_proj)
        if hasattr(self, "btn_add"):
            self.btn_add.setVisible(not is_proj)
        # 分类筛选栏在项目视图下隐藏
        if hasattr(self, "cat_btns"):
            for b in self.cat_btns.values():
                b.setVisible(not is_proj)
        if hasattr(self, "catbar_widget"):
            self.catbar_widget.setVisible(not is_proj)
        if hasattr(self, "btn_multi"):
            self.btn_multi.setVisible(not is_proj)
        if hasattr(self, "btn_project_multi"):
            self.btn_project_multi.setVisible(is_proj)
            self.btn_project_sel_all.setVisible(is_proj and self.select_mode)
        if is_proj:
            self._refresh_project_pick()

    def _build_project_bar(self):
        """项目待办工具栏：项目下拉（独占一行）+ 批量导入/导出（下一行）（默认隐藏）"""
        bar = QFrame()
        bar.setObjectName("projbar")
        outer = QVBoxLayout(bar)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        # 第一行：项目名称下拉（独占整行，展示更宽）
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(6)
        self.proj_pick = QComboBox(self)
        self.proj_pick.setObjectName("projpick")
        self.proj_pick.setMinimumHeight(34)
        self.proj_pick.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.proj_pick.activated.connect(self._on_project_pick)
        row1.addWidget(self.proj_pick, 1)
        # 管理项目入口：弹出所有项目可重命名/删除
        self.btn_proj_manage = QPushButton("⚙")
        self.btn_proj_manage.setObjectName("secondarybtn")
        self.btn_proj_manage.setFixedSize(34, 34)
        self.btn_proj_manage.setToolTip("管理项目（重命名 / 删除）")
        self.btn_proj_manage.setCursor(Qt.PointingHandCursor)
        self.btn_proj_manage.clicked.connect(self._manage_projects_dialog)
        row1.addWidget(self.btn_proj_manage)
        outer.addLayout(row1)
        # 第二行：批量导入（宽）+ 导出 + 多选（等比更宽，配色区分）
        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(8)
        self.btn_import = QPushButton("＋ 添加待办")
        self.btn_import.setObjectName("secondarybtn")
        self.btn_import.setFixedHeight(36)
        self.btn_import.setCursor(Qt.PointingHandCursor)
        self.btn_import.clicked.connect(self._batch_import_dialog)
        row2.addWidget(self.btn_import, 3)
        self.btn_export = QPushButton("⬇ 导出")
        self.btn_export.setObjectName("secondarybtn")
        self.btn_export.setFixedHeight(36)
        self.btn_export.setCursor(Qt.PointingHandCursor)
        self.btn_export.clicked.connect(self._export_project)
        row2.addWidget(self.btn_export, 1)
        self.btn_project_multi = QPushButton("多选")
        self.btn_project_multi.setObjectName("secondarybtn")
        self.btn_project_multi.setFixedHeight(36)
        self.btn_project_multi.setCursor(Qt.PointingHandCursor)
        self.btn_project_multi.clicked.connect(self._toggle_select_mode)
        row2.addWidget(self.btn_project_multi, 1)
        self.btn_project_sel_all = QPushButton("全选")
        self.btn_project_sel_all.setObjectName("selallbtn")
        self.btn_project_sel_all.setFixedHeight(36)
        self.btn_project_sel_all.setCursor(Qt.PointingHandCursor)
        self.btn_project_sel_all.clicked.connect(self._batch_select_all)
        self.btn_project_sel_all.setVisible(False)
        row2.addWidget(self.btn_project_sel_all, 1)
        outer.addLayout(row2)
        self.project_bar = bar
        bar.setVisible(False)
        return bar

    def _refresh_project_pick(self):
        """刷新项目下拉框内容，保持当前选中"""
        if not hasattr(self, "proj_pick"):
            return
        projs = self.store.projects()
        self.proj_pick.blockSignals(True)
        self.proj_pick.clear()
        if projs:
            self.proj_pick.addItems(projs)
            if self.active_project not in projs:
                self.active_project = projs[0]
            self.proj_pick.setCurrentText(self.active_project)
        else:
            self.proj_pick.addItem("（暂无项目，点击添加待办新建）")
            self.active_project = ""
        self.proj_pick.blockSignals(False)

    def _on_project_pick(self, idx):
        projs = self.store.projects()
        if 0 <= idx < len(projs):
            self.active_project = projs[idx]
            if self.select_mode:
                self.selected_ids.clear()
                self._update_batch_lbl()
            self.refresh()

    # -- 项目管理 --
    def _manage_projects_dialog(self):
        """弹窗：列出所有项目，支持重命名 / 删除整个项目"""
        from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QListWidget,
                                       QListWidgetItem, QMessageBox, QInputDialog)
        projs = self.store.projects()
        dlg = QDialog(self)
        dlg.setWindowTitle("管理项目")
        dlg.setStyleSheet(self._dialog_qss())
        dlg.setMinimumWidth(360)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)
        if not projs:
            v.addWidget(QLabel("暂无项目，先用「添加待办」新建吧～"))
            bb = QDialogButtonBox(QDialogButtonBox.Ok)
            bb.accepted.connect(dlg.accept)
            v.addWidget(bb)
            dlg.exec()
            return
        v.addWidget(QLabel("选中一个项目后可重命名或删除："))
        lst = QListWidget()
        for p in projs:
            total, done = self.store.project_stats(p)
            it = QListWidgetItem(f"{p}   （{done}/{total}）")
            it.setData(Qt.UserRole, p)
            lst.addItem(it)
        lst.setCurrentRow(0)
        v.addWidget(lst)

        row = QHBoxLayout()
        btn_rename = QPushButton("✎ 重命名")
        btn_rename.setObjectName("secondarybtn")
        btn_del = QPushButton("🗑 删除项目")
        btn_del.setObjectName("secondarybtn")
        row.addWidget(btn_rename, 1)
        row.addWidget(btn_del, 1)
        v.addLayout(row)

        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(dlg.reject)
        bb.button(QDialogButtonBox.Close).clicked.connect(dlg.reject)
        v.addWidget(bb)

        def _cur_proj():
            it = lst.currentItem()
            return it.data(Qt.UserRole) if it else None

        def _do_rename():
            p = _cur_proj()
            if not p:
                return
            new, ok = QInputDialog.getText(dlg, "重命名项目", "新的项目名称：", text=p)
            new = (new or "").strip()
            if ok and new and new != p:
                self.store.rename_project(p, new)
                if self.active_project == p:
                    self.active_project = new
                self._refresh_project_pick()
                self.refresh()
                dlg.accept()

        def _do_delete():
            p = _cur_proj()
            if not p:
                return
            total, _ = self.store.project_stats(p)
            m = QMessageBox(dlg)
            m.setWindowTitle("删除项目")
            m.setText(f"确定删除项目「{p}」吗？\n该项目下 {total} 条待办将一并删除，不可恢复。")
            m.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            m.setDefaultButton(QMessageBox.No)
            if m.exec() == QMessageBox.Yes:
                self.store.delete_project(p)
                if self.active_project == p:
                    self.active_project = ""
                self._refresh_project_pick()
                self.refresh()
                dlg.accept()

        btn_rename.clicked.connect(_do_rename)
        btn_del.clicked.connect(_do_delete)
        dlg.exec()

    # -- 添加待办（批量粘贴 / 单个填写，Tab 分页）--
    def _batch_import_dialog(self):
        """弹窗：Tab 分页「批量粘贴」/「单个填写」，两页数据隔离，归入一个项目。"""
        from PySide6.QtWidgets import (
            QDialog, QDialogButtonBox, QTabWidget, QWidget)
        dlg = QDialog(self)
        dlg.setWindowTitle("添加待办")
        dlg.setStyleSheet(self._dialog_qss())
        dlg.setMinimumWidth(380)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)

        # 上次表单记忆（分类/紧急度，项目不记）
        mem = getattr(self, "_add_form_memory", None) or {}

        # ---- 项目名：二选一（下拉选已有 / ➕新建项目）----
        v.addWidget(QLabel("项目名称"))
        NEW = "➕ 新建项目…"
        existing = self.store.projects()
        proj_pick = QComboBox()
        proj_pick.addItem(NEW)
        proj_pick.addItems(existing)
        proj_new = QLineEdit()
        proj_new.setPlaceholderText("输入新项目名，例如：2026-W30 本周项目")

        def _sync_proj():
            proj_new.setVisible(proj_pick.currentText() == NEW)
        proj_pick.currentIndexChanged.connect(lambda _=None: _sync_proj())
        if self.active_project and self.active_project in existing:
            proj_pick.setCurrentText(self.active_project)
        elif existing:
            proj_pick.setCurrentIndex(1)
        v.addWidget(proj_pick)
        v.addWidget(proj_new)
        _sync_proj()

        # ---- 分类 / 优先级（带记忆回填）----
        row = QHBoxLayout(); row.setSpacing(10)
        cbox = QVBoxLayout(); cbox.setSpacing(4)
        cbox.addWidget(QLabel("分类"))
        cat = QComboBox(); cat.addItems(self.categories)
        if mem.get("category") in self.categories:
            cat.setCurrentText(mem["category"])
        cbox.addWidget(cat); row.addLayout(cbox, 1)
        pbox = QVBoxLayout(); pbox.setSpacing(4)
        pbox.addWidget(QLabel("紧急程度"))
        pr = QComboBox(); pr.addItems(PRIORITIES)
        pr.setCurrentText(mem["priority"]
                          if mem.get("priority") in PRIORITIES else "普通")
        pbox.addWidget(pr); row.addLayout(pbox, 1)
        v.addLayout(row)

        # ---- Tab 分页 ----
        tabs = QTabWidget()
        page_batch = QWidget(); pb = QVBoxLayout(page_batch)
        pb.setContentsMargins(0, 8, 0, 0); pb.setSpacing(8)
        page_single = QWidget(); ps = QVBoxLayout(page_single)
        ps.setContentsMargins(0, 8, 0, 0); ps.setSpacing(8)

        # 批量粘贴页
        te = QTextEdit()
        te.setPlaceholderText(
            "示例：\n"
            "【P1】完成周报｜08-05｜补充关键数据\n"
            "对齐需求｜明天\n"
            "评审设计稿\n"
            "每行一条待办，竖线分隔：内容｜优先级｜日期｜备注")
        te.setMinimumHeight(150)
        te.setTabChangesFocus(True)
        pb.addWidget(te)
        hint = QLabel(
            "格式：内容 | 优先级 | 日期 | 备注（后三项都可省略）\n"
            "· 优先级：" + " / ".join(PRIORITIES) + "\n"
            "· 日期：08-05、2026-08-05、明天、周五 等\n"
            "· 第2列不是优先级词时当备注；支持从 Excel 直接粘贴（Tab 分列）")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{self.theme['sub']};font-weight:normal;")
        pb.addWidget(hint)
        pb.addWidget(QLabel("解析预览"))
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setFixedHeight(96)
        preview.setStyleSheet(
            f"QTextEdit{{border:1px dashed {_qss_alpha(self.theme['accent'], 0x66)};"
            f"border-radius:8px;background:{_qss_alpha(self.theme['accent'], 0x10)};"
            f"color:{self.theme['sub']};padding:6px;font-size:12px;}}")
        pb.addWidget(preview)

        def _refresh_preview():
            default_pr = pr.currentText()
            rows = []; ok = 0
            for raw in te.toPlainText().splitlines():
                if not raw.strip():
                    continue
                p = self.store._parse_batch_line(raw)
                if not p:
                    continue
                ok += 1
                seg = [p["text"], p["priority"] or default_pr + "(默认)"]
                if p["due"]:
                    seg.append("📅" + p["due"])
                if p["note"]:
                    seg.append("📝" + p["note"])
                rows.append("· " + "　".join(seg))
            if ok:
                preview.setPlainText(f"共 {ok} 条：\n" + "\n".join(rows))
            else:
                preview.setPlainText("（在上方输入后这里显示解析结果）")
        te.textChanged.connect(_refresh_preview)
        pr.currentTextChanged.connect(lambda _=None: _refresh_preview())
        _refresh_preview()

        # 单个填写页
        ps.addWidget(QLabel("待办内容"))
        single_text = QLineEdit()
        single_text.setPlaceholderText("这条待办要做什么？")
        ps.addWidget(single_text)
        # 截止日期（循环/提醒/循环截止折叠其中，与编辑待办一致）
        ps.addWidget(QLabel("截止日期"))
        _single_due = {"val": ""}
        _single_recur = {"val": "不循环"}
        _single_remind = {"val": "到期当天"}
        _single_rend = {"val": ""}
        srow = QHBoxLayout(); srow.setSpacing(8)
        btn_single_due = QPushButton("📅  点击选择日期")
        btn_single_due.setCursor(Qt.PointingHandCursor)
        def _pick_single_due():
            prev = self._pending_due
            self._pending_due = _single_due["val"]
            self._pick_due(recur_state=_single_recur, remind_state=_single_remind,
                           recur_end_state=_single_rend)
            _single_due["val"] = self._pending_due
            self._pending_due = prev
            btn_single_due.setText(
                f"📅  {_single_due['val']}" if _single_due["val"] else "📅  点击选择日期")
        btn_single_due.clicked.connect(_pick_single_due)
        srow.addWidget(btn_single_due, 1)
        btn_single_due_clear = QPushButton("清除")
        btn_single_due_clear.setCursor(Qt.PointingHandCursor)
        def _clear_single_due():
            _single_due["val"] = ""
            btn_single_due.setText("📅  点击选择日期")
        btn_single_due_clear.clicked.connect(_clear_single_due)
        srow.addWidget(btn_single_due_clear)
        ps.addLayout(srow)
        ps.addWidget(QLabel("备注（可选）"))
        single_note = QTextEdit()
        single_note.setPlaceholderText("记录进行中的注意事项…")
        single_note.setFixedHeight(90)
        single_note.setStyleSheet(
            f"QTextEdit{{border:1px solid {_qss_alpha(self.theme['accent'], 0x66)};"
            f"border-left:3px solid {self.theme['accent']};border-radius:8px;"
            f"background:{_qss_alpha(self.theme['accent'], 0x18)};"
            f"color:{self.theme['text']};padding:6px;}}")
        ps.addWidget(single_note)
        ps.addStretch(1)

        tabs.addTab(page_batch, "📥 批量粘贴")
        tabs.addTab(page_single, "✏️ 单个填写")
        tabs.setCurrentIndex(0)
        v.addWidget(tabs)

        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("添加")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)

        if dlg.exec() != QDialog.Accepted:
            return
        if proj_pick.currentText() == NEW:
            project = proj_new.text().strip()
        else:
            project = proj_pick.currentText().strip()
        if not project:
            self._show_toast("请填写或选择项目名称")
            return

        is_batch = (tabs.currentIndex() == 0)
        if is_batch:
            lines = te.toPlainText().splitlines()
            parsed = [p for p in (self.store._parse_batch_line(ln)
                                  for ln in lines) if p]
            if not parsed:
                self._show_toast("没有可导入的内容")
                return
            exist_names = {
                (t.get("text", "") or "").strip()
                for t in self.store.tasks
                if t.get("project", "") == project
            }
            dup = [p for p in parsed if p["text"] in exist_names]
            skip_dup = False
            if dup:
                choice = self._dup_confirm_dialog(len(dup))
                if choice == "cancel":
                    return
                skip_dup = (choice == "skip")
            feed = ([p for p in parsed if p["text"] not in exist_names]
                    if skip_dup else parsed)
            rebuilt = []
            for p in feed:
                cols = [p["text"]]
                if p["priority"]:
                    cols.append(p["priority"])
                if p["due"]:
                    cols.append(p["due"])
                if p["note"]:
                    cols.append(p["note"])
                rebuilt.append(" | ".join(cols))
            n = self.store.add_batch(rebuilt, project=project,
                                     category=cat.currentText(),
                                     priority=pr.currentText())
            skipped = (len(parsed) - len(feed)) if skip_dup else 0
        else:
            txt = single_text.text().strip()
            if not txt:
                self._show_toast("请填写待办内容")
                return
            self.store.add(txt, category=cat.currentText(),
                           due=_single_due["val"],
                           priority=pr.currentText(),
                           recur=_single_recur["val"],
                           recur_end=_single_rend["val"],
                           remind=_single_remind["val"],
                           note=single_note.toPlainText().strip(),
                           project=project)
            n = 1; skipped = 0
        if n == 0:
            self._show_toast("没有新增内容")
            return
        self._add_form_memory = {
            "category": cat.currentText(),
            "priority": pr.currentText(),
        }
        self.active_project = project
        self.view_mode = "project"
        for k, b in self.tab_btns.items():
            b.setChecked(k == "project")
        self._apply_view_mode()
        self.refresh()
        msg = f"已添加 {n} 条到「{project}」"
        if skipped:
            msg += f"，跳过 {skipped} 条重复"
        self._show_toast(msg)

    def _dup_confirm_dialog(self, count):
        """检测到疑似重复时的三选一弹窗，返回 'add'/'skip'/'cancel'。"""
        from PySide6.QtWidgets import QDialog
        dlg = QDialog(self)
        dlg.setWindowTitle("检测到重复")
        dlg.setStyleSheet(self._dialog_qss())
        dlg.setMinimumWidth(300)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 18, 20, 18); v.setSpacing(12)
        lbl = QLabel(f"检测到 {count} 条与现有待办同名，如何处理？")
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"color:{self.theme['text']};")
        v.addWidget(lbl)
        result = {"v": "cancel"}
        rowb = QHBoxLayout(); rowb.setSpacing(8)
        b_skip = QPushButton("跳过重复")
        b_add = QPushButton("继续新增")
        b_cancel = QPushButton("取消")
        for b in (b_skip, b_add, b_cancel):
            b.setCursor(Qt.PointingHandCursor)
        def _pick(val):
            result["v"] = val; dlg.accept()
        b_skip.clicked.connect(lambda: _pick("skip"))
        b_add.clicked.connect(lambda: _pick("add"))
        b_cancel.clicked.connect(lambda: _pick("cancel"))
        rowb.addWidget(b_skip, 1); rowb.addWidget(b_add, 1)
        rowb.addWidget(b_cancel, 1)
        v.addLayout(rowb)
        dlg.exec()
        return result["v"]

    # -- 通用导出：把一批任务写入 CSV / TXT --
    def _task_export_date(self, t):
        """取任务用于日期区间过滤的日期(YYYY-MM-DD)：
        优先截止日期(due)，未填则回退创建当日(created)。"""
        due = (t.get("due", "") or "").strip()
        if due:
            return due[:10]
        created = (t.get("created", "") or "").strip()
        return created[:10] if created else ""

    def _write_tasks_export(self, path, items, header_lines=None,
                            with_project_col=False):
        """把任务列表写入文件（CSV 或 TXT），返回是否成功。

        header_lines: TXT 顶部说明行列表；CSV 时忽略。
        with_project_col: CSV 是否额外输出「项目」列。
        """
        try:
            is_csv = path.lower().endswith(".csv")
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                if is_csv:
                    import csv
                    w = csv.writer(f)
                    cols = ["状态", "待办内容", "分类", "优先级", "截止", "备注"]
                    if with_project_col:
                        cols = ["项目"] + cols
                    w.writerow(cols)
                    for t in items:
                        row = [
                            "已完成" if t.get("status") == "done" else "未完成",
                            t.get("text", ""), t.get("category", ""),
                            t.get("priority", ""), t.get("due", ""),
                            t.get("note", "").replace("\n", " "),
                        ]
                        if with_project_col:
                            row = [t.get("project", "")] + row
                        w.writerow(row)
                else:
                    for hl in (header_lines or []):
                        f.write(hl + "\n")
                    if header_lines:
                        f.write("=" * 30 + "\n")
                    for t in items:
                        mark = "[✓]" if t.get("status") == "done" else "[ ]"
                        line = f"{mark} {t.get('text', '')}"
                        if t.get("due"):
                            line += f"  (截止 {t.get('due')})"
                        f.write(line + "\n")
                        if t.get("note"):
                            f.write(f"    备注：{t.get('note')}\n")
            self._show_toast(f"已导出：{os.path.basename(path)}")
            return True
        except Exception as ex:
            self._show_toast(f"导出失败：{ex}")
            return False

    # -- 导出当前项目 --
    def _export_project(self):
        if self.view_mode != "project" or not self.active_project:
            self._show_toast("请先选择一个项目")
            return
        items = [t for t in self.store.tasks
                 if t.get("project", "") == self.active_project]
        if not items:
            self._show_toast("该项目暂无待办")
            return
        total, done = self.store.project_stats(self.active_project)
        # 排序：未完成在前
        items = sorted(items, key=lambda t: (t.get("status") == "done",
                                             t.get("created", "")))
        default_name = f"{self.active_project}_完成情况.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出项目完成情况", default_name,
            "CSV 文件 (*.csv);;文本文件 (*.txt)")
        if not path:
            return
        header = [f"项目：{self.active_project}", f"完成情况：{done}/{total}"]
        self._write_tasks_export(path, items, header_lines=header)

    # -- 导出首页待办（按日期区间 + 完成状态筛选）--
    def _export_daily_dialog(self):
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        from PySide6.QtCore import QDate
        dlg = QDialog(self)
        dlg.setWindowTitle("导出待办")
        dlg.setStyleSheet(self._dialog_qss())
        dlg.setMinimumWidth(340)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)
        hint = QLabel("按日期区间与完成状态筛选后导出（无截止日期的按创建当日计算）")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{self.theme['sub']};font-weight:normal;")
        v.addWidget(hint)
        # 日期区间：开始 / 结束（复用日历弹窗）
        _range = {"from": "", "to": ""}
        v.addWidget(QLabel("日期区间（可留空表示不限）"))
        drow = QHBoxLayout(); drow.setSpacing(8)
        btn_from = QPushButton("📅  开始日期")
        btn_to = QPushButton("📅  结束日期")
        for b in (btn_from, btn_to):
            b.setCursor(Qt.PointingHandCursor)

        def _pick_range(key, btn, label):
            prev = self._pending_due
            self._pending_due = _range[key]
            self._pick_due()
            _range[key] = (self._pending_due or "")[:10]
            self._pending_due = prev
            btn.setText(f"📅  {_range[key]}" if _range[key] else f"📅  {label}")
        btn_from.clicked.connect(lambda: _pick_range("from", btn_from, "开始日期"))
        btn_to.clicked.connect(lambda: _pick_range("to", btn_to, "结束日期"))
        drow.addWidget(btn_from, 1); drow.addWidget(btn_to, 1)
        v.addLayout(drow)
        # 完成状态
        v.addWidget(QLabel("完成状态"))
        st = QComboBox(); st.addItems(["全部", "仅未完成", "仅已完成"])
        v.addWidget(st)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("导出")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() != QDialog.Accepted:
            return
        d_from, d_to = _range["from"], _range["to"]
        want = st.currentText()
        # 仅导出首页待办（非项目任务）
        items = [t for t in self.store.tasks if not t.get("project", "")]
        picked = []
        for t in items:
            if want == "仅未完成" and t.get("status") == "done":
                continue
            if want == "仅已完成" and t.get("status") != "done":
                continue
            d = self._task_export_date(t)
            if d_from and (not d or d < d_from):
                continue
            if d_to and (not d or d > d_to):
                continue
            picked.append(t)
        if not picked:
            self._show_toast("没有符合条件的待办")
            return
        picked = sorted(picked, key=lambda t: (t.get("status") == "done",
                                               self._task_export_date(t)))
        rng = f"{d_from or '不限'} ~ {d_to or '不限'}"
        default_name = "待办导出.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出待办", default_name,
            "CSV 文件 (*.csv);;文本文件 (*.txt)")
        if not path:
            return
        header = [f"导出范围：{rng}", f"完成状态：{want}",
                  f"共 {len(picked)} 条"]
        self._write_tasks_export(path, picked, header_lines=header)


    def _build_input(self):
        lay = QHBoxLayout()
        lay.setSpacing(8)
        # 隐藏控件：保留以兼容内部逻辑（分类/日期/优先级），不显示在界面上
        # 注意必须指定 parent=self，否则无父窗口的控件会作为独立顶级窗口浮空闪现
        self.input = QLineEdit(self)
        self.input.setObjectName("input")
        self.input.hide()

        self.cat_pick = QComboBox(self)
        self.cat_pick.setObjectName("catpick")
        self.cat_pick.addItems(self.categories)
        self.cat_pick.addItem("＋新建…")
        self.cat_pick.activated.connect(self._on_catpick)
        self.cat_pick.hide()

        self.pr_pick = QComboBox(self)
        self.pr_pick.setObjectName("prpick")
        self.pr_pick.addItems(PRIORITIES)
        self.pr_pick.setCurrentText("普通")
        self.pr_pick.hide()

        self._pending_due = ""
        self.btn_date = QPushButton("📅", self)
        self.btn_date.setObjectName("datebtn")
        self.btn_date.hide()

        # 界面上只放一个大按钮：点击后新建一条待办并直接进入编辑
        self.btn_add = QPushButton("＋ 添加待办")
        self.btn_add.setObjectName("addbtn")
        self.btn_add.setFixedHeight(40)
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_and_edit)
        lay.addWidget(self.btn_add, 1)
        return lay

    def _add_and_edit(self):
        """在待办列表最上面新起一个内联可编辑行（含日期/优先级/循环等选项）"""
        # 若已有内联编辑行则聚焦，不重复创建
        if getattr(self, "_inline_row", None) is not None:
            try:
                self._inline_edit.setFocus()
            except Exception:
                pass
            return
        self._inline_due = ""
        row = QWidget()
        row.setObjectName("inlinerow")
        outer = QVBoxLayout(row)
        outer.setContentsMargins(10, 8, 10, 8)
        outer.setSpacing(6)

        # 第一行：内容 + 日期 + 保存 + 取消
        rl = QHBoxLayout()
        rl.setSpacing(8)
        ed = QLineEdit()
        ed.setObjectName("inlineedit")
        ed.setPlaceholderText("输入待办内容，回车保存…")
        rl.addWidget(ed, 1)

        btn_cal = QPushButton("📅")
        btn_cal.setObjectName("inlinedate")
        btn_cal.setFixedSize(46, 30)
        btn_cal.setCursor(Qt.PointingHandCursor)
        rl.addWidget(btn_cal)

        btn_ok = QPushButton("✓")
        btn_ok.setObjectName("inlineok")
        btn_ok.setFixedSize(34, 30)
        btn_ok.setCursor(Qt.PointingHandCursor)
        rl.addWidget(btn_ok)

        btn_cancel = QPushButton("✕")
        btn_cancel.setObjectName("inlinecancel")
        btn_cancel.setFixedSize(34, 30)
        btn_cancel.setCursor(Qt.PointingHandCursor)
        rl.addWidget(btn_cancel)
        outer.addLayout(rl)

        # 第二行：分类 + 优先级 + 提醒
        rl2 = QHBoxLayout()
        rl2.setSpacing(6)
        ct = QComboBox()
        ct.setObjectName("inlinect")
        ct.addItems(self.categories)
        # 默认跟随当前所在分类；“全部”下默认“其他”，不再默认第一项(工作)
        if self.active_cat != "全部" and self.active_cat in self.categories:
            ct.setCurrentText(self.active_cat)
        elif "其他" in self.categories:
            ct.setCurrentText("其他")
        ct.setFixedHeight(26)
        rl2.addWidget(ct, 1)

        pr = QComboBox()
        pr.setObjectName("inlinepr")
        pr.addItems(PRIORITIES)
        pr.setCurrentText("普通")
        pr.setFixedHeight(26)
        rl2.addWidget(pr, 1)
        outer.addLayout(rl2)

        # 提醒时间已合并到「日期弹窗」底部
        self._inline_remind_val = "到期当天"

        # 循环设置已合并到「日期弹窗」底部，内联行不再单独放循环行（减少按钮）
        self._inline_recur_val = "不循环"
        self._inline_rend_val = ""

        row.setStyleSheet(
            f"#inlinerow{{background:{self.theme['card']};border:1px solid "
            f"{_qss_alpha(self.theme['accent'], 0x80)};border-radius:13px;}}"
            f"#inlineedit{{border:none;background:transparent;font-size:14px;"
            f"color:{self.theme['text']};}}"
            f"#inlinedate,#inlineok,#inlinecancel{{border:1px solid {self.theme['border']};"
            f"border-radius:8px;background:{self.theme['panel']};"
            f"color:{self.theme['sub']};font-size:14px;}}"
            f"#inlinedate:hover{{color:{self.theme['accent']};"
            f"border-color:{self.theme['accent']};}}"
            f"#inlineok{{color:#FFFFFF;background:{self.theme['accent']};"
            f"border-color:{self.theme['accent']};font-weight:bold;}}"
            f"#inlineok:hover{{background:{self.theme['accent2']};"
            f"border-color:{self.theme['accent2']};}}"
            f"#inlinecancel:hover{{color:#FFFFFF;background:#E5484D;border-color:#E5484D;}}"
            f"#inlinepr,#inlinerc,#inlinerend,#inlinect,#inlinermd{{border:1px solid {self.theme['border']};"
            f"border-radius:13px;background:{self.theme['panel']};color:{self.theme['text']};"
            f"font-size:11px;padding:2px 10px;}}"
            f"#inlinepr:hover,#inlinerc:hover,#inlinerend:hover,#inlinect:hover,#inlinermd:hover{{"
            f"border:1px solid {self.theme['accent']};}}"
            f"#inlinepr::drop-down,#inlinerc::drop-down,#inlinect::drop-down,#inlinermd::drop-down{{border:none;width:28px;"
            f"background:transparent;subcontrol-origin:padding;"
            f"subcontrol-position:right center;}}"
            f"#inlinepr::down-arrow,#inlinerc::down-arrow,#inlinect::down-arrow,#inlinermd::down-arrow{{"
            f"image:none;width:0;height:0;border:none;background:transparent;}}"
            f"#inlinepr QAbstractItemView,#inlinerc QAbstractItemView,#inlinect QAbstractItemView,#inlinermd QAbstractItemView{{"
            f"border:1px solid {self.theme['border']};border-radius:8px;"
            f"background:{self.theme['panel']};color:{self.theme['text']};"
            f"outline:none;padding:4px;"
            f"selection-background-color:{self.theme['accent']};"
            f"selection-color:#ffffff;}}"
        )

        self._inline_row = row
        self._inline_edit = ed
        self._inline_datebtn = btn_cal
        self._inline_pr = pr
        self._inline_ct = ct
        self._inline_rmd = None
        self._inline_rc = None
        self._inline_rendbtn = None

        def pick_date():
            self._pick_inline_due()
        def save():
            self._save_inline()
        def cancel():
            self._close_inline()

        btn_cal.clicked.connect(pick_date)
        btn_ok.clicked.connect(save)
        btn_cancel.clicked.connect(cancel)
        ed.returnPressed.connect(save)

        # 插入到列表最上面
        self.list_lay.insertWidget(0, row)
        ed.setFocus()

    def _pick_inline_recur_end(self):
        """为内联行选择循环截止日期（复用日历弹窗）"""
        prev = self._pending_due
        self._pending_due = getattr(self, "_inline_rend_val", "")
        self._pick_due()
        self._inline_rend_val = self._pending_due
        self._pending_due = prev
        if getattr(self, "_inline_rendbtn", None) is not None:
            self._inline_rendbtn.setText(
                self._inline_rend_val[5:] if self._inline_rend_val
                else "循环截止日期")

    def _pick_inline_due(self):
        """为内联编辑行选择截止日期（复用日历弹窗，写入 _inline_due）。

        循环设置已合并进日期弹窗：传入 recur_state，选完写回 _inline_recur_val。
        """
        prev = self._pending_due
        self._pending_due = self._inline_due
        recur_state = {"val": getattr(self, "_inline_recur_val", "不循环")}
        remind_state = {"val": getattr(self, "_inline_remind_val", "到期当天")}
        self._pick_due(recur_state=recur_state, remind_state=remind_state)
        self._inline_due = self._pending_due
        self._inline_recur_val = recur_state.get("val") or "不循环"
        self._inline_remind_val = remind_state.get("val") or "到期当天"
        self._pending_due = prev
        self._update_inline_date_display()

    def _update_inline_date_display(self) -> None:
        """更新内联日期按钮文字，并按内容调整宽度避免日期被截断。"""
        button = getattr(self, "_inline_datebtn", None)
        if button is None:
            return
        text = f"📅 {self._inline_due[5:]}" if self._inline_due else "📅"
        button.setText(text)
        content_width = button.fontMetrics().horizontalAdvance(text)
        button.setFixedWidth(max(46, min(135, content_width + 20)))

    def _save_inline(self):
        """保存内联编辑行内容为正式待办（含优先级/循环/循环截止）"""
        if getattr(self, "_inline_edit", None) is None:
            return
        text = self._inline_edit.text().strip()
        if not text:
            self._close_inline()
            return
        cat = self._inline_ct.currentText() if getattr(
            self, "_inline_ct", None) is not None else (
            self.active_cat if self.active_cat != "全部" else "其他")
        self.store.add(text, cat, due=self._inline_due,
                       priority=self._inline_pr.currentText(),
                       recur=getattr(self, "_inline_recur_val", "不循环"),
                       recur_end=getattr(self, "_inline_rend_val", ""),
                       remind=getattr(self, "_inline_remind_val", "到期当天"))
        self._reset_inline_refs()
        self.refresh()

    def _reset_inline_refs(self):
        self._inline_row = None
        self._inline_edit = None
        self._inline_datebtn = None
        self._inline_pr = None
        self._inline_ct = None
        self._inline_rmd = None
        self._inline_rc = None
        self._inline_rendbtn = None
        self._inline_rend_val = ""
        self._inline_recur_val = "不循环"
        self._inline_remind_val = "到期当天"
        self._inline_due = ""

    def _close_inline(self):
        """取消并移除内联编辑行"""
        row = getattr(self, "_inline_row", None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()
        self._reset_inline_refs()

    def _build_catbar(self):
        self.catbar_widget = QFrame()
        self.catbar_widget.setObjectName("catbar")
        # 外层：可滚动的标签区（左，占满剩余宽度）+ 固定按钮区（右）
        outer = QHBoxLayout(self.catbar_widget)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(6)
        # 左右整体垂直居中对齐，避免出现滚动条时标签与右侧按钮错位
        outer.setAlignment(Qt.AlignVCenter)

        # ---- 左：横向可滚动的分类标签 ----
        self.cat_scroll = QScrollArea()
        self.cat_scroll.setObjectName("catscroll")
        self.cat_scroll.setWidgetResizable(True)
        self.cat_scroll.setFrameShape(QFrame.NoFrame)
        self.cat_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cat_scroll.setFixedHeight(30)
        self.cat_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        chips_holder = QWidget()
        self.catbar = QHBoxLayout(chips_holder)
        self.catbar.setContentsMargins(0, 0, 0, 0)
        self.catbar.setSpacing(6)
        # 标签在容器内垂直居中，避免与右侧按钮高度错位
        self.catbar.setAlignment(Qt.AlignVCenter)
        self.cat_btns = {}
        for name in ["全部"] + self.categories:
            b = QPushButton(name)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(name == self.active_cat)
            b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            b.setFixedHeight(28)
            b.clicked.connect(lambda _=False, n=name: self._set_cat(n))
            self.cat_btns[name] = b
            self.catbar.addWidget(b)
        self.btn_new_cat = QPushButton("＋ 标签")
        self.btn_new_cat.setObjectName("chip")
        self.btn_new_cat.setFixedHeight(28)
        self.btn_new_cat.setCursor(Qt.PointingHandCursor)
        self.btn_new_cat.setToolTip("新建标签")
        self.btn_new_cat.clicked.connect(self._create_category_from_bar)
        self.catbar.addWidget(self.btn_new_cat)
        self.catbar.addStretch()
        self.cat_scroll.setWidget(chips_holder)
        # 鼠标滚轮上下 → 转成横向滚动，方便无横向滚轮的鼠标
        self.cat_scroll.installEventFilter(self)
        outer.addWidget(self.cat_scroll, 1)

        # ---- 右：固定的导出 / 多选 / 全选按钮 ----
        self.btn_daily_export = QPushButton("导出")
        self.btn_daily_export.setObjectName("chip")
        self.btn_daily_export.setCursor(Qt.PointingHandCursor)
        self.btn_daily_export.setToolTip("导出待办（按日期区间/完成状态）")
        self.btn_daily_export.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_daily_export.setFixedHeight(28)
        self.btn_daily_export.clicked.connect(self._export_daily_dialog)
        outer.addWidget(self.btn_daily_export)
        self.btn_multi = QPushButton("☑")
        self.btn_multi.setObjectName("chip")
        self.btn_multi.setCursor(Qt.PointingHandCursor)
        self.btn_multi.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_multi.setFixedHeight(28)
        self.btn_multi.clicked.connect(self._toggle_select_mode)
        outer.addWidget(self.btn_multi)
        self.btn_sel_all = QPushButton("全选")
        self.btn_sel_all.setObjectName("chip")
        self.btn_sel_all.setCursor(Qt.PointingHandCursor)
        self.btn_sel_all.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_sel_all.setFixedHeight(28)
        self.btn_sel_all.clicked.connect(self._batch_select_all)
        self.btn_sel_all.setVisible(False)
        outer.addWidget(self.btn_sel_all)
        return self.catbar_widget

    def eventFilter(self, obj, event):
        # 分类标签区：把竖直滚轮转成横向滚动，方便普通鼠标左右浏览标签
        try:
            from PySide6.QtCore import QEvent
            if (obj is getattr(self, "cat_scroll", None)
                    and event.type() == QEvent.Wheel):
                bar = self.cat_scroll.horizontalScrollBar()
                delta = event.angleDelta().y() or event.angleDelta().x()
                bar.setValue(bar.value() - delta)
                return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def _build_batch_bar(self):
        bar = QFrame()
        bar.setObjectName("batchbar")
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(10, 6, 10, 6)
        lay.setSpacing(6)
        self.batch_lbl = QLabel("已选 0")
        self.batch_lbl.setObjectName("batchlbl")
        lay.addWidget(self.batch_lbl)
        lay.addStretch()
        self.btn_batch_done = QPushButton("✓完成")
        self.btn_batch_cat = QPushButton("改分类")
        self.btn_batch_del = QPushButton("✕删除")
        for b in (self.btn_batch_done,
                  self.btn_batch_cat, self.btn_batch_del):
            b.setObjectName("batchbtn")
            b.setCursor(Qt.PointingHandCursor)
            lay.addWidget(b)
        self.btn_batch_del.setObjectName("batchdanger")
        self.btn_batch_done.clicked.connect(self._batch_done)
        self.btn_batch_cat.clicked.connect(self._batch_set_cat)
        self.btn_batch_del.clicked.connect(self._batch_delete)
        return bar

    # -- 多选/批量 --
    def _toggle_select_mode(self):
        self.select_mode = not self.select_mode
        if not self.select_mode:
            self.selected_ids.clear()
        self.batch_bar.setVisible(self.select_mode)
        is_project = self.view_mode == "project"
        self.btn_sel_all.setVisible(self.select_mode and not is_project)
        self.btn_project_sel_all.setVisible(self.select_mode and is_project)
        self.btn_multi.setText("✕" if self.select_mode else "☑")
        self.btn_project_multi.setText(
            "取消" if self.select_mode else "多选"
        )
        self._update_batch_lbl()
        # 原地切换每张卡片的选择模式，避免重建整表导致闪烁
        for i in range(self.list_lay.count()):
            w = self.list_lay.itemAt(i).widget()
            if isinstance(w, TaskCard):
                w.set_select_mode(
                    self.select_mode,
                    selected=w.task["id"] in self.selected_ids,
                )

    def _on_card_select(self, tid, checked):
        if checked:
            self.selected_ids.add(tid)
        else:
            self.selected_ids.discard(tid)
        self._update_batch_lbl()

    def _update_batch_lbl(self):
        if hasattr(self, "batch_lbl"):
            self.batch_lbl.setText(f"已选 {len(self.selected_ids)}")

    def _visible_task_ids(self):
        ids = []
        for t in self.store.tasks:
            if self.view_mode == "project":
                if not self.active_project or t.get("project", "") != self.active_project:
                    continue
            else:
                if t.get("project", ""):
                    continue
                if self.active_cat != "全部" and t.get("category") != self.active_cat:
                    continue
            if self.keyword and self.keyword not in t.get("text", ""):
                continue
            ids.append(t["id"])
        return ids

    def _batch_select_all(self):
        vis = self._visible_task_ids()
        if self.selected_ids.issuperset(vis):
            self.selected_ids.clear()
        else:
            self.selected_ids.update(vis)
        self._update_batch_lbl()
        # 原地更新每张卡片的选中态，避免重建整表导致闪烁
        for i in range(self.list_lay.count()):
            w = self.list_lay.itemAt(i).widget()
            if isinstance(w, TaskCard):
                w.set_selected(w.task["id"] in self.selected_ids)

    def _batch_done(self):
        for tid in list(self.selected_ids):
            self.store.update(tid, status="done")
        self.selected_ids.clear()
        self._update_batch_lbl()
        self.refresh()

    def _batch_delete(self):
        for tid in list(self.selected_ids):
            self.store.delete(tid)
        self.selected_ids.clear()
        self._update_batch_lbl()
        self.refresh()

    def _batch_set_cat(self):
        if not self.selected_ids:
            return
        m = QMenu(self)
        m.addAction("改为分类").setEnabled(False)
        m.addSeparator()
        for name in CATEGORIES:
            act = m.addAction(name)
            act.triggered.connect(lambda _=False, n=name: self._apply_batch_cat(n))
        m.exec(self.btn_batch_cat.mapToGlobal(
            self.btn_batch_cat.rect().bottomLeft()))

    def _apply_batch_cat(self, name):
        for tid in list(self.selected_ids):
            self.store.update(tid, category=name)
        self.selected_ids.clear()
        self._update_batch_lbl()
        self.refresh()

    # -- 样式 --
    def _apply_window_style(self):
        t = self.theme
        self.setStyleSheet(f"""
            QPushButton {{ outline: none; }}
            QPushButton:disabled {{ color: {t['done']}; background: {t['border']}; }}
            QLabel#apptitle {{
                color: {t['text']}; font-size: 16px; font-weight: 700;
            }}
            QFrame#batchbar {{
                background: {t['panel']}; border-radius: 14px;
                border: 1px solid {t['border']};
            }}
            QLabel#batchlbl {{ color: {t['accent']}; font-size: 12px; font-weight: bold; }}
            QPushButton#batchbtn {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 10px; color: {t['text']}; font-size: 12px;
                padding: 6px 11px; font-weight: 600;
            }}
            QPushButton#batchbtn:hover {{
                background: {_qss_alpha(t['accent'], 0x16)};
                border-color: {t['accent']};
                color: {t['accent']};
            }}
            QPushButton#batchdanger {{
                background: transparent;
                border: 1px solid {_qss_alpha('#E5484D', 0x55)};
                border-radius: 10px; color: #E5484D; font-size: 12px;
                padding: 6px 11px; font-weight: 600;
            }}
            QPushButton#batchdanger:hover {{
                background: #E5484D; color: #FFFFFF; border-color: #E5484D;
            }}
            QLabel#cheer {{ color: {t['accent']}; font-size: 11px; font-weight: bold; }}
            QLabel#cheer:hover {{ color: {t['accent2']}; }}
            QPushButton#titlebtn, QPushButton#closebtn {{
                background: {_qss_alpha(t['panel'], 0x88)};
                border: 1px solid transparent;
                border-radius: 10px; color: {t['sub']};
                font-size: 15px; font-weight: bold;
            }}
            QPushButton#titlebtn:hover {{
                background: {t['card_hover']}; border-color: {t['border']};
                color: {t['text']};
            }}
            QPushButton#closebtn:hover {{ background: #E5484D; color: #FFFFFF; }}
            QPushButton#titlebtn:pressed, QPushButton#closebtn:pressed {{
                padding-top: 2px;
            }}
            QFrame#stats {{
                background: {t['panel']}; border-radius: 14px;
                border: 1px solid {t['border']};
            }}
            QLabel#statstext {{ color: {t['text']}; font-size: 13px; font-weight: bold; }}
            QLabel#statspct {{ color: {t['accent']}; font-size: 13px; font-weight: bold; }}
            QPushButton#tabbtn {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 11px; padding: 8px 10px;
                color: {t['sub']}; font-size: 13px; font-weight: 600;
            }}
            QPushButton#tabbtn:checked {{
                background: {_qss_alpha(t['accent'], 0x20)};
                border: 1px solid {_qss_alpha(t['accent'], 0x65)};
                color: {t['accent']};
            }}
            QPushButton#tabbtn:hover {{
                color: {t['accent']}; border-color: {t['accent']};
                background: {_qss_alpha(t['accent'], 0x10)};
            }}
            QPushButton#tabbtn:checked:hover {{
                color: {t['accent']}; background: {_qss_alpha(t['accent'], 0x2B)};
            }}
            QFrame#barbg {{ background: {t['border']}; border-radius: 4px; }}
            QFrame#barfg {{ background: {t['accent']}; border-radius: 4px; }}
            QLineEdit#input {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 12px; padding: 0 12px; color: {t['text']};
                font-size: 13px;
            }}
            QLineEdit#input:focus {{ border: 1.5px solid {t['accent']}; }}
            QComboBox#catpick {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 12px; padding: 0 8px; color: {t['text']}; font-size: 12px;
            }}
            QComboBox::drop-down {{
                border: none; width: 30px; background: transparent;
            }}
            QComboBox::down-arrow {{
                image: none; width: 0; height: 0; border: none;
            }}
            QComboBox#catpick::drop-down {{ border: none; width: 30px; }}
            QComboBox#projpick {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 12px; padding: 0 8px; color: {t['text']};
                font-size: 12px; font-weight: 500;
            }}
            QComboBox#projpick::drop-down {{ border: none; width: 30px; }}
            QLabel#projlbl {{ color: {t['sub']}; font-size: 13px; font-weight: bold; }}
            QComboBox#prpick {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 12px; padding: 0 8px; color: {t['text']}; font-size: 12px;
            }}
            QComboBox#prpick::drop-down {{ border: none; width: 30px; }}
            QComboBox QAbstractItemView {{
                background: {t['panel']}; color: {t['text']};
                selection-background-color: {t['accent']}; border-radius: 8px;
            }}
            QPushButton#addbtn {{
                background: {t['accent']}; border: 1px solid {t['accent']};
                border-radius: 12px; color: #FFFFFF;
                font-size: 14px; font-weight: 700;
            }}
            QPushButton#addbtn:hover {{ background: {t['accent2']}; }}
            QPushButton#addbtn:pressed {{ padding-top: 2px; }}
            QPushButton#secondarybtn {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 11px; color: {t['text']};
                font-size: 12px; font-weight: 500;
            }}
            QPushButton#secondarybtn:hover {{
                color: {t['accent']}; border-color: {t['accent']};
                background: {_qss_alpha(t['accent'], 0x10)};
            }}
            QPushButton#exportbtn {{
                background: #22B07D; border: none;
                border-radius: 11px; color: #FFFFFF;
                font-size: 12px; font-weight: 500;
            }}
            QPushButton#exportbtn:hover {{ background: #1C9A6C; }}
            QPushButton#exportbtn:pressed {{ background: #178257; }}
            QPushButton#selallbtn {{
                background: {t['accent']}; border: none;
                border-radius: 11px; color: #FFFFFF;
                font-size: 12px; font-weight: 500;
            }}
            QPushButton#selallbtn:hover {{ background: {_qss_alpha(t['accent'], 0xDD)}; }}
            QPushButton#datebtn {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 12px; color: {t['accent']}; font-size: 15px;
            }}
            QPushButton#datebtn:hover {{ background: {t['accent']}; color: #FFFFFF; }}
            QPushButton#chip {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 11px; padding: 5px 10px; color: {t['sub']};
                font-size: 12px; font-weight: 500;
            }}
            QPushButton#chip:hover {{
                color: {t['accent']}; border-color: {t['accent']};
                background: {_qss_alpha(t['accent'], 0x10)};
            }}
            QPushButton#chip:checked {{
                background: {_qss_alpha(t['accent'], 0x1C)};
                color: {t['accent']};
                border-color: {_qss_alpha(t['accent'], 0x60)};
                font-weight: bold;
            }}
            QLabel#emptyState {{
                color: {t['sub']}; background: {_qss_alpha(t['card'], 0x70)};
                border: 1px dashed {t['border']}; border-radius: 14px;
                font-size: 13px; padding: 28px 12px;
            }}
            QScrollArea#scroll {{ background: transparent; border: none; }}
            QScrollArea#scroll > QWidget > QWidget {{ background: transparent; }}
            QScrollArea#catscroll {{ background: transparent; border: none; }}
            QScrollArea#catscroll > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:horizontal {{ background: transparent; height: 5px; margin: 0 2px; }}
            QScrollBar::handle:horizontal {{ background: {_qss_alpha(t['sub'], 0x50)}; border-radius: 2px; min-width: 24px; }}
            QScrollBar::handle:horizontal:hover {{ background: {t['sub']}; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 24px; }}
            QScrollBar::handle:vertical:hover {{ background: {t['sub']}; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
            QMenu {{
                background: {t['panel']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 12px; padding: 7px;
            }}
            QMenu::item {{ padding: 8px 24px; border-radius: 8px; }}
            QMenu::item:selected {{ background: {t['accent']}; color: #FFFFFF; }}
            QMenu::item:disabled {{ color: {t['done']}; }}
            QMenu::separator {{
                height: 1px; background: {t['border']}; margin: 5px 8px;
            }}
            QToolTip {{
                color: {t['text']}; background: {t['panel']};
                border: 1px solid {t['border']}; border-radius: 7px;
                padding: 5px 7px;
            }}
        """)

    # -- 折叠 --
    def _apply_collapsed(self):
        vis = not self.collapsed
        self._set_body_visible(vis)
        if self.collapsed:
            # 折叠：缩小根布局上下边距，让标题栏在小高度里垂直居中不被裁切
            self.layout().setContentsMargins(14, 10, 14, 10)
            self.setMinimumHeight(0)
            self.setFixedHeight(48)
        else:
            self.layout().setContentsMargins(14, 12, 14, 14)
            self.setMaximumHeight(16777215)
            self.setMinimumHeight(420)
            self.resize(self.width(), self.expanded_height)
        # 折叠时按钮图标切换
        self.btn_collapse.setText("▢" if self.collapsed else "–")

    def _toggle_collapse(self):
        # 展开→折叠前，先记住当前展开高度
        if not self.collapsed:
            self.expanded_height = self.height()
            self.cfg["expanded_height"] = self.expanded_height
        self.collapsed = not self.collapsed
        self._apply_collapsed()
        self._save_cfg()

    def _set_body_visible(self, vis):
        self.stats_box.setVisible(vis)
        self.scroll.setVisible(vis)
        # 兼容用隐藏控件(input/cat_pick/btn_date)不参与显隐，避免浮空
        is_project = self.view_mode == "project"
        self.btn_add.setVisible(vis and not is_project)
        self.project_bar.setVisible(vis and is_project)
        self.catbar_widget.setVisible(vis and not is_project)
        if hasattr(self, "btn_multi"):
            self.btn_multi.setVisible(vis and not is_project)
        if hasattr(self, "btn_project_multi"):
            self.btn_project_multi.setVisible(vis and is_project)
        # 折叠时只保留“待办清单”标题与折叠/关闭按钮，其余全部收起
        self.cheer_lbl.setVisible(vis)
        for b in (self.btn_theme, self.btn_menu):
            b.setVisible(vis)
        # 全选按钮只在“展开 + 多选模式”下显示
        if hasattr(self, "btn_sel_all"):
            self.btn_sel_all.setVisible(
                vis and self.select_mode and not is_project
            )
        if hasattr(self, "btn_project_sel_all"):
            self.btn_project_sel_all.setVisible(
                vis and self.select_mode and is_project
            )
        # 折叠时隐藏批量条
        if hasattr(self, "batch_bar"):
            self.batch_bar.setVisible(vis and getattr(self, "select_mode", False))

    # -- 拖拽移动 / 边缘拉伸调整大小 --
    def _edge_at(self, pos):
        """判断鼠标位于窗口哪条边缘，返回如 'left'/'topright' 的组合字符串"""
        if getattr(self, "collapsed", False):
            return ""   # 折叠态不允许拉伸
        m = self._resize_margin
        r = self.rect()
        left = pos.x() <= m
        right = pos.x() >= r.width() - m
        top = pos.y() <= m
        bottom = pos.y() >= r.height() - m
        edges = ""
        if top:
            edges += "top"
        elif bottom:
            edges += "bottom"
        if left:
            edges += "left"
        elif right:
            edges += "right"
        return edges

    def _cursor_for_edge(self, edges):
        if edges in ("left", "right"):
            return Qt.SizeHorCursor
        if edges in ("top", "bottom"):
            return Qt.SizeVerCursor
        if edges in ("topleft", "bottomright"):
            return Qt.SizeFDiagCursor
        if edges in ("topright", "bottomleft"):
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            edges = self._edge_at(e.position().toPoint())
            if edges:
                # 命中边缘：进入拉伸模式
                self._resizing = True
                self._resize_edges = edges
                self._resize_start_geo = self.geometry()
                self._resize_start_pos = e.globalPosition().toPoint()
                e.accept()
                return
            # 否则按住空白处拖动整个窗口
            self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
            e.accept()

    def mouseMoveEvent(self, e):
        # 正在拉伸：按边缘方向调整几何
        if getattr(self, "_resizing", False) and (e.buttons() & Qt.LeftButton):
            self._do_resize(e.globalPosition().toPoint())
            e.accept()
            return
        # 按住拖动窗口
        if self._drag_pos and (e.buttons() & Qt.LeftButton):
            self.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
            return
        # 未按下：仅根据边缘更新光标形状
        edges = self._edge_at(e.position().toPoint())
        self.setCursor(self._cursor_for_edge(edges))

    def _do_resize(self, gpos):
        d = gpos - self._resize_start_pos
        geo = QRect(self._resize_start_geo)
        min_w = self.minimumWidth() or 300
        min_h = self.minimumHeight() or 420
        edges = self._resize_edges
        if "left" in edges:
            new_left = geo.left() + d.x()
            if geo.right() - new_left + 1 < min_w:
                new_left = geo.right() - min_w + 1
            geo.setLeft(new_left)
        if "right" in edges:
            new_right = geo.right() + d.x()
            if new_right - geo.left() + 1 < min_w:
                new_right = geo.left() + min_w - 1
            geo.setRight(new_right)
        if "top" in edges:
            new_top = geo.top() + d.y()
            if geo.bottom() - new_top + 1 < min_h:
                new_top = geo.bottom() - min_h + 1
            geo.setTop(new_top)
        if "bottom" in edges:
            new_bottom = geo.bottom() + d.y()
            if new_bottom - geo.top() + 1 < min_h:
                new_bottom = geo.top() + min_h - 1
            geo.setBottom(new_bottom)
        self.setGeometry(geo)

    def mouseReleaseEvent(self, e):
        if getattr(self, "_resizing", False):
            # 结束拉伸：记录当前展开高度，便于下次展开还原
            self._resizing = False
            self._resize_edges = ""
            if not getattr(self, "collapsed", False):
                self.expanded_height = self.height()
                self.cfg["expanded_height"] = self.expanded_height
        self._drag_pos = None
        self.setCursor(Qt.ArrowCursor)
        self._save_cfg()

    # -- 渲染任务列表 --
    def refresh(self, animate=True):
        # 清空旧卡片
        # 内联编辑行会随列表清空被删除，重置其引用避免悬空
        if getattr(self, "_inline_row", None) is not None:
            self._reset_inline_refs()
        while self.list_lay.count() > 1:
            item = self.list_lay.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        tasks = self.store.tasks
        # 视图过滤：日常待办只看无项目的；项目待办只看当前项目
        if self.view_mode == "project":
            tasks = [t for t in tasks
                     if t.get("project", "") == self.active_project
                     and self.active_project]
        else:
            tasks = [t for t in tasks if not t.get("project", "")]
            if self.active_cat != "全部":
                tasks = [t for t in tasks if t.get("category") == self.active_cat]
        if self.keyword:
            tasks = [t for t in tasks if self.keyword in t["text"].lower()]
        # 排序：完成置底；未完成按 优先级 > 截止时间 > 状态
        rank = {"todo": 0, "doing": 1, "done": 2}

        def sort_key(t):
            done_flag = 1 if t["status"] == "done" else 0
            # 置顶的排在最前（已完成的仍置底，不受置顶影响）
            pin_flag = 0 if t.get("pinned", False) else 1
            pr = PRIORITY_RANK.get(t.get("priority", "普通"), 2)
            return (done_flag, pin_flag, pr, due_sort_key(t.get("due", "")),
                    rank.get(t["status"], 0), t["created"])
        tasks = sorted(tasks, key=sort_key)

        if not tasks:
            empty = QLabel("✓\n暂无待办\n享受清爽的一天")
            empty.setObjectName("emptyState")
            empty.setAlignment(Qt.AlignCenter)
            self.list_lay.insertWidget(0, empty)
        else:
            for i, t in enumerate(tasks):
                card = TaskCard(t, self.theme,
                                select_mode=self.select_mode,
                                selected=t["id"] in self.selected_ids)
                card.toggled.connect(self._on_toggle)
                card.deleted.connect(self._on_delete)
                card.edited.connect(self._on_edit)
                card.pinned.connect(self._on_pin)
                card.sub_toggled.connect(self._on_sub_toggle)
                card.select_toggled.connect(self._on_card_select)
                card.configure_strong.connect(self._on_configure_strong)
                self.list_lay.insertWidget(i, card)
                if animate:
                    self._fade_in(card, i)

        self._update_stats()

    def _reorder_silent(self):
        """静默重排列表（不播放淡入动画，避免闪烁感）"""
        self.refresh(animate=False)

    def _fade_in(self, w, idx):
        eff = QGraphicsOpacityEffect(w)
        w.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(260)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        QTimer.singleShot(idx * 40, anim.start)
        w._anim = anim

    def _update_stats(self):
        if self.view_mode == "project":
            # 项目待办 tab：展示当前项目的「完成/总计」，不展示今日
            if self.active_project:
                p_total, p_done = self.store.project_stats(self.active_project)
            else:
                p_total, p_done = 0, 0
            total, done = p_total, p_done
            self.stats_text.setText(f"{self.active_project or '项目'} {done}/{total}")
        else:
            # 日常待办 tab：今日口径（只算日常、今天/过期/无日期）
            total, done, urgent = self.store.stats()
            if urgent > 0:
                self.stats_text.setText(f"今日 {done}/{total}   🔥紧急 {urgent}")
            else:
                self.stats_text.setText(f"今日 {done}/{total}")
        pct = int(done / total * 100) if total else 0
        self.stats_pct.setText(f"{pct}%")
        # 进度条动画
        full = self.bar_bg.width()
        target = int(full * pct / 100)
        anim = QPropertyAnimation(self.bar_fg, b"geometry", self)
        anim.setDuration(400)
        anim.setStartValue(self.bar_fg.geometry())
        anim.setEndValue(QRect(0, 0, target, 8))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        anim.start()
        self._bar_anim = anim

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._update_stats)

    # -- 任务操作 --
    def _on_catpick(self, idx):
        """分类下拉选中『＋新建…』时弹框创建新分类"""
        if self.cat_pick.itemText(idx) != "＋新建…":
            return
        name = self._prompt_new_category()
        if name:
            self.cat_pick.setCurrentText(name)
        else:
            self.cat_pick.setCurrentIndex(0)

    def _create_category_from_bar(self) -> None:
        """从日常待办标签栏新建分类并立即选中。"""
        name = self._prompt_new_category()
        if name:
            self._set_cat(name)

    def _prompt_new_category(self) -> str:
        """显示新建分类弹窗，成功时返回分类名称。"""
        from PySide6.QtWidgets import QInputDialog
        dialog = QInputDialog(self)
        dialog.setWindowTitle("新建分类")
        dialog.setLabelText("分类名称")
        dialog.setOkButtonText("创建")
        dialog.setCancelButtonText("取消")
        dialog.setStyleSheet(self._dialog_qss())
        ok = dialog.exec() == QInputDialog.Accepted
        name = dialog.textValue()
        name = (name or "").strip()
        if ok and name and name not in self.categories:
            self._add_category(name)
            return name
        if ok and name in self.categories:
            return name
        return ""

    def _add_category(self, name):
        """新增分类并同步到下拉、筛选栏、配置"""
        self.categories.append(name)
        self.cfg["categories"] = self.categories
        self._save_cfg()
        # 刷新分类下拉（保留＋新建…在末尾）
        self.cat_pick.blockSignals(True)
        self.cat_pick.clear()
        self.cat_pick.addItems(self.categories)
        self.cat_pick.addItem("＋新建…")
        self.cat_pick.blockSignals(False)
        # 在筛选栏追加新分类按钮
        b = QPushButton(name)
        b.setObjectName("chip")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        b.clicked.connect(lambda _=False, n=name: self._set_cat(n))
        self.cat_btns[name] = b
        self.catbar.insertWidget(self.catbar.indexOf(self.btn_new_cat), b)

    def _pick_due(self, recur_state=None, remind_state=None, recur_end_state=None):
        """弹出日历选择截止时间，并可选精确到时间点。

        recur_state: 可选 dict，形如 {"val": "不循环"}。传入时弹窗底部
        显示「循环重复」下拉，确定后将选中值写回 recur_state["val"]。
        remind_state: 可选 dict，形如 {"val": "到期当天"}。传入时弹窗底部
        显示「提醒时间」下拉，确定后写回 remind_state["val"]。
        二者合并进日期弹窗，减少待办卡片上的按钮。
        """
        from PySide6.QtWidgets import (QDialog, QVBoxLayout,
                                       QDialogButtonBox, QHBoxLayout, QPushButton,
                                       QCheckBox, QTimeEdit, QFrame, QLabel,
                                       QComboBox, QAbstractSpinBox, QDateEdit)
        from PySide6.QtCore import QDate, QLocale, QTime
        from PySide6.QtGui import QTextCharFormat, QColor
        dlg = QDialog(self)
        dlg.setWindowTitle("选择截止时间")
        dlg.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        dlg.setAttribute(Qt.WA_TranslucentBackground)
        dlg.setMinimumWidth(420)
        dlg.setStyleSheet(self._dialog_qss() + self._calendar_qss())
        shell = QVBoxLayout(dlg)
        shell.setContentsMargins(18, 18, 18, 18)
        surface = QFrame()
        surface.setObjectName("dialogSurface")
        shadow = QGraphicsDropShadowEffect(surface)
        shadow.setBlurRadius(34)
        shadow.setOffset(0, 8)
        shadow_color = QColor("#182230")
        shadow_color.setAlpha(75)
        shadow.setColor(shadow_color)
        surface.setGraphicsEffect(shadow)
        shell.addWidget(surface)

        v = QVBoxLayout(surface)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(14)

        head = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("选择截止时间")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("为待办安排一个明确的完成节点")
        subtitle.setObjectName("dialogSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        head.addLayout(title_col)
        head.addStretch()
        selected_lbl = QLabel()
        selected_lbl.setObjectName("selectedDate")
        head.addWidget(selected_lbl, 0, Qt.AlignVCenter)
        v.addLayout(head)

        cal_card = QFrame()
        cal_card.setObjectName("calendarCard")
        cal_lay = QVBoxLayout(cal_card)
        cal_lay.setContentsMargins(8, 8, 8, 8)
        cal = _StyledCalendarWidget(self.theme)
        cal.setLocale(QLocale(QLocale.Chinese, QLocale.China))
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)  # 去掉左侧周数列
        cal.setGridVisible(False)
        cal.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        cal.setNavigationBarVisible(True)

        # 相邻月份弱化显示，当月日期恢复主题文字色；今天用强调色标记。
        def _format_calendar_page():
            muted_fmt = QTextCharFormat()
            muted = QColor(self.theme["sub"])
            muted.setAlpha(85)
            muted_fmt.setForeground(muted)
            normal_fmt = QTextCharFormat()
            normal_fmt.setForeground(QColor(self.theme["text"]))
            page_m = cal.monthShown()
            page_y = cal.yearShown()
            d = QDate(page_y, page_m, 1).addDays(-14)
            for _ in range(56):
                if d.month() != page_m:
                    cal.setDateTextFormat(d, muted_fmt)
                else:
                    cal.setDateTextFormat(d, normal_fmt)
                d = d.addDays(1)
            today = QDate.currentDate()
            if today.year() == page_y and today.month() == page_m:
                today_fmt = QTextCharFormat()
                today_fmt.setForeground(QColor(self.theme["accent"]))
                today_fmt.setFontWeight(700)
                cal.setDateTextFormat(today, today_fmt)

        def _sync_selected_label():
            date = cal.selectedDate()
            selected_lbl.setText(date.toString("MM月dd日  ddd"))

        cal.currentPageChanged.connect(lambda *_: _format_calendar_page())
        cal.selectionChanged.connect(_sync_selected_label)
        _format_calendar_page()
        # 预置已有日期/时间
        cur_date, cur_time = parse_due(self._pending_due)
        if cur_date is not None:
            cal.setSelectedDate(QDate(cur_date.year, cur_date.month, cur_date.day))
        _sync_selected_label()
        cal_lay.addWidget(cal)
        v.addWidget(cal_card)

        # 时间点选择行
        time_card = QFrame()
        time_card.setObjectName("timeCard")
        trow = QHBoxLayout(time_card)
        trow.setContentsMargins(12, 9, 12, 9)
        trow.setSpacing(10)
        chk_time = QCheckBox("指定具体时间点")
        chk_time.setChecked(cur_time is not None)
        trow.addWidget(chk_time)
        trow.addStretch()
        time_edit = QTimeEdit()
        time_edit.setObjectName("timeEdit")
        time_edit.setButtonSymbols(QAbstractSpinBox.NoButtons)
        time_edit.setDisplayFormat("HH:mm")
        time_edit.setTime(QTime(cur_time.hour, cur_time.minute)
                          if cur_time else QTime(18, 0))
        time_edit.setEnabled(cur_time is not None)
        chk_time.toggled.connect(time_edit.setEnabled)
        trow.addWidget(time_edit)
        v.addWidget(time_card)

        # 循环设置行（仅在传入 recur_state 时显示；把「是否循环」合并进日期弹窗）
        recur_pick = None
        recur_end_pick = None
        if recur_state is not None:
            recur_card = QFrame()
            recur_card.setObjectName("timeCard")
            recur_col = QVBoxLayout(recur_card)
            recur_col.setContentsMargins(12, 9, 12, 9)
            recur_col.setSpacing(8)
            rrow = QHBoxLayout()
            rrow.setSpacing(10)
            rrow.addWidget(QLabel("循环重复"))
            rrow.addStretch()
            recur_pick = QComboBox()
            recur_pick.setObjectName("timeEdit")
            recur_pick.addItems(RECUR_TYPES)
            recur_pick.setCurrentText(recur_state.get("val") or "不循环")
            recur_pick.setMinimumWidth(120)
            rrow.addWidget(recur_pick)
            recur_col.addLayout(rrow)
            # 循环截止日期（仅当选择了循环时才可用，合并进日期弹窗）
            if recur_end_state is not None:
                erow = QHBoxLayout()
                erow.setSpacing(10)
                erow.addWidget(QLabel("循环截止"))
                erow.addStretch()
                recur_end_pick = QDateEdit()
                recur_end_pick.setObjectName("timeEdit")
                recur_end_pick.setCalendarPopup(True)
                recur_end_pick.setDisplayFormat("yyyy-MM-dd")
                recur_end_pick.setMinimumWidth(140)
                _ev = recur_end_state.get("val") or ""
                if _ev:
                    _ed = QDate.fromString(_ev[:10], "yyyy-MM-dd")
                    if _ed.isValid():
                        recur_end_pick.setDate(_ed)
                    else:
                        recur_end_pick.setDate(QDate.currentDate())
                else:
                    recur_end_pick.setDate(QDate.currentDate())
                erow.addWidget(recur_end_pick)
                chk_recur_end = QCheckBox("设置循环结束日期")
                chk_recur_end.setChecked(bool(_ev))
                recur_end_pick.setEnabled(bool(_ev))
                chk_recur_end.toggled.connect(recur_end_pick.setEnabled)
                def _sync_recur_end_vis(txt=None):
                    on = recur_pick.currentText() != "不循环"
                    chk_recur_end.setVisible(on)
                    recur_end_pick.setVisible(on)
                recur_pick.currentTextChanged.connect(_sync_recur_end_vis)
                _sync_recur_end_vis()
                erow2 = QHBoxLayout()
                erow2.addWidget(chk_recur_end)
                erow2.addStretch()
                recur_col.addLayout(erow2)
                recur_col.addLayout(erow)
            v.addWidget(recur_card)

        # 提醒时间行（仅在传入 remind_state 时显示；把「提醒」合并进日期弹窗）
        remind_pick = None
        if remind_state is not None:
            remind_card = QFrame()
            remind_card.setObjectName("timeCard")
            mrow = QHBoxLayout(remind_card)
            mrow.setContentsMargins(12, 9, 12, 9)
            mrow.setSpacing(10)
            mrow.addWidget(QLabel("提醒时间"))
            mrow.addStretch()
            remind_pick = QComboBox()
            remind_pick.setObjectName("timeEdit")
            remind_pick.addItems(list(REMIND_TYPES.keys()))
            remind_pick.setCurrentText(remind_state.get("val") or "到期当天")
            remind_pick.setMinimumWidth(120)
            mrow.addWidget(remind_pick)
            v.addWidget(remind_card)

        row = QHBoxLayout()
        btn_clear = QPushButton("清除")
        btn_clear.setObjectName("dangerGhost")
        btn_clear.setCursor(Qt.PointingHandCursor)
        row.addWidget(btn_clear)
        row.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("确定")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        row.addWidget(bb)
        v.addLayout(row)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        btn_clear.clicked.connect(lambda: (setattr(self, "_pending_due", ""),
                                           self._update_date_btn(), dlg.reject()))
        if dlg.exec() == QDialog.Accepted:
            due = cal.selectedDate().toString("yyyy-MM-dd")
            if chk_time.isChecked():
                due += " " + time_edit.time().toString("HH:mm")
            self._pending_due = due
            if recur_state is not None and recur_pick is not None:
                recur_state["val"] = recur_pick.currentText()
                # 循环截止：不循环或未勾选结束日期时清空
                if recur_end_state is not None:
                    if (recur_pick.currentText() != "不循环"
                            and recur_end_pick is not None
                     and recur_end_pick.isEnabled()):
                        recur_end_state["val"] = \
                            recur_end_pick.date().toString("yyyy-MM-dd")
                    else:
                        recur_end_state["val"] = ""
            if remind_state is not None and remind_pick is not None:
                remind_state["val"] = remind_pick.currentText()
            self._update_date_btn()

    def _update_date_btn(self):
        if self._pending_due:
            d, tm = parse_due(self._pending_due)
            if d is not None:
                txt = d.strftime("%m-%d")
                if tm:
                    txt += tm.strftime(" %H:%M")
            else:
                txt = self._pending_due
            self.btn_date.setText(txt)
            self.btn_date.setToolTip(f"截止 {self._pending_due}（点击修改）")
        else:
            self.btn_date.setText("📅")
            self.btn_date.setToolTip("设置截止时间")

    def _add_task(self):
        text = self.input.text().strip()
        if not text:
            return
        cat = self.cat_pick.currentText()
        if cat == "＋新建…":
            cat = self.categories[0] if self.categories else "其他"
        self.store.add(text, cat,
                       due=self._pending_due,
                       priority=self.pr_pick.currentText())
        self.input.clear()
        self.pr_pick.setCurrentText("普通")
        self._pending_due = ""
        self._update_date_btn()
        self.refresh()

    def _on_toggle(self, tid):
        self.store.toggle(tid)
        # 原地刷新该卡片，避免整表重建导致的闪烁
        for i in range(self.list_lay.count()):
            w = self.list_lay.itemAt(i).widget()
            if isinstance(w, TaskCard) and w.task["id"] == tid:
                w.refresh_status()
                break
        self._update_stats()
        # 循环任务完成会生成新任务，或需重排完成置底 → 延迟一次静默重排
        QTimer.singleShot(280, self._reorder_silent)

    def _on_sub_toggle(self, tid, idx):
        self.store.toggle_sub(tid, idx)
        self.refresh(animate=False)

    def _on_pin(self, tid):
        """切换某条待办的置顶状态，并重排列表。"""
        cur = False
        for t in self.store.tasks:
            if t["id"] == tid:
                cur = bool(t.get("pinned", False))
                break
        self.store.update(tid, pinned=not cur)
        self.refresh(animate=False)

    def _on_configure_strong(self, tid):
        """打开强提醒设置窗口；确认后写回任务 strong 字段并保存。"""
        task = next((t for t in self.store.tasks if t["id"] == tid), None)
        if task is None:
            return
        dlg = StrongRemindDialog(self.theme, task, self)
        if dlg.exec():
            # 对话框 accept() 已把设置写入 task["strong"]（同一对象引用）
            self.store.save()
            self.refresh(animate=False)

    def _on_delete(self, tid):
        self.store.delete(tid)
        # 只移除对应卡片并让下方待办平滑上移，避免整表重建导致的闪烁
        target = None
        for i in range(self.list_lay.count()):
            w = self.list_lay.itemAt(i).widget()
            if isinstance(w, TaskCard) and w.task["id"] == tid:
                target = w
                break
        if target is None:
            self.refresh(animate=False)
            return
        self._collapse_and_remove(target)
        self._update_stats()

    def _collapse_and_remove(self, card):
        """对单张卡片做淡出+高度收缩动画，结束后销毁，下方卡片自然上移"""
        eff = QGraphicsOpacityEffect(card)
        card.setGraphicsEffect(eff)
        fade = QPropertyAnimation(eff, b"opacity", self)
        fade.setDuration(160)
        fade.setStartValue(1.0)
        fade.setEndValue(0.0)
        fade.setEasingCurve(QEasingCurve.OutCubic)
        shrink = QPropertyAnimation(card, b"maximumHeight", self)
        shrink.setDuration(200)
        shrink.setStartValue(card.sizeHint().height())
        shrink.setEndValue(0)
        shrink.setEasingCurve(QEasingCurve.OutCubic)
        self._del_anims = getattr(self, "_del_anims", [])
        self._del_anims += [fade, shrink]

        def _done():
            self.list_lay.removeWidget(card)
            card.deleteLater()
            for a in (fade, shrink):
                if a in self._del_anims:
                    self._del_anims.remove(a)
        shrink.finished.connect(_done)
        fade.start()
        shrink.start()

    def _calendar_qss(self):
        """日历弹窗专用样式，保持浅色与深色主题一致。"""
        t = self.theme
        return f"""
            QDialog {{ background: transparent; }}
            QFrame#dialogSurface {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 17px;
            }}
            QLabel#dialogTitle {{
                color: {t['text']}; font-size: 17px; font-weight: 700;
            }}
            QLabel#dialogSubtitle {{
                color: {t['sub']}; font-size: 11px; font-weight: 400;
            }}
            QLabel#selectedDate {{
                color: {t['accent']};
                background: {_qss_alpha(t['accent'], 0x18)};
                border: 1px solid {_qss_alpha(t['accent'], 0x35)};
                border-radius: 10px;
                padding: 6px 10px; font-size: 12px; font-weight: 700;
            }}
            QFrame#calendarCard {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 14px;
            }}
            QCalendarWidget {{
                background: transparent; color: {t['text']};
            }}
            QCalendarWidget QWidget#qt_calendar_navigationbar {{
                background: transparent; border: none; padding: 4px;
            }}
            QCalendarWidget QToolButton {{
                color: {t['text']}; background: transparent; border: none;
                border-radius: 9px; min-height: 30px; padding: 2px 9px;
                font-size: 13px; font-weight: 700;
            }}
            QCalendarWidget QToolButton:hover {{
                color: {t['accent']};
                background: {_qss_alpha(t['accent'], 0x18)};
            }}
            /* 月份/年份按钮：去掉下拉箭头指示器，避免「七月˅」文字错落 */
            QCalendarWidget QToolButton#qt_calendar_monthbutton,
            QCalendarWidget QToolButton#qt_calendar_yearbutton {{
                padding: 2px 14px; margin: 0 2px;
            }}
            QCalendarWidget QToolButton#qt_calendar_monthbutton::menu-indicator,
            QCalendarWidget QToolButton#qt_calendar_yearbutton::menu-indicator {{
                image: none; width: 0; height: 0;
                subcontrol-position: right center;
            }}
            QCalendarWidget QToolButton#qt_calendar_prevmonth,
            QCalendarWidget QToolButton#qt_calendar_nextmonth {{
                qproperty-icon: none; color: {t['sub']};
                min-width: 30px; max-width: 30px; padding: 0;
            }}
            QCalendarWidget QToolButton#qt_calendar_prevmonth {{
                qproperty-text: "‹";
            }}
            QCalendarWidget QToolButton#qt_calendar_nextmonth {{
                qproperty-text: "›";
            }}
            QCalendarWidget QMenu {{
                background: {t['panel']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 10px;
                padding: 5px;
            }}
            QCalendarWidget QSpinBox {{
                color: {t['text']}; background: {t['panel']};
                selection-background-color: {t['accent']};
                border: 1px solid {t['border']}; border-radius: 8px;
                padding: 4px 8px;
            }}
            QCalendarWidget QAbstractItemView {{
                color: {t['text']}; background: transparent; border: none;
                outline: none; selection-background-color: transparent;
                selection-color: #FFFFFF; font-size: 12px;
            }}
            QCalendarWidget QAbstractItemView::item {{
                border-radius: 9px; padding: 5px;
            }}
            QCalendarWidget QAbstractItemView::item:hover {{
                color: {t['accent']};
                background: {_qss_alpha(t['accent'], 0x16)};
            }}
            QCalendarWidget QHeaderView {{
                background: transparent; color: {t['sub']}; border: none;
            }}
            QCalendarWidget QHeaderView::section {{
                background: transparent; color: {t['sub']}; border: none;
                padding: 5px 0; font-size: 11px; font-weight: 600;
            }}
            QFrame#timeCard {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 12px;
            }}
            QCheckBox {{
                color: {t['text']}; spacing: 8px; font-size: 12px;
                font-weight: 600;
            }}
            QCheckBox::indicator {{
                width: 17px; height: 17px; border-radius: 5px;
                border: 1px solid {t['border']}; background: {t['panel']};
            }}
            QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
            QCheckBox::indicator:checked {{
                background: {t['accent']}; border-color: {t['accent']};
            }}
            QTimeEdit#timeEdit {{
                color: {t['text']}; background: {t['panel']};
                border: 1px solid {t['border']}; border-radius: 9px;
                padding: 6px 10px; font-size: 13px; font-weight: 700;
            }}
            QTimeEdit#timeEdit:focus {{ border-color: {t['accent']}; }}
            QTimeEdit#timeEdit:disabled {{
                color: {t['done']}; background: {t['border']};
            }}
            QPushButton#dangerGhost {{
                color: #D92D20; background: transparent; border: none;
                padding: 8px 12px;
            }}
            QPushButton#dangerGhost:hover {{
                color: #FFFFFF; background: #D92D20; border: none;
            }}
        """

    def _dialog_qss(self):
        """编辑弹窗统一样式，跟随当前主题"""
        t = self.theme
        return f"""
            QDialog {{ background: {t['panel']}; color: {t['text']}; }}
            QLabel {{ color: {t['sub']}; font-size: 12px; font-weight: bold; }}
            QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
                background: {t['card']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 10px;
                padding: 8px 11px; font-size: 13px;
            }}
            QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover, QTextEdit:hover {{
                border-color: {_qss_alpha(t['accent'], 0x80)};
            }}
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
                border: 1px solid {t['accent']}; background: {t['panel']};
            }}
            QComboBox::drop-down {{
                border: none; width: 30px; background: transparent;
            }}
            QComboBox::down-arrow {{
                image: none; width: 0; height: 0; border: none;
            }}
            QComboBox QAbstractItemView {{
                background: {t['panel']}; color: {t['text']};
                selection-background-color: {t['accent']};
                selection-color: #FFFFFF;
                border: 1px solid {t['border']}; border-radius: 9px;
                outline: none; padding: 4px;
            }}
            QCheckBox {{
                color: {t['text']}; font-size: 12px; spacing: 7px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 5px;
                border: 1px solid {t['border']}; background: {t['card']};
            }}
            QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
            QCheckBox::indicator:checked {{
                background: {t['accent']}; border-color: {t['accent']};
            }}
            QPushButton {{
                background: {t['card']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 10px;
                padding: 8px 16px; font-size: 13px; font-weight: 600;
            }}
            QPushButton:hover {{
                border-color: {t['accent']}; color: {t['accent']};
                background: {_qss_alpha(t['accent'], 0x10)};
            }}
            QPushButton:pressed {{ padding-top: 9px; padding-bottom: 7px; }}
            QPushButton:disabled {{
                color: {t['done']}; background: {t['border']};
                border-color: {t['border']};
            }}
            QDialogButtonBox QPushButton {{ min-width: 78px; padding: 9px 18px; }}
            QDialogButtonBox QPushButton:default {{
                background: {t['accent']}; color: #FFFFFF;
                border: 1px solid {t['accent']};
            }}
            QDialogButtonBox QPushButton:default:hover {{
                background: {t['accent2']}; border: 1px solid {t['accent2']};
                color: #FFFFFF;
            }}
            QScrollBar:vertical {{
                background: transparent; width: 7px; margin: 2px;
            }}
            QScrollBar::handle:vertical {{
                background: {t['border']}; border-radius: 3px; min-height: 24px;
            }}
            QScrollBar::handle:vertical:hover {{ background: {t['sub']}; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        """

    def _on_edit(self, tid):
        task = next((t for t in self.store.tasks if t["id"] == tid), None)
        if not task:
            return
        from PySide6.QtWidgets import QDialog, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("编辑待办")
        dlg.setStyleSheet(self._dialog_qss())
        v = QVBoxLayout(dlg)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(10)
        v.addWidget(QLabel("内容"))
        ed = QLineEdit(task["text"])
        ed.setPlaceholderText("这条待办要做什么？")
        v.addWidget(ed)
        row = QHBoxLayout()
        row.setSpacing(10)
        cbox = QVBoxLayout(); cbox.setSpacing(4)
        cbox.addWidget(QLabel("分类"))
        cat = QComboBox()
        cat.addItems(self.categories)
        cat.setCurrentText(task.get("category", "其他"))
        cbox.addWidget(cat)
        row.addLayout(cbox, 1)
        pbox = QVBoxLayout(); pbox.setSpacing(4)
        pbox.addWidget(QLabel("紧急程度"))
        pr = QComboBox()
        pr.addItems(PRIORITIES)
        pr.setCurrentText(task.get("priority", "普通"))
        pbox.addWidget(pr)
        row.addLayout(pbox, 1)
        v.addLayout(row)
        # 截止日期（日历选择）——循环/提醒折叠其中
        v.addWidget(QLabel("截止日期"))
        drow = QHBoxLayout(); drow.setSpacing(8)
        _edit_due = {"val": task.get("due", "")}
        _recur_state = {"val": task.get("recur", "不循环")}
        _remind_state = {"val": task.get("remind", "到期当天")}
        _recur_end = {"val": task.get("recur_end", "")}
        btn_due = QPushButton(
            f"📅  {_edit_due['val']}" if _edit_due["val"] else "📅  点击选择日期")
        btn_due.setCursor(Qt.PointingHandCursor)
        def _pick_edit_due():
            prev = self._pending_due
            self._pending_due = _edit_due["val"]
            self._pick_due(recur_state=_recur_state, remind_state=_remind_state,
                           recur_end_state=_recur_end)
            _edit_due["val"] = self._pending_due
            self._pending_due = prev
            btn_due.setText(
                f"📅  {_edit_due['val']}" if _edit_due["val"] else "📅  点击选择日期")
        btn_due.clicked.connect(_pick_edit_due)
        drow.addWidget(btn_due, 1)
        btn_due_clear = QPushButton("清除")
        btn_due_clear.setCursor(Qt.PointingHandCursor)
        def _clear_edit_due():
            _edit_due["val"] = ""
            btn_due.setText("📅  点击选择日期")
        btn_due_clear.clicked.connect(_clear_edit_due)
        drow.addWidget(btn_due_clear)
        v.addLayout(drow)
        # 备注——常驻文本框展示（与添加待办/项目待办一致，不再折叠）
        v.addWidget(QLabel("备注（可选）"))
        note_edit = QTextEdit()
        note_edit.setPlaceholderText("记录进行中的注意事项…")
        note_edit.setPlainText(task.get("note", ""))
        note_edit.setFixedHeight(70)
        note_edit.setStyleSheet(
            f"QTextEdit{{border:1px solid {_qss_alpha(self.theme['accent'], 0x66)};"
            f"border-left:3px solid {self.theme['accent']};border-radius:8px;"
            f"background:{_qss_alpha(self.theme['accent'], 0x18)};"
            f"color:{self.theme['text']};padding:6px;}}")
        v.addWidget(note_edit)
        # 小步骤（把大待办拆成几步，可选）——分条式：每步一行，可勾选 / 删除
        v.addWidget(QLabel("小步骤（可选，把这条待办拆成几步）"))
        from PySide6.QtWidgets import QWidget as _QWidget
        sub_wrap = _QWidget()
        sub_box = QVBoxLayout(sub_wrap)
        sub_box.setContentsMargins(0, 0, 0, 0)
        sub_box.setSpacing(6)
        v.addWidget(sub_wrap)
        sub_rows = []

        def _make_sub_row(text="", done=False):
            r = QHBoxLayout(); r.setSpacing(6)
            state = {"done": done}
            btn_chk = QPushButton("☑" if done else "☐")
            btn_chk.setCursor(Qt.PointingHandCursor)
            btn_chk.setFixedWidth(28)
            edit = QLineEdit(text)
            edit.setPlaceholderText("这一步要做什么？")
            btn_del = QPushButton("✕")
            btn_del.setCursor(Qt.PointingHandCursor)
            btn_del.setFixedWidth(28)

            def _toggle():
                state["done"] = not state["done"]
                btn_chk.setText("☑" if state["done"] else "☐")
                edit.setStyleSheet(
                    "text-decoration: line-through; color:#98A2B3;"
                    if state["done"] else "")
            btn_chk.clicked.connect(_toggle)
            if done:
                edit.setStyleSheet("text-decoration: line-through; color:#98A2B3;")

            rec = {"state": state, "edit": edit,
                   "widgets": [btn_chk, edit, btn_del], "layout": r}

            def _remove():
                for w in rec["widgets"]:
                    w.setParent(None)
                sub_box.removeItem(r)
                if rec in sub_rows:
                    sub_rows.remove(rec)
            btn_del.clicked.connect(_remove)

            r.addWidget(btn_chk)
            r.addWidget(edit, 1)
            r.addWidget(btn_del)
            sub_box.addLayout(r)
            sub_rows.append(rec)

        for s in task.get("subtasks", []):
            _make_sub_row(s.get("text", ""), s.get("done", False))
        btn_add_sub = QPushButton("＋ 添加一步")
        btn_add_sub.setCursor(Qt.PointingHandCursor)
        btn_add_sub.clicked.connect(lambda: _make_sub_row())
        v.addWidget(btn_add_sub)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("保存")
        bb.button(QDialogButtonBox.Cancel).setText("取消")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        v.addWidget(bb)
        if dlg.exec() == QDialog.Accepted and ed.text().strip():
            subs = []
            for rec in sub_rows:
                txt = rec["edit"].text().strip()
                if txt:
                    subs.append({"text": txt, "done": rec["state"]["done"]})
            self.store.update(tid, text=ed.text().strip(),
                              category=cat.currentText(),
                              priority=pr.currentText(),
                              due=_edit_due["val"],
                              recur=_recur_state["val"],
                              recur_end=_recur_end["val"],
                              remind=_remind_state["val"],
                              remind_log=[],
                              note=note_edit.toPlainText().strip(),
                              subtasks=subs)
            self.refresh()

    def _set_cat(self, name):
        self.active_cat = name
        for n, b in self.cat_btns.items():
            b.setChecked(n == name)
        self.refresh()

    # -- 主题 --
    def _pick_theme(self):
        """简略主题菜单：快速切换 + 「主题商店与DIY」入口跳弹窗。"""
        m = QMenu(self)
        m.addAction("选择主题").setEnabled(False)
        m.addSeparator()
        # 只展示前 8 个内置示例主题，但确保当前正在使用的主题始终可见
        shown = BUILTIN_THEME_ORDER[:8]
        if self.theme_name not in shown and self.theme_name in THEME_ORDER:
            shown = shown[:-1] + [self.theme_name]
        for name in shown:
            act = m.addAction(("● " if name == self.theme_name else "○ ") + name)
            act.setCheckable(True)
            act.setChecked(name == self.theme_name)
            act.triggered.connect(lambda checked=False, n=name: self._set_theme(n))
        m.addSeparator()
        store = m.addAction("🎨  主题商店与 DIY…")
        store.triggered.connect(self._open_theme_market)
        m.addSeparator()
        m.addAction("背景图片").setEnabled(False)
        pic = m.addAction("上传背景图片…")
        pic.triggered.connect(self._pick_bg_image)
        if self.cfg.get("bg_image"):
            clr_pic = m.addAction("清除背景图片")
            clr_pic.triggered.connect(self._clear_bg_image)
        pos = self.btn_theme.mapToGlobal(self.btn_theme.rect().bottomLeft())
        m.exec(pos)

    def _open_theme_market(self):
        """打开主题商店弹窗（卡片网格预览 + DIY 配色）。

        悬浮小西瓜是置顶窗口，会盖住模态弹窗（正好压在按钮上时点不动），
        所以打开商店期间暂时藏起小西瓜，关闭后恢复。"""
        ball = getattr(self, "floating_ball", None)
        ball_was_visible = ball is not None and ball.isVisible()
        if ball_was_visible:
            ball.hide()
        try:
            dlg = ThemeMarketDialog(self, self)
            dlg.exec()
        finally:
            ball = getattr(self, "floating_ball", None)
            if ball_was_visible and ball is not None:
                ball.show()
                try:
                    if IS_MAC:
                        _mac_bring_to_front(ball)
                    else:
                        ball.raise_()
                except Exception:
                    pass

    # -- 自定义图片背景 --
    def _load_bg_image(self):
        """从配置读取背景图片路径并加载为 QPixmap"""
        from PySide6.QtGui import QPixmap
        path = self.cfg.get("bg_image", "")
        if path and os.path.isfile(path):
            pm = QPixmap(path)
            self._bg_pixmap = pm if not pm.isNull() else None
        else:
            self._bg_pixmap = None

    def _pick_bg_image(self):
        """选择一张图片作为窗口背景"""
        from PySide6.QtWidgets import QFileDialog
        fn, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if not fn:
            return
        self.cfg["bg_image"] = fn
        self._load_bg_image()
        self._save_cfg()
        self.update()

    def _clear_bg_image(self):
        """清除自定义背景图片，恢复纯色主题"""
        self.cfg["bg_image"] = ""
        self._bg_pixmap = None
        self._save_cfg()
        self.update()

    def _set_theme(self, name):
        if name not in THEMES:
            return
        self.theme_name = name
        self.theme = THEMES[self.theme_name]
        self._apply_window_style()
        self.refresh()
        self.update()
        self._save_cfg()

    def _preview_theme(self, theme):
        """临时把一套配色套到主窗口上（不改 theme_name、不落盘）。
        DIY 配色弹窗的实时预览用；取消时再用原配色调用一次即可还原。"""
        self.theme = theme
        self._apply_window_style()
        self.refresh()
        self.update()

    def _show_menu(self):
        m = QMenu(self)
        m.addAction(f"🍉 西瓜todo v{APP_VERSION}").setEnabled(False)
        m.addSeparator()
        m.addAction(f"主题：{self.theme_name}（点🎨选择）").setEnabled(False)
        m.addSeparator()
        top = m.addAction("取消置顶" if self.cfg.get("topmost", False) else "窗口置顶")
        top.triggered.connect(self._toggle_topmost)
        auto = m.addAction("关闭开机自启" if self.cfg.get("autostart") else "开机自启")
        auto.triggered.connect(self._toggle_autostart)
        hk = m.addAction(f"快捷键设置（当前 {self._hotkey_label()}）")
        hk.triggered.connect(self._show_hotkey_dialog)
        m.addSeparator()
        ball = m.addAction(
            "收起悬浮西瓜" if getattr(self, "floating_ball", None) else "🍉 悬浮桌面小西瓜")
        ball.triggered.connect(self._toggle_floating_ball)
        m.addSeparator()
        # 打开数据文件夹
        open_folder = m.addAction("📂 打开数据文件夹")
        open_folder.triggered.connect(self._open_data_folder)
        m.addSeparator()
        clr = m.addAction("清除已完成")
        clr.triggered.connect(lambda: (self.store.clear_done(), self.refresh()))
        m.addSeparator()
        hide_a = m.addAction("隐藏到后台")
        hide_a.triggered.connect(self.hide)
        quit_a = m.addAction("彻底退出程序")
        quit_a.triggered.connect(self._real_quit)
        m.exec(QCursor.pos())

    def _open_data_folder(self):
        """打开数据文件夹(todo_data.json 和 todo_config.json 所在目录)"""
        import subprocess
        folder = USER_DIR
        if os.path.exists(folder):
            if IS_WIN:
                # Windows: 用 explorer 打开并选中文件夹
                subprocess.run(['explorer', folder], shell=False)
            elif IS_MAC:
                # macOS: 用 open 命令打开
                subprocess.run(['open', folder])
            else:
                # Linux: 尝试用默认文件管理器打开
                subprocess.run(['xdg-open', folder])
        else:
            self._show_toast("数据文件夹不存在")

    def _real_quit(self):
        """彻底退出程序（不再驻留后台）"""
        from PySide6.QtWidgets import QApplication
        self._exiting = True
        self._save_cfg()
        self._cleanup_before_quit()
        QApplication.quit()

    def _hotkey_label(self):
        """把当前快捷键配置拼成可读文本。
        Windows → Ctrl+Alt+T；macOS → ⌘⌥T（用 Mac 惯用修饰键符号）"""
        hk = self.cfg.get("hotkey") or {}
        key = str(hk.get("key", "T")).upper()
        if IS_MAC:
            # macOS 惯例：ctrl 位对应 ⌘Command，alt 位对应 ⌥Option
            parts = []
            if hk.get("ctrl", True):
                parts.append("⌘")
            if hk.get("alt", True):
                parts.append("⌥")
            if hk.get("shift", False):
                parts.append("⇧")
            return "".join(parts) + key
        parts = []
        if hk.get("ctrl", True):
            parts.append("Ctrl")
        if hk.get("alt", True):
            parts.append("Alt")
        if hk.get("shift", False):
            parts.append("Shift")
        parts.append(key)
        return "+".join(parts)

    def _show_hotkey_dialog(self):
        """快捷键设置对话框：选修饰键 + 主键，保存后立即重注册全局热键"""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout,
                                       QCheckBox, QLabel,
                                       QDialogButtonBox)
        hk = self.cfg.get("hotkey") or {}
        dlg = QDialog(self)
        dlg.setWindowTitle("快捷键设置")
        dlg.setStyleSheet(self._dialog_qss())
        dlg.setMinimumWidth(360)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        lay.addWidget(QLabel("设置「召唤/隐藏窗口」的全局快捷键：\n（至少勾选一个修饰键）"))
        if IS_MAC:
            tip = QLabel("macOS 使用 Command / Option / Shift 组合键；"
                         "保存后立即生效。")
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#667085;font-size:12px;")
            lay.addWidget(tip)

        row = QHBoxLayout()
        # 修饰键名称按平台显示：Mac 用 ⌘Command / ⌥Option
        if IS_MAC:
            chk_ctrl = QCheckBox("⌘ Command")
            chk_alt = QCheckBox("⌥ Option")
            chk_shift = QCheckBox("⇧ Shift")
        else:
            chk_ctrl = QCheckBox("Ctrl")
            chk_alt = QCheckBox("Alt")
            chk_shift = QCheckBox("Shift")
        chk_ctrl.setChecked(hk.get("ctrl", True))
        chk_alt.setChecked(hk.get("alt", True))
        chk_shift.setChecked(hk.get("shift", False))
        row.addWidget(chk_ctrl); row.addWidget(chk_alt); row.addWidget(chk_shift)
        lay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("主键："))
        key_pick = QComboBox()
        keys = [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        keys += [str(n) for n in range(0, 10)]
        keys += ["F" + str(n) for n in range(1, 13)]
        key_pick.addItems(keys)
        cur_key = str(hk.get("key", "T")).upper()
        if cur_key in keys:
            key_pick.setCurrentText(cur_key)
        row2.addWidget(key_pick, 1)
        lay.addLayout(row2)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("保存")
        btns.button(QDialogButtonBox.Cancel).setText("取消")
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)

        if dlg.exec() == QDialog.Accepted:
            if not (chk_ctrl.isChecked() or chk_alt.isChecked() or chk_shift.isChecked()):
                chk_ctrl.setChecked(True)  # 兜底：至少一个修饰键
            self.cfg["hotkey"] = {
                "ctrl": chk_ctrl.isChecked(),
                "alt": chk_alt.isChecked(),
                "shift": chk_shift.isChecked(),
                "key": key_pick.currentText(),
            }
            self._save_cfg()
            # 立即重注册全局热键
            self._hotkey_filter = _register_global_hotkey(self)
            if self._hotkey_filter is None and (IS_WIN or IS_MAC):
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(
                    self,
                    "快捷键注册失败",
                    "该快捷键可能已被其他应用占用，请换一个组合后重试。",
                )

    def toggle_visibility(self):
        """全局快捷键召唤/隐藏：可见时隐藏；隐藏时以完整界面召回并置前"""
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            # 若之前处于折叠状态，召回时强制恢复为完整展开界面
            if getattr(self, "collapsed", False):
                self.collapsed = False
                self._apply_collapsed()
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def summon_to_front(self):
        """把窗口召回到前台并置顶激活（用于再次双击程序时唤起已运行实例）。"""
        if getattr(self, "collapsed", False):
            self.collapsed = False
            self._apply_collapsed()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    # -- 桌面悬浮小西瓜 --
    def _toggle_floating_ball(self):
        """开/关桌面悬浮小西瓜，并把状态写入配置。"""
        on = not bool(getattr(self, "floating_ball", None))
        self.cfg["floating_ball"] = on
        if on:
            self._show_floating_ball()
        else:
            self._hide_floating_ball()
        self._save_cfg()

    def _show_floating_ball(self):
        if getattr(self, "floating_ball", None) is None:
            self.floating_ball = FloatingBall(self)
        self.floating_ball.show()
        # macOS 上用 orderFrontRegardless 把悬浮球顶到最前且浮在主窗口之上，
        # 但绝不激活本 App（不影响微信等前台 App 焦点）；延迟一帧确保主窗口
        # show 之后悬浮球仍在最前，避免被主窗口遮挡导致“桌面上看不到西瓜”。
        if IS_MAC:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: _mac_bring_to_front(self.floating_ball))
        else:
            self.floating_ball.raise_()

    def _hide_floating_ball(self):
        if getattr(self, "floating_ball", None) is not None:
            try:
                self.floating_ball.close()
            except Exception:
                pass
            self.floating_ball = None

    # -- 系统托盘 --
    def _setup_tray(self):
        """在系统托盘放一个图标（Windows 右下角通知区 / macOS 右上角菜单栏），
        让用户能直观看到程序在运行，并可通过它显示/隐藏窗口或退出。"""
        self.tray = None
        try:
            if not QSystemTrayIcon.isSystemTrayAvailable():
                return
            logo_path = _resource_path("watermelon_logo.svg")
            icon = QIcon(str(logo_path)) if logo_path.exists() else self.windowIcon()
            if icon.isNull():
                # 兜底：用应用图标
                icon = QApplication.windowIcon()
            self.tray = QSystemTrayIcon(icon, self)
            self.tray.setToolTip("西瓜todo 正在运行")

            from PySide6.QtGui import QAction
            menu = QMenu()
            act_show = QAction("显示 / 隐藏窗口", self)
            act_show.triggered.connect(self._toggle_visibility)
            act_quit = QAction("退出", self)
            act_quit.triggered.connect(self._quit_from_tray)
            menu.addAction(act_show)
            menu.addSeparator()
            menu.addAction(act_quit)
            self.tray.setContextMenu(menu)

            # 双击 / 单击托盘图标：唤起窗口到前台
            self.tray.activated.connect(self._on_tray_activated)
            self.tray.show()

            # 首次运行时弹一条气泡提示，告诉用户去哪找它（不同系统托盘位置不同）
            if not self.cfg.get("tray_tip_shown", False):
                if sys.platform == "darwin":
                    tray_where = "屏幕右上角菜单栏"   # macOS 状态栏在顶部
                else:
                    tray_where = "屏幕右下角托盘"       # Windows / Linux 在右下角
                try:
                    self.tray.showMessage(
                        "西瓜todo 已启动",
                        f"窗口在桌面上；关闭窗口后可在{tray_where}的小西瓜里重新打开。",
                        QSystemTrayIcon.Information, 5000)
                except Exception:
                    pass
                self.cfg["tray_tip_shown"] = True
                save_config(self.cfg)
        except Exception:
            self.tray = None

    def _on_tray_activated(self, reason):
        # 双击或单击（Trigger）都唤起窗口
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.summon_to_front()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self.summon_to_front()

    def _quit_from_tray(self):
        """从托盘菜单彻底退出。"""
        self._exiting = True
        self.close()

    def _toggle_topmost(self):
        cur = self.cfg.get("topmost", False)
        self.cfg["topmost"] = not cur
        self.setWindowFlags(_float_window_flags(topmost=self.cfg["topmost"]))
        _apply_no_steal_focus(self, accept_focus=True)
        self.show()
        self._save_cfg()

    def _toggle_autostart(self):
        newv = not self.cfg.get("autostart", False)
        if set_autostart(newv):
            self.cfg["autostart"] = newv
            self._save_cfg()

    # -- 提醒 --
    def _check_reminders(self):
        now = datetime.datetime.now()
        changed = False
        for t in self.store.tasks:
            if t["status"] == "done":
                continue
            due = t.get("due", "")
            if not due:
                continue
            d, tm = parse_due(due)
            if d is None:
                continue
            lead = REMIND_TYPES.get(t.get("remind", "到期当天"), 0)
            if lead is None:   # 关闭提醒
                continue
            log = t.setdefault("remind_log", [])
            due_dt = due_datetime(due)   # 无时间点时按当天 23:59
            if due_dt is None:
                continue

            # ① 提前提醒（分钟制）：在 截止 - lead 分钟 之后、截止之前触发一次
            if lead > 0 and "ahead" not in log:
                remind_at = due_dt - datetime.timedelta(minutes=lead)
                if remind_at <= now < due_dt:
                    self._notify(t["text"], self._lead_phrase(lead), due, urgent=False)
                    log.append("ahead")
                    changed = True

            # ② 到期/过期提醒：到点后触发一次
            if now >= due_dt and "due" not in log:
                overdue = now > due_dt + datetime.timedelta(minutes=1)
                self._notify(t["text"], "已过期" if overdue else "现在到期啦",
                             due, urgent=True)
                log.append("due")
                t["notified"] = True
                changed = True

        # === 强提醒 ===
        # 规则：任务未做完、且开启了强提醒，则在“截止前 N 单位 ~ 截止”时间窗内，
        # 每隔“每 M 单位”弹出一次（居中强提醒弹窗 + 可选悬浮小西瓜浮窗），
        # 受“最多 N 次”上限约束。非阻塞，避免卡住提醒检查循环。
        for t in self.store.tasks:
            if t["status"] == "done":
                continue
            s = t.get("strong") or _default_strong()
            if not s.get("enabled"):
                continue
            due = t.get("due", "")
            due_dt = due_datetime(due) if due else None
            if due_dt is None:
                continue
            # 起始时刻：截止前 before_value 单位；before=0 表示“从现在起就提醒”
            if int(s.get("before_value", 1)) <= 0:
                start_dt = datetime.datetime.min
            else:
                start_dt = due_dt - datetime.timedelta(
                    seconds=_strong_seconds(s["before_value"], s["before_unit"]))
            if now < start_dt or now >= due_dt:
                continue
            interval_sec = _strong_seconds(s["interval_value"], s["interval_unit"])
            last_dt = None
            if s.get("last"):
                try:
                    last_dt = datetime.datetime.fromisoformat(s["last"])
                except Exception:
                    last_dt = None
            if last_dt is not None and (now - last_dt).total_seconds() < interval_sec:
                continue  # 还没到下一次提醒
            max_count = int(s.get("max_count", 0) or 0)
            if max_count > 0 and int(s.get("count", 0)) >= max_count:
                continue  # 已达次数上限
            text = (t.get("text") or "").strip() or "未命名待办"
            # 可选：悬浮小西瓜浮窗提醒
            if s.get("float_window") and getattr(self, "floating_ball", None) is not None:
                self.floating_ball.force_bubble("记得" + text + "哦～", ms=6000)
            # 居中强提醒弹窗（非阻塞，8 秒后自动关闭）
            dlg = ReminderPopup(self.theme, text, "强提醒", due=due, urgent=True, parent=self)
            dlg.show()
            QTimer.singleShot(8000, dlg.close)
            s["last"] = now.isoformat(timespec="seconds")
            s["count"] = int(s.get("count", 0)) + 1
            changed = True

        if changed:
            self.store.save()

    @staticmethod
    def _lead_phrase(lead):
        """把提前分钟数转成友好话术"""
        if lead >= 1440:
            return f"还有 {lead // 1440} 天到期"
        if lead >= 60:
            h = lead // 60
            return f"还有 {h} 小时到期"
        return f"还有 {lead} 分钟到期"

    def _notify(self, task_text, phrase, due="", urgent=False):
        """居中的高颜值提醒弹窗（无边框 / 圆角 / 跟随主题）"""
        try:
            dlg = ReminderPopup(self.theme, task_text, phrase, due, urgent, self)
            dlg.exec()
        except Exception:
            # 兜底：极端情况下退回系统弹窗，保证提醒不丢
            from PySide6.QtWidgets import QMessageBox
            box = QMessageBox(self)
            box.setWindowTitle("🍉 西瓜todo 提醒")
            box.setText(f"「{task_text}」{phrase}")
            box.setWindowFlags(box.windowFlags() | Qt.WindowStaysOnTopHint)
            box.exec()

    # -- 配置持久化 --
    def _save_cfg(self):
        g = self.geometry()
        # 折叠态下真实高度是 52，不能写入 geometry；用展开高度
        if not self.collapsed:
            self.expanded_height = g.height()
        h = self.expanded_height
        self.cfg["geometry"] = [g.x(), g.y(), g.width(), h]
        self.cfg["expanded_height"] = self.expanded_height
        self.cfg["theme"] = self.theme_name
        self.cfg["collapsed"] = self.collapsed
        save_config(self.cfg)

    def _cleanup_before_quit(self):
        """彻底退出前释放后台资源：托盘、悬浮球、单实例锁、全局热键。"""
        # 移除托盘图标，避免退出后残留
        try:
            if getattr(self, "tray", None) is not None:
                self.tray.hide()
                self.tray = None
        except Exception:
            pass
        # 关闭悬浮小西瓜，避免残留在桌面
        try:
            if getattr(self, "floating_ball", None) is not None:
                self.floating_ball.close()
                self.floating_ball = None
        except Exception:
            pass
        # 释放单实例锁 + 注销全局热键，避免进程残留导致下次打不开
        try:
            global _single_server
            if _single_server is not None:
                _single_server.close()
                from PySide6.QtNetwork import QLocalServer
                QLocalServer.removeServer("DesktopTodo_SingleInstance")
        except Exception:
            pass
        _unregister_global_hotkey(self)

    def closeEvent(self, e):
        if getattr(self, "_exiting", False):
            # 真正退出：释放后台资源后允许窗口关闭
            self._cleanup_before_quit()
            super().closeEvent(e)
            return
        # 点红点关闭 = 缩到托盘（不真正退出，进程继续驻留后台）
        self._save_cfg()
        e.ignore()
        self.hide()


# ----------------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------------
class _HotkeyFilter(QAbstractNativeEventFilter):
    """Win32 全局热键过滤器：捕获 WM_HOTKEY 并回调"""
    WM_HOTKEY = 0x0312

    def __init__(self, hotkey_id, callback):
        super().__init__()
        self.hotkey_id = hotkey_id
        self.callback = callback

    def nativeEventFilter(self, event_type, message):
        try:
            if event_type in (b"windows_generic_MSG", "windows_generic_MSG"):
                msg = ctypes.wintypes.MSG.from_address(int(message))
                if msg.message == self.WM_HOTKEY and msg.wParam == self.hotkey_id:
                    self.callback()
        except Exception:
            pass
        return False, 0, 0


def _key_to_vk(key):
    """把单个主键字符转成 Win32 虚拟键码。支持 A-Z、0-9、F1-F12"""
    if not key:
        return 0x54  # 默认 T
    key = key.strip().upper()
    if key.startswith("F") and key[1:].isdigit():
        n = int(key[1:])
        if 1 <= n <= 12:
            return 0x70 + (n - 1)  # VK_F1 = 0x70
    if len(key) == 1:
        c = key[0]
        if "A" <= c <= "Z" or "0" <= c <= "9":
            return ord(c)
    return 0x54


class _MacEventTypeSpec(ctypes.Structure if IS_MAC else object):
    """Carbon 事件类型描述。"""

    if IS_MAC:
        _fields_ = [
            ("event_class", ctypes.c_uint32),
            ("event_kind", ctypes.c_uint32),
        ]


class _MacEventHotKeyID(ctypes.Structure if IS_MAC else object):
    """Carbon 全局快捷键标识。"""

    if IS_MAC:
        _fields_ = [
            ("signature", ctypes.c_uint32),
            ("hotkey_id", ctypes.c_uint32),
        ]


class _MacGlobalHotkey:
    """使用 macOS Carbon API 注册系统级全局快捷键。"""

    EVENT_CLASS_KEYBOARD = int.from_bytes(b"keyb", "big")
    EVENT_HOTKEY_PRESSED = 5
    HOTKEY_SIGNATURE = int.from_bytes(b"WMTD", "big")

    def __init__(self, key_code, modifiers, callback):
        hitoolbox_path = (
            "/System/Library/Frameworks/Carbon.framework/Frameworks/"
            "HIToolbox.framework/HIToolbox"
        )
        self._carbon = ctypes.cdll.LoadLibrary(hitoolbox_path)
        self._callback = callback
        self._handler_ref = ctypes.c_void_p()
        self._hotkey_ref = ctypes.c_void_p()
        self._event_handler_proc = ctypes.CFUNCTYPE(
            ctypes.c_int32,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
        )
        self._handler_callback = self._event_handler_proc(self._on_hotkey)
        self._configure_api()

        event_type = _MacEventTypeSpec(
            self.EVENT_CLASS_KEYBOARD,
            self.EVENT_HOTKEY_PRESSED,
        )
        status = self._carbon.InstallEventHandler(
            self._carbon.GetApplicationEventTarget(),
            self._handler_callback,
            1,
            ctypes.byref(event_type),
            None,
            ctypes.byref(self._handler_ref),
        )
        if status != 0:
            raise RuntimeError(f"安装 macOS 快捷键事件处理器失败：{status}")

        hotkey_id = _MacEventHotKeyID(self.HOTKEY_SIGNATURE, 1)
        status = self._carbon.RegisterEventHotKey(
            key_code,
            modifiers,
            hotkey_id,
            self._carbon.GetApplicationEventTarget(),
            0,
            ctypes.byref(self._hotkey_ref),
        )
        if status != 0:
            self.close()
            raise RuntimeError(f"注册 macOS 全局快捷键失败：{status}")

    def _configure_api(self):
        self._carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        self._carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            self._event_handler_proc,
            ctypes.c_uint32,
            ctypes.POINTER(_MacEventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._carbon.InstallEventHandler.restype = ctypes.c_int32
        self._carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            _MacEventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        self._carbon.RegisterEventHotKey.restype = ctypes.c_int32
        self._carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        self._carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]

    def _on_hotkey(self, _next_handler, _event, _user_data):
        try:
            self._callback()
        except RuntimeError:
            pass
        return 0

    def close(self):
        """注销快捷键并移除 Carbon 事件处理器。"""
        if self._hotkey_ref.value:
            self._carbon.UnregisterEventHotKey(self._hotkey_ref)
            self._hotkey_ref = ctypes.c_void_p()
        if self._handler_ref.value:
            self._carbon.RemoveEventHandler(self._handler_ref)
            self._handler_ref = ctypes.c_void_p()


def _key_to_mac_keycode(key):
    """把主键转换成 macOS 虚拟键码。"""
    key_codes = {
        "A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5, "Z": 6,
        "X": 7, "C": 8, "V": 9, "B": 11, "Q": 12, "W": 13, "E": 14,
        "R": 15, "Y": 16, "T": 17, "1": 18, "2": 19, "3": 20,
        "4": 21, "6": 22, "5": 23, "9": 25, "7": 26, "8": 28,
        "0": 29, "O": 31, "U": 32, "I": 34, "P": 35, "L": 37,
        "J": 38, "K": 40, "N": 45, "M": 46,
        "F1": 122, "F2": 120, "F3": 99, "F4": 118, "F5": 96,
        "F6": 97, "F7": 98, "F8": 100, "F9": 101, "F10": 109,
        "F11": 103, "F12": 111,
    }
    return key_codes.get(str(key).strip().upper(), key_codes["T"])


def _unregister_global_hotkey(widget):
    """注销当前平台的全局快捷键。"""
    old = getattr(widget, "_hotkey_filter", None)
    if IS_WIN:
        try:
            ctypes.windll.user32.UnregisterHotKey(None, 0xB001)
        except (AttributeError, OSError):
            pass
        if old is not None:
            try:
                QApplication.instance().removeNativeEventFilter(old)
            except RuntimeError:
                pass
    elif IS_MAC and old is not None:
        old.close()
    widget._hotkey_filter = None


def _register_global_hotkey(widget):
    """按配置注册全局热键召唤窗口，可重复调用以更新绑定。"""
    _unregister_global_hotkey(widget)
    if IS_MAC:
        try:
            hk = (widget.cfg.get("hotkey") or {}) if hasattr(widget, "cfg") else {}
            modifiers = 0
            if hk.get("ctrl", True):
                modifiers |= 1 << 8  # cmdKey
            if hk.get("alt", True):
                modifiers |= 1 << 11  # optionKey
            if hk.get("shift", False):
                modifiers |= 1 << 9  # shiftKey
            if modifiers == 0:
                modifiers = (1 << 8) | (1 << 11)
            key_code = _key_to_mac_keycode(hk.get("key", "T"))
            return _MacGlobalHotkey(
                key_code,
                modifiers,
                widget.toggle_visibility,
            )
        except (OSError, RuntimeError):
            return None
    if not IS_WIN:
        return None
    try:
        import ctypes.wintypes  # noqa
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        HOTKEY_ID = 0xB001
        user32 = ctypes.windll.user32

        hk = (widget.cfg.get("hotkey") or {}) if hasattr(widget, "cfg") else {}
        mods = 0
        if hk.get("ctrl", True):
            mods |= MOD_CONTROL
        if hk.get("alt", True):
            mods |= MOD_ALT
        if hk.get("shift", False):
            mods |= MOD_SHIFT
        if mods == 0:
            mods = MOD_CONTROL | MOD_ALT  # 至少要一个修饰键
        vk = _key_to_vk(hk.get("key", "T"))

        if not user32.RegisterHotKey(None, HOTKEY_ID, mods, vk):
            return None
        flt = _HotkeyFilter(HOTKEY_ID, widget.toggle_visibility)
        QApplication.instance().installNativeEventFilter(flt)
        return flt
    except Exception:
        return None


# ----------------------------------------------------------------------------
# 检查更新：后台线程请求 GitHub 最新 Release，比当前版本新则回主线程弹窗
# ----------------------------------------------------------------------------
def _parse_version(v):
    # "v2.3" / "2.3.1" → (2, 3, 1) 便于比较；非数字段忽略
    nums = []
    for part in str(v).lstrip("vV").split("."):
        try:
            nums.append(int("".join(ch for ch in part if ch.isdigit())))
        except ValueError:
            nums.append(0)
    return tuple(nums) if nums else (0,)


class _UpdateChecker(QThread):
    # 发现新版本时发射：(最新版本号, 更新说明)
    found = Signal(str, str)

    def run(self):
        try:
            import json as _json
            from urllib.request import urlopen, Request
            req = Request(UPDATE_API, headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "watermelon-todo-updater",
            })
            with urlopen(req, timeout=8) as resp:
                data = _json.loads(resp.read().decode("utf-8"))
            latest = str(data.get("tag_name") or "").strip()
            body = str(data.get("body") or "").strip()
            if latest and _parse_version(latest) > _parse_version(APP_VERSION):
                self.found.emit(latest, body)
        except Exception:
            # 网络不通/超时/无发布等一律静默，不打扰用户
            pass


def _start_update_check(parent):
    checker = _UpdateChecker(parent)

    def _on_found(latest, body):
        from PySide6.QtWidgets import QMessageBox
        note = body[:300] + ("…" if len(body) > 300 else "") if body else ""
        text = f"发现新版本 {latest}（当前 {APP_VERSION}）。\n\n是否前往下载页更新？"
        if note:
            text += f"\n\n更新说明：\n{note}"
        box = QMessageBox(parent)
        box.setWindowTitle("西瓜todo · 检查更新")
        box.setIcon(QMessageBox.Information)
        box.setText(text)
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.button(QMessageBox.Yes).setText("去下载")
        box.button(QMessageBox.No).setText("以后再说")
        if box.exec() == QMessageBox.Yes:
            QDesktopServices.openUrl(QUrl(RELEASE_PAGE))

    checker.found.connect(_on_found)
    checker.start()
    # 挂到 parent 上防止被垃圾回收
    parent._update_checker = checker


def main():
    app = QApplication(sys.argv)
    # Windows 命名互斥体：供 Inno Setup 安装器（AppMutex）识别本程序是否在运行，
    # 从而在覆盖安装时可靠地检测并请求关闭旧版，避免卡在“Closing applications...”。
    # 名称必须与 .iss 里的 AppMutex 完全一致。
    if IS_WIN:
        try:
            import ctypes
            _WT_MUTEX_NAME = "WatermelonTodo_AppMutex"
            # 保存到模块级引用，防止被 GC 释放导致 mutex 提前消失
            global _wt_app_mutex
            _wt_app_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, _WT_MUTEX_NAME)
        except Exception:
            pass
    logo_path = _resource_path("watermelon_logo.svg")
    if logo_path.exists():
        app.setWindowIcon(QIcon(str(logo_path)))
    app.setQuitOnLastWindowClosed(False)  # 点红点关闭 = 缩到托盘，不自动退出
    # 单实例检测：用 QLocalServer/QLocalSocket。相比 QSharedMemory，它能可靠区分
    # “真有实例在运行”（能连上 server）和“上次异常退出的残留”（连不上则移除陈旧 server 重建），
    # 避免残留导致程序永远打不开。
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    _SRV_NAME = "DesktopTodo_SingleInstance"
    _probe = QLocalSocket()
    _probe.connectToServer(_SRV_NAME)
    if _probe.waitForConnected(300):
        # 已有实例在运行：发一条 "show" 通知老实例把窗口召回前台，然后自己退出
        try:
            _probe.write(b"show")
            _probe.flush()
            _probe.waitForBytesWritten(300)
        except Exception:
            pass
        _probe.abort()
        sys.exit(0)
    _probe.abort()
    global _single_server
    QLocalServer.removeServer(_SRV_NAME)   # 清理上次异常退出可能残留的陈旧 server
    _single_server = QLocalServer()
    _single_server.listen(_SRV_NAME)
    try:
        # 按平台选择系统自带中文字体，避免缺字/方框
        if IS_WIN:
            _families = ["微软雅黑", "Microsoft YaHei"]
        elif IS_MAC:
            _families = ["PingFang SC", "苹方-简", "Heiti SC", "STHeiti"]
        else:
            _families = ["Noto Sans CJK SC", "WenQuanYi Micro Hei", "Sans Serif"]
        _f = QFont()
        _f.setFamilies(_families)
        _f.setPointSize(10)
        app.setFont(_f)
    except Exception:
        pass
    w = TodoWidget()
    w.show()
    # macOS 修复：点 dock 图标只是把 App 激活，不会自动把被隐藏的 Qt 主窗口 show 出来
    # （Qt 未实现 macOS 的“重新打开”处理器）。在 App 变为激活态、且主窗口不可见时，
    # 主动召回到前台，使 dock 点击与托盘/悬浮球单击行为一致。
    app.applicationStateChanged.connect(
        lambda st: w.summon_to_front()
        if st == Qt.ApplicationActive and not w.isVisible() else None
    )
    # 当再次启动本程序时，新实例会连上来发 "show"，这里收到后把窗口召回前台
    def _on_new_connection():
        try:
            sock = _single_server.nextPendingConnection()
            if sock is None:
                return
            def _handle():
                try:
                    sock.readAll()
                except Exception:
                    pass
                w.summon_to_front()
                sock.disconnectFromServer()
            sock.readyRead.connect(_handle)
            # 兜底：即便没读到数据，短暂延时后也召回一次
            QTimer.singleShot(200, w.summon_to_front)
        except Exception:
            pass
    _single_server.newConnection.connect(_on_new_connection)
    # 注册全局快捷键：Windows 为 Ctrl+Alt+T，macOS 为 Command+Option+T
    w._hotkey_filter = _register_global_hotkey(w)
    # 启动 3 秒后后台检查更新（不阻塞界面，网络异常静默）
    QTimer.singleShot(3000, lambda: _start_update_check(w))
    sys.exit(app.exec())


if __name__ == "__main__":
    # pythonw 下 stdout/stderr 为 None，且崩溃无控制台可见 —— 兜底重定向并记录异常到日志
    import io
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()
    try:
        main()
    except SystemExit:
        raise
    except Exception:
        import traceback
        try:
            _log = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "_crash.log")
            with open(_log, "w", encoding="utf-8") as _f:
                _f.write(traceback.format_exc())
        except Exception:
            pass
        raise
