"""截止时间的解析、展示与排序。

``due`` 字段统一用字符串保存，兼容两种格式：

- ``"YYYY-MM-DD"``：只到日，逻辑上按当天 23:59 处理；
- ``"YYYY-MM-DD HH:MM"``：精确到分钟。

之所以不直接存 ``datetime``，是为了让 JSON 文件保持可读、可手工编辑，
并与 v1/v2 的历史数据完全兼容。
"""

import calendar
import datetime
from typing import Optional

DATE_FORMAT = "%Y-%m-%d"
DATETIME_FORMAT = "%Y-%m-%d %H:%M"

# 没有指定时间点时，视为当天的这个时刻到期
DEFAULT_DUE_TIME = datetime.time(23, 59)

# 循环周期：与 backend.models.enums.Recurrence 的取值保持一致
_WEEKEND_START = 5  # date.weekday() >= 5 即周六、周日


def parse_due(due: str) -> tuple[Optional[datetime.date], Optional[datetime.time]]:
    """把 ``due`` 字符串拆成 (日期, 时间)。

    Args:
        due: 截止时间字符串，可为空。

    Returns:
        ``(date, time)``；只有日期时 time 为 None；解析失败返回 ``(None, None)``。
    """
    text = (due or "").strip()
    if not text:
        return None, None
    for fmt, has_time in ((DATETIME_FORMAT, True), (DATE_FORMAT, False)):
        try:
            parsed = datetime.datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.date(), (parsed.time() if has_time else None)
    return None, None


def due_datetime(due: str) -> Optional[datetime.datetime]:
    """把 ``due`` 解析为 datetime；没有时间点时按当天 23:59 计。"""
    day, moment = parse_due(due)
    if day is None:
        return None
    return datetime.datetime.combine(day, moment or DEFAULT_DUE_TIME)


def format_due(due: str) -> str:
    """把 ``due`` 格式化成简短展示文本，例如 ``08-05 18:00``。"""
    day, moment = parse_due(due)
    if day is None:
        return (due or "").strip()
    text = day.strftime("%m-%d")
    if moment is not None:
        text += moment.strftime(" %H:%M")
    return text


def due_label(due: str, now: Optional[datetime.datetime] = None) -> tuple[str, bool]:
    """生成任务卡片上的截止时间标签。

    Args:
        due: 截止时间字符串。
        now: 参照当前时间，便于测试注入。

    Returns:
        ``(展示文本, 是否紧急)``；紧急表示已过期或就在最近两天内。
    """
    if not (due or "").strip():
        return "", False
    day, moment = parse_due(due)
    if day is None:
        return due.strip(), False

    current = now or datetime.datetime.now()
    suffix = moment.strftime(" %H:%M") if moment else ""
    delta_days = (day - current.date()).days

    if delta_days < 0:
        return f"已过期 {-delta_days} 天", True
    if delta_days == 0:
        if moment is not None and datetime.datetime.combine(day, moment) < current:
            return f"今天{suffix} 已过", True
        return f"今天{suffix}", True
    if delta_days == 1:
        return f"明天{suffix}", True
    if delta_days <= 7:
        return f"{delta_days} 天后{suffix}", False
    return day.strftime("%m-%d") + suffix, False


def due_sort_key(due: str) -> datetime.datetime:
    """排序用的截止时间。

    没填截止时间的任务视为「今天要做」（今天 23:59），而不是排到最后，
    这样它与填了远期日期的任务在同一优先级下能按紧急程度自然排序。
    """
    parsed = due_datetime(due)
    if parsed is None:
        return datetime.datetime.combine(datetime.date.today(), DEFAULT_DUE_TIME)
    return parsed


def advance_date(
    base: datetime.date,
    recurrence: str,
    anchor_day: Optional[int] = None,
) -> Optional[datetime.date]:
    """按循环周期推算下一次的日期。

    Args:
        base: 基准日期，通常是上一期的截止日。
        recurrence: 循环类型，见 :class:`backend.models.enums.Recurrence`。
        anchor_day: 循环最初锚定的「几号」。每月/每年循环必须传，否则遇到短月
            会被永久带偏：1 月 31 日推出 2 月 28 日后，再以 28 日为基准推算，
            后面每一期就都固定在 28 日了。传了它就能推回 3 月 31 日。

    Returns:
        下一次日期；``recurrence`` 不是循环类型时返回 None。
    """
    if recurrence == "每日":
        return base + datetime.timedelta(days=1)
    if recurrence == "工作日":
        following = base + datetime.timedelta(days=1)
        while following.weekday() >= _WEEKEND_START:
            following += datetime.timedelta(days=1)
        return following
    if recurrence == "每周":
        return base + datetime.timedelta(days=7)
    if recurrence == "每月":
        month = base.month + 1
        year = base.year + (month - 1) // 12
        month = (month - 1) % 12 + 1
        return _clamp_to_month(year, month, anchor_day or base.day)
    if recurrence == "每年":
        return _clamp_to_month(base.year + 1, base.month, anchor_day or base.day)
    return None


def _clamp_to_month(year: int, month: int, day: int) -> datetime.date:
    """取该年月的第 ``day`` 天；该月没有这一天时取月末。"""
    return datetime.date(year, month, min(day, calendar.monthrange(year, month)[1]))


def combine_due(day: datetime.date, moment: Optional[datetime.time]) -> str:
    """把日期与可选时间点拼回 ``due`` 字符串。"""
    text = day.strftime(DATE_FORMAT)
    if moment is not None:
        text += moment.strftime(" %H:%M")
    return text
