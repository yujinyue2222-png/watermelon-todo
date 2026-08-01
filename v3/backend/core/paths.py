"""路径解析：资源目录与用户数据目录。

约定：
- **资源**（图标、SVG）随程序分发，只读，位于 ``<项目根>/assets``；
  被 PyInstaller 打包后位于临时解包目录 ``sys._MEIPASS/assets``。
- **数据**（待办、配置）属于用户，写入系统标准用户目录，
  与程序文件分离，卸载或移动程序都不会丢失。
"""

import logging
import os
import shutil
import sys
from pathlib import Path

from backend.core.constants import (
    ASSETS_DIR_NAME,
    CONFIG_FILE_NAME,
    DATA_FILE_NAME,
    USER_DIR_NAME,
)
from backend.core.platform_info import IS_MACOS, IS_WINDOWS

logger = logging.getLogger(__name__)

# 本文件位于 <项目根>/backend/core/paths.py
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resource_root() -> Path:
    """返回只读资源的根目录（兼容源码运行与 PyInstaller 打包）。"""
    bundle_dir = getattr(sys, "_MEIPASS", None)
    return Path(bundle_dir) if bundle_dir else PROJECT_ROOT


def asset_path(name: str) -> Path:
    """返回 ``assets`` 下某个资源文件的完整路径。

    Args:
        name: 资源文件名，例如 ``watermelon_logo.svg``。
    """
    return resource_root() / ASSETS_DIR_NAME / name


def user_data_dir() -> Path:
    """返回用户数据目录，必要时创建；不可写时退回项目根目录。"""
    if IS_WINDOWS:
        base = Path(os.environ.get("APPDATA") or Path.home())
    elif IS_MACOS:
        base = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg) if xdg else Path.home() / ".local" / "share"

    target = base / USER_DIR_NAME
    try:
        target.mkdir(parents=True, exist_ok=True)
        # 必须真的试写一次：mkdir(exist_ok=True) 对一个已存在的只读目录也会成功，
        # 只判断能不能创建的话，这个「不可写就退回」的兜底根本不会触发，
        # 用户会得到一个看着正常、实际什么都存不下的程序
        probe = target / ".write_probe"
        probe.touch()
        probe.unlink()
    except OSError as exc:
        logger.warning("用户数据目录 %s 不可写：%s，退回程序目录", target, exc)
        return PROJECT_ROOT
    return target


def data_file() -> Path:
    """待办数据文件路径。"""
    return user_data_dir() / DATA_FILE_NAME


def config_file() -> Path:
    """配置文件路径。"""
    return user_data_dir() / CONFIG_FILE_NAME


def migrate_legacy_files(legacy_dirs: tuple[Path, ...] = ()) -> None:
    """首次运行时把旧版本遗留在程序目录旁的数据搬到用户目录。

    仅当用户目录还没有对应文件时才复制，绝不覆盖新数据。

    Args:
        legacy_dirs: 需要额外探测的历史数据目录。
    """
    target_dir = user_data_dir()
    candidates = (PROJECT_ROOT, PROJECT_ROOT.parent, *legacy_dirs)
    for name in (DATA_FILE_NAME, CONFIG_FILE_NAME):
        target = target_dir / name
        if target.exists():
            continue
        for source_dir in candidates:
            source = source_dir / name
            if source == target or not source.is_file():
                continue
            try:
                shutil.copy2(source, target)
            except OSError as exc:
                logger.warning("迁移旧数据 %s 失败：%s", source, exc)
            else:
                logger.info("已迁移旧数据：%s -> %s", source, target)
                break
