"""同步服务的 SQLite 存储。

表结构极简，只够支撑「按用户增量同步」：

``users``
    每个同步码一行，附带一个单调递增的 ``seq`` 计数器。
``tasks``
    ``(user_id, task_id)`` 为主键；``payload`` 是整条待办的 JSON 原文；
    ``server_seq`` 是该用户维度的写入序号，客户端靠它做增量拉取。

并发策略：每个请求开一个连接（SQLite 打开成本很低）并启用 WAL，
写操作放在 ``BEGIN IMMEDIATE`` 事务里，几个人用不会有锁竞争问题。
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# 单次拉取返回的最大条数，超过则让客户端再来一轮
PULL_PAGE_SIZE = 500

# 每个同步码允许保存的最大待办数，防止单个用户把小服务器写爆
MAX_TASKS_PER_USER = 5000

# 允许客户端时间戳比服务端超前的幅度。因为冲突用「后写覆盖」判定，
# 一条来自未来的时间戳会让这条待办再也无法被改回来，所以必须封顶。
MAX_CLOCK_SKEW_MS = 5 * 60 * 1000

# 单条 IN 查询里最多塞多少个参数，避开 SQLite 的变量数上限
_MAX_QUERY_VARIABLES = 500

# UPSERT 语法要求的最低 SQLite 版本
_MIN_SQLITE_VERSION = (3, 24, 0)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id      TEXT PRIMARY KEY,
    created_at   INTEGER NOT NULL,
    last_seen_at INTEGER NOT NULL,
    seq          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tasks (
    user_id           TEXT    NOT NULL,
    task_id           TEXT    NOT NULL,
    payload           TEXT    NOT NULL,
    updated_at        INTEGER NOT NULL,
    server_updated_at INTEGER NOT NULL DEFAULT 0,
    deleted           INTEGER NOT NULL DEFAULT 0,
    server_seq        INTEGER NOT NULL,
    PRIMARY KEY (user_id, task_id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_seq ON tasks (user_id, server_seq);
"""


def now_ms() -> int:
    """当前 UTC 时间的毫秒时间戳。"""
    return int(time.time() * 1000)


