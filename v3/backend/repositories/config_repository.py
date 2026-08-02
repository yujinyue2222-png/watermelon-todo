"""配置仓库。"""

import logging
from pathlib import Path

from backend.models.app_config import AppConfig
from backend.repositories.json_store import read_json, write_json

logger = logging.getLogger(__name__)


class ConfigRepository:
    """把 :class:`~backend.models.app_config.AppConfig` 读写到 JSON 文件。"""

    def __init__(self, path: Path) -> None:
        """
        Args:
            path: 配置文件路径。
        """
        self._path = path

    @property
    def path(self) -> Path:
        """配置文件路径。"""
        return self._path

    def load(self) -> AppConfig:
        """读取配置；缺失或损坏时返回全默认配置。"""
        raw = read_json(self._path)
        if not isinstance(raw, dict):
            if raw is not None:
                logger.error("%s 顶层不是对象，使用默认配置", self._path)
            return AppConfig()
        return AppConfig.from_dict(raw)

    def save(self, config: AppConfig) -> bool:
        """写回配置。

        Args:
            config: 要保存的配置。

        Returns:
            是否保存成功。
        """
        return write_json(self._path, config.to_dict())
