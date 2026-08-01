"""持久化层：把领域模型读写到本地 JSON 文件。

服务层只依赖这一层的接口，将来换成 SQLite 或远端 HTTP 接口时，
只需要提供同样的方法签名，业务代码无需改动。
"""

from backend.repositories.config_repository import ConfigRepository
from backend.repositories.task_repository import TaskRepository

__all__ = ["ConfigRepository", "TaskRepository"]
