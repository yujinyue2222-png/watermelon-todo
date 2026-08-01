"""配色方案、主题管理与样式表。"""

from frontend.theme.palettes import BUILTIN_THEMES, DEFAULT_THEME_NAME, Theme
from frontend.theme.theme_manager import ThemeManager

__all__ = ["BUILTIN_THEMES", "DEFAULT_THEME_NAME", "Theme", "ThemeManager"]
