"""同步服务的 HTTP 层。

路由：

===========================  ==================================================
``GET  /api/health``          健康检查与概况
``POST /api/sync``            一次往返完成推送 + 拉取
``OPTIONS /api/*``            CORS 预检（便于把网页部署到别处）
``GET  /`` 及其他路径          可选的静态网页（手机端 PWA）
===========================  ==================================================

鉴权按「同步码即身份」处理：谁知道同步码就能读写该码下的数据，因此客户端默认
生成一串足够长的随机码。若想再加一道门，可设置环境变量
``WATERMELON_ACCESS_TOKEN``，届时所有 ``/api`` 请求都必须带
``X-Access-Token`` 头（网页端会把它存在本地）。
"""

from __future__ import annotations

import hmac
import json
import logging
import mimetypes
import re
import socket
import sqlite3
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote

from server import SERVER_VERSION
from server.database import SyncDatabase, now_ms

logger = logging.getLogger(__name__)

# 请求体上限 4MB：一次全量上传几千条待办也够了
MAX_BODY_BYTES = 4 * 1024 * 1024

# 同时在处理的连接数上限。ThreadingHTTPServer 默认来者不拒，而每个连接都可能
# 缓冲一整个请求体，不封顶的话几十个并发请求就能顶穿 systemd 单元里的 MemoryMax，
# 触发 OOM + 自动重启的死循环
MAX_CONCURRENT_REQUESTS = 32

# 单个连接的空闲超时（秒）。开了 keep-alive，不设超时的话空闲连接会一直占着名额
CONNECTION_TIMEOUT_SECONDS = 30

# 同步码允许的字符与长度，顺手挡掉畸形输入
_USER_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")

_JSON_CONTENT_TYPE = "application/json; charset=utf-8"
_INDEX_FILE = "index.html"
# 网页文件不缓存，避免用户拿到旧版界面
_NO_STORE = "no-store, must-revalidate"


