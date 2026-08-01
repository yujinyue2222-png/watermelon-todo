"""开机 / 登录自启。

- Windows：在「启动」文件夹放一个快捷方式；
- macOS：在 ``~/Library/LaunchAgents`` 写一个 LaunchAgent plist；
- 其他平台：暂不支持。

源码运行时启动的是入口脚本 ``run.py``；打包后直接启动可执行文件本身。
（v2 这里硬编码了已不存在的 ``todo_qt.py``，导致源码模式自启失效，此处已修正。）
"""

from __future__ import annotations

import logging
import os
import plistlib
import subprocess
import sys
from pathlib import Path

from backend.core.constants import APP_ID, APP_NAME
from backend.core.paths import PROJECT_ROOT
from backend.core.platform_info import IS_FROZEN, IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)

ENTRY_SCRIPT_NAME = "run.py"
_WINDOWS_SHORTCUT_NAME = f"{APP_NAME}.lnk"
_MAC_PLIST_NAME = f"{APP_ID}.plist"


def is_autostart_supported() -> bool:
    """当前平台是否支持自启设置。"""
    return IS_WINDOWS or IS_MACOS


def launch_command() -> list[str]:
    """返回用于自启的启动命令。

    Returns:
        打包后为 ``[可执行文件]``；源码运行为 ``[python, run.py]``。
    """
    if IS_FROZEN:
        return [sys.executable]
    return [sys.executable, str(PROJECT_ROOT / ENTRY_SCRIPT_NAME)]


def set_autostart(enable: bool) -> bool:
    """开启或关闭自启。

    Args:
        enable: True 表示开启。

    Returns:
        是否设置成功；不支持的平台返回 False。
    """
    if IS_WINDOWS:
        return _set_autostart_windows(enable)
    if IS_MACOS:
        return _set_autostart_macos(enable)
    logger.info("当前平台不支持开机自启")
    return False


def _powershell_literal(text: str) -> str:
    """把字符串包成 PowerShell 单引号字面量（内部的单引号写两遍）。"""
    return "'" + text.replace("'", "''") + "'"


def _startup_dir() -> Path:
    """Windows 启动文件夹。"""
    appdata = os.environ.get("APPDATA") or str(Path.home())
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _set_autostart_windows(enable: bool) -> bool:
    """Windows：通过启动文件夹的快捷方式实现。"""
    link = _startup_dir() / _WINDOWS_SHORTCUT_NAME
    if not enable:
        try:
            link.unlink(missing_ok=True)
        except OSError as exc:
            logger.error("移除自启快捷方式失败：%s", exc)
            return False
        return True

    command = launch_command()
    target = command[0]
    arguments = " ".join(f'"{item}"' for item in command[1:])
    # 所有路径都用 PowerShell 单引号字面量包起来：双引号串里 $ 和反引号会被展开，
    # 而路径里带撇号（"Zhang's PC"）会直接把语句截断
    script = (
        "$shell = New-Object -ComObject WScript.Shell;"
        f"$link = $shell.CreateShortcut({_powershell_literal(str(link))});"
        f"$link.TargetPath = {_powershell_literal(target)};"
        f"$link.Arguments = {_powershell_literal(arguments)};"
        f"$link.WorkingDirectory = {_powershell_literal(str(PROJECT_ROOT))};"
        "$link.Save()"
    )
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.error("创建自启快捷方式失败：%s", exc)
        return False
    return True


def _set_autostart_macos(enable: bool) -> bool:
    """macOS：通过 LaunchAgent plist 实现登录自启。"""
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    plist_path = agents_dir / _MAC_PLIST_NAME

    if not enable:
        try:
            plist_path.unlink(missing_ok=True)
        except OSError as exc:
            logger.error("移除 LaunchAgent 失败：%s", exc)
            return False
        return True

    # 用 plistlib 生成，不要自己拼 XML：路径里出现 & 或 < 都是合法的，
    # 手拼会写出一个非法 plist，launchd 直接忽略而这里照样返回成功
    payload = {
        "Label": APP_ID,
        "ProgramArguments": launch_command(),
        "RunAtLoad": True,
    }
    try:
        agents_dir.mkdir(parents=True, exist_ok=True)
        with plist_path.open("wb") as handle:
            plistlib.dump(payload, handle)
    except OSError as exc:
        logger.error("写入 LaunchAgent 失败：%s", exc)
        return False
    return True
