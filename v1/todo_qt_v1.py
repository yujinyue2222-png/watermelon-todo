# -*- coding: utf-8 -*-
"""
桌面待办插件 · PySide6 高颜值版  (v1.0)
- 无边框 / 圆角 / 半透明毛玻璃质感
- 精致任务卡片 + 微交互动效
- 多套精品主题
- JSON 本地持久化 / 定时提醒 / 开机自启
- 全局快捷键可自定义

版本历史：
  v1.0  (2026-07-13) 首个正式版：分条小步骤、时间点截止、%APPDATA% 数据隔离、
                      单文件 exe 分发、可配置全局快捷键
"""

APP_VERSION = "1.0"
import sys
import os
import json
import random
import getpass
import datetime
# 平台判断：Windows 才使用 Win32 相关能力（ctypes / 全局热键 / 启动文件夹）
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"
if IS_WIN:
    import ctypes
    import ctypes.wintypes

from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QLineEdit, QVBoxLayout,
    QHBoxLayout, QScrollArea, QFrame, QGraphicsDropShadowEffect, QComboBox,
    QMenu, QSizePolicy, QGraphicsOpacityEffect, QLayout
)
from PySide6.QtCore import (
    Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, QRect, QSize, Signal,
    QAbstractNativeEventFilter
)
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPainterPath, QBrush, QCursor, QIcon, QFontDatabase
)

# ----------------------------------------------------------------------------
# 路径
# ----------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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
}
THEME_ORDER = list(THEMES.keys())

CAT_COLORS = {
    "工作": "#4C6FFF", "生活": "#2FA96B",
    "学习": "#F2751F", "其他": "#8A94A6",
}


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
    "{name}，你比想象中更棒 💖",
    "{name}，把大事拆小，就不难啦 📌",
    "{name}，深呼吸，开始行动吧 🌈",
    "{name}，今天的努力都算数 ⭐",
    "{name}，冲鸭，好运在路上 🍭",
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

    def save(self):
        try:
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self.tasks, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def add(self, text, category="其他", due="", priority="普通",
            recur="不循环", recur_end="", remind="到期当天"):
        tid = str(int(datetime.datetime.now().timestamp() * 1000))
        self.tasks.append({
            "id": tid, "text": text, "status": "todo",
            "category": category, "due": due, "priority": priority,
            "recur": recur, "recur_end": recur_end, "subtasks": [],
            "remind": remind, "remind_log": [],
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "notified": False,
        })
        self.save()
        return tid

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
        total = len(self.tasks)
        done = sum(1 for t in self.tasks if t["status"] == "done")
        urgent = sum(1 for t in self.tasks
                     if t["status"] != "done"
                     and t.get("priority") in URGENT_PRIORITIES)
        return total, done, urgent


