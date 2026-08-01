"""多端同步。

同步被拆成三步，目的是让「网络」和「改数据」分开，桌面端就能把耗时的 HTTP
放到后台线程，而合并仍在主线程做，不会和界面操作同时改同一份任务列表：

1. :meth:`~backend.sync.engine.SyncEngine.prepare` —— 主线程，挑出本地待推送的改动
2. :meth:`~backend.sync.engine.SyncEngine.exchange` —— 后台线程，纯网络请求
3. :meth:`~backend.sync.engine.SyncEngine.apply` —— 主线程，合并结果并落盘

只想同步一次、不在意线程的场景（命令行、测试）直接用
:meth:`~backend.sync.engine.SyncEngine.sync_now`。
"""

from backend.sync.client import SyncClient, SyncError
from backend.sync.engine import PushBatch, SyncEngine, SyncResult
from backend.sync.identity import generate_sync_code, is_valid_sync_code

__all__ = [
    "PushBatch",
    "SyncClient",
    "SyncEngine",
    "SyncError",
    "SyncResult",
    "generate_sync_code",
    "is_valid_sync_code",
]
