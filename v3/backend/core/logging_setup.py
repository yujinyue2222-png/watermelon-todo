"""日志初始化。

程序内禁止用 ``print`` 输出业务日志，统一走 ``logging``。
打包成 GUI 程序后没有控制台，因此除了标准输出还会写一份日志文件到用户数据目录。
"""

import logging
import sys
from pathlib import Path
from typing import Optional

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE_NAME = "app.log"
MAX_LOG_BYTES = 512 * 1024


def setup_logging(log_dir: Optional[Path] = None, level: int = logging.INFO) -> None:
    """配置根 logger。

    Args:
        log_dir: 日志文件目录；为 None 时只输出到 stderr。
        level: 日志级别。
    """
    handlers: list[logging.Handler] = []
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))

    if log_dir is not None:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file = log_dir / LOG_FILE_NAME
            # 超过阈值直接截断，避免长期运行把日志养大（无需引入 rotating 依赖）
            if log_file.exists() and log_file.stat().st_size > MAX_LOG_BYTES:
                log_file.unlink()
            handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
        except OSError as exc:
            logging.getLogger(__name__).warning("日志文件不可用：%s", exc)

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        handlers=handlers,
        force=True,
    )
