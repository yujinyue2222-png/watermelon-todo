"""桌面悬浮小西瓜。

一个无边框置顶的小挂件：会走路、会眨眼、会换表情，鼠标悬停时冒出一句话，
完成待办时撒花庆祝。左键单击唤起主界面，拖动可换位置，右键出菜单。

关键设计：
- 未完成待办越多，它走得越快（一种温和的催促）；
- 所有绘制先画到离屏位图，再以 ``CompositionMode_Source`` 整体替换到窗口，
  这样透明区域也会覆盖旧像素，彻底消除 macOS 上的白色残影；
- macOS 上**绝不**调用 ``raise_()``，否则会周期性抢走其他应用的键盘焦点。
"""

from __future__ import annotations

import logging
import math
import random
import sys
from typing import Any, Optional, Protocol

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QWidget,
)

from backend.api import TodoBackend
from backend.core.platform_info import IS_MACOS
from frontend.native.window_effects import (
    apply_no_steal_focus,
    bring_to_front_quietly,
    float_window_flags,
    strip_native_window_shadow,
)
from frontend.theme.qss import menu_qss
from frontend.theme.theme_manager import ThemeManager
from frontend.windows import ball_faces
from frontend.windows.ball_speech import (
    CELEBRATE_LINES,
    HOVER_LINES,
    strong_remind_line,
)

logger = logging.getLogger(__name__)

# ---- 动画节奏 ----
_FRAME_INTERVAL_MS = 30  # 约 33fps
_FRAME_SECONDS = 0.03
_HOVER_POLL_MS = 120
_HOVER_HIDE_DELAY_MS = 3000  # 鼠标离开后气泡再留 3 秒，避免一闪即逝
_WALK_FREQUENCY = 5.0
_TOPMOST_EVERY_FRAMES = 60
_STATS_EVERY_FRAMES = 60
_SPEED_EVERY_FRAMES = 20

# ---- 速度：未完成越多走越快 ----
_MIN_SPEED = 0.5
_MAX_SPEED = 1.6
_SPEED_PER_TASK = 0.1

# ---- 随机事件概率（每帧）----
_BLINK_CHANCE = 0.012
_HOP_CHANCE = 0.004
_TURN_CHANCE = 0.0015
_FACE_CHANCE = 0.006

_TURN_DURATION = 1.0
_CELEBRATE_COOLDOWN = 8.0
_BURST_PARTICLES = 14
_GRAVITY = 80.0

# ---- 气泡 ----
_BUBBLE_PREFERRED_WIDTH = 240
_BUBBLE_MIN_WIDTH = 180
_BUBBLE_GAP = 2
_FORCED_BUBBLE_MS = 6000
_CELEBRATE_BUBBLE_MS = 5000


class BallHost(Protocol):
    """悬浮球需要宿主窗口提供的能力。"""

    def summon_to_front(self) -> None:
        """把主界面唤到前台。"""

    def hide_floating_ball(self) -> None:
        """收起悬浮球。"""

    def quit_application(self) -> None:
        """彻底退出程序。"""


