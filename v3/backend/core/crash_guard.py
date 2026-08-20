"""崩溃留痕。

打包成 GUI 程序后没有控制台，Qt 事件循环里未捕获的异常会被静默吞掉、
进程直接消失，导致「莫名就不在了」却查不到原因。

本模块统一安装两道防线：

1. ``sys.excepthook``：捕获主线程未处理的 Python 异常，写进日志文件。
2. ``threading.excepthook``：捕获子线程（如同步线程）里的未处理异常。
3. ``faulthandler``：捕获 C 层的致命错误（段错误等），把原生栈也写进日志文件。

安装后，任何异常退出都会在 ``app.log`` 留下完整栈，方便定位。
"""

from __future__ import annotations

import faulthandler
import logging
import sys
import threading
from pathlib import Path
from types import TracebackType
from typing import Optional, Type

logger = logging.getLogger(__name__)

_FAULT_LOG_NAME = "crash.log"
# 持有原生崩溃日志的文件句柄，避免被 GC 关闭
_fault_file = None


def install_crash_guard(log_dir: Optional[Path] = None) -> None:
    """安装全局异常与致命错误捕获。

    Args:
        log_dir: 原生崩溃日志目录；为 None 时只捕获 Python 异常，不落原生栈。
    """
    sys.excepthook = _handle_uncaught
    _install_thread_hook()
    _install_faulthandler(log_dir)


def _handle_uncaught(
    exc_type: Type[BaseException],
    exc_value: BaseException,
    exc_tb: Optional[TracebackType],
) -> None:
    """主线程未捕获异常：写日志，但不强制退出。"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical(
        "未捕获异常导致异常状态：%s",
        exc_value,
        exc_info=(exc_type, exc_value, exc_tb),
    )


def _install_thread_hook() -> None:
    """子线程未捕获异常也写日志（Python 3.8+）。"""
    if not hasattr(threading, "excepthook"):
        return

    def _thread_hook(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, SystemExit):
            return
        logger.critical(
            "子线程 %s 未捕获异常：%s",
            getattr(args.thread, "name", "?"),
            args.exc_value,
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    threading.excepthook = _thread_hook


def _install_faulthandler(log_dir: Optional[Path]) -> None:
    """把 C 层致命错误的原生栈写到独立文件。"""
    global _fault_file
    if log_dir is None:
        try:
            faulthandler.enable()
        except (RuntimeError, ValueError):
            pass
        return
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        _fault_file = open(log_dir / _FAULT_LOG_NAME, "a", encoding="utf-8")
        faulthandler.enable(file=_fault_file, all_threads=True)
    except (OSError, RuntimeError, ValueError) as exc:
        logger.warning("faulthandler 启用失败：%s", exc)