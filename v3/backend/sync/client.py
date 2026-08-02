"""同步服务的 HTTP 客户端。

只用标准库 ``urllib``，不引入 requests——桌面端要打包分发，少一个依赖少一份体积。
所有网络异常都归一成 :class:`SyncError`，并带上一句人能看懂的中文原因，
方便直接显示在界面上。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.core.constants import (
    APP_VERSION,
    HEALTH_API_PATH,
    SYNC_API_PATH,
    SYNC_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_USER_AGENT = f"watermelon-todo/{APP_VERSION}"
_JSON_CONTENT_TYPE = "application/json; charset=utf-8"


class SyncError(Exception):
    """同步失败（网络不通、服务端报错、返回内容非法等）。"""


class SyncClient:
    """与同步服务通信。"""

    def __init__(
        self,
        server_url: str,
        access_token: str = "",
        timeout: int = SYNC_TIMEOUT_SECONDS,
    ) -> None:
        """
        Args:
            server_url: 服务地址，例如 ``http://47.120.58.231:52121``。
            access_token: 服务端开启了令牌校验时填写。
            timeout: 单次请求超时秒数。
        """
        self._base_url = (server_url or "").strip().rstrip("/") + "/"
        self._access_token = (access_token or "").strip()
        self._timeout = timeout

    @property
    def server_url(self) -> str:
        """规范化后的服务地址。"""
        return self._base_url.rstrip("/")

    def health(self) -> dict[str, Any]:
        """探测服务是否可用。

        Returns:
            服务端概况。

        Raises:
            SyncError: 连不上或返回异常。
        """
        return self._request(HEALTH_API_PATH, payload=None)

    def sync(
        self,
        user_id: str,
        since: int,
        changes: Sequence[dict[str, Any]],
    ) -> dict[str, Any]:
        """一次往返完成推送与拉取。

        Args:
            user_id: 同步码。
            since: 本地游标。
            changes: 待上传的待办（已转成字典）。

        Returns:
            服务端响应，含 ``cursor`` / ``changes`` / ``accepted`` / ``more``。

        Raises:
            SyncError: 网络失败或响应非法。
        """
        payload = {"user_id": user_id, "since": since, "changes": list(changes)}
        return self._request(SYNC_API_PATH, payload=payload)

    # ------------------------------------------------------------------ 内部
    def _request(
        self,
        path: str,
        payload: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        """发一次请求并解析 JSON 响应。"""
        if not self._base_url.strip("/"):
            raise SyncError("没有填写同步服务器地址")

        url = urljoin(self._base_url, path.lstrip("/"))
        headers = {"User-Agent": _USER_AGENT, "Accept": _JSON_CONTENT_TYPE}
        body = None
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = _JSON_CONTENT_TYPE
        if self._access_token:
            headers["X-Access-Token"] = self._access_token

        try:
            # Request() 也要放进来：服务器地址是用户手填的，缺少 http:// 前缀时
            # 它抛的是 ValueError，漏在外面会直接打死调用方所在的后台线程
            request = Request(url, data=body, headers=headers, method="POST" if body else "GET")
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raise SyncError(self._describe_http_error(exc)) from exc
        except URLError as exc:
            raise SyncError(f"连不上同步服务器：{exc.reason}") from exc
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            raise SyncError(f"同步请求失败：{exc}") from exc

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SyncError("服务端返回的不是合法 JSON") from exc
        if not isinstance(parsed, dict):
            raise SyncError("服务端返回格式异常")
        return parsed

    @staticmethod
    def _describe_http_error(error: HTTPError) -> str:
        """把 HTTP 错误翻译成可读提示。"""
        if error.code == 401:
            return "访问令牌不正确"
        if error.code == 413:
            return "本地数据太大，服务端拒收"
        detail = ""
        try:
            payload = json.loads(error.read().decode("utf-8"))
            detail = str(payload.get("detail") or payload.get("error") or "")
        except (OSError, UnicodeDecodeError, json.JSONDecodeError, AttributeError):
            detail = ""
        suffix = f"：{detail}" if detail else ""
        return f"服务端返回 {error.code}{suffix}"
