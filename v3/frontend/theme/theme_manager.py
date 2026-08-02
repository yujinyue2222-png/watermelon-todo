"""主题管理。

集中持有「当前用哪套配色」这一状态，配色变化时发出 :attr:`ThemeManager.changed`
信号，由主窗口与各弹窗自行刷新样式，避免相互直接调用。
"""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QObject, Signal

from backend.api import TodoBackend
from frontend.theme.palettes import (
    BUILTIN_THEME_ORDER,
    BUILTIN_THEMES,
    DEFAULT_THEME_NAME,
    THEME_SHOWCASE_LIMIT,
    Theme,
)

logger = logging.getLogger(__name__)

DIY_NAME_SUFFIX = "·DIY"


class ThemeManager(QObject):
    """当前配色的唯一来源。

    Signals:
        changed: 配色或背景图发生变化（含临时预览）。
    """

    changed = Signal()

    def __init__(self, backend: TodoBackend, parent: Optional[QObject] = None) -> None:
        """
        Args:
            backend: 后端门面，用于读写配置。
            parent: Qt 父对象。
        """
        super().__init__(parent)
        self._backend = backend
        self._themes: dict[str, Theme] = dict(BUILTIN_THEMES)
        self._order: list[str] = list(BUILTIN_THEME_ORDER)
        self._preview: Optional[Theme] = None

        for name, theme in backend.config.custom_themes.items():
            self._themes[name] = theme
            if name not in self._order:
                self._order.append(name)

        self._current_name = backend.config.theme
        if self._current_name not in self._themes:
            logger.warning("配置里的主题「%s」不存在，回退到默认主题", self._current_name)
            self._current_name = DEFAULT_THEME_NAME

    # ------------------------------------------------------------------ 读取
    @property
    def current_name(self) -> str:
        """当前主题名。"""
        return self._current_name

    @property
    def current(self) -> Theme:
        """当前生效的配色（预览态优先）。"""
        return self._preview or self._themes[self._current_name]

    @property
    def names(self) -> list[str]:
        """全部可用主题名（内置 + DIY）。"""
        return list(self._order)

    def theme_of(self, name: str) -> Theme:
        """按名字取配色；不存在时返回默认主题。"""
        return self._themes.get(name, BUILTIN_THEMES[DEFAULT_THEME_NAME])

    def showcase_names(self) -> list[str]:
        """主题市场/菜单里展示的主题名。

        只展示前若干个内置示例，但保证当前正在用的主题一定可见。
        """
        shown = list(BUILTIN_THEME_ORDER[:THEME_SHOWCASE_LIMIT])
        if self._current_name not in shown and self._current_name in self._themes:
            shown = shown[:-1] + [self._current_name]
        return shown

    def is_custom(self, name: str) -> bool:
        """是否为 DIY 主题。"""
        return name in self._backend.config.custom_themes

    # ------------------------------------------------------------------ 写入
    def apply(self, name: str) -> None:
        """切换主题并持久化。"""
        if name not in self._themes:
            logger.warning("忽略未知主题：%s", name)
            return
        self._preview = None
        self._current_name = name
        self._backend.config.theme = name
        self._backend.save_config()
        self.changed.emit()

    def preview(self, theme: Optional[Theme]) -> None:
        """临时套用一套配色用于实时预览，不写配置。

        Args:
            theme: 预览配色；传 None 表示取消预览、回到已保存的主题。
        """
        self._preview = theme
        self.changed.emit()

    def save_custom(self, name: str, theme: Theme) -> str:
        """保存一套 DIY 配色并立即应用。

        与内置主题重名时自动加后缀，避免覆盖内置配色。

        Args:
            name: 用户输入的主题名。
            theme: 完整配色字典。

        Returns:
            实际保存使用的主题名。
        """
        final_name = (name or "").strip() or "我的配色"
        customs = self._backend.config.custom_themes
        if final_name in BUILTIN_THEMES and final_name not in customs:
            final_name += DIY_NAME_SUFFIX

        customs[final_name] = theme
        self._themes[final_name] = theme
        if final_name not in self._order:
            self._order.append(final_name)
        logger.info("保存 DIY 主题：%s", final_name)
        self.apply(final_name)
        return final_name

    # -------------------------------------------------------------- 背景图片
    @property
    def background_image(self) -> str:
        """自定义背景图路径；空串表示没有。"""
        return self._backend.config.background_image

    def set_background_image(self, path: str) -> None:
        """设置背景图并持久化。"""
        self._backend.config.background_image = path
        self._backend.save_config()
        self.changed.emit()

    def clear_background_image(self) -> None:
        """清除背景图。"""
        self.set_background_image("")
