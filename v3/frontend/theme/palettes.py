"""视觉令牌：配色方案与语义色。

一套主题就是一个字典，键含义如下：

===============  ==============================================
键                含义
===============  ==============================================
``bg``            窗口底色，支持 ``#RRGGBBAA``（8 位含透明度）
``gradient``      可选，``[(位置, 颜色)]``，有则覆盖 ``bg`` 画渐变
``panel``         面板/弹窗底色
``card``          任务卡片底色
``card_hover``    卡片悬停底色
``text``          主文字色
``sub``           次要文字色
``accent``        主题主色
``accent2``       主色的浅色变体（悬停态）
``border``        描边色
``shadow``        阴影色
``done``          已完成文字色
===============  ==============================================
"""

from typing import Any, Dict

# 一套主题的配色表
Theme = Dict[str, Any]

DEFAULT_THEME_NAME = "极光白"

BUILTIN_THEMES: dict[str, Theme] = {
    "极光白": {
        "bg": "#FBFCFEE6", "panel": "#FFFFFF", "card": "#F5F7FB",
        "card_hover": "#EEF2F9", "text": "#1F2733", "sub": "#8A94A6",
        "accent": "#4C6FFF", "accent2": "#6E8BFF", "border": "#E6EAF2",
        "shadow": "#20324D", "done": "#B4BCCB",
    },
    "奶油极光": {
        "bg": "#FFF9F4F2", "panel": "#FFFDF9", "card": "#FFFBF7",
        "card_hover": "#F8F1EC", "text": "#181716", "sub": "#77716C",
        "accent": "#6C5CE7", "accent2": "#8478EA", "border": "#EDE6DF",
        "shadow": "#53473D", "done": "#BDB6AF",
        "gradient": [
            (0.0, "#F8D6E5"),
            (0.38, "#FFF5E2"),
            (0.68, "#F5F6C9"),
            (1.0, "#C9F1EA"),
        ],
    },
    "曜石黑": {
        "bg": "#151A22F2", "panel": "#1C2129", "card": "#232A34",
        "card_hover": "#2A3340", "text": "#EAEEF5", "sub": "#8791A0",
        "accent": "#5B7FFF", "accent2": "#7C97FF", "border": "#2E3742",
        "shadow": "#000000", "done": "#5A6472",
    },
    "薄雾蓝": {
        "bg": "#E3EEFBE6", "panel": "#EDF4FE", "card": "#FFFFFF",
        "card_hover": "#E1ECFB", "text": "#1E3A5F", "sub": "#6E86A6",
        "accent": "#4A90E2", "accent2": "#78B4F0", "border": "#CFE0F5",
        "shadow": "#2C5A8F", "done": "#A7BCD6",
    },
    "抹茶绿": {
        "bg": "#F0F7F1E6", "panel": "#F9FCF9", "card": "#FFFFFF",
        "card_hover": "#EAF4EC", "text": "#233529", "sub": "#7A9083",
        "accent": "#2FA96B", "accent2": "#4FC186", "border": "#DBEBE0",
        "shadow": "#1C4A32", "done": "#AECBB7",
    },
    "落日橘": {
        "bg": "#FEF4EEE6", "panel": "#FFF9F5", "card": "#FFFFFF",
        "card_hover": "#FCEEE3", "text": "#3A2A22", "sub": "#A88E7F",
        "accent": "#F2751F", "accent2": "#FB9450", "border": "#F5E2D4",
        "shadow": "#6B3A18", "done": "#D9C2B3",
    },
    "暗夜紫": {
        "bg": "#1A1626F2", "panel": "#221D33", "card": "#2A2440",
        "card_hover": "#332C4D", "text": "#EEE9F7", "sub": "#9A90B4",
        "accent": "#9B6BFF", "accent2": "#B48CFF", "border": "#382F52",
        "shadow": "#000000", "done": "#6C6284",
    },
    "西瓜红": {
        "bg": "#FFF0F1E6", "panel": "#FFF6F6", "card": "#FFFFFF",
        "card_hover": "#FCE6E8", "text": "#3A1F24", "sub": "#B08890",
        "accent": "#F0405A", "accent2": "#FF6E82", "border": "#F6D9DD",
        "shadow": "#7A1F2C", "done": "#E0B7BD",
    },
    "樱花粉": {
        "bg": "#FDEFF5E6", "panel": "#FEF6FA", "card": "#FFFFFF",
        "card_hover": "#FBE6EF", "text": "#3E2733", "sub": "#B58AA0",
        "accent": "#F06AAE", "accent2": "#FB93C6", "border": "#F6DCE8",
        "shadow": "#7A2B57", "done": "#E4BCD2",
    },
    "海洋青": {
        "bg": "#E9F7F6E6", "panel": "#F2FBFA", "card": "#FFFFFF",
        "card_hover": "#DFF3F1", "text": "#173234", "sub": "#6E9896",
        "accent": "#0FB5AE", "accent2": "#3FD0C9", "border": "#CFEAE8",
        "shadow": "#0A4B47", "done": "#A9D3D0",
    },
    "深邃蓝": {
        "bg": "#0E1726F2", "panel": "#152033", "card": "#1B283E",
        "card_hover": "#233150", "text": "#E6EDF7", "sub": "#7E8DA6",
        "accent": "#3DA9FC", "accent2": "#6BC0FF", "border": "#27324A",
        "shadow": "#000000", "done": "#4A5A75",
    },
    "薄荷青": {
        "bg": "#E8F8F4E6", "panel": "#F2FBF8", "card": "#FFFFFF",
        "card_hover": "#DFF3EE", "text": "#1E3A33", "sub": "#6E9A8E",
        "accent": "#16BFA0", "accent2": "#3FD8BC", "border": "#CDEAE2",
        "shadow": "#0A4A3C", "done": "#A5D5CB",
    },
    "焦糖棕": {
        "bg": "#F7EFE6E6", "panel": "#FBF5EE", "card": "#FFFFFF",
        "card_hover": "#F2E6D8", "text": "#3A2A1E", "sub": "#9C8270",
        "accent": "#B07B4E", "accent2": "#D29B6B", "border": "#ECDDCD",
        "shadow": "#5A3A1E", "done": "#D2BCA4",
    },
    "玫瑰金": {
        "bg": "#FCEEEDE6", "panel": "#FEF5F4", "card": "#FFFFFF",
        "card_hover": "#FBE7E5", "text": "#3E2A2C", "sub": "#B08E92",
        "accent": "#E08A8E", "accent2": "#F0AEB1", "border": "#F4D9D8",
        "shadow": "#7A3A42", "done": "#E2BCBE",
    },
    "蜜桃汽水": {
        "bg": "#FFEEE7E6", "panel": "#FFF6F1", "card": "#FFFFFF",
        "card_hover": "#FFE7DE", "text": "#3D2A24", "sub": "#A07C70",
        "accent": "#FF7A59", "accent2": "#FFA07E", "border": "#F5DCD0",
        "shadow": "#7A3A22", "done": "#E0BFB5",
        "gradient": [
            (0.0, "#FFD9C2"),
            (0.38, "#FFB3C6"),
            (0.7, "#E2C2F5"),
            (1.0, "#BFE3FF"),
        ],
    },
    "晚霞": {
        "bg": "#FFF1E8E6", "panel": "#FFF7F2", "card": "#FFFFFF",
        "card_hover": "#FCE7DF", "text": "#3A2433", "sub": "#9E7892",
        "accent": "#F25C7A", "accent2": "#FF8AA5", "border": "#F5D8DE",
        "shadow": "#7A2A44", "done": "#E0BBC6",
        "gradient": [
            (0.0, "#FF9D8B"),
            (0.4, "#FF6A88"),
            (0.72, "#FF99AC"),
            (1.0, "#8E7AE6"),
        ],
    },
    "极光夜": {
        "bg": "#0B1220F2", "panel": "#101A2E", "card": "#172238",
        "card_hover": "#1F2C48", "text": "#E6EEF8", "sub": "#7E8DA6",
        "accent": "#3FE0C0", "accent2": "#6BE8D0", "border": "#243150",
        "shadow": "#000000", "done": "#4A5A75",
        "gradient": [
            (0.0, "#08182A"),
            (0.4, "#0E2A3C"),
            (0.72, "#1A2052"),
            (1.0, "#2C154A"),
        ],
    },
    "棉花糖": {
        "bg": "#FCF0F5E6", "panel": "#FEF6FA", "card": "#FFFFFF",
        "card_hover": "#FBE7EF", "text": "#3A2740", "sub": "#A988A0",
        "accent": "#C56AC0", "accent2": "#E094DC", "border": "#F3D9E8",
        "shadow": "#6A2A5C", "done": "#DDBED2",
        "gradient": [
            (0.0, "#FFD1E8"),
            (0.35, "#D7E4FF"),
            (0.7, "#D6F5E6"),
            (1.0, "#EADDFF"),
        ],
    },
    "莫兰迪晨雾": {
        "bg": "#EDEAE5E6", "panel": "#F4F1EC", "card": "#FFFFFF",
        "card_hover": "#EAE5DE", "text": "#3A352F", "sub": "#8C857B",
        "accent": "#B08968", "accent2": "#C9A384", "border": "#E0DAD0",
        "shadow": "#5A5048", "done": "#C2BAAF",
        "gradient": [(0.0, "#D8CFC2"), (0.5, "#C9B6AE"), (1.0, "#A8B5AE")],
    },
}

