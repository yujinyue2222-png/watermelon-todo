"""批量粘贴文本的解析。

每行一条待办，用竖线（``|`` 或 ``｜``）或 Tab 分列：

    内容 | 优先级 | 日期 | 备注

后三列都可省略。第 2 列如果不是优先级词就当作备注；第 3 列日期无法识别时
同样并入备注。用 Tab 分列是为了支持直接从 Excel 复制粘贴。
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Optional

from backend.models.enums import Priority

# 行首的列表符号：- * • · 以及 1. / 1、 / (1) 这类编号
_BULLET_PATTERN = re.compile(r"^\s*(?:[-*•·]|\(?\d+[\.\)、])\s*")

# 「(下)周三」「星期五」「礼拜天」
_WEEKDAY_PATTERN = re.compile(r"^(下)?(?:周|星期|礼拜)([一二三四五六日天])$")
_FULL_DATE_PATTERN = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$")
_SHORT_DATE_PATTERN = re.compile(r"^(\d{1,2})[-/](\d{1,2})$")

_RELATIVE_DAYS = {
    "今天": 0,
    "今日": 0,
    "明天": 1,
    "明日": 1,
    "后天": 2,
    "大后天": 3,
}
_WEEKDAY_INDEX = {
    "一": 0,
    "二": 1,
    "三": 2,
    "四": 3,
    "五": 4,
    "六": 5,
    "日": 6,
    "天": 6,
}

_COLUMN_SEPARATOR = "|"


@dataclass
class ParsedTaskLine:
    """一行文本解析出的待办要素。"""

    text: str
    priority: str = ""
    due: str = ""
    note: str = ""


def strip_bullet(text: str) -> str:
    """去掉行首的列表符号或编号。"""
    return _BULLET_PATTERN.sub("", text or "").strip()


def normalize_date_token(token: str, today: Optional[datetime.date] = None) -> str:
    """把日期片段归一化成 ``YYYY-MM-DD``。

    支持 ``2026-08-05`` / ``08-05`` / ``08/05`` / ``今天`` / ``明天`` /
    ``后天`` / ``周五`` / ``下周一`` 等写法。

    Args:
        token: 待识别的片段。
        today: 相对日期的基准日，便于测试注入。

    Returns:
        归一化后的日期字符串；无法识别时返回空串。
    """
    text = (token or "").strip()
    if not text:
        return ""
    base = today or datetime.date.today()

    if text in _RELATIVE_DAYS:
        return (base + datetime.timedelta(days=_RELATIVE_DAYS[text])).isoformat()

    weekday_match = _WEEKDAY_PATTERN.match(text)
    if weekday_match:
        target = _WEEKDAY_INDEX[weekday_match.group(2)]
        if weekday_match.group(1):
            # 「下周X」= 下一个自然周（周一起算）的第 X 天。
            # 不能在下面那个取模结果上再加 7：取模已经滚进下周了，
            # 对早于今天的星期几会一路跳到两周以后
            delta = (7 - base.weekday()) + target
        else:
            delta = (target - base.weekday()) % 7
        return (base + datetime.timedelta(days=delta)).isoformat()

    full_match = _FULL_DATE_PATTERN.match(text)
    if full_match:
        return _safe_date(
            int(full_match.group(1)),
            int(full_match.group(2)),
            int(full_match.group(3)),
        )

    short_match = _SHORT_DATE_PATTERN.match(text)
    if short_match:
        return _safe_date(base.year, int(short_match.group(1)), int(short_match.group(2)))

    return ""


def parse_line(raw: str, today: Optional[datetime.date] = None) -> Optional[ParsedTaskLine]:
    """解析一行文本。

    Args:
        raw: 原始行。
        today: 相对日期的基准日。

    Returns:
        解析结果；空行或只有分隔符的行返回 None。
    """
    cleaned = strip_bullet(raw)
    if not cleaned:
        return None

    normalized = cleaned.replace("｜", _COLUMN_SEPARATOR).replace("\t", _COLUMN_SEPARATOR)
    columns = [part.strip() for part in normalized.split(_COLUMN_SEPARATOR)]
    text = columns[0]
    if not text:
        return None

    rest = columns[1:]
    priority = ""
    due = ""

    if rest:
        # 先过一遍旧值映射，否则从 v2 复制出来的「紧急」既认不出优先级，
        # 又会因为没被消费掉而把后面的日期列一起挤掉
        candidate = Priority.LEGACY_MAP.get(rest[0], rest[0])
        if candidate in Priority.ORDER:
            priority = candidate
            rest = rest[1:]

    if rest:
        recognized = normalize_date_token(rest[0], today)
        if recognized:
            due = recognized
            rest = rest[1:]

    note = " ".join(part for part in rest if part).strip()
    return ParsedTaskLine(text=text, priority=priority, due=due, note=note)


def parse_batch_text(
    text: str,
    today: Optional[datetime.date] = None,
) -> list[ParsedTaskLine]:
    """解析多行文本，自动跳过空行。

    Args:
        text: 多行原始文本。
        today: 相对日期的基准日。

    Returns:
        逐行解析出的待办要素列表。
    """
    results = []
    for line in (text or "").splitlines():
        parsed = parse_line(line, today)
        if parsed is not None:
            results.append(parsed)
    return results


def _safe_date(year: int, month: int, day: int) -> str:
    """构造日期字符串，非法日期返回空串。"""
    try:
        return datetime.date(year, month, day).isoformat()
    except ValueError:
        return ""
