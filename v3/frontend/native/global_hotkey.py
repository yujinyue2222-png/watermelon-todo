"""系统级全局快捷键。

- Windows：``RegisterHotKey`` + Qt 原生事件过滤器捕获 ``WM_HOTKEY``；
- macOS：Carbon 的 ``RegisterEventHotKey``（需要 HIToolbox 框架）；
- 其他平台：不支持，注册返回 False。

注册失败通常意味着组合键被别的应用占用，交由调用方提示用户换一个。
"""

from __future__ import annotations

import ctypes
import logging
from typing import Callable, Optional

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtWidgets import QApplication

from backend.core.platform_info import IS_MACOS, IS_WINDOWS
from backend.models.app_config import HotkeySpec

logger = logging.getLogger(__name__)

HotkeyCallback = Callable[[], None]

# ---------------------------------------------------------------- Windows
_WM_HOTKEY = 0x0312
_HOTKEY_ID = 0xB001
_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_VK_T = 0x54
_VK_F1 = 0x70

# ---------------------------------------------------------------- macOS
_CARBON_PATH = (
    "/System/Library/Frameworks/Carbon.framework/Frameworks/"
    "HIToolbox.framework/HIToolbox"
)
_EVENT_CLASS_KEYBOARD = int.from_bytes(b"keyb", "big")
_EVENT_HOTKEY_PRESSED = 5
_HOTKEY_SIGNATURE = int.from_bytes(b"WMTD", "big")
_CMD_KEY = 1 << 8
_SHIFT_KEY = 1 << 9
_OPTION_KEY = 1 << 11

# macOS 虚拟键码表
_MAC_KEY_CODES = {
    "A": 0, "S": 1, "D": 2, "F": 3, "H": 4, "G": 5, "Z": 6, "X": 7, "C": 8,
    "V": 9, "B": 11, "Q": 12, "W": 13, "E": 14, "R": 15, "Y": 16, "T": 17,
    "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "9": 25, "7": 26,
    "8": 28, "0": 29, "O": 31, "U": 32, "I": 34, "P": 35, "L": 37, "J": 38,
    "K": 40, "N": 45, "M": 46,
    "F1": 122, "F2": 120, "F3": 99, "F4": 118, "F5": 96, "F6": 97, "F7": 98,
    "F8": 100, "F9": 101, "F10": 109, "F11": 103, "F12": 111,
}


class _WindowsHotkeyFilter(QAbstractNativeEventFilter):
    """捕获 ``WM_HOTKEY`` 消息并触发回调。"""

    def __init__(self, hotkey_id: int, callback: HotkeyCallback) -> None:
        super().__init__()
        self._hotkey_id = hotkey_id
        self._callback = callback

    def nativeEventFilter(self, event_type, message):  # noqa: N802 (Qt 命名)
        """Qt 原生事件回调，返回 ``(是否拦截, result)``。"""
        if event_type not in (b"windows_generic_MSG", "windows_generic_MSG"):
            return False, 0
        try:
            import ctypes.wintypes

            msg = ctypes.wintypes.MSG.from_address(int(message))
        except (ImportError, ValueError, TypeError) as exc:
            logger.debug("解析原生消息失败：%s", exc)
            return False, 0
        if msg.message == _WM_HOTKEY and msg.wParam == self._hotkey_id:
            self._callback()
        return False, 0


class _MacEventTypeSpec(ctypes.Structure):
    """Carbon 事件类型描述。"""

    _fields_ = [("event_class", ctypes.c_uint32), ("event_kind", ctypes.c_uint32)]


class _MacEventHotKeyID(ctypes.Structure):
    """Carbon 全局快捷键标识。"""

    _fields_ = [("signature", ctypes.c_uint32), ("hotkey_id", ctypes.c_uint32)]


class _MacHotkey:
    """通过 Carbon API 注册的一个全局快捷键。"""

    def __init__(self, key_code: int, modifiers: int, callback: HotkeyCallback) -> None:
        """
        Args:
            key_code: macOS 虚拟键码。
            modifiers: Carbon 修饰键掩码。
            callback: 命中时的回调。

        Raises:
            OSError: HIToolbox 载入失败。
            RuntimeError: 安装事件处理器或注册快捷键失败。
        """
        self._carbon = ctypes.cdll.LoadLibrary(_CARBON_PATH)
        self._callback = callback
        self._handler_ref = ctypes.c_void_p()
        self._hotkey_ref = ctypes.c_void_p()
        self._handler_proto = ctypes.CFUNCTYPE(
            ctypes.c_int32, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p
        )
        # 必须保留引用，否则回调函数会被 GC 回收导致进程崩溃
        self._handler = self._handler_proto(self._on_hotkey)
        self._configure_signatures()

        event_type = _MacEventTypeSpec(_EVENT_CLASS_KEYBOARD, _EVENT_HOTKEY_PRESSED)
        status = self._carbon.InstallEventHandler(
            self._carbon.GetApplicationEventTarget(),
            self._handler,
            1,
            ctypes.byref(event_type),
            None,
            ctypes.byref(self._handler_ref),
        )
        if status != 0:
            raise RuntimeError(f"安装 macOS 快捷键事件处理器失败：{status}")

        hotkey_id = _MacEventHotKeyID(_HOTKEY_SIGNATURE, 1)
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

    def _configure_signatures(self) -> None:
        """声明 Carbon 函数签名。"""
        carbon = self._carbon
        carbon.GetApplicationEventTarget.restype = ctypes.c_void_p
        carbon.InstallEventHandler.argtypes = [
            ctypes.c_void_p,
            self._handler_proto,
            ctypes.c_uint32,
            ctypes.POINTER(_MacEventTypeSpec),
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.InstallEventHandler.restype = ctypes.c_int32
        carbon.RegisterEventHotKey.argtypes = [
            ctypes.c_uint32,
            ctypes.c_uint32,
            _MacEventHotKeyID,
            ctypes.c_void_p,
            ctypes.c_uint32,
            ctypes.POINTER(ctypes.c_void_p),
        ]
        carbon.RegisterEventHotKey.restype = ctypes.c_int32
        carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]
        carbon.RemoveEventHandler.argtypes = [ctypes.c_void_p]

    def _on_hotkey(self, _next_handler, _event, _user_data) -> int:
        """Carbon 事件回调。"""
        try:
            self._callback()
        except RuntimeError as exc:  # 回调里抛异常会直接崩进程，必须兜住
            logger.error("快捷键回调异常：%s", exc)
        return 0

    def close(self) -> None:
        """注销快捷键并移除事件处理器。"""
        if self._hotkey_ref.value:
            self._carbon.UnregisterEventHotKey(self._hotkey_ref)
            self._hotkey_ref = ctypes.c_void_p()
        if self._handler_ref.value:
            self._carbon.RemoveEventHandler(self._handler_ref)
            self._handler_ref = ctypes.c_void_p()


