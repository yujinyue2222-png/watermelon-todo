"""同步服务入口。

    python3 -m server --host 0.0.0.0 --port 52121

常用参数见 ``--help``。所有参数都有环境变量对应项，便于写进 systemd 配置。
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sqlite3
import sys
import threading
from pathlib import Path

from server import SERVER_VERSION
from server.database import SyncDatabase, now_ms
from server.http_api import create_server

logger = logging.getLogger("watermelon.server")

DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 52121
DEFAULT_DB_PATH = Path("~/.watermelon-sync/sync.db")

# 墓碑保留天数：超过这个时间的「已删除」记录会被物理清理
TOMBSTONE_RETENTION_DAYS = 60
_CLEANUP_INTERVAL_SECONDS = 24 * 3600
_MS_PER_DAY = 24 * 3600 * 1000


def parse_args(argv: list) -> argparse.Namespace:
    """解析命令行参数。

    Args:
        argv: 不含程序名的参数列表。
    """
    parser = argparse.ArgumentParser(
        prog="python3 -m server",
        description="西瓜todo 同步服务（纯标准库，无第三方依赖）",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("WATERMELON_HOST", DEFAULT_HOST),
        help=f"监听地址，默认 {DEFAULT_HOST}",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("WATERMELON_PORT", DEFAULT_PORT)),
        help=f"监听端口，默认 {DEFAULT_PORT}",
    )
    parser.add_argument(
        "--db",
        default=os.environ.get("WATERMELON_DB", str(DEFAULT_DB_PATH)),
        help=f"SQLite 文件路径，默认 {DEFAULT_DB_PATH}",
    )
    parser.add_argument(
        "--web",
        default=os.environ.get("WATERMELON_WEB", ""),
        help="静态网页目录（手机端 PWA）；留空则只提供 API",
    )
    parser.add_argument(
        "--access-token",
        default=os.environ.get("WATERMELON_ACCESS_TOKEN", ""),
        help="可选的访问令牌；设置后所有 /api 请求需带 X-Access-Token 头",
    )
    parser.add_argument("--debug", action="store_true", help="输出调试日志")
    return parser.parse_args(argv)


def run(args: argparse.Namespace) -> int:
    """启动服务并阻塞运行。

    Args:
        args: 已解析的命令行参数。

    Returns:
        进程退出码。
    """
    database = SyncDatabase(Path(args.db).expanduser())
    web_root = Path(args.web).expanduser() if args.web else None
    if web_root is not None and not web_root.is_dir():
        logger.warning("网页目录不存在，将只提供 API：%s", web_root)
        web_root = None

    server = create_server(
        host=args.host,
        port=args.port,
        database=database,
        web_root=web_root,
        access_token=args.access_token or None,
    )
    _install_signal_handlers(server)
    cleanup_stop = _start_cleanup_worker(database)

    logger.info(
        "西瓜todo 同步服务 v%s 已启动：http://%s:%d%s",
        SERVER_VERSION,
        args.host,
        args.port,
        "（含网页）" if web_root else "（仅 API）",
    )
    logger.info("数据库：%s", database.path)
    if args.access_token:
        logger.info("已启用访问令牌校验")

    try:
        server.serve_forever()
    finally:
        cleanup_stop.set()
        server.server_close()
        logger.info("同步服务已停止")
    return 0


def main() -> int:
    """程序入口。

    Returns:
        进程退出码：0 正常退出，1 出现未捕获异常。
    """
    args = parse_args(sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        return run(args)
    except OSError as exc:
        # 端口被占用、权限不足等，给出可操作的提示
        logger.error("启动失败：%s", exc)
        return 1
    except Exception as exc:  # noqa: BLE001 顶层兜底
        logger.exception("运行异常：%s", exc)
        return 1


def _install_signal_handlers(server) -> None:
    """收到 TERM/INT 时优雅停机，便于 systemd 管理。"""

    def shutdown(signum, _frame) -> None:
        logger.info("收到信号 %s，正在停机", signum)
        threading.Thread(target=server.shutdown, daemon=True).start()

    for name in ("SIGTERM", "SIGINT"):
        handler = getattr(signal, name, None)
        if handler is not None:
            signal.signal(handler, shutdown)


def _start_cleanup_worker(database: SyncDatabase) -> threading.Event:
    """起一个后台线程，每天清理一次过期墓碑。

    Returns:
        停机用的 Event：``set()`` 后线程会在下一次检查时退出。
    """
    stop = threading.Event()

    def loop() -> None:
        while not stop.wait(_CLEANUP_INTERVAL_SECONDS):
            try:
                removed = database.purge_tombstones(
                    now_ms() - TOMBSTONE_RETENTION_DAYS * _MS_PER_DAY
                )
            except sqlite3.Error as exc:
                logger.error("清理墓碑失败：%s", exc)
            else:
                if removed:
                    logger.info("已清理 %d 条过期删除记录", removed)

    threading.Thread(target=loop, name="tombstone-cleanup", daemon=True).start()
    return stop


if __name__ == "__main__":
    sys.exit(main())
