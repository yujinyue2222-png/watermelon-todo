"""检查新版本。

只做一次 HTTPS GET 拿 GitHub 最新 Release 信息。网络不通、超时、仓库还没发布过
版本等情况一律**静默**返回 None——检查更新失败不该打扰用户。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

from backend.core.constants import (
    APP_VERSION,
    RELEASE_PAGE,
    UPDATE_API,
    UPDATE_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)

_USER_AGENT = "watermelon-todo-updater"
_NOTES_LIMIT = 300

# 版本号每一段开头的连续 ASCII 数字
_LEADING_DIGITS = re.compile(r"^(\d+)")


@dataclass
class ReleaseInfo:
    """一个可下载的新版本。"""

    version: str
    notes: str = ""
    page_url: str = RELEASE_PAGE

    def short_notes(self, limit: int = _NOTES_LIMIT) -> str:
        """截断后的更新说明，避免弹窗被超长文本撑爆。"""
        if len(self.notes) <= limit:
            return self.notes
        return self.notes[:limit] + "…"


def parse_version(text: str) -> tuple[int, ...]:
    """把 ``v2.3`` / ``2.3.1`` 解析成可比较的数字元组。

    只取每段开头的连续数字，后面的预发布后缀一律忽略：
    ``v3.7`` / ``v3.7-beta`` / ``v3.7-rc1`` 都是 ``(3, 7)``。
    非数字片段按 0 处理。
    """
    numbers = []
    for part in str(text).lstrip("vV").split("."):
        # 不能把整段里的数字全拼起来：那样 "7-rc1" 会变成 71，
        # 一个预发布版会被判成比正式版还新
        match = _LEADING_DIGITS.match(part.strip())
        numbers.append(int(match.group(1)) if match else 0)
    return tuple(numbers) if numbers else (0,)


class UpdateService:
    """版本检查服务。"""

    def __init__(
        self,
        api_url: str = UPDATE_API,
        current_version: str = APP_VERSION,
        timeout: int = UPDATE_TIMEOUT_SECONDS,
    ) -> None:
        """
        Args:
            api_url: Release 接口地址。
            current_version: 当前版本号。
            timeout: 请求超时秒数。
        """
        self._api_url = api_url
        self._current_version = current_version
        self._timeout = timeout

    @property
    def current_version(self) -> str:
        """当前版本号。"""
        return self._current_version

    def check(self) -> Optional[ReleaseInfo]:
        """查询是否有更新。

        Returns:
            比当前版本更新的 Release；已是最新或查询失败返回 None。
        """
        payload = self._fetch()
        if payload is None:
            return None
        latest = str(payload.get("tag_name") or "").strip()
        if not latest:
            return None
        if parse_version(latest) <= parse_version(self._current_version):
            logger.debug("已是最新版本：%s", self._current_version)
            return None
        notes = str(payload.get("body") or "").strip()
        logger.info("发现新版本：%s（当前 %s）", latest, self._current_version)
        return ReleaseInfo(version=latest, notes=notes)

    def _fetch(self) -> Optional[dict]:
        """请求 Release 接口，失败返回 None。"""
        request = Request(
            self._api_url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": _USER_AGENT,
            },
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                # errors="replace"：门户认证页之类的非 UTF-8 响应不该抛异常，
                # 反正下面 JSON 解析失败一样会静默返回 None
                raw = response.read().decode("utf-8", errors="replace")
        except (URLError, OSError, ValueError) as exc:
            logger.debug("检查更新失败（忽略）：%s", exc)
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.debug("检查更新返回内容非 JSON：%s", exc)
            return None
        return payload if isinstance(payload, dict) else None