class HoverBubble(QWidget):
    """从小西瓜右上方冒出的一句话气泡。

    鼠标穿透（``WA_TransparentForMouseEvents``），否则气泡会挡住小西瓜自己的
    悬停检测，导致气泡不断闪烁。
    """

    def __init__(self) -> None:
        super().__init__(None)
        # macOS 上用普通 Window 而非 Tool，否则非激活 app 时气泡窗口不会显示
        flags = Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        if not IS_MACOS:
            flags |= Qt.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        if IS_MACOS:
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)

        self._label = QLabel("", self)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(_BUBBLE_PREFERRED_WIDTH)
        self._label.setStyleSheet(
            "QLabel { color: #2b2b2b;"
            " font: 14px/1.5 'PingFang SC', 'Microsoft YaHei', sans-serif; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 11, 15, 11)
        layout.addWidget(self._label)
        self.adjustSize()

    def set_text(self, text: str) -> None:
        """更新文案并按内容收缩尺寸。"""
        self._label.setText(text)
        self.adjustSize()

    def set_max_width(self, width: int) -> None:
        """限制文本宽度（贴屏幕右缘时临时收窄）。"""
        self._label.setMaximumWidth(width)
        self.adjustSize()

    def paintEvent(self, event) -> None:  # noqa: N802
        """画白色圆角底。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(QColor(255, 255, 255, 240))
        painter.setPen(QColor(0, 0, 0, 25))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 14, 14)

    def showEvent(self, event) -> None:  # noqa: N802
        """显示时去掉 macOS 的窗口阴影，避免浅色桌面出现白色重影。"""
        super().showEvent(event)
        strip_native_window_shadow(self)


class FloatingBall(QWidget):
    """会走路的小西瓜。"""

    SIZE = 56  # 西瓜本体直径
    PAD_X = 14  # 左右留白（给摆动）
    PAD_TOP = 6  # 顶部留白（给弹跳）
    PAD_BOTTOM = 20  # 底部留白（给腿和脚）

    def __init__(
        self,
        backend: TodoBackend,
        themes: ThemeManager,
        host: BallHost,
    ) -> None:
        """
        Args:
            backend: 后端门面（读配置、读统计）。
            themes: 主题管理器（右键菜单配色）。
            host: 宿主窗口，提供唤起/收起/退出能力。
        """
        super().__init__(None)
        self._backend = backend
        self._themes = themes
        self._host = host
        self._random = random.Random()

        self.width_px = self.SIZE + self.PAD_X * 2
        self.height_px = self.SIZE + self.PAD_TOP + self.PAD_BOTTOM

        self.setWindowFlags(float_window_flags(topmost=True))
        apply_no_steal_focus(self, accept_focus=False)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # 主动开启 hover 投递：macOS 上「不抢焦点」的窗口不点一下收不到 enter/leave
        self.setAttribute(Qt.WA_Hover, True)
        self.setMouseTracking(True)
        self.setFixedSize(self.width_px, self.height_px)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("西瓜todo · 点击打开 / 右键退出")

        self._drag_offset: Optional[Any] = None
        self._dragged = False
        self._bubble: Optional[HoverBubble] = None
        self._bubble_timer: Optional[QTimer] = None
        self._hover_inside = False

        # 动画状态
        self._elapsed = 0.0
        self._speed = _MIN_SPEED
        self._speed_ticks = 0
        self._topmost_ticks = 0
        self._stats_ticks = 0
        self._blink_progress = 0.0
        self._face = ball_faces.NORMAL
        self._face_remaining = 0.0
        self._hop_energy = 0.0
        self._turn_remaining = 0.0
        self._particles: list[dict[str, Any]] = []
        self._done_today: Optional[int] = None
        self._celebrate_cooldown = 0.0

        self._faces = ball_faces.build_faces(self.SIZE, self.devicePixelRatioF())
        self._restore_position()

        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(_HOVER_POLL_MS)
        self._hover_timer.timeout.connect(self._check_hover)
        self._hover_timer.start()

        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(_FRAME_INTERVAL_MS)
        self._animation_timer.timeout.connect(self._on_tick)
        self._animation_timer.start()

    # ------------------------------------------------------------------ 对外
    def force_bubble(self, text: str, duration_ms: int = _FORCED_BUBBLE_MS) -> None:
        """强提醒：强制弹出气泡并在若干毫秒后自动消失。

        会顺带露个惊讶脸 + 蹦一下，吸引注意。
        """
        self._show_bubble_for(text, duration_ms)
        if ball_faces.SURPRISED in self._faces:
            self._face = ball_faces.SURPRISED
            self._face_remaining = 2.0
        if self._hop_energy <= 0:
            self._hop_energy = 1.0

    def showEvent(self, event) -> None:  # noqa: N802
        """显示时去掉 macOS 窗口阴影并把背景设为全透明。"""
        super().showEvent(event)
        strip_native_window_shadow(self)

    def closeEvent(self, event) -> None:  # noqa: N802
        """关闭时一起收掉气泡与定时器。"""
        self._hover_timer.stop()
        self._animation_timer.stop()
        if self._bubble is not None:
            self._bubble.close()
            self._bubble = None
        super().closeEvent(event)

    # ------------------------------------------------------------------ 位置
    def _restore_position(self) -> None:
        """恢复上次拖动到的位置，否则放到屏幕右下角偏上。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            self.move(1000, 600)
            return
        area = screen.availableGeometry()
        saved = self._backend.config.floating_ball_pos
        if saved is not None:
            x = min(max(saved[0], area.left()), area.right() - self.width_px)
            y = min(max(saved[1], area.top()), area.bottom() - self.height_px)
        else:
            x = area.right() - self.width_px - 24
            y = area.bottom() - self.height_px - 120
        self.move(x, y)

    def _body_rect(self) -> QRect:
        """西瓜本体的悬停判定区。

        控件比本体大一圈（要给弹跳、摆动、腿留空间），气泡又故意压在右上角，
        如果拿整个控件当判定区，光标停在角落会和气泡反复互相触发进入/离开。
        判定区只放宽 1px，保证永远比气泡的 2px 间隙更小。
        """
        return QRect(self.PAD_X - 1, self.PAD_TOP - 1, self.SIZE + 2, self.SIZE + 2)

    # ------------------------------------------------------------------ 悬停
    def enterEvent(self, event) -> None:  # noqa: N802
        """交给轮询统一判定，避免平台差异。"""
        self._check_hover()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        """确保气泡收起。"""
        if self._hover_inside:
            self._hover_inside = False
            self._hide_bubble()
        super().leaveEvent(event)

    def _check_hover(self) -> None:
        """轮询光标是否在本体内，用状态跳变驱动气泡显隐。

        比 enterEvent/leaveEvent 可靠：既不受「窗口未激活收不到事件」影响，
        也不会因气泡尺寸变化产生抖动。
        """
        if not self.isVisible():
            if self._hover_inside:
                self._hover_inside = False
                self._hide_bubble()
            return
        if self._drag_offset is not None:
            return  # 拖动中不打扰

        # 直接用全局屏幕坐标判断光标是否落在「西瓜本体」区域内，
        # 避免无焦点 Tool 窗口上 mapFromGlobal 坐标漂移导致永远判定为 False。
        geo = self.geometry()
        cursor = QCursor.pos()
        body_left = geo.x() + self.PAD_X - 1
        body_top = geo.y() + self.PAD_TOP - 1
        inside = (
            geo.x() <= cursor.x() <= geo.x() + geo.width()
            and geo.y() <= cursor.y() <= geo.y() + geo.height()
        )
        if inside == self._hover_inside:
            return  # 状态没变就不换台词，杜绝文字飞快切换
        self._hover_inside = inside
        if inside:
            self._show_hover_bubble()
        else:
            # 鼠标离开后给一点宽限时间，让气泡淡出前能被看到；
            # 但强提醒/庆祝等定时气泡不受影响（由自己的计时器控制）。
            if not self._bubble_is_timed():
                self._schedule_hide_bubble()

    def _show_hover_bubble(self) -> None:
        """悬停时优先催促开启了强提醒的未完成待办；否则说陪伴/鼓励语。"""
        if not self._backend.config.bubble_speak:
            return
        self._ensure_bubble()
        if self._bubble_timer is not None:
            self._bubble_timer.stop()
        text = self._strong_remind_text()
        if text is None:
            text = self._random.choice(HOVER_LINES)
        self._bubble.set_text(text)
        self._position_bubble()

    def _strong_remind_text(self) -> Optional[str]:
        """若有强提醒且未完成的待办，返回随机一条催促文案；否则 None。"""
        try:
            tasks = self._backend.tasks.tasks  # TaskService 用 .tasks 属性暴露全量待办
        except Exception as exc:  # noqa: BLE001
            logger.debug("读取待办列表失败：%s", exc)
            return None
        candidates = [
            t
            for t in tasks
            if getattr(t, "strong", None) is not None
            and t.strong.enabled
            and t.strong.float_window
            and not t.is_done
        ]
        if not candidates:
            return None
        # 优先到期/紧急的，再随机挑一条
        candidates.sort(key=lambda t: (t.due_at is None, t.due_at))
        task = self._random.choice(candidates)
        return strong_remind_line(task.text or "这条待办")

    def _show_bubble_for(self, text: str, duration_ms: int) -> None:
        """显示一条会自动消失的气泡（不抢焦点）。"""
        self._ensure_bubble()
        self._bubble.set_text(text)
        self._position_bubble()
        if self._bubble_timer is None:
            self._bubble_timer = QTimer(self)
            self._bubble_timer.setSingleShot(True)
            self._bubble_timer.timeout.connect(self._hide_bubble)
        self._bubble_timer.start(max(1000, duration_ms))

    def _ensure_bubble(self) -> None:
        """懒创建气泡窗口。"""
        if self._bubble is None:
            self._bubble = HoverBubble()

    def _bubble_is_timed(self) -> bool:
        """当前是否有一条自动倒计时的气泡在显示。"""
        return self._bubble_timer is not None and self._bubble_timer.isActive()

    def _hide_bubble(self) -> None:
        """收起气泡。"""
        if self._bubble is not None:
            self._bubble.hide()

    def _schedule_hide_bubble(self) -> None:
        """鼠标离开后延迟收起悬停气泡，避免一闪即逝；定时气泡不受影响。"""
        if self._bubble_timer is None:
            self._bubble_timer = QTimer(self)
            self._bubble_timer.setSingleShot(True)
            self._bubble_timer.timeout.connect(self._hide_bubble)
        # 悬停气泡的宽限时长（毫秒）
        self._bubble_timer.start(_HOVER_HIDE_DELAY_MS)

    def _position_bubble(self) -> None:
        """气泡永远从西瓜右上方冒出。

        规则简单且无平台差异：紧贴本体右侧、压在本体顶部上方；只有当西瓜贴着
        屏幕右缘、气泡会顶出屏幕时才把气泡往左收一点，**绝不**翻到左边。

        找屏幕用「本体中心点落在哪块屏」而不是 ``self.screen()``：后者在 Windows
        上对无边框 Qt.Tool 窗口可能返回错误屏幕，导致左右判定飘。
        """
        if self._bubble is None:
            return

        screen = QApplication.screenAt(self.geometry().center()) or self.screen()
        if screen is None:
            screen = QApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else None

        body_right = self.x() + self.PAD_X + self.SIZE
        if area is not None:
            right_space = area.right() - (body_right + _BUBBLE_GAP) - 16
            max_width = max(_BUBBLE_MIN_WIDTH, min(_BUBBLE_PREFERRED_WIDTH, int(right_space)))
        else:
            max_width = _BUBBLE_PREFERRED_WIDTH
        self._bubble.set_max_width(max_width)

        width = self._bubble.width()
        height = self._bubble.height()
        # 显示在西瓜「右上方」（球右侧 + 上方）
        x = body_right + _BUBBLE_GAP
        y = self.y() + self.PAD_TOP - height - _BUBBLE_GAP
        if area is not None:
            x = max(area.left() + 4, min(x, area.right() - width - 4))
            y = max(area.top() + 4, min(y, area.bottom() - height - 4))

        self._bubble.move(x, y)
        self._bubble.show()
        bring_to_front_quietly(self._bubble)
        # 再强制一次置顶，确保跨应用窗口也压在最前
        self._bubble.raise_()

    # ------------------------------------------------------------------ 动画
    def _current_speed(self) -> float:
        """未完成待办越多走越快：0 个是散步，每多 1 个加一点，有上限。"""
        summary = self._backend.stats.today()
        return max(
            _MIN_SPEED,
            min(_MAX_SPEED, _MIN_SPEED + summary.remaining * _SPEED_PER_TASK),
        )

    def _on_tick(self) -> None:
        """每帧推进动画状态。"""
        if not self.isVisible():
            return  # 隐藏时不重绘，省 CPU

        self._update_speed()
        self._maintain_topmost()

        # 速度越快，时间推进越快 → 步频与弹跳一起变快
        self._elapsed += _FRAME_SECONDS * self._speed
        self._update_blink()
        self._update_actions()
        self._update_particles()
        self._poll_celebration()
        self._update_face()
        self.update()

    def _update_speed(self) -> None:
        """每 20 帧刷新一次速度，不必每帧都统计。"""
        self._speed_ticks += 1
        if self._speed_ticks >= _SPEED_EVERY_FRAMES:
            self._speed_ticks = 0
            self._speed = self._current_speed()

    def _maintain_topmost(self) -> None:
        """每约 2 秒维护一次置顶。

        macOS 分支只调整窗口层级、不激活本应用；否则会周期性抢走微信等
        应用的键盘/输入法焦点（v2 曾出现「开着小西瓜就打不了字」）。
        """
        self._topmost_ticks += 1
        if self._topmost_ticks < _TOPMOST_EVERY_FRAMES:
            return
        self._topmost_ticks = 0
        bring_to_front_quietly(self)

    def _update_blink(self) -> None:
        """随机眨眼。"""
        if self._blink_progress > 0:
            self._blink_progress = max(0.0, self._blink_progress - 0.08)
        elif self._random.random() < _BLINK_CHANCE:
            self._blink_progress = 1.0

    def _update_actions(self) -> None:
        """偶尔蹦一下、偶尔转个身。"""
        vigor_bonus = 0.6 + 0.8 * (self._speed - _MIN_SPEED)
        if self._hop_energy > 0:
            self._hop_energy = max(0.0, self._hop_energy - 0.06)
        elif self._random.random() < _HOP_CHANCE * vigor_bonus:
            self._hop_energy = 1.0

        if self._turn_remaining > 0:
            self._turn_remaining -= _FRAME_SECONDS
        elif self._speed <= 0.7 and self._random.random() < _TURN_CHANCE:
            # 悠闲的时候才有空臭美
            self._turn_remaining = _TURN_DURATION

    def _update_particles(self) -> None:
        """推进花瓣/星星/爱心粒子。"""
        if not self._particles:
            return
        alive = []
        for particle in self._particles:
            particle["x"] += particle["vx"] * _FRAME_SECONDS
            particle["y"] += particle["vy"] * _FRAME_SECONDS
            particle["vy"] += _GRAVITY * _FRAME_SECONDS
            particle["rotation"] += particle["spin"] * _FRAME_SECONDS
            particle["life"] -= _FRAME_SECONDS
            if particle["life"] > 0:
                alive.append(particle)
        self._particles = alive

    def _poll_celebration(self) -> None:
        """每约 2 秒查一次今日完成数，变多就庆祝。"""
        if self._celebrate_cooldown > 0:
            self._celebrate_cooldown -= _FRAME_SECONDS
        self._stats_ticks += 1
        if self._stats_ticks < _STATS_EVERY_FRAMES:
            return
        self._stats_ticks = 0

        done = self._backend.stats.today().done
        if self._done_today is None:
            self._done_today = done  # 首次只建立基线，不庆祝
        elif done > self._done_today and self._celebrate_cooldown <= 0:
            self._celebrate(done)
            self._celebrate_cooldown = _CELEBRATE_COOLDOWN
        self._done_today = done

    def _celebrate(self, done_today: int) -> None:
        """撒花 + 换庆祝脸 + 说一句庆祝语。"""
        if self._backend.config.bubble_speak:
            line = self._random.choice(CELEBRATE_LINES).format(count=done_today)
            self._show_bubble_for(line, _CELEBRATE_BUBBLE_MS)
        face = self._random.choice([ball_faces.LOVE, ball_faces.CHEER])
        if face in self._faces:
            self._face = face
            self._face_remaining = 2.5
        self._emit_particles()

    def _emit_particles(self) -> None:
        """朝四周撒出一把粒子。"""
        center_x = self.width_px / 2.0
        center_y = self.PAD_TOP + self.SIZE / 2.0
        for _ in range(_BURST_PARTICLES):
            angle = self._random.uniform(0, 2 * math.pi)
            speed = self._random.uniform(40, 110)
            self._particles.append(
                {
                    "x": center_x,
                    "y": center_y,
                    "vx": math.cos(angle) * speed,
                    "vy": math.sin(angle) * speed - 60,  # 略微向上
                    "life": self._random.uniform(0.9, 1.6),
                    "max_life": 1.6,
                    "size": self._random.uniform(5, 9),
                    "rotation": self._random.uniform(0, 360),
                    "spin": self._random.uniform(-220, 220),
                    "kind": self._random.choice(["petal", "star", "heart"]),
                }
            )

    def _update_face(self) -> None:
        """表情优先级：眨眼 > 指定表情 > 随机心情 > 常态。"""
        if self._blink_progress > 0.35 and ball_faces.BLINK in self._faces:
            self._face = ball_faces.BLINK
            return
        if self._face_remaining > 0:
            self._face_remaining -= _FRAME_SECONDS
            if self._face_remaining <= 0:
                self._face = ball_faces.NORMAL
            return
        if self._random.random() >= _FACE_CHANCE:
            self._face = ball_faces.NORMAL
            return

        if self._speed <= 0.6:  # 悠闲：犯困/满足
            candidates = [ball_faces.SLEEPY, ball_faces.CHEERFUL]
        elif self._speed >= 1.3:  # 忙碌：惊讶/打鸡血
            candidates = [ball_faces.SURPRISED, ball_faces.CHEERFUL]
        else:
            candidates = [ball_faces.CHEERFUL, ball_faces.SURPRISED]
        face = self._random.choice(candidates)
        if face in self._faces:
            self._face = face
            self._face_remaining = self._random.uniform(1.6, 3.0)
        else:
            self._face = ball_faces.NORMAL

    # ------------------------------------------------------------------ 绘制
    def paintEvent(self, event) -> None:  # noqa: N802
        """先画到离屏位图，再整体替换到窗口。

        直接画到窗口时，macOS 上上一帧的像素不会被透明区覆盖，会留下白色残影。
        用 ``CompositionMode_Source`` 整体覆盖即可彻底解决。
        """
        ratio = self.devicePixelRatioF()
        buffer = QPixmap(int(self.width() * ratio), int(self.height() * ratio))
        buffer.setDevicePixelRatio(ratio)
        buffer.fill(QColor(0, 0, 0, 0))

        painter = QPainter(buffer)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        self._draw_body_and_legs(painter)
        if self._particles:
            self._draw_particles(painter)
        painter.end()

        window_painter = QPainter(self)
        window_painter.setCompositionMode(QPainter.CompositionMode_Source)
        window_painter.drawPixmap(0, 0, buffer)
        window_painter.end()

    def _draw_body_and_legs(self, painter: QPainter) -> None:
        """画本体与两条腿。

        身体和腿画在同一套 ``translate + rotate`` 变换里，这样四肢永远吸附在
        西瓜身上，一起摇晃/弹跳，绝不脱节。
        """
        size = self.SIZE
        body_x = self.PAD_X
        body_y = self.PAD_TOP
        body_bottom = body_y + size

        # 活力系数 0（悠闲）~1（快步），越大摆幅与弹跳越夸张
        vigor = min(1.0, max(0.0, (self._speed - _MIN_SPEED) / 1.1))
        walk_phase = math.sin(self._elapsed * _WALK_FREQUENCY)
        swing_degrees = walk_phase * (5.0 + vigor * 4.0)
        bob = abs(walk_phase) * (2.0 + vigor * 4.0) + self._hop_energy * (size * 0.22)

        painter.save()
        pivot_x = self.width_px / 2.0
        painter.translate(pivot_x, body_bottom - bob)
        painter.rotate(swing_degrees)
        painter.translate(-pivot_x, -body_bottom)
        self._apply_turn(painter, body_x, body_y, size)

        target = QRectF(body_x, body_y, size, size)
        face = self._faces.get(self._face) or self._faces.get(ball_faces.NORMAL)
        if face is not None:
            painter.drawPixmap(target, face, QRectF(face.rect()))
        else:
            font = QFont()
            font.setPointSize(int(size * 0.7))
            painter.setFont(font)
            painter.setPen(QColor("#000000"))
            painter.drawText(target, Qt.AlignCenter, "🍉")

        self._draw_legs(painter, body_x, body_y, size, vigor)
        painter.restore()

    def _apply_turn(
        self,
        painter: QPainter,
        body_x: float,
        body_y: float,
        size: float,
    ) -> None:
        """3D 转身：用水平方向的余弦收缩模拟绕竖直轴转一圈。

        正 → 侧 → 背（镜像）→ 侧 → 正，不是 2D 翻跟头。
        """
        if self._turn_remaining <= 0:
            return
        progress = 1.0 - max(0.0, min(1.0, self._turn_remaining / _TURN_DURATION))
        scale_x = math.cos(progress * 2.0 * math.pi)  # 1 → 0 → -1 → 0 → 1
        if abs(scale_x) < 0.06:
            # 完全侧身时保留一条薄边，看起来更立体
            scale_x = 0.06 if scale_x >= 0 else -0.06
        center_x = body_x + size / 2.0
        center_y = body_y + size / 2.0
        painter.translate(center_x, center_y)
        painter.scale(scale_x, 1.0)
        painter.translate(-center_x, -center_y)

    def _draw_legs(
        self,
        painter: QPainter,
        body_x: float,
        body_y: float,
        size: float,
        vigor: float,
    ) -> None:
        """两条腿一前一后交替迈步。

        坐标取自 ``watermelon_ball.svg`` 的真实几何（viewBox 1024，三角形西瓜）：
        底边圆弧最低点在正中央 (512, 888)，腿从这附近长出。
        """

        def scale_x(svg_x: float) -> float:
            return body_x + size * (svg_x / 1024.0)

        def scale_y(svg_y: float) -> float:
            return body_y + size * (svg_y / 1024.0)

        hip_y = scale_y(878.0)
        leg_length = size * 0.10
        stride = 0.06 + vigor * 0.05
        direction = -1  # 固定朝一个方向走，避免脚朝向来回翻转显得别扭

        white_pen = QPen(QColor("#FFFFFF"), 3)
        white_pen.setCapStyle(Qt.RoundCap)
        white_pen.setJoinStyle(Qt.RoundJoin)
        # 先画更粗的黑色描边打底，再用白线盖上，这样白腿在白色桌面上也看得见
        edge_pen = QPen(QColor("#222222"), 5)
        edge_pen.setCapStyle(Qt.RoundCap)
        edge_pen.setJoinStyle(Qt.RoundJoin)

        for index, side in enumerate((-1, 1)):
            hip_x = scale_x(512.0 + side * 62.0)
            # 两条腿相位相差半个周期
            phase = math.sin(
                self._elapsed * _WALK_FREQUENCY + (0.0 if index == 0 else math.pi)
            )
            foot_x = hip_x + direction * phase * size * stride
            foot_y = hip_y + leg_length
            toe_x = foot_x + direction * size * 0.05

            hip_point = QPointF(hip_x, hip_y)
            foot_point = QPointF(foot_x, foot_y)
            toe_point = QPointF(toe_x, foot_y)
            # 描边从大腿根往下 35% 处开始，让腿与身体的连接处自然融入
            edge_start = QPointF(
                hip_x + (foot_x - hip_x) * 0.35,
                hip_y + (foot_y - hip_y) * 0.35,
            )

            painter.setPen(edge_pen)
            painter.drawLine(edge_start, foot_point)
            painter.drawLine(foot_point, toe_point)
            painter.setPen(white_pen)
            painter.drawLine(hip_point, foot_point)
            painter.drawLine(foot_point, toe_point)

    def _draw_particles(self, painter: QPainter) -> None:
        """画花瓣 / 星星 / 爱心，带淡出。"""
        for particle in self._particles:
            opacity = max(0.0, min(1.0, particle["life"] / particle["max_life"]))
            size = particle["size"]
            painter.save()
            painter.translate(particle["x"], particle["y"])
            painter.rotate(particle["rotation"])
            painter.setPen(Qt.NoPen)

            kind = particle["kind"]
            if kind == "petal":
                color = QColor("#FFC2D1")
                color.setAlpha(int(255 * opacity))
                painter.setBrush(QBrush(color))
                painter.drawEllipse(QPointF(0, 0), size, size * 0.6)
            elif kind == "star":
                color = QColor("#FFD23F")
                color.setAlpha(int(255 * opacity))
                painter.setBrush(QBrush(color))
                painter.drawPath(self._star_path(size))
            else:
                color = QColor("#FF5C7A")
                color.setAlpha(int(255 * opacity))
                painter.setBrush(QBrush(color))
                painter.drawPath(self._heart_path(size))
            painter.restore()

    @staticmethod
    def _star_path(size: float) -> QPainterPath:
        """四角星路径。"""
        path = QPainterPath()
        path.moveTo(0, -size)
        path.cubicTo(size * 0.25, -size * 0.25, size * 0.25, -size * 0.25, size, 0)
        path.cubicTo(size * 0.25, size * 0.25, size * 0.25, size * 0.25, 0, size)
        path.cubicTo(-size * 0.25, size * 0.25, -size * 0.25, size * 0.25, -size, 0)
        path.cubicTo(-size * 0.25, -size * 0.25, -size * 0.25, -size * 0.25, 0, -size)
        return path

    @staticmethod
    def _heart_path(size: float) -> QPainterPath:
        """心形路径。"""
        path = QPainterPath()
        path.moveTo(0, size * 0.6)
        path.cubicTo(-size * 1.1, -size * 0.1, -size * 0.5, -size * 0.9, 0, -size * 0.3)
        path.cubicTo(size * 0.5, -size * 0.9, size * 1.1, -size * 0.1, 0, size * 0.6)
        return path

    # ------------------------------------------------------------------ 交互
    def mousePressEvent(self, event) -> None:  # noqa: N802
        """按下左键：记录拖动起点。"""
        if event.button() == Qt.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )
            self._dragged = False
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        """拖动移动位置。"""
        if self._drag_offset is not None and (event.buttons() & Qt.LeftButton):
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            self._dragged = True
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        """未拖动即单击 → 唤起主界面；拖动过 → 记住新位置。"""
        if event.button() != Qt.LeftButton:
            return
        if self._dragged:
            geometry = self.geometry()
            self._backend.config.floating_ball_pos = [geometry.x(), geometry.y()]
            self._backend.save_config()
        else:
            self._host.summon_to_front()
            # 主窗口被唤起后会盖住置顶的小西瓜，这里把它重新浮上来
            bring_to_front_quietly(self)
        self._drag_offset = None
        event.accept()

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        """右键菜单：打开主界面 / 开关说话 / 收起 / 退出。"""
        theme = self._themes.current
        menu = QMenu(self)
        menu.setStyleSheet(menu_qss(theme))

        open_action = menu.addAction("打开主界面")
        menu.addSeparator()
        speaking = self._backend.config.bubble_speak
        speak_action = menu.addAction("关闭西瓜说话" if speaking else "开启西瓜说话")
        hide_action = menu.addAction("收起悬浮西瓜")
        quit_action = menu.addAction("退出程序")

        chosen = menu.exec(event.globalPos())
        if chosen is None:
            return
        if chosen == open_action:
            self._host.summon_to_front()
        elif chosen == speak_action:
            self._backend.config.bubble_speak = not speaking
            self._backend.save_config()
            # 由开到关时立刻收起闲聊气泡（强提醒不受影响）
            if speaking and not self._bubble_is_timed():
                self._hide_bubble()
        elif chosen == hide_action:
            self._host.hide_floating_ball()
        elif chosen == quit_action:
            self._host.quit_application()
