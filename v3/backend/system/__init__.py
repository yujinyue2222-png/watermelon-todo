"""操作系统集成：开机自启等与平台强相关的能力。"""

from backend.system.autostart import is_autostart_supported, set_autostart

__all__ = ["is_autostart_supported", "set_autostart"]