# 内置主题的展示顺序（DIY 主题追加在其后）
BUILTIN_THEME_ORDER = tuple(BUILTIN_THEMES.keys())

# 主题市场首页展示的示例数量
THEME_SHOWCASE_LIMIT = 8

# DIY 配色可调的颜色项：(主题键, 中文名)
DIY_COLOR_KEYS = (
    ("accent", "主色"),
    ("accent2", "副色"),
    ("panel", "面板"),
    ("card", "卡片"),
    ("text", "文字"),
    ("sub", "副文字"),
    ("border", "边框"),
)

# 分类语义色（未列出的分类使用主题的 sub 色）
CATEGORY_COLORS = {
    "工作": "#4C6FFF",
    "生活": "#2FA96B",
    "学习": "#F2751F",
    "其他": "#8A94A6",
}

# 紧急程度语义色
PRIORITY_COLORS = {
    "P0": "#D92D20",
    "P1": "#F2564B",
    "P2": "#F58C4B",
    "重要": "#F5A623",
    "普通": "#98A2B3",
}

# 卡片上的图标
PRIORITY_ICONS = {"P0": "🔥", "P1": "", "P2": "", "重要": "⭐", "普通": ""}
STATUS_ICONS = {"todo": "○", "doing": "◐", "done": "●"}
RECUR_ICON = "🔁"
REMIND_ICON = "🔔"
PIN_ICON = "📌"

# 通用语义色（不随主题变化）
DANGER_COLOR = "#E5484D"
DANGER_STRONG_COLOR = "#D92D20"
URGENT_COLOR = "#F2564B"
SUCCESS_COLOR = "#22B07D"


def build_diy_theme(colors: dict[str, str]) -> Theme:
    """把 DIY 选出的若干颜色补全成一套完整主题。

    Args:
        colors: 至少包含 :data:`DIY_COLOR_KEYS` 中的键。

    Returns:
        完整主题字典。
    """
    return {
        "bg": colors["panel"],
        "panel": colors["panel"],
        "card": colors["card"],
        "card_hover": colors["card"],
        "text": colors["text"],
        "sub": colors["sub"],
        "accent": colors["accent"],
        "accent2": colors["accent2"],
        "border": colors["border"],
        "shadow": "#000000",
        "done": colors["sub"],
    }
