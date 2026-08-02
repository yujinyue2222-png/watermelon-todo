"""业务服务层。

每个服务只做一件事，互相之间通过构造函数注入依赖，方便单独测试：

- :class:`~backend.services.task_service.TaskService`：待办增删改查与循环任务
- :class:`~backend.services.project_service.ProjectService`：项目维度操作
- :class:`~backend.services.stats_service.StatsService`：统计口径
- :class:`~backend.services.reminder_service.ReminderService`：提醒判定
- :class:`~backend.services.export_service.ExportService`：导出 CSV/TXT
- :class:`~backend.services.update_service.UpdateService`：检查新版本
"""

from backend.services.batch_parser import ParsedTaskLine, parse_batch_text, parse_line
from backend.services.export_service import (
    DateRange,
    ExportError,
    ExportService,
    StatusFilter,
)
from backend.services.project_service import ProjectService, ProjectSummary
from backend.services.reminder_service import ReminderEvent, ReminderKind, ReminderService
from backend.services.stats_service import StatsService, TodaySummary
from backend.services.task_service import BatchResult, TaskDraft, TaskQuery, TaskService
from backend.services.update_service import ReleaseInfo, UpdateService

__all__ = [
    "BatchResult",
    "DateRange",
    "ExportError",
    "ExportService",
    "ParsedTaskLine",
    "ProjectService",
    "ProjectSummary",
    "ReleaseInfo",
    "ReminderEvent",
    "ReminderKind",
    "ReminderService",
    "StatsService",
    "StatusFilter",
    "TaskDraft",
    "TaskQuery",
    "TaskService",
    "TodaySummary",
    "UpdateService",
    "parse_batch_text",
    "parse_line",
]
