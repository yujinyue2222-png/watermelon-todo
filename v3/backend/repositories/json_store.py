"""JSON 文件读写的公共实现。

统一处理三件事：编码（UTF-8）、原子写入、以及「文件损坏不能让程序打不开」。
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def read_json(path: Path) -> Optional[Any]:
    """读取 JSON 文件。

    Args:
        path: 文件路径。

    Returns:
        解析后的对象；文件不存在、内容损坏或不可读时返回 None。
    """
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("读取 %s 失败：%s", path, exc)
    except json.JSONDecodeError as exc:
        # 数据文件被外部程序改坏时不能直接崩，交给调用方按空数据处理
        logger.error("%s 不是合法 JSON（第 %s 行）：%s", path, exc.lineno, exc.msg)
    return None


def write_json(path: Path, payload: Any) -> bool:
    """原子写入 JSON 文件。

    先写同目录下的临时文件再 ``os.replace``，避免写入过程中断电/崩溃
    导致原文件被截断成半截 JSON。

    Args:
        path: 目标文件路径。
        payload: 可被 ``json.dump`` 序列化的对象。

    Returns:
        是否写入成功。
    """
    temp_path = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        _fsync_directory(path.parent)
    except (OSError, TypeError, ValueError) as exc:
        logger.error("写入 %s 失败：%s", path, exc)
        _remove_quietly(temp_path)
        return False
    return True


def _fsync_directory(directory: Path) -> None:
    """把目录项本身刷盘，让 ``os.replace`` 的结果真正持久化。

    只 fsync 文件内容是不够的：改名记在目录里，掉电后目录项可能还指着旧文件。
    Windows 不允许 ``open`` 一个目录，那里直接跳过。
    """
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        return  # Windows 或没有目录读权限，尽力而为即可
    try:
        os.fsync(fd)
    except OSError as exc:
        logger.debug("目录 %s 刷盘失败（忽略）：%s", directory, exc)
    finally:
        os.close(fd)


def _remove_quietly(path: Path) -> None:
    """删除临时文件，忽略不存在或权限问题。"""
    try:
        path.unlink()
    except OSError:
        pass