class SyncRequestHandler(BaseHTTPRequestHandler):
    """处理同步请求与静态网页。"""

    server_version = f"WatermelonSync/{SERVER_VERSION}"
    protocol_version = "HTTP/1.1"
    timeout = CONNECTION_TIMEOUT_SECONDS

    # 由 create_server 注入
    database: SyncDatabase
    web_root: Optional[Path] = None
    access_token: Optional[str] = None

    # -------------------------------------------------------------- 路由入口
    def do_GET(self) -> None:  # noqa: N802 (BaseHTTPRequestHandler 命名)
        """处理 GET：健康检查或静态文件。"""
        path = self._clean_path()
        # 令牌校验要放在路由之前：健康检查会暴露用户数、待办数与库大小，
        # 配置了令牌就不该让匿名调用者读到
        if path.startswith("/api/") and not self._check_access_token():
            return
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, self._health_payload())
            return
        if path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
            return
        self._serve_static(path)

    def do_HEAD(self) -> None:  # noqa: N802
        """HEAD 与 GET 同路由，只是不发送正文。"""
        self.do_GET()

    def do_POST(self) -> None:  # noqa: N802
        """处理 POST：目前只有 ``/api/sync``。"""
        path = self._clean_path()
        if path != "/api/sync":
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "unknown endpoint"})
            return
        if not self._check_access_token():
            return

        payload = self._read_json_body()
        if payload is None:
            return

        user_id = str(payload.get("user_id") or "").strip()
        if not _USER_ID_PATTERN.match(user_id):
            self._send_json(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid user_id", "detail": "同步码需为 6-64 位字母/数字/-/_"},
            )
            return

        changes = payload.get("changes")
        if changes is None:
            changes = []
        if not isinstance(changes, list):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "changes must be a list"})
            return

        since = payload.get("since", 0)
        try:
            since = max(0, int(since))
        except (TypeError, ValueError):
            since = 0

        valid_changes = [item for item in changes if isinstance(item, dict)]
        try:
            result = self.database.sync(user_id, since, valid_changes)
        except sqlite3.Error as exc:
            # 不能让异常穿透到 socketserver：那样连接会被直接掐断而不回任何响应，
            # 客户端只能显示成「连不上服务器」，完全看不出是服务端故障
            logger.exception("同步失败：%s", exc)
            self._send_json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "database unavailable", "detail": "服务端繁忙，请稍后重试"},
            )
            return
        logger.info(
            "同步 user=%s 上传=%d 接受=%d 下发=%d 游标=%d",
            user_id,
            len(valid_changes),
            len(result["accepted"]),
            len(result["changes"]),
            result["cursor"],
        )
        self._send_json(HTTPStatus.OK, result)

    def do_OPTIONS(self) -> None:  # noqa: N802
        """CORS 预检。"""
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # -------------------------------------------------------------- 静态网页
    def _serve_static(self, path: str) -> None:
        """发送网页文件。

        手机端 PWA 由同一个服务托管，页面与接口同源，
        既没有混合内容限制也不需要 CORS。
        """
        if self.web_root is None:
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": "web ui not enabled", "hint": "启动时加 --web <目录> 可托管网页"},
            )
            return

        # 先解码百分号转义，否则带空格或中文的文件名会取不到，
        # 而且 %2e%2e%2f 这类编码过的穿越串会绕过下面的检查
        relative = unquote(path).lstrip("/") or _INDEX_FILE
        target = (self.web_root / relative).resolve()
        # 防目录穿越：必须按路径层级判断。用字符串前缀比较的话，
        # web_root 为 /opt/app/web 时 /opt/app/web-secret/x 会被误放行
        try:
            target.relative_to(self.web_root)
        except ValueError:
            logger.warning("拒绝越界的静态文件请求：%s", self.path)
            self._send_json(HTTPStatus.FORBIDDEN, {"error": "forbidden"})
            return
        if target.is_dir():
            target = target / _INDEX_FILE
        if not target.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return

        try:
            body = target.read_bytes()
        except OSError as exc:
            logger.error("读取网页文件失败 %s：%s", target, exc)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "read failed"})
            return

        content_type, _ = mimetypes.guess_type(str(target))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", _NO_STORE)
        self._send_cors_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    # ------------------------------------------------------------------ 工具
    def _clean_path(self) -> str:
        """去掉查询串后的请求路径。"""
        return self.path.split("?", 1)[0].split("#", 1)[0]

    def _health_payload(self) -> dict[str, Any]:
        """健康检查响应体。"""
        payload = {
            "ok": True,
            "service": "watermelon-todo-sync",
            "version": SERVER_VERSION,
            "server_time": now_ms(),
            "web_ui": self.web_root is not None,
            "auth_required": bool(self.access_token),
        }
        payload.update(self.database.stats())
        return payload

    def _check_access_token(self) -> bool:
        """校验可选的访问令牌。"""
        if not self.access_token:
            return True
        provided = self.headers.get("X-Access-Token", "")
        # 常量时间比较：普通 == 会在第一个不同字节处短路，配合无限次重试
        # 可以按前缀逐字节把令牌试出来。
        # 先编码成 bytes：compare_digest 对含非 ASCII 的 str 会直接抛 TypeError
        if hmac.compare_digest(
            provided.encode("utf-8", "surrogatepass"),
            self.access_token.encode("utf-8", "surrogatepass"),
        ):
            return True
        self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "invalid access token"})
        return False

    def _read_json_body(self) -> Optional[dict[str, Any]]:
        """读取并解析 JSON 请求体；失败时已自行回复错误。"""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "empty body"})
            return None
        if length > MAX_BODY_BYTES:
            self._send_json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                {"error": "body too large", "limit": MAX_BODY_BYTES},
            )
            return None

        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"invalid json: {exc}"})
            return None
        if not isinstance(payload, dict):
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": "body must be an object"})
            return None
        return payload

    def _send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        """发送 JSON 响应。"""
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", _JSON_CONTENT_TYPE)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", _NO_STORE)
        self._send_cors_headers()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_cors_headers(self) -> None:
        """允许跨域，方便把网页部署到 Pages 等其他地方。"""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Access-Token")
        self.send_header("Access-Control-Max-Age", "86400")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        """把 http.server 的访问日志接到 logging。"""
        logger.debug("%s - %s", self.address_string(), format % args)


class BoundedThreadingHTTPServer(ThreadingHTTPServer):
    """并发连接数有上限的 HTTP 服务。

    超出上限的连接不会被拒绝，只是排队等待空出名额，
    这样内存占用有个可预期的天花板。
    """

    daemon_threads = True

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)

    def process_request(self, request: socket.socket, client_address: Any) -> None:
        """占一个名额再交给工作线程。"""
        self._slots.acquire()
        try:
            super().process_request(request, client_address)
        except BaseException:
            # 线程没起来就得把名额还回去，否则会一路漏到无名额可用
            self._slots.release()
            raise

    def shutdown_request(self, request: socket.socket) -> None:
        """连接收尾时归还名额（工作线程在 finally 里一定会走到这）。"""
        try:
            super().shutdown_request(request)
        finally:
            self._slots.release()


def create_server(
    host: str,
    port: int,
    database: SyncDatabase,
    web_root: Optional[Path] = None,
    access_token: Optional[str] = None,
) -> ThreadingHTTPServer:
    """创建（但不启动）HTTP 服务。

    Args:
        host: 监听地址；对外服务用 ``0.0.0.0``。
        port: 监听端口。
        database: 同步数据库。
        web_root: 静态网页目录；为 None 时只提供 API。
        access_token: 可选的访问令牌。

    Returns:
        已绑定端口的服务对象，调用方负责 ``serve_forever()``。
    """
    handler = type(
        "BoundSyncRequestHandler",
        (SyncRequestHandler,),
        {
            "database": database,
            "web_root": web_root.resolve() if web_root else None,
            "access_token": access_token,
        },
    )
    server = BoundedThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server
