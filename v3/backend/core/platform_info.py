"""运行平台判断。

集中一处判断，避免各模块重复写 ``sys.platform`` 字符串比较。
"""

import sys

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
IS_LINUX = not IS_WINDOWS and not IS_MACOS

# 是否运行在 PyInstaller 打包后的可执行文件中
IS_FROZEN = bool(getattr(sys, "frozen", False))
