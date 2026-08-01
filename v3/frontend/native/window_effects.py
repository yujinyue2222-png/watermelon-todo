"""无边框悬浮窗口的跨平台修补。

桌面挂件类窗口（主面板、悬浮小西瓜、提醒弹窗）都是「无边框 + 置顶 + 半透明」，
这类窗口在 macOS 与 Windows 上的原生行为差异很大，本模块集中处理这些差异：

1. **不抢焦点**：macOS 把 ``Qt.Tool`` 映射成 NSPanel，鼠标划过就会变成 key window，
   会把正在打字的其他应用（比如微信）的键盘焦点抢走，因此 macOS 改用普通窗口
   并显式禁止激活。
2. **不留白色重影**：macOS 会给无边框窗口加一层阴影/浅色背景，浅色桌面下看着像
   「没抠图」，需要关掉窗口阴影并把背景设成 clearColor。
3. **置顶但不激活**：需要把悬浮球提到主窗口之上时，用 ``orderFrontRegardless``
   只调整窗口层级，不让本应用变成前台应用。

所有 ctypes/Objective-C 调用都做了兜底：失败只记 debug 日志，绝不影响功能。
"""

import ctypes
import logging
from ctypes.util import find_library
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

from backend.core.platform_info import IS_MACOS

logger = logging.getLogger(__name__)

# Objective-C runtime 调用可能抛出的异常
_NATIVE_ERRORS = (OSError, AttributeError, ValueError, TypeError, RuntimeError)

# 只有 cocoa 平台插件的 winId() 才是 NSView 指针
_COCOA_PLATFORM = "cocoa"


def _can_use_appkit() -> bool:
    """当前是否真的跑在 macOS 原生窗口系统上。

    光判断 ``IS_MACOS`` 不够：``QT_QPA_PLATFORM=offscreen``（无头测试、截图工具、
    CI）时 ``sys.platform`` 仍是 darwin，但 ``winId()`` 返回的不是 NSView 指针，
    把 Objective-C 消息发给它会直接段错误——异常处理拦不住段错误。
    """
    if not IS_MACOS:
        return False
    app = QGuiApplication.instance()
    return app is not None and app.platformName() == _COCOA_PLATFORM


def float_window_flags(topmost: bool = False) -> Qt.WindowFlags:
    """返回桌面悬浮窗口应使用的窗口标志。

    Args:
        topmost: 是否置顶。

    Returns:
        窗口标志组合。Windows/Linux 用 ``Qt.Tool`` 隐藏任务栏图标；
        macOS 用普通 ``Qt.Window`` 以免 NSPanel 抢键盘焦点。
    """
    flags = Qt.FramelessWindowHint
    flags |= Qt.Window if IS_MACOS else Qt.Tool
    if topmost:
        flags |= Qt.WindowStaysOnTopHint
    return flags


def apply_no_steal_focus(widget: QWidget, accept_focus: bool = True) -> None:
    """让窗口显示时不主动激活、鼠标划过不抢键盘焦点。

    Args:
        widget: 目标窗口。
        accept_focus: 是否允许接收键盘焦点。纯展示的悬浮球传 False；
            需要输入的主面板与弹窗保持 True。
    """
    widget.setAttribute(Qt.WA_ShowWithoutActivating, True)
    if IS_MACOS:
        widget.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
    if not accept_focus:
        widget.setFocusPolicy(Qt.NoFocus)


def bring_to_front_quietly(widget: QWidget) -> None:
    """把窗口提到最前，但**不激活**本应用。

    macOS 上用 NSWindow 的 ``orderFrontRegardless``；其他平台退回 ``raise_()``。
    主窗口被唤起后会盖住置顶的悬浮球，用这个函数可以把球重新浮上来，
    同时不打断用户在其他应用里的输入。
    """
    if not _can_use_appkit():
        widget.raise_()
        return
    window = _native_window(widget)
    if window is None:
        return
    try:
        objc, selector = _objc_runtime()
        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        send(window, selector(b"orderFrontRegardless"))
    except _NATIVE_ERRORS as exc:
        logger.debug("orderFrontRegardless 失败：%s", exc)


def strip_native_window_shadow(widget: QWidget) -> None:
    """关闭 macOS 的窗口阴影并把背景设为完全透明。

    只做属性设置，不改变窗口类型，风险极低；非 macOS 原生窗口系统直接返回。
    """
    if not _can_use_appkit():
        return
    window = _native_window(widget)
    if window is None:
        return
    try:
        objc, selector = _objc_runtime()
        send = objc.objc_msgSend

        # 1) 关掉窗口阴影：浅色桌面下这层光晕最像「白色重影」
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        send(window, selector(b"setHasShadow:"), ctypes.c_int(0))

        # 2) 背景色设为 NSColor.clearColor
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.objc_getClass.argtypes = [ctypes.c_char_p]
        ns_color = objc.objc_getClass(b"NSColor")
        if not ns_color:
            return
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        clear_color = ctypes.c_void_p(send(ns_color, selector(b"clearColor")))
        if clear_color:
            send.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
            send(window, selector(b"setBackgroundColor:"), clear_color)
    except _NATIVE_ERRORS as exc:
        logger.debug("设置窗口透明失败：%s", exc)


def _objc_runtime() -> tuple[ctypes.CDLL, "ctypes._FuncPointer"]:
    """载入 Objective-C runtime，返回 ``(libobjc, sel_registerName)``。"""
    library = ctypes.cdll.LoadLibrary(find_library("objc") or "/usr/lib/libobjc.dylib")
    selector = library.sel_registerName
    selector.restype = ctypes.c_void_p
    selector.argtypes = [ctypes.c_char_p]
    return library, selector


def _native_window(widget: QWidget) -> Optional[ctypes.c_void_p]:
    """取 Qt 控件背后的 NSWindow 指针；取不到返回 None。

    调用前必须先过 :func:`_can_use_appkit`：非 cocoa 平台下 ``winId()``
    不是 NSView 指针，向它发消息会段错误而不是抛异常。
    """
    if not _can_use_appkit():
        return None
    try:
        objc, selector = _objc_runtime()
        send = objc.objc_msgSend
        send.restype = ctypes.c_void_p
        send.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        view = ctypes.c_void_p(int(widget.winId()))
        window = ctypes.c_void_p(send(view, selector(b"window")))
    except _NATIVE_ERRORS as exc:
        logger.debug("获取 NSWindow 失败：%s", exc)
        return None
    return window if window.value else None