def load_config():
    default = {"theme": "极光白", "topmost": True,
               "geometry": [140, 120, 340, 500], "collapsed": False,
               "autostart": False, "categories": list(CATEGORIES),
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
    """无截止时间排最后（按 datetime 精确排序）"""
    dt = due_datetime(due)
    if dt is None:
        return datetime.datetime.max
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
PRIORITY_ICON = {"P0": "🔥", "P1": "🔥", "P2": "🔥", "重要": "⭐", "普通": ""}
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


class ReminderPopup(QWidget):
    """居中显示的高颜值提醒弹窗：无边框、圆角、阴影、跟随主题配色。
    自带一层半透明遮罩铺满屏幕，把注意力聚焦到中央卡片上。"""

    def __init__(self, theme, task_text, phrase, due="", urgent=False, parent=None):
        super().__init__(None)
        self.theme = theme
        self._result_loop = None
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
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


class TaskCard(QFrame):
    toggled = Signal(str)
    deleted = Signal(str)
    edited = Signal(str)
    sub_toggled = Signal(str, int)   # (任务id, 子任务索引)
    select_toggled = Signal(str, bool)   # (任务id, 是否选中)
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        top = QWidget()
        lay = QHBoxLayout(top)
        lay.setContentsMargins(12, 6, 10, 6)
        lay.setSpacing(8)

        # 优先级左侧色条
        self.pbar = QFrame()
        self.pbar.setObjectName("pbar")
        self.pbar.setFixedWidth(4)
        lay.addWidget(self.pbar)

        # 状态圆点按钮（选择模式下变为复选框）
        self.dot = QPushButton()
        self.dot.setObjectName("dot")
        self.dot.setFixedSize(24, 24)
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

        # 编辑按钮（悬浮显示）
        self.edit_btn = QPushButton("✎")
        self.edit_btn.setObjectName("edit")
        self.edit_btn.setFixedSize(22, 22)
        self.edit_btn.setCursor(Qt.PointingHandCursor)
        self.edit_btn.clicked.connect(lambda: self.edited.emit(self.task["id"]))
        self.edit_btn.setVisible(False)
        lay.addWidget(self.edit_btn, 0, Qt.AlignVCenter)

        # 删除按钮（悬浮显示）
        self.del_btn = QPushButton("✕")
        self.del_btn.setObjectName("del")
        self.del_btn.setFixedSize(22, 22)
        self.del_btn.setCursor(Qt.PointingHandCursor)
        self.del_btn.clicked.connect(lambda: self.deleted.emit(self.task["id"]))
        self.del_btn.setVisible(False)
        lay.addWidget(self.del_btn, 0, Qt.AlignVCenter)

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

    def _toggle_subs(self):
        self.sub_panel.setVisible(not self.sub_panel.isVisible())

    def _on_select_click(self):
        self.selected = not self.selected
        self.dot.setText("☑" if self.selected else "☐")
        self.select_toggled.emit(self.task["id"], self.selected)

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
        self.setStyleSheet(f"""
            QFrame#card {{
                background: {t['card']};
                border-radius: 8px;
                border: none;
                border-bottom: 1px solid {t['border']};
            }}
            QFrame#pbar {{
                background: {'transparent' if (done or pr == '普通') else pc};
                border-radius: 2px;
            }}
            QLabel#prio {{
                color: #FFFFFF; font-size: 11px; font-weight: bold;
                background: {pc}; border-radius: 7px; padding: 2px 8px;
            }}
            QPushButton#dot {{
                background: transparent; border: none;
                color: {t['accent']}; font-size: 18px; font-weight: bold;
            }}
            QLabel#title {{
                color: {title_color}; font-size: 14px;
                text-decoration: {deco};
            }}
            QLabel#cat {{
                color: {c}; font-size: 11px; font-weight: bold;
                background: {c}22; border-radius: 7px;
                padding: 2px 8px;
            }}
            QLabel#due {{
                color: {t['sub']}; font-size: 11px;
                background: {t['border']}; border-radius: 7px; padding: 2px 8px;
            }}
            QLabel#due_urgent {{
                color: #FFFFFF; font-size: 11px; font-weight: bold;
                background: #F2564B; border-radius: 7px; padding: 2px 8px;
            }}
            QLabel#recur {{
                color: {t['accent']}; font-size: 11px; font-weight: bold;
                background: {t['accent']}22; border-radius: 7px; padding: 2px 8px;
            }}
            QPushButton#del {{
                background: transparent; border: none;
                color: {t['sub']}; font-size: 13px;
            }}
            QPushButton#del:hover {{ color: #F2564B; }}
            QPushButton#edit {{
                background: transparent; border: none;
                color: {t['sub']}; font-size: 13px;
            }}
            QPushButton#edit:hover {{ color: {t['accent']}; }}
            QPushButton#subbadge {{
                color: {t['accent']}; font-size: 11px; font-weight: bold;
                background: {t['accent']}22; border: none;
                border-radius: 7px; padding: 2px 8px;
            }}
            QWidget#subpanel {{ background: transparent; }}
            QPushButton#subitem {{
                color: {t['sub']}; font-size: 12px; text-align: left;
                background: transparent; border: none; padding: 1px 4px;
            }}
            QPushButton#subitem:hover {{ color: {t['accent']}; }}
        """)

    def enterEvent(self, e):
        self._hover = True
        self.del_btn.setVisible(True)
        self.edit_btn.setVisible(True)
        self.setStyleSheet(self.styleSheet().replace(
            self.theme["card"], self.theme["card_hover"], 1))
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.del_btn.setVisible(False)
        self.edit_btn.setVisible(False)
        self._apply_style()
        super().leaveEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.edited.emit(self.task["id"])
        super().mouseDoubleClickEvent(e)


# ----------------------------------------------------------------------------
# 主窗口
# ----------------------------------------------------------------------------
class TodoWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.store = Store()
        self.cfg = load_config()
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
        self.categories = self.cfg.get("categories") or list(CATEGORIES)
        self._bg_pixmap = None
        self._load_bg_image()

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Tool |
            (Qt.WindowStaysOnTopHint if self.cfg.get("topmost", False) else Qt.Widget))
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

        # 定时提醒
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._check_reminders)
        self.timer.start(30000)

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
        root.addLayout(self._build_input())
        root.addLayout(self._build_catbar())

        # 任务列表滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setObjectName("scroll")
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_holder = QWidget()
        self.list_lay = QVBoxLayout(self.list_holder)
        self.list_lay.setContentsMargins(0, 2, 0, 2)
        self.list_lay.setSpacing(2)
        self.list_lay.addStretch()
        self.scroll.setWidget(self.list_holder)
        root.addWidget(self.scroll, 1)

        # 批量操作条（多选模式时显示）
        self.batch_bar = self._build_batch_bar()
        root.addWidget(self.batch_bar)
        self.batch_bar.setVisible(False)

        self._apply_window_style()
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
            b.setFixedSize(28, 28)
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

        rmd = QComboBox()
        rmd.setObjectName("inlinermd")
        rmd.addItems(list(REMIND_TYPES.keys()))
        rmd.setCurrentText("到期当天")
        rmd.setFixedHeight(26)
        rl2.addWidget(rmd, 1)
        outer.addLayout(rl2)

        # 第三行：循环 + 循环截止
        rl3 = QHBoxLayout()
        rl3.setSpacing(6)
        rc = QComboBox()
        rc.setObjectName("inlinerc")
        rc.addItems(RECUR_TYPES)
        rc.setCurrentText("不循环")
        rc.setFixedHeight(26)
        rl3.addWidget(rc, 1)

        self._inline_rend_val = ""
        btn_rend = QPushButton("循环截止日期")
        btn_rend.setObjectName("inlinerend")
        btn_rend.setFixedHeight(26)
        btn_rend.setCursor(Qt.PointingHandCursor)
        rl3.addWidget(btn_rend, 1)
        outer.addLayout(rl3)

        row.setStyleSheet(
            f"#inlinerow{{background:{self.theme['card']};border:1px solid "
            f"{self.theme['accent']};border-radius:10px;}}"
            f"#inlineedit{{border:none;background:transparent;font-size:14px;"
            f"color:{self.theme['text']};}}"
            f"#inlinedate,#inlineok,#inlinecancel{{border:none;border-radius:6px;"
            f"background:{self.theme['border']};font-size:14px;}}"
            f"#inlineok{{color:{self.theme['accent']};}}"
            f"#inlinepr,#inlinerc,#inlinerend,#inlinect,#inlinermd{{border:1px solid {self.theme['border']};"
            f"border-radius:13px;background:{self.theme['panel']};color:{self.theme['text']};"
            f"font-size:11px;padding:2px 10px;}}"
            f"#inlinepr:hover,#inlinerc:hover,#inlinerend:hover,#inlinect:hover,#inlinermd:hover{{"
            f"border:1px solid {self.theme['accent']};}}"
            f"#inlinepr::drop-down,#inlinerc::drop-down{{border:none;width:20px;"
            f"background:transparent;subcontrol-origin:padding;"
            f"subcontrol-position:right center;}}"
            f"#inlinepr::down-arrow,#inlinerc::down-arrow{{"
            f"image:none;width:7px;height:7px;background:transparent;"
            f"border:2px solid {self.theme['sub']};border-top:none;"
            f"border-right:none;margin-right:7px;margin-top:-4px;}}"
            f"#inlinepr QAbstractItemView,#inlinerc QAbstractItemView{{"
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
        self._inline_rmd = rmd
        self._inline_rc = rc
        self._inline_rendbtn = btn_rend

        def pick_date():
            self._pick_inline_due()
        def pick_rend():
            self._pick_inline_recur_end()
        def save():
            self._save_inline()
        def cancel():
            self._close_inline()

        btn_cal.clicked.connect(pick_date)
        btn_rend.clicked.connect(pick_rend)
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
        """为内联编辑行选择截止日期（复用日历弹窗，写入 _inline_due）"""
        prev = self._pending_due
        self._pending_due = self._inline_due
        self._pick_due()
        self._inline_due = self._pending_due
        self._pending_due = prev
        if getattr(self, "_inline_datebtn", None) is not None:
            self._inline_datebtn.setText(
                self._inline_due[5:] if self._inline_due else "📅")

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
                       recur=self._inline_rc.currentText(),
                       recur_end=getattr(self, "_inline_rend_val", ""),
                       remind=self._inline_rmd.currentText() if getattr(
                           self, "_inline_rmd", None) is not None else "到期当天")
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
        self._inline_due = ""

    def _close_inline(self):
        """取消并移除内联编辑行"""
        row = getattr(self, "_inline_row", None)
        if row is not None:
            row.setParent(None)
            row.deleteLater()
        self._reset_inline_refs()

    def _build_catbar(self):
        self.catbar = QHBoxLayout()
        self.catbar.setSpacing(6)
        self.cat_btns = {}
        for name in ["全部"] + self.categories:
            b = QPushButton(name)
            b.setObjectName("chip")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.setChecked(name == self.active_cat)
            b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            b.clicked.connect(lambda _=False, n=name: self._set_cat(n))
            self.cat_btns[name] = b
            self.catbar.addWidget(b)
        self.catbar.addStretch()
        # 多选按钮放在标签类型行最右边
        self.btn_multi = QPushButton("☑")
        self.btn_multi.setObjectName("chip")
        self.btn_multi.setCursor(Qt.PointingHandCursor)
        self.btn_multi.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_multi.clicked.connect(self._toggle_select_mode)
        self.catbar.addWidget(self.btn_multi)
        # 全选按钮放在标签类型行最右边，仅多选模式下显示
        self.btn_sel_all = QPushButton("全选")
        self.btn_sel_all.setObjectName("chip")
        self.btn_sel_all.setCursor(Qt.PointingHandCursor)
        self.btn_sel_all.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.btn_sel_all.clicked.connect(self._batch_select_all)
        self.btn_sel_all.setVisible(False)
        self.catbar.addWidget(self.btn_sel_all)
        return self.catbar

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
        self.btn_sel_all.setVisible(self.select_mode)
        self.btn_multi.setText("✕" if self.select_mode else "☑")
        self._update_batch_lbl()
        self.refresh()

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
        self.refresh()

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
            QLabel#apptitle {{ color: {t['text']}; font-size: 15px; font-weight: bold; }}
            QFrame#batchbar {{
                background: {t['panel']}; border-radius: 13px;
                border: 1px solid {t['border']};
            }}
            QLabel#batchlbl {{ color: {t['accent']}; font-size: 12px; font-weight: bold; }}
            QPushButton#batchbtn {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 11px; color: {t['text']}; font-size: 12px;
                padding: 4px 10px;
            }}
            QPushButton#batchbtn:hover {{ background: {t['accent']}; color: #FFFFFF; }}
            QLabel#cheer {{ color: {t['accent']}; font-size: 11px; font-weight: bold; }}
            QLabel#cheer:hover {{ color: {t['accent2']}; }}
            QPushButton#titlebtn, QPushButton#closebtn {{
                background: transparent; border: none; border-radius: 14px;
                color: {t['sub']}; font-size: 15px; font-weight: bold;
            }}
            QPushButton#titlebtn:hover {{ background: {t['card_hover']}; color: {t['text']}; }}
            QPushButton#closebtn:hover {{ background: #E5484D; color: #FFFFFF; }}
            QFrame#stats {{
                background: {t['panel']}; border-radius: 15px;
                border: 1px solid {t['border']};
            }}
            QLabel#statstext {{ color: {t['text']}; font-size: 13px; font-weight: bold; }}
            QLabel#statspct {{ color: {t['accent']}; font-size: 13px; font-weight: bold; }}
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
            QComboBox#catpick::drop-down {{ border: none; width: 14px; }}
            QComboBox#prpick {{
                background: {t['panel']}; border: 1px solid {t['border']};
                border-radius: 12px; padding: 0 8px; color: {t['text']}; font-size: 12px;
            }}
            QComboBox#prpick::drop-down {{ border: none; width: 14px; }}
            QComboBox QAbstractItemView {{
                background: {t['panel']}; color: {t['text']};
                selection-background-color: {t['accent']}; border-radius: 8px;
            }}
            QPushButton#addbtn {{
                background: {t['accent']}; border: none; border-radius: 12px;
                color: #FFFFFF; font-size: 14px; font-weight: bold;
            }}
            QPushButton#addbtn:hover {{ background: {t['accent2']}; }}
            QPushButton#datebtn {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 12px; color: {t['accent']}; font-size: 15px;
            }}
            QPushButton#datebtn:hover {{ background: {t['accent']}; color: #FFFFFF; }}
            QPushButton#chip {{
                background: {t['card']}; border: 1px solid {t['border']};
                border-radius: 12px; padding: 4px 9px; color: {t['sub']};
                font-size: 12px;
            }}
            QPushButton#chip:checked {{
                background: {t['accent']}; color: #FFFFFF; border: none; font-weight: bold;
            }}
            QScrollArea#scroll {{ background: transparent; border: none; }}
            QScrollArea#scroll > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
            QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 3px; min-height: 24px; }}
            QScrollBar::handle:vertical:hover {{ background: {t['sub']}; }}
            QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
            QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
            QMenu {{
                background: {t['panel']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 10px; padding: 6px;
            }}
            QMenu::item {{ padding: 7px 22px; border-radius: 7px; }}
            QMenu::item:selected {{ background: {t['accent']}; color: #FFFFFF; }}
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
        self.btn_add.setVisible(vis)
        for b in self.cat_btns.values():
            b.setVisible(vis)
        if hasattr(self, "btn_multi"):
            self.btn_multi.setVisible(vis)
        # 折叠时只保留“待办清单”标题与折叠/关闭按钮，其余全部收起
        self.cheer_lbl.setVisible(vis)
        for b in (self.btn_theme, self.btn_menu):
            b.setVisible(vis)
        # 全选按钮只在“展开 + 多选模式”下显示
        if hasattr(self, "btn_sel_all"):
            self.btn_sel_all.setVisible(vis and getattr(self, "select_mode", False))
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
        if self.active_cat != "全部":
            tasks = [t for t in tasks if t.get("category") == self.active_cat]
        if self.keyword:
            tasks = [t for t in tasks if self.keyword in t["text"].lower()]
        # 排序：完成置底；未完成按 优先级 > 截止时间 > 状态
        rank = {"todo": 0, "doing": 1, "done": 2}

        def sort_key(t):
            done_flag = 1 if t["status"] == "done" else 0
            pr = PRIORITY_RANK.get(t.get("priority", "普通"), 2)
            return (done_flag, pr, due_sort_key(t.get("due", "")),
                    rank.get(t["status"], 0), t["created"])
        tasks = sorted(tasks, key=sort_key)

        if not tasks:
            empty = QLabel("暂无待办，享受清爽的一天 ☕")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                f"color:{self.theme['sub']};font-size:13px;padding:30px 0;")
            self.list_lay.insertWidget(0, empty)
        else:
            for i, t in enumerate(tasks):
                card = TaskCard(t, self.theme,
                                select_mode=self.select_mode,
                                selected=t["id"] in self.selected_ids)
                card.toggled.connect(self._on_toggle)
                card.deleted.connect(self._on_delete)
                card.edited.connect(self._on_edit)
                card.sub_toggled.connect(self._on_sub_toggle)
                card.select_toggled.connect(self._on_card_select)
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
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "新建分类", "分类名称：")
        name = (name or "").strip()
        if ok and name and name not in self.categories:
            self._add_category(name)
            self.cat_pick.setCurrentText(name)
        else:
            self.cat_pick.setCurrentIndex(0)

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
        self.catbar.insertWidget(self.catbar.count() - 2, b)

    def _pick_due(self):
        """弹出日历选择截止时间，并可选精确到时间点"""
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QCalendarWidget,
                                       QDialogButtonBox, QHBoxLayout, QPushButton,
                                       QCheckBox, QTimeEdit)
        from PySide6.QtCore import QDate, QTime
        from PySide6.QtGui import QTextCharFormat, QColor
        dlg = QDialog(self)
        dlg.setWindowTitle("选择截止时间")
        v = QVBoxLayout(dlg)
        cal = QCalendarWidget()
        cal.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)  # 去掉左侧周数列
        cal.setGridVisible(False)
        # 选中日期高亮加深：用主题强调色做背景 + 白字加粗，明显区分
        _acc = self.theme.get("accent", "#4C8DFF")
        cal.setStyleSheet(
            "QCalendarWidget QAbstractItemView:enabled {"
            "  selection-background-color: %s;"
            "  selection-color: #FFFFFF;"
            "  outline: 0;"
            "}"
            "QCalendarWidget QAbstractItemView:enabled:selected {"
            "  font-weight: bold;"
            "}" % _acc)
        # 隐藏相邻月份日期（设为透明）
        hide_fmt = QTextCharFormat()
        hide_fmt.setForeground(QColor(0, 0, 0, 0))
        cal.setDateTextFormat(QDate(), hide_fmt)  # 基准
        def _hide_other_month():
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(0, 0, 0, 0))
            page_m = cal.monthShown()
            page_y = cal.yearShown()
            d = QDate(page_y, page_m, 1).addDays(-14)
            for _ in range(56):
                if d.month() != page_m:
                    cal.setDateTextFormat(d, fmt)
                else:
                    cal.setDateTextFormat(d, QTextCharFormat())
                d = d.addDays(1)
        cal.currentPageChanged.connect(lambda *_: _hide_other_month())
        _hide_other_month()
        # 预置已有日期/时间
        cur_date, cur_time = parse_due(self._pending_due)
        if cur_date is not None:
            cal.setSelectedDate(QDate(cur_date.year, cur_date.month, cur_date.day))
        v.addWidget(cal)
        # 时间点选择行
        trow = QHBoxLayout(); trow.setSpacing(8)
        chk_time = QCheckBox("指定具体时间点")
        chk_time.setChecked(cur_time is not None)
        trow.addWidget(chk_time)
        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH:mm")
        time_edit.setTime(QTime(cur_time.hour, cur_time.minute)
                          if cur_time else QTime(18, 0))
        time_edit.setEnabled(cur_time is not None)
        chk_time.toggled.connect(time_edit.setEnabled)
        trow.addWidget(time_edit)
        trow.addStretch()
        v.addLayout(trow)
        row = QHBoxLayout()
        btn_clear = QPushButton("清除")
        row.addWidget(btn_clear)
        row.addStretch()
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
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

    def _dialog_qss(self):
        """编辑弹窗统一样式，跟随当前主题"""
        t = self.theme
        return f"""
            QDialog {{ background: {t['panel']}; }}
            QLabel {{ color: {t['sub']}; font-size: 12px; font-weight: bold; }}
            QLineEdit, QComboBox, QPlainTextEdit {{
                background: {t['card']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 9px;
                padding: 7px 10px; font-size: 13px;
            }}
            QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
                border: 1px solid {t['accent']};
            }}
            QComboBox::drop-down {{ border: none; width: 22px; }}
            QComboBox QAbstractItemView {{
                background: {t['panel']}; color: {t['text']};
                selection-background-color: {t['accent']};
                selection-color: #FFFFFF;
                border: 1px solid {t['border']}; border-radius: 8px;
                outline: none; padding: 2px;
            }}
            QPushButton {{
                background: {t['card']}; color: {t['text']};
                border: 1px solid {t['border']}; border-radius: 9px;
                padding: 7px 16px; font-size: 13px;
            }}
            QPushButton:hover {{
                border: 1px solid {t['accent']}; color: {t['accent']};
            }}
            QDialogButtonBox QPushButton {{ min-width: 76px; padding: 8px 18px; }}
            QDialogButtonBox QPushButton:default {{
                background: {t['accent']}; color: #FFFFFF;
                border: 1px solid {t['accent']};
            }}
            QDialogButtonBox QPushButton:default:hover {{
                background: {t['accent2']}; border: 1px solid {t['accent2']};
                color: #FFFFFF;
            }}
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
        title = QLabel("✏️ 编辑待办")
        title.setStyleSheet(
            f"color:{self.theme['text']};font-size:16px;font-weight:bold;")
        v.addWidget(title)
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
        # 截止日期（日历选择）
        v.addWidget(QLabel("截止日期"))
        drow = QHBoxLayout(); drow.setSpacing(8)
        _edit_due = {"val": task.get("due", "")}
        btn_due = QPushButton(
            f"📅  {_edit_due['val']}" if _edit_due["val"] else "📅  点击选择日期")
        btn_due.setCursor(Qt.PointingHandCursor)
        def _pick_edit_due():
            prev = self._pending_due
            self._pending_due = _edit_due["val"]
            self._pick_due()
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
        # 循环设置
        v.addWidget(QLabel("循环重复"))
        rrow = QHBoxLayout(); rrow.setSpacing(8)
        rc = QComboBox()
        rc.addItems(RECUR_TYPES)
        rc.setCurrentText(task.get("recur", "不循环"))
        rrow.addWidget(rc, 1)
        _recur_end = {"val": task.get("recur_end", "")}
        btn_rend = QPushButton(
            f"📅  {_recur_end['val']}" if _recur_end["val"] else "📅  循环截止（可选）")
        btn_rend.setCursor(Qt.PointingHandCursor)
        def _pick_recur_end():
            prev = self._pending_due
            self._pending_due = _recur_end["val"]
            self._pick_due()
            _recur_end["val"] = self._pending_due
            self._pending_due = prev
            btn_rend.setText(
                f"📅  {_recur_end['val']}" if _recur_end["val"] else "📅  循环截止（可选）")
        btn_rend.clicked.connect(_pick_recur_end)
        rrow.addWidget(btn_rend, 1)
        v.addLayout(rrow)
        # 提醒设置
        v.addWidget(QLabel("提醒时间"))
        rmd = QComboBox()
        rmd.addItems(list(REMIND_TYPES.keys()))
        rmd.setCurrentText(task.get("remind", "到期当天"))
        v.addWidget(rmd)
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
                              recur=rc.currentText(),
                              recur_end=_recur_end["val"],
                              remind=rmd.currentText(),
                              remind_log=[],
                              subtasks=subs)
            self.refresh()

    def _set_cat(self, name):
        self.active_cat = name
        for n, b in self.cat_btns.items():
            b.setChecked(n == name)
        self.refresh()

    # -- 主题 --
    def _pick_theme(self):
        """弹出主题选择列表，勾选当前主题"""
        m = QMenu(self)
        m.addAction("选择主题").setEnabled(False)
        m.addSeparator()
        for name in THEME_ORDER:
            act = m.addAction(("● " if name == self.theme_name else "○ ") + name)
            act.setCheckable(True)
            act.setChecked(name == self.theme_name)
            act.triggered.connect(lambda checked=False, n=name: self._set_theme(n))
        m.addSeparator()
        m.addAction("背景图片").setEnabled(False)
        pic = m.addAction("上传背景图片…")
        pic.triggered.connect(self._pick_bg_image)
        if self.cfg.get("bg_image"):
            clr_pic = m.addAction("清除背景图片")
            clr_pic.triggered.connect(self._clear_bg_image)
        # 菜单弹在主题按钮下方
        pos = self.btn_theme.mapToGlobal(self.btn_theme.rect().bottomLeft())
        m.exec(pos)

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
        clr = m.addAction("清除已完成")
        clr.triggered.connect(lambda: (self.store.clear_done(), self.refresh()))
        m.addSeparator()
        hide_a = m.addAction("隐藏到后台")
        hide_a.triggered.connect(self.hide)
        quit_a = m.addAction("彻底退出程序")
        quit_a.triggered.connect(self._real_quit)
        m.exec(QCursor.pos())

    def _real_quit(self):
        """彻底退出程序（不再驻留后台）"""
        from PySide6.QtWidgets import QApplication
        self._save_cfg()
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
                                       QCheckBox, QComboBox, QLabel,
                                       QDialogButtonBox)
        hk = self.cfg.get("hotkey") or {}
        dlg = QDialog(self)
        dlg.setWindowTitle("快捷键设置")
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("设置「召唤/隐藏窗口」的全局快捷键：\n（至少勾选一个修饰键）"))
        # macOS 目前无系统级全局热键 API，提示用户此设置仅 Windows 生效
        if IS_MAC:
            tip = QLabel("⚠️ macOS 暂不支持全局快捷键唤起，此设置仅作记录；\n"
                         "请通过程序坞图标或点按窗口来显示/隐藏。")
            tip.setWordWrap(True)
            tip.setStyleSheet("color:#F2564B;font-size:12px;")
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

    def _toggle_topmost(self):
        cur = self.cfg.get("topmost", False)
        self.cfg["topmost"] = not cur
        flags = Qt.FramelessWindowHint | Qt.Tool
        if self.cfg["topmost"]:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)
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

    def closeEvent(self, e):
        self._save_cfg()
        super().closeEvent(e)


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


def _register_global_hotkey(widget):
    """按配置注册全局热键召唤窗口（仅 Windows）。可重复调用以更新绑定"""
    if not IS_WIN:
        # macOS/Linux 无系统级全局热键 API（Win32 RegisterHotKey 不可用），
        # 直接跳过：功能优雅降级，程序其余部分正常工作
        return None
    try:
        import ctypes.wintypes  # noqa
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        MOD_SHIFT = 0x0004
        HOTKEY_ID = 0xB001
        user32 = ctypes.windll.user32

        # 先注销旧的（若存在），再按最新配置注册
        try:
            user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception:
            pass
        old = getattr(widget, "_hotkey_filter", None)
        if old is not None:
            try:
                QApplication.instance().removeNativeEventFilter(old)
            except Exception:
                pass

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


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    # 单实例检测：用 QLocalServer/QLocalSocket。相比 QSharedMemory，它能可靠区分
    # “真有实例在运行”（能连上 server）和“上次异常退出的残留”（连不上则移除陈旧 server 重建），
    # 避免残留导致程序永远打不开。
    from PySide6.QtNetwork import QLocalServer, QLocalSocket
    _SRV_NAME = "DesktopTodo_SingleInstance"
    _probe = QLocalSocket()
    _probe.connectToServer(_SRV_NAME)
    if _probe.waitForConnected(300):
        # 已有实例在运行，直接退出（快捷键 Ctrl+Alt+T 会召唤已运行的窗口）
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
    # 注册全局快捷键 Ctrl+Alt+T 召唤/隐藏窗口
    w._hotkey_filter = _register_global_hotkey(w)
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
