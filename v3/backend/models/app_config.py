"""应用配置模型。

JSON 里的键名与 v2 完全一致，因此新旧版本共用同一份配置文件也不会丢设置。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from backend.core.constants import DEFAULT_CATEGORIES, DEFAULT_SYNC_SERVER

DEFAULT_THEME = "极光白"
MIN_WINDOW_WIDTH = 300
MIN_EXPANDED_HEIGHT = 420


@dataclass
class WindowGeometry:
    """主窗口位置与尺寸。"""

    x: int = 140
    y: int = 120
    width: int = 340
    height: int = 500

    @classmethod
    def from_list(cls, raw: Any) -> WindowGeometry:
        """从 ``[x, y, w, h]`` 构建；格式不对时用默认值。"""
        default = cls()
        if not isinstance(raw, (list, tuple)) or len(raw) != 4:
            return default
        try:
            values = [int(item) for item in raw]
        except (TypeError, ValueError):
            return default
        return cls(*values)

    def to_list(self) -> list[int]:
        """序列化为 ``[x, y, w, h]``。"""
        return [self.x, self.y, self.width, self.height]


@dataclass
class HotkeySpec:
    """召唤/隐藏窗口的全局快捷键。

    ``ctrl`` 在 macOS 上对应 Command，``alt`` 对应 Option，
    这样同一份配置在两个平台上都能表达「主修饰键 + 次修饰键」。
    """

    ctrl: bool = True
    alt: bool = True
    shift: bool = False
    key: str = "T"

    def normalized(self) -> HotkeySpec:
        """保证至少有一个修饰键，主键统一大写。"""
        # 主键的清洗要放在两个分支之外：只补修饰键而不清主键的话，
        # 空串或带空格的主键会原样写进配置文件并拿去注册快捷键
        key = (self.key or "T").strip().upper()
        if not (self.ctrl or self.alt or self.shift):
            return HotkeySpec(ctrl=True, alt=True, shift=self.shift, key=key)
        return HotkeySpec(ctrl=self.ctrl, alt=self.alt, shift=self.shift, key=key)

    def label(self, mac_style: bool = False) -> str:
        """拼成可读文本，例如 ``Ctrl+Alt+T`` 或 ``⌘⌥T``。"""
        spec = self.normalized()
        if mac_style:
            parts = []
            if spec.ctrl:
                parts.append("⌘")
            if spec.alt:
                parts.append("⌥")
            if spec.shift:
                parts.append("⇧")
            return "".join(parts) + spec.key
        parts = []
        if spec.ctrl:
            parts.append("Ctrl")
        if spec.alt:
            parts.append("Alt")
        if spec.shift:
            parts.append("Shift")
        parts.append(spec.key)
        return "+".join(parts)

    @classmethod
    def from_dict(cls, raw: Any) -> HotkeySpec:
        """从 JSON 字典构建。"""
        default = cls()
        if not isinstance(raw, dict):
            return default
        return cls(
            ctrl=bool(raw.get("ctrl", default.ctrl)),
            alt=bool(raw.get("alt", default.alt)),
            shift=bool(raw.get("shift", default.shift)),
            key=str(raw.get("key") or default.key),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 字典。"""
        return {"ctrl": self.ctrl, "alt": self.alt, "shift": self.shift, "key": self.key}


