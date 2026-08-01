"""全局常量：应用元信息、文件名与默认值。

这里只放「与界面无关」的常量；颜色、图标等展示相关的常量属于前端，
放在 ``frontend/theme/palettes.py``。
"""

APP_NAME = "西瓜todo"
APP_VERSION = "3.10"
APP_ID = "com.watermelon.desktoptodo"

# 用户数据目录名（Windows: %APPDATA%\DesktopTodo，macOS: ~/Library/Application Support/DesktopTodo）
USER_DIR_NAME = "DesktopTodo"
DATA_FILE_NAME = "todo_data.json"
CONFIG_FILE_NAME = "todo_config.json"
ASSETS_DIR_NAME = "assets"

LOGO_FILE_NAME = "watermelon_logo.svg"
BALL_FILE_NAME = "watermelon_ball.svg"

# 检查更新：GitHub 最新 Release 接口 + 下载页
UPDATE_API = "https://api.github.com/repos/yujinyue2222-png/watermelon-todo/releases/latest"
RELEASE_PAGE = "https://github.com/yujinyue2222-png/watermelon-todo/releases/latest"
UPDATE_TIMEOUT_SECONDS = 8

# 单实例互斥：QLocalServer 名称 + Windows 命名互斥体（与安装包 AppMutex 保持一致）
SINGLE_INSTANCE_KEY = "DesktopTodo_SingleInstance"
WINDOWS_APP_MUTEX = "WatermelonTodo_AppMutex"

DEFAULT_CATEGORIES = ("工作", "生活", "学习", "其他")

# 任务卡片上备注预览的最大字数
NOTE_PREVIEW_LIMIT = 32

# 提醒检查间隔（毫秒）
REMINDER_INTERVAL_MS = 30_000

# ---------------------------------------------------------------- 多端同步
# 默认同步服务地址；用户可在「同步设置」里改
DEFAULT_SYNC_SERVER = "http://47.120.58.231:52121"
SYNC_API_PATH = "/api/sync"
HEALTH_API_PATH = "/api/health"
# 自动同步间隔（毫秒）
SYNC_INTERVAL_MS = 60_000
# 单次同步请求超时（秒）
SYNC_TIMEOUT_SECONDS = 10
