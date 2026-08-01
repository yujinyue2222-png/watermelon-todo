"""与操作系统直接交互的能力（窗口层级、全局快捷键）。"""

from frontend.native.global_hotkey import GlobalHotkey
from frontend.native.window_effects import (
    apply_no_steal_focus,
    bring_to_front_quietly,
    float_window_flags,
    strip_native_window_shadow,
)

__all__ = [
    "GlobalHotkey",
    "apply_no_steal_focus",
    "bring_to_front_quietly",
    "float_window_flags",
    "strip_native_window_shadow",
]
