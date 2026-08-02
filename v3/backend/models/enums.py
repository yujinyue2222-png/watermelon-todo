"""业务取值集合。

这里刻意使用「字符串常量 + 命名空间类」而不是 :mod:`enum`：
待办数据以 JSON 明文保存，直接存中文字面量能让数据文件保持可读、
可手工编辑，并与 v1/v2 的历史数据完全兼容。
"""

from typing import Optional


class TaskStatus:
    """任务状态。"""

    TODO = "todo"
    DOING = "doing"
    DONE = "done"

    ORDER = (TODO, DOING, DONE)
    # 列表排序时的次级权重（未开始 → 进行中 → 已完成）
    RANK = {TODO: 0, DOING: 1, DONE: 2}


class Priority:
    """紧急程度：P0/P1/P2 为紧急档，其后是重要与普通。"""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    IMPORTANT = "重要"
    NORMAL = "普通"

    DEFAULT = NORMAL
    ORDER = (P0, P1, P2, IMPORTANT, NORMAL)
    RANK = {P0: 0, P1: 1, P2: 2, IMPORTANT: 3, NORMAL: 4}
    # 统计「今日紧急」时计入的档位
    URGENT = (P0, P1, P2)
    # 旧数据迁移：v1 的「紧急」并入 P1
    LEGACY_MAP = {"紧急": P1}


class Recurrence:
    """循环周期。"""

    NONE = "不循环"
    DAILY = "每日"
    WORKDAY = "工作日"
    WEEKLY = "每周"
    MONTHLY = "每月"
    YEARLY = "每年"

    DEFAULT = NONE
    ORDER = (NONE, DAILY, WORKDAY, WEEKLY, MONTHLY, YEARLY)

    @classmethod
    def is_repeating(cls, value: str) -> bool:
        """是否为有效的循环周期（``不循环``与非法值都返回 False）。"""
        return value in cls.ORDER and value != cls.NONE


class Remind:
    """普通提醒档位。

    ``LEAD_MINUTES`` 是「提前多少分钟提醒」：None 表示关闭，0 表示到期当刻。
    分钟级提醒需要截止时间带具体时间点才精确；只填日期时按当天 23:59 推算。
    """

    OFF = "关闭提醒"
    ON_TIME = "到期当天"
    BEFORE_10_MIN = "结束前10分钟"
    BEFORE_30_MIN = "结束前30分钟"
    BEFORE_2_HOUR = "结束前2小时"
    BEFORE_1_DAY = "提前1天"
    BEFORE_3_DAY = "提前3天"

    DEFAULT = ON_TIME
    LEAD_MINUTES = {
        OFF: None,
        ON_TIME: 0,
        BEFORE_10_MIN: 10,
        BEFORE_30_MIN: 30,
        BEFORE_2_HOUR: 120,
        BEFORE_1_DAY: 1440,
        BEFORE_3_DAY: 4320,
    }
    ORDER = tuple(LEAD_MINUTES.keys())

    @classmethod
    def lead_minutes(cls, value: str) -> Optional[int]:
        """取提前分钟数；未知取值按默认档处理。"""
        return cls.LEAD_MINUTES.get(value, cls.LEAD_MINUTES[cls.DEFAULT])


class StrongUnit:
    """强提醒的时间单位。"""

    DAY = "天"
    HOUR = "小时"
    MINUTE = "分钟"

    ORDER = (DAY, HOUR, MINUTE)
    SECONDS = {DAY: 86_400, HOUR: 3_600, MINUTE: 60}
    # 强提醒最短间隔，防止刷屏
    MIN_INTERVAL_SECONDS = 60

    @classmethod
    def to_seconds(cls, value: int, unit: str) -> int:
        """把「数值 + 单位」换算成秒，并做最小值保护。"""
        try:
            seconds = int(value) * cls.SECONDS.get(unit, cls.SECONDS[cls.HOUR])
        except (TypeError, ValueError):
            seconds = cls.SECONDS[cls.HOUR]
        return max(cls.MIN_INTERVAL_SECONDS, seconds)


class ViewMode:
    """主界面的两个并列视图。"""

    DAILY = "daily"
    PROJECT = "project"


# 分类筛选栏里代表「不过滤」的伪分类
CATEGORY_ALL = "全部"
