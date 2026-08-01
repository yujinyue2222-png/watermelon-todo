"""后端统一门面。

前端只认识这一个类：所有数据读写都通过 ``backend.tasks`` / ``backend.projects``
等服务对象完成，前端不直接接触文件、JSON 或路径。

这样做的目的是把「前后端边界」收拢到一处——将来把本地 JSON 换成 SQLite，
或把服务实现改成调用远端 HTTP 接口时，只要保持这些服务的方法签名不变，
前端代码一行都不用改。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from backend.core import paths
from backend.core.constants import APP_NAME, APP_VERSION
from backend.models.app_config import AppConfig, SyncSettings
from backend.repositories.config_repository import ConfigRepository
from backend.repositories.task_repository import TaskRepository
from backend.services.export_service import ExportService
from backend.services.project_service import ProjectService
from backend.services.reminder_service import ReminderService
from backend.services.stats_service import StatsService
from backend.services.task_service import TaskService
from backend.services.update_service import UpdateService
from backend.sync.engine import SyncEngine
from backend.sync.identity import generate_sync_code, is_valid_sync_code
from backend.system.autostart import is_autostart_supported, set_autostart

logger = logging.getLogger(__name__)


class TodoBackend:
    """聚合全部后端能力的门面。

    Attributes:
        tasks: 待办服务。
        projects: 项目服务。
        stats: 统计服务。
        reminders: 提醒服务。
        exporter: 导出服务。
        updates: 版本检查服务。
        sync: 多端同步引擎。
        config: 当前配置（内存对象，改完记得调用 :meth:`save_config`）。
    """

    def __init__(
        self,
        data_path: Optional[Path] = None,
        config_path: Optional[Path] = None,
        migrate_legacy: bool = True,
    ) -> None:
        """
        Args:
            data_path: 待办数据文件；默认取用户数据目录。
            config_path: 配置文件；默认取用户数据目录。
            migrate_legacy: 是否尝试迁移旧版本遗留在程序目录旁的数据。
        """
        if migrate_legacy and data_path is None and config_path is None:
            paths.migrate_legacy_files()

        self._config_repository = ConfigRepository(config_path or paths.config_file())
        self._task_repository = TaskRepository(data_path or paths.data_file())

        self.config: AppConfig = self._config_repository.load()
        self.tasks = TaskService(self._task_repository)
        self.projects = ProjectService(self.tasks)
        self.stats = StatsService(self.tasks)
        self.reminders = ReminderService(self.tasks)
        self.exporter = ExportService()
        self.updates = UpdateService(current_version=APP_VERSION)
        self.sync = SyncEngine(self.tasks, self.config.sync, self.save_config)

        logger.info(
            "%s v%s 后端就绪：%d 条待办，数据目录 %s",
            APP_NAME,
            APP_VERSION,
            len(self.tasks.tasks),
            self.data_dir,
        )

    @property
    def data_dir(self) -> Path:
        """数据文件所在目录（供「打开数据文件夹」使用）。"""
        return self._task_repository.path.parent

    def save_config(self) -> bool:
        """把当前配置写回磁盘。"""
        return self._config_repository.save(self.config)

    def update_sync_settings(self, settings: SyncSettings) -> None:
        """整体替换同步设置并重建同步引擎。

        引擎持有的是设置对象本身（为了就地更新游标），所以换设置时必须重建，
        否则引擎还在用旧对象。

        Args:
            settings: 新的同步设置。
        """
        self.config.sync = settings
        self.sync = SyncEngine(self.tasks, settings, self.save_config)
        self.save_config()

    def ensure_sync_code(self) -> str:
        """确保存在同步码，没有就生成一个并保存。

        Returns:
            当前使用的同步码。
        """
        settings = self.config.sync
        if not is_valid_sync_code(settings.user_id):
            settings.user_id = generate_sync_code()
            self.save_config()
            logger.info("已生成新的同步码")
        return settings.user_id

    def apply_autostart(self, enable: bool) -> bool:
        """设置开机自启并同步到配置。

        Args:
            enable: 是否开启。

        Returns:
            是否设置成功；失败时配置不会被改动。
        """
        if not is_autostart_supported():
            return False
        if not set_autostart(enable):
            return False
        self.config.autostart = enable
        self.save_config()
        return True
