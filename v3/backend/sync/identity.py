"""同步码的生成与校验。

同步码既是用户标识也是唯一凭证——服务端不做密码校验，谁拿到同步码就能读写
这份数据。因此默认生成的是一串 22 位随机字符（约 128 位熵），别人猜不到；
换设备时把它抄过去就完成了「登录」。

**不要把同步码贴到公开的地方**（截图、公开仓库、聊天群）。
"""

import re
import secrets

# 与服务端 ``_USER_ID_PATTERN`` 保持一致
_CODE_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{6,64}$")

# 16 字节 → base64url 后 22 个字符
_CODE_BYTES = 16


def generate_sync_code() -> str:
    """生成一个新的随机同步码。"""
    return secrets.token_urlsafe(_CODE_BYTES)


def is_valid_sync_code(code: str) -> bool:
    """校验同步码格式：6-64 位字母、数字、``-``、``_``。"""
    return bool(_CODE_PATTERN.match((code or "").strip()))
