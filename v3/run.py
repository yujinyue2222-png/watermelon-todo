#!/usr/bin/env python3
"""西瓜todo 桌面版入口。

用法：

    python run.py

顶层只做三件事：把项目根加入模块搜索路径、初始化日志、启动界面。
"""

import argparse
import io
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.logging_setup import setup_logging  # noqa: E402
from backend.core.paths import user_data_dir  # noqa: E402

logger = logging.getLogger("watermelon")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 不含程序名的参数列表。
    """
    parser = argparse.ArgumentParser(description="西瓜todo 桌面待办")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="输出调试日志",
    )
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    """启动图形界面。

    Args:
        args: 已解析的命令行参数。

    Returns:
        进程退出码。
    """
    setup_logging(
        log_dir=user_data_dir(),
        level=logging.DEBUG if args.debug else logging.INFO,
    )
    # 延迟到日志初始化之后再导入前端，保证 Qt 的告警也能进日志
    from frontend.application import run_app

    return run_app(sys.argv[:1])


def main() -> int:
    """程序入口。

    Returns:
        进程退出码：0 正常退出，1 出现未捕获异常。
    """
    _ensure_std_streams()
    args = parse_args(sys.argv[1:])
    try:
        return run(args)
    except Exception as exc:  # noqa: BLE001 顶层兜底，保证异常一定被记录
        logger.exception("启动失败：%s", exc)
        return 1


def _ensure_std_streams() -> None:
    """打包成 GUI 程序后 stdout/stderr 可能是 None，先补上占位对象。"""
    if sys.stdout is None:
        sys.stdout = io.StringIO()
    if sys.stderr is None:
        sys.stderr = io.StringIO()


if __name__ == "__main__":
    sys.exit(main())