@dataclass
class SyncSettings:
    """多端同步设置。

    Attributes:
        user_id: 同步码。谁拿到它就能读写这份数据，因此默认生成一串长随机码，
            换设备时把它抄过去即可完成「登录」。
        cursor: 上次成功同步拿到的服务端游标，用于增量拉取。
        access_token: 服务端若开启了访问令牌校验，这里填同一个串。
        last_error: 最近一次同步的失败原因，用于界面提示。
    """

    enabled: bool = False
    server_url: str = DEFAULT_SYNC_SERVER
    user_id: str = ""
    access_token: str = ""
    cursor: int = 0
    last_sync_at: int = 0
    last_error: str = ""

    @property
    def is_configured(self) -> bool:
        """是否已具备可同步的最小配置。"""
        return bool(self.enabled and self.server_url.strip() and self.user_id.strip())

    @classmethod
    def from_dict(cls, raw: Any) -> SyncSettings:
        """从 JSON 字典构建。"""
        default = cls()
        if not isinstance(raw, dict):
            return default
        try:
            cursor = int(raw.get("cursor", default.cursor))
        except (TypeError, ValueError):
            cursor = default.cursor
        try:
            last_sync_at = int(raw.get("last_sync_at", default.last_sync_at))
        except (TypeError, ValueError):
            last_sync_at = default.last_sync_at
        return cls(
            enabled=bool(raw.get("enabled", default.enabled)),
            server_url=str(raw.get("server_url") or default.server_url),
            user_id=str(raw.get("user_id") or ""),
            access_token=str(raw.get("access_token") or ""),
            cursor=max(0, cursor),
            last_sync_at=max(0, last_sync_at),
            last_error=str(raw.get("last_error") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 字典。"""
        return {
            "enabled": self.enabled,
            "server_url": self.server_url,
            "user_id": self.user_id,
            "access_token": self.access_token,
            "cursor": self.cursor,
            "last_sync_at": self.last_sync_at,
            "last_error": self.last_error,
        }


@dataclass
class AppConfig:
    """用户偏好设置的聚合。

    Attributes:
        custom_themes: DIY 配色，``{主题名: 主题配色字典}``。
        background_image: 主窗口背景图路径（JSON 键沿用 v2 的 ``bg_image``）。
    """

    theme: str = DEFAULT_THEME
    topmost: bool = True
    geometry: WindowGeometry = field(default_factory=WindowGeometry)
    expanded_height: int = 500
    collapsed: bool = False
    autostart: bool = False
    categories: list[str] = field(default_factory=lambda: list(DEFAULT_CATEGORIES))
    floating_ball: bool = True
    floating_ball_pos: Optional[list[int]] = None
    bubble_speak: bool = True
    hotkey: HotkeySpec = field(default_factory=HotkeySpec)
    custom_themes: dict[str, dict[str, Any]] = field(default_factory=dict)
    background_image: str = ""
    tray_tip_shown: bool = False
    sync: SyncSettings = field(default_factory=SyncSettings)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> AppConfig:
        """从 JSON 字典构建，并兼容 v2 的旧键。"""
        default = cls()
        geometry = WindowGeometry.from_list(raw.get("geometry"))

        categories_raw = raw.get("categories")
        if isinstance(categories_raw, list) and categories_raw:
            categories = [str(item) for item in categories_raw]
        else:
            categories = list(DEFAULT_CATEGORIES)

        custom_themes: dict[str, dict[str, Any]] = {}
        themes_raw = raw.get("custom_themes")
        if isinstance(themes_raw, dict):
            for name, theme in themes_raw.items():
                if isinstance(theme, dict) and theme:
                    custom_themes[str(name)] = dict(theme)
        # 兼容 v2 早期只支持一套匿名 DIY 配色的写法
        legacy_theme = raw.get("custom_theme")
        if isinstance(legacy_theme, dict) and legacy_theme and "自定义" not in custom_themes:
            custom_themes["自定义"] = dict(legacy_theme)

        ball_pos = raw.get("floating_ball_pos")
        floating_ball_pos: Optional[list[int]] = None
        if isinstance(ball_pos, (list, tuple)) and len(ball_pos) == 2:
            try:
                floating_ball_pos = [int(ball_pos[0]), int(ball_pos[1])]
            except (TypeError, ValueError):
                floating_ball_pos = None

        expanded = raw.get("expanded_height", geometry.height)
        try:
            expanded_height = int(expanded)
        except (TypeError, ValueError):
            expanded_height = default.expanded_height
        expanded_height = max(MIN_EXPANDED_HEIGHT, expanded_height)

        return cls(
            theme=str(raw.get("theme") or default.theme),
            topmost=bool(raw.get("topmost", default.topmost)),
            geometry=geometry,
            expanded_height=expanded_height,
            collapsed=bool(raw.get("collapsed", default.collapsed)),
            autostart=bool(raw.get("autostart", default.autostart)),
            categories=categories,
            floating_ball=bool(raw.get("floating_ball", default.floating_ball)),
            floating_ball_pos=floating_ball_pos,
            bubble_speak=bool(raw.get("bubble_speak", default.bubble_speak)),
            hotkey=HotkeySpec.from_dict(raw.get("hotkey")),
            custom_themes=custom_themes,
            background_image=str(raw.get("bg_image") or ""),
            tray_tip_shown=bool(raw.get("tray_tip_shown", default.tray_tip_shown)),
            sync=SyncSettings.from_dict(raw.get("sync")),
        )

    def to_dict(self) -> dict[str, Any]:
        """序列化为 JSON 字典。"""
        payload = {
            "theme": self.theme,
            "topmost": self.topmost,
            "geometry": self.geometry.to_list(),
            "expanded_height": self.expanded_height,
            "collapsed": self.collapsed,
            "autostart": self.autostart,
            "categories": list(self.categories),
            "floating_ball": self.floating_ball,
            "floating_ball_pos": self.floating_ball_pos,
            "bubble_speak": self.bubble_speak,
            "hotkey": self.hotkey.to_dict(),
            "custom_themes": {name: dict(t) for name, t in self.custom_themes.items()},
            "bg_image": self.background_image,
            "tray_tip_shown": self.tray_tip_shown,
            "sync": self.sync.to_dict(),
        }
        # 回写 v2 的旧键，两个版本共用同一份配置文件时 DIY 配色才不会丢
        if "自定义" in self.custom_themes:
            payload["custom_theme"] = dict(self.custom_themes["自定义"])
        return payload

    def add_category(self, name: str) -> bool:
        """追加一个分类，已存在时返回 False。"""
        cleaned = (name or "").strip()
        if not cleaned or cleaned in self.categories:
            return False
        self.categories.append(cleaned)
        return True