class GlobalHotkey:
    """全局快捷键的跨平台封装，可反复注册以更新绑定。"""

    def __init__(self) -> None:
        self._windows_filter: Optional[_WindowsHotkeyFilter] = None
        self._mac_hotkey: Optional[_MacHotkey] = None

    @property
    def is_registered(self) -> bool:
        """当前是否已成功注册。"""
        return self._windows_filter is not None or self._mac_hotkey is not None

    @property
    def is_supported(self) -> bool:
        """当前平台是否支持全局快捷键。"""
        return IS_WINDOWS or IS_MACOS

    def register(self, spec: HotkeySpec, callback: HotkeyCallback) -> bool:
        """注册快捷键，会先注销旧的绑定。

        Args:
            spec: 快捷键配置。
            callback: 命中时执行的回调。

        Returns:
            是否注册成功；平台不支持或组合键被占用时返回 False。
        """
        self.unregister()
        normalized = spec.normalized()
        if IS_WINDOWS:
            return self._register_windows(normalized, callback)
        if IS_MACOS:
            return self._register_macos(normalized, callback)
        logger.info("当前平台不支持全局快捷键")
        return False

    def unregister(self) -> None:
        """注销当前快捷键。"""
        if self._windows_filter is not None:
            try:
                ctypes.windll.user32.UnregisterHotKey(None, _HOTKEY_ID)
            except (AttributeError, OSError) as exc:
                logger.debug("注销 Windows 热键失败：%s", exc)
            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._windows_filter)
            self._windows_filter = None
        if self._mac_hotkey is not None:
            self._mac_hotkey.close()
            self._mac_hotkey = None

    # ------------------------------------------------------------------ 内部
    def _register_windows(self, spec: HotkeySpec, callback: HotkeyCallback) -> bool:
        """Windows 平台注册。"""
        modifiers = 0
        if spec.ctrl:
            modifiers |= _MOD_CONTROL
        if spec.alt:
            modifiers |= _MOD_ALT
        if spec.shift:
            modifiers |= _MOD_SHIFT

        try:
            registered = ctypes.windll.user32.RegisterHotKey(
                None, _HOTKEY_ID, modifiers, _to_windows_vk(spec.key)
            )
        except (AttributeError, OSError) as exc:
            logger.error("注册 Windows 热键失败：%s", exc)
            return False
        if not registered:
            logger.warning("热键 %s 可能已被其他程序占用", spec.label())
            return False

        app = QApplication.instance()
        if app is None:
            return False
        self._windows_filter = _WindowsHotkeyFilter(_HOTKEY_ID, callback)
        app.installNativeEventFilter(self._windows_filter)
        logger.info("已注册全局热键：%s", spec.label())
        return True

    def _register_macos(self, spec: HotkeySpec, callback: HotkeyCallback) -> bool:
        """macOS 平台注册。"""
        modifiers = 0
        if spec.ctrl:
            modifiers |= _CMD_KEY
        if spec.alt:
            modifiers |= _OPTION_KEY
        if spec.shift:
            modifiers |= _SHIFT_KEY

        try:
            self._mac_hotkey = _MacHotkey(
                _to_mac_key_code(spec.key), modifiers, callback
            )
        except (OSError, RuntimeError) as exc:
            logger.warning("注册 macOS 热键 %s 失败：%s", spec.label(True), exc)
            self._mac_hotkey = None
            return False
        logger.info("已注册全局热键：%s", spec.label(True))
        return True


def available_keys() -> list[str]:
    """快捷键设置界面可选的主键列表。"""
    letters = [chr(code) for code in range(ord("A"), ord("Z") + 1)]
    digits = [str(number) for number in range(10)]
    functions = [f"F{number}" for number in range(1, 13)]
    return letters + digits + functions


def _to_windows_vk(key: str) -> int:
    """主键 → Win32 虚拟键码。"""
    text = (key or "").strip().upper()
    if text.startswith("F") and text[1:].isdigit():
        number = int(text[1:])
        if 1 <= number <= 12:
            return _VK_F1 + number - 1
    if len(text) == 1 and (text.isdigit() or "A" <= text <= "Z"):
        return ord(text)
    return _VK_T


def _to_mac_key_code(key: str) -> int:
    """主键 → macOS 虚拟键码。"""
    return _MAC_KEY_CODES.get((key or "").strip().upper(), _MAC_KEY_CODES["T"])
