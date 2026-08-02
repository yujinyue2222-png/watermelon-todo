"""西瓜 todo 后端层。

本包只负责数据、业务规则与系统集成，**不依赖任何 GUI 框架**，
因此可以被桌面前端、命令行工具或未来的 HTTP 服务复用。

对外统一入口是 :class:`backend.api.TodoBackend`。
"""

from backend.api import TodoBackend

__all__ = ["TodoBackend"]