class SyncDatabase:
    """同步数据的读写入口。"""

    def __init__(self, path: Path) -> None:
        """
        Args:
            path: SQLite 文件路径；父目录不存在会自动创建。

        Raises:
            RuntimeError: 运行环境的 SQLite 太旧，不支持 UPSERT 语法。
        """
        if sqlite3.sqlite_version_info < _MIN_SQLITE_VERSION:
            required = ".".join(str(part) for part in _MIN_SQLITE_VERSION)
            raise RuntimeError(
                f"需要 SQLite >= {required}（当前 {sqlite3.sqlite_version}）"
            )
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.executescript(_SCHEMA)
            self._migrate(connection)
            connection.commit()
        logger.info("同步数据库就绪：%s", self._path)

    @property
    def path(self) -> Path:
        """数据库文件路径。"""
        return self._path

    def _connect(self) -> sqlite3.Connection:
        """开一个连接（WAL 模式，超时 5 秒）。"""
        connection = sqlite3.connect(str(self._path), timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def sync(
        self,
        user_id: str,
        since: int,
        changes: Iterable[dict[str, Any]],
    ) -> dict[str, Any]:
        """执行一次推拉合并。

        Args:
            user_id: 同步码。
            since: 客户端上次拿到的游标；0 表示全量拉取。
            changes: 客户端上传的待办（每条至少含 ``id`` / ``updated_at``）。

        Returns:
            ``{"cursor": int, "changes": [...], "accepted": [...], "rejected": [...],
            "refused": [...], "more": bool, "server_time": int}``

            ``rejected`` 与 ``refused`` 含义完全不同，客户端必须分开处理：
            前者表示「服务端已有同样或更新的版本」，这条推送可以就此作罢；
            后者表示「服务端根本没能存下」，客户端必须保留脏标记等下次重试。
        """
        accepted: list[str] = []
        rejected: list[str] = []
        refused: list[str] = []
        moment = now_ms()
        ceiling = moment + MAX_CLOCK_SKEW_MS
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._touch_user(connection, user_id)
            stored_count = self._count_tasks(connection, user_id)

            for item in changes:
                task_id = str(item.get("id") or "").strip()
                if not task_id:
                    continue
                # 时钟不准的设备（电池耗尽、手动改过日期）会带来「来自未来」的时间戳，
                # 而后写覆盖会让这种记录永远无法被任何设备改回来，所以按服务端时钟封顶
                incoming_at = min(_as_int(item.get("updated_at")), ceiling)
                current = connection.execute(
                    "SELECT updated_at FROM tasks WHERE user_id=? AND task_id=?",
                    (user_id, task_id),
                ).fetchone()

                # 后写覆盖：时间戳不比服务端新就忽略。平局判服务端赢，客户端侧
                # 用 >= 接受远端版本与这里保持一致，否则两边会各执己见永久分叉。
                # 这条会被强制回发，保证客户端一定拿到服务端的权威版本
                if current is not None and incoming_at <= int(current["updated_at"]):
                    rejected.append(task_id)
                    continue
                if current is None and stored_count >= MAX_TASKS_PER_USER:
                    logger.warning("同步码 %s 待办数超过上限，拒绝新增", user_id)
                    refused.append(task_id)
                    continue

                # 封顶后的时间戳要写回报文里再存：其他客户端是从 payload 读
                # updated_at 的，只改索引列的话它们拿到的还是那个未来时间戳
                if _as_int(item.get("updated_at")) != incoming_at:
                    item = dict(item, updated_at=incoming_at)

                sequence = self._next_seq(connection, user_id)
                connection.execute(
                    "INSERT INTO tasks"
                    " (user_id, task_id, payload, updated_at, server_updated_at,"
                    "  deleted, server_seq)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(user_id, task_id) DO UPDATE SET"
                    " payload=excluded.payload, updated_at=excluded.updated_at,"
                    " server_updated_at=excluded.server_updated_at,"
                    " deleted=excluded.deleted, server_seq=excluded.server_seq",
                    (
                        user_id,
                        task_id,
                        json.dumps(item, ensure_ascii=False),
                        incoming_at,
                        moment,
                        1 if item.get("deleted") else 0,
                        sequence,
                    ),
                )
                if current is None:
                    stored_count += 1
                accepted.append(task_id)

            rows = connection.execute(
                "SELECT task_id, payload, server_seq FROM tasks"
                " WHERE user_id=? AND server_seq > ?"
                " ORDER BY server_seq LIMIT ?",
                (user_id, since, PULL_PAGE_SIZE),
            ).fetchall()
            # 游标只看增量查询的结果，强制回发的记录序号可能远小于 since，
            # 混进来会让游标倒退、下次重复拉取
            cursor = int(rows[-1]["server_seq"]) if rows else since
            already = {row["task_id"] for row in rows}
            forced = self._fetch_by_ids(
                connection,
                user_id,
                [task_id for task_id in rejected if task_id not in already],
            )
            connection.commit()

        pulled = []
        for row in list(rows) + forced:
            try:
                pulled.append(json.loads(row["payload"]))
            except json.JSONDecodeError:
                logger.error("跳过损坏的待办记录：user=%s seq=%s", user_id, row["server_seq"])

        return {
            "cursor": cursor,
            "changes": pulled,
            "accepted": accepted,
            "rejected": rejected,
            "refused": refused,
            "more": len(rows) >= PULL_PAGE_SIZE,
            "server_time": now_ms(),
        }

    def stats(self) -> dict[str, Any]:
        """服务端概况，用于 ``/api/health``。"""
        with self._connect() as connection:
            users = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
            tasks = connection.execute("SELECT COUNT(*) AS n FROM tasks").fetchone()["n"]
        size_bytes = self._path.stat().st_size if self._path.is_file() else 0
        return {"users": users, "tasks": tasks, "db_bytes": size_bytes}

    def purge_tombstones(self, older_than_ms: int) -> int:
        """清理过期的删除墓碑，返回清理条数。

        墓碑要留足够久，保证长期离线的设备回来后仍能收到「这条已删除」；
        超过保留期后就没必要再占空间了。

        Args:
            older_than_ms: 早于该时间戳的墓碑会被物理删除。
        """
        with self._connect() as connection:
            # 按服务端写入时间而不是客户端时间戳判断，否则一台时钟错乱的设备
            # 就能让自己的墓碑立刻被清掉，删除便再也传不到其他设备
            cursor = connection.execute(
                "DELETE FROM tasks WHERE deleted=1 AND server_updated_at < ?",
                (older_than_ms,),
            )
            connection.commit()
            return cursor.rowcount

    # ------------------------------------------------------------------ 内部
    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        """把老版本建的库补齐到当前表结构。"""
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(tasks)")}
        if "server_updated_at" not in columns:
            connection.execute(
                "ALTER TABLE tasks ADD COLUMN server_updated_at INTEGER NOT NULL DEFAULT 0"
            )
            # 老数据没有服务端写入时间，先用客户端时间戳兜底，
            # 否则它们会被下一次清理当成「远古墓碑」全部删掉
            connection.execute("UPDATE tasks SET server_updated_at = updated_at")
            logger.info("已为 tasks 表补充 server_updated_at 列")

    @staticmethod
    def _fetch_by_ids(
        connection: sqlite3.Connection,
        user_id: str,
        task_ids: list[str],
    ) -> list[sqlite3.Row]:
        """按 ID 取出若干条记录，用于把权威版本强制回发给客户端。"""
        rows: list[sqlite3.Row] = []
        for start in range(0, len(task_ids), _MAX_QUERY_VARIABLES):
            chunk = task_ids[start : start + _MAX_QUERY_VARIABLES]
            placeholders = ",".join("?" * len(chunk))
            rows.extend(
                connection.execute(
                    "SELECT task_id, payload, server_seq FROM tasks"
                    f" WHERE user_id=? AND task_id IN ({placeholders})",
                    (user_id, *chunk),
                ).fetchall()
            )
        return rows

    @staticmethod
    def _touch_user(connection: sqlite3.Connection, user_id: str) -> None:
        """记录同步码的首次出现与最近活跃时间。"""
        moment = now_ms()
        connection.execute(
            "INSERT INTO users (user_id, created_at, last_seen_at, seq)"
            " VALUES (?, ?, ?, 0)"
            " ON CONFLICT(user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at",
            (user_id, moment, moment),
        )

    @staticmethod
    def _next_seq(connection: sqlite3.Connection, user_id: str) -> int:
        """取该用户的下一个写入序号。"""
        connection.execute(
            "UPDATE users SET seq = seq + 1 WHERE user_id=?",
            (user_id,),
        )
        row = connection.execute(
            "SELECT seq FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        return int(row["seq"])

    @staticmethod
    def _count_tasks(connection: sqlite3.Connection, user_id: str) -> int:
        """该用户已存的待办数。"""
        row = connection.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE user_id=?", (user_id,)
        ).fetchone()
        return int(row["n"])


def _as_int(value: Any, fallback: int = 0) -> int:
    """尽力把值转成 int。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback
