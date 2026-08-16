"""台词库：小西瓜的气泡文案与主界面的鼓励语。"""

import getpass
import logging
import os
import random

logger = logging.getLogger(__name__)

_FALLBACK_NICKNAME = "亲爱的"

# 悬停时说的陪伴 / 提醒 / 治愈语
HOVER_LINES = (
    # 陪伴 · 打气
    "抱抱西瓜，歇会儿吧～",
    "今天也要元气满满 🍉",
    "待办再多，慢慢来不急",
    "你辛苦啦，奖励自己一口西瓜",
    "别绷太紧，西瓜都替你放松啦",
    "一步一步来，你已经很棒啦",
    "累了就靠一会儿，我陪着你 🍉",
    "慢一点没关系，方向对就行",
    "你比自己想象中更能扛哦",
    "今天的你，已经足够努力啦",
    "不用赶，稳稳的就很好",
    "西瓜给你打气：冲鸭，但别硬撑～",
    "做完一件就少一件，加油 💪",
    "情绪也要按时清空哦",
    "你值得被温柔对待，先从自己开始",
    # 身体 · 提醒
    "记得喝水哦 💧",
    "久坐啦，起来动动肩膀吧",
    "眼睛酸了就看看远处 👀",
    "深呼吸，世界不会崩塌",
    "别忘了好好吃饭呀 🍚",
    "该起来伸个懒腰啦～",
    "护好颈椎，别一直低头哦",
    "困了就眯一会儿，效率更高",
    # 心情 · 治愈
    "坏心情？扔给西瓜吧 🍉",
    "今天也有好好爱自己吗？",
    "不开心的话，先暂停一下下",
    "把焦虑放一放，先做眼前这件",
    "你已经处理了好多事，了不起",
    "允许自己偶尔摆烂一小会儿",
    "生活是长跑，不必事事争先",
    "西瓜相信你，会越来越顺的",
)

# 完成待办后的庆祝文案，``{count}`` 是今日已完成数
CELEBRATE_LINES = (
    "哇你太棒了！今天已完成 {count} 个待办 🎉",
    "厉害！今天 {count} 个待办搞定啦 ✨",
    "牛！{count} 个完成，继续冲 💪",
    "太赞了～今天 {count} 个待办收工 🍉",
    "你超棒的，今天 {count} 个待办拿下！🌟",
)

# 主界面标题下的随机鼓励语，``{name}`` 是用户昵称
CHEER_LINES = (
    "{name}，加油啦！✨",
    "{name}，今天也要元气满满哦~ 🌸",
    "{name}，一件一件来，你可以的！💪",
    "{name}，慢慢来，会更快 🍀",
    "{name}，完成的每一件都值得鼓励 🎉",
    "{name}，别忘了对自己好一点 ☕",
    "{name}，前进一小步也是胜利 🚀",
    "{name}，你比想象中更棒💖",
    "{name}，把大事拆小，就不难啦📌",
    "{name}，深呼吸，开始行动吧🌈",
    "{name}，今天的努力都算数⭐",
    "{name}，冲鸭，好运在路上🍭",
    "{name}，你已经很努力了，别太苛责自己🫶",
    "{name}，做完一件就奖励自己一下吧🍰",
    "{name}，星光不问赶路人，加油🌟",
    "{name}，先完成，再完美✍️",
    "{name}，休息也是效率的一部分😴",
    "{name}，你今天的样子超级可爱🐻",
    "{name}，再坚持一下下就好啦🐣",
    "{name}，把焦虑写进清单，它就变小了📝",
    "{name}，今天也是被期待的一天呀🌤️",
    "{name}，稳住，我们能赢🎮",
    "{name}，一步一步，风景都在路上🚶",
    "{name}，别急，好事正在发生🌷",
    "{name}，你值得所有的好运气🍀",
    "{name}，喝口水，继续发光吧💡",
    "{name}，完成度 > 完美度，先动起来⚡",
    "{name}，今天的你也在悄悄变强🌱",
    "{name}，累了就抱抱西瓜再出发🍉",
)

# 鼠标悬停小西瓜时，若有待办开启了强提醒且未完成，优先催促
# {task} 是待办文字；多条强提醒时随机挑一条任务来念
STRONG_REMIND_LINES = (
    "{task}还没做哦，抓紧时间记得哦～",
    "{task}还没完成呢，赶紧去处理一下吧💪",
    "{task}在等你啦，别拖太久哦⏰",
    "{task}记得做哦，不然小西瓜要催你啦🔔",
    "叮咚～{task}还没搞定，快去完成它🌟",
    "{task}别落下呀，现在就去做最省心✅",
)


def nickname() -> str:
    """取用于称呼用户的昵称：优先系统用户名。"""
    try:
        name = getpass.getuser()
    except (KeyError, OSError) as exc:
        logger.debug("读取系统用户名失败：%s", exc)
        name = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    return name or _FALLBACK_NICKNAME


def random_cheer(name: str) -> str:
    """随机取一句鼓励语。

    Args:
        name: 用户昵称。
    """
    return random.choice(CHEER_LINES).format(name=name)


def strong_remind_line(task_text: str) -> str:
    """随机取一句强提醒催促语，``{task}`` 是待办文字。"""
    quoted = f"「{task_text}」" if task_text else task_text
    return random.choice(STRONG_REMIND_LINES).format(task=quoted)
