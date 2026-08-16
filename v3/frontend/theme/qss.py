"""样式表生成。

v2 把 Qt 样式表散落在各个控件的 ``_apply_style`` 里，改配色要翻好几处。
这里把所有 QSS 收拢成纯函数：输入配色，输出样式字符串，不碰任何控件状态，
方便统一调整视觉细节。
"""

from __future__ import annotations

from frontend.theme.palettes import (
    DANGER_COLOR,
    DANGER_STRONG_COLOR,
    SUCCESS_COLOR,
    URGENT_COLOR,
    Theme,
)


def alpha(color: str, value: int) -> str:
    """把 ``#RRGGBB`` 转成 Qt 样式表用的 ``#AARRGGBB``。

    Args:
        color: 颜色字符串，多余的透明度位会被忽略。
        value: 透明度 0-255。

    Returns:
        带透明度前缀的颜色字符串。
    """
    rgb = str(color).lstrip("#")[:6]
    clamped = max(0, min(255, int(value)))
    return f"#{clamped:02X}{rgb}"


def main_window_qss(theme: Theme) -> str:
    """主窗口及其内部控件的样式。"""
    return f"""
        QPushButton {{ outline: none; }}
        QPushButton:disabled {{ color: {theme['done']}; background: {theme['border']}; }}
        QLabel#apptitle {{ color: {theme['text']}; font-size: 16px; font-weight: 700; }}
        QLabel#cheer {{ color: {theme['accent']}; font-size: 11px; font-weight: bold; }}
        QLabel#cheer:hover {{ color: {theme['accent2']}; }}

        QPushButton#titlebtn, QPushButton#closebtn {{
            background: {alpha(theme['panel'], 0x88)};
            border: 1px solid transparent;
            border-radius: 10px; color: {theme['sub']};
            font-size: 15px; font-weight: bold;
        }}
        QPushButton#titlebtn:hover {{
            background: {theme['card_hover']}; border-color: {theme['border']};
            color: {theme['text']};
        }}
        QPushButton#closebtn:hover {{ background: {DANGER_COLOR}; color: #FFFFFF; }}
        QPushButton#titlebtn:pressed, QPushButton#closebtn:pressed {{ padding-top: 2px; }}

        QFrame#stats {{
            background: {theme['panel']}; border-radius: 14px;
            border: 1px solid {theme['border']};
        }}
        QLabel#statstext {{ color: {theme['text']}; font-size: 13px; font-weight: bold; }}
        QLabel#statspct {{ color: {theme['accent']}; font-size: 13px; font-weight: bold; }}
        QFrame#barbg {{ background: {theme['border']}; border-radius: 4px; }}
        QFrame#barfg {{ background: {theme['accent']}; border-radius: 4px; }}

        QPushButton#tabbtn {{
            background: {theme['panel']}; border: 1px solid {theme['border']};
            border-radius: 11px; padding: 8px 10px;
            color: {theme['sub']}; font-size: 13px; font-weight: 600;
        }}
        QPushButton#tabbtn:checked {{
            background: {alpha(theme['accent'], 0x20)};
            border: 1px solid {alpha(theme['accent'], 0x65)};
            color: {theme['accent']};
        }}
        QPushButton#tabbtn:hover {{
            color: {theme['accent']}; border-color: {theme['accent']};
            background: {alpha(theme['accent'], 0x10)};
        }}
        QPushButton#tabbtn:checked:hover {{
            color: {theme['accent']}; background: {alpha(theme['accent'], 0x2B)};
        }}

        QPushButton#addbtn {{
            background: {theme['accent']}; border: 1px solid {theme['accent']};
            border-radius: 12px; color: #FFFFFF; font-size: 14px; font-weight: 700;
        }}
        QPushButton#addbtn:hover {{ background: {theme['accent2']}; }}
        QPushButton#addbtn:pressed {{ padding-top: 2px; }}

        QPushButton#secondarybtn {{
            background: {theme['panel']}; border: 1px solid {theme['border']};
            border-radius: 11px; color: {theme['text']};
            font-size: 12px; font-weight: 500;
        }}
        QPushButton#secondarybtn:hover {{
            color: {theme['accent']}; border-color: {theme['accent']};
            background: {alpha(theme['accent'], 0x10)};
        }}
        QPushButton#exportbtn {{
            background: {SUCCESS_COLOR}; border: none; border-radius: 11px;
            color: #FFFFFF; font-size: 12px; font-weight: 500;
        }}
        QPushButton#exportbtn:hover {{ background: #1C9A6C; }}
        QPushButton#selallbtn {{
            background: {theme['accent']}; border: none; border-radius: 11px;
            color: #FFFFFF; font-size: 12px; font-weight: 500;
        }}
        QPushButton#selallbtn:hover {{ background: {alpha(theme['accent'], 0xDD)}; }}

        QPushButton#chip {{
            background: {theme['card']}; border: 1px solid {theme['border']};
            border-radius: 11px; padding: 5px 10px; color: {theme['sub']};
            font-size: 12px; font-weight: 500;
        }}
        QPushButton#chip:hover {{
            color: {theme['accent']}; border-color: {theme['accent']};
            background: {alpha(theme['accent'], 0x10)};
        }}
        QPushButton#chip:checked {{
            background: {alpha(theme['accent'], 0x1C)}; color: {theme['accent']};
            border-color: {alpha(theme['accent'], 0x60)}; font-weight: bold;
        }}

        QComboBox#projpick {{
            background: {theme['panel']}; border: 1px solid {theme['border']};
            border-radius: 12px; padding: 0 8px; color: {theme['text']};
            font-size: 12px; font-weight: 500;
        }}
        QComboBox::drop-down {{ border: none; width: 30px; background: transparent; }}
        QComboBox::down-arrow {{ image: none; width: 0; height: 0; border: none; }}
        QComboBox QAbstractItemView {{
            background: {theme['panel']}; color: {theme['text']};
            selection-background-color: {theme['accent']}; border-radius: 8px;
        }}

        QFrame#batchbar {{
            background: {theme['panel']}; border-radius: 14px;
            border: 1px solid {theme['border']};
        }}
        QLabel#batchlbl {{
            color: {theme['accent']}; font-size: 12px; font-weight: bold;
        }}
        QPushButton#batchbtn {{
            background: {theme['card']}; border: 1px solid {theme['border']};
            border-radius: 10px; color: {theme['text']}; font-size: 12px;
            padding: 6px 11px; font-weight: 600;
        }}
        QPushButton#batchbtn:hover {{
            background: {alpha(theme['accent'], 0x16)};
            border-color: {theme['accent']}; color: {theme['accent']};
        }}
        QPushButton#batchdanger {{
            background: transparent;
            border: 1px solid {alpha(DANGER_COLOR, 0x55)};
            border-radius: 10px; color: {DANGER_COLOR}; font-size: 12px;
            padding: 6px 11px; font-weight: 600;
        }}
        QPushButton#batchdanger:hover {{
            background: {DANGER_COLOR}; color: #FFFFFF; border-color: {DANGER_COLOR};
        }}

        QLabel#emptyState {{
            color: {theme['sub']}; background: {alpha(theme['card'], 0x70)};
            border: 1px dashed {theme['border']}; border-radius: 14px;
            font-size: 13px; padding: 28px 12px;
        }}

        QScrollArea#scroll, QScrollArea#catscroll {{
            background: transparent; border: none;
        }}
        QScrollArea#scroll > QWidget > QWidget,
        QScrollArea#catscroll > QWidget > QWidget {{ background: transparent; }}
        QScrollBar:horizontal {{
            background: transparent; height: 5px; margin: 0 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {alpha(theme['sub'], 0x50)}; border-radius: 2px; min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {theme['sub']}; }}
        QScrollBar:vertical {{ background: transparent; width: 6px; margin: 2px; }}
        QScrollBar::handle:vertical {{
            background: {theme['border']}; border-radius: 3px; min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {theme['sub']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

        {menu_qss(theme)}
        QToolTip {{
            color: {theme['text']}; background: {theme['panel']};
            border: 1px solid {theme['border']}; border-radius: 7px; padding: 5px 7px;
        }}
    """


def menu_qss(theme: Theme) -> str:
    """右键菜单与下拉菜单的样式。"""
    return f"""
        QMenu {{
            background: {theme['panel']}; color: {theme['text']};
            border: 1px solid {theme['border']}; border-radius: 12px; padding: 7px;
        }}
        QMenu::item {{ padding: 8px 24px; border-radius: 8px; }}
        QMenu::item:selected {{ background: {theme['accent']}; color: #FFFFFF; }}
        QMenu::item:disabled {{ color: {theme['done']}; }}
        QMenu::separator {{
            height: 1px; background: {theme['border']}; margin: 5px 8px;
        }}
    """


def card_menu_qss(theme: Theme) -> str:
    """任务卡片右键菜单：底色用卡片色，与卡片本身呼应。"""
    return f"""
        QMenu {{
            background: {theme['card']}; border: 1px solid {theme['border']};
            border-radius: 10px; padding: 6px;
        }}
        QMenu::item {{
            color: {theme['text']}; font-size: 13px;
            padding: 7px 22px 7px 14px; border-radius: 7px;
        }}
        QMenu::item:selected {{
            background: {alpha(theme['accent'], 0x22)}; color: {theme['accent']};
        }}
        QMenu::separator {{
            height: 1px; background: {theme['border']}; margin: 5px 8px;
        }}
    """


def task_card_qss(
    theme: Theme,
    category_color: str,
    priority_color: str,
    is_done: bool,
    is_hovered: bool,
    show_priority_bar: bool,
) -> str:
    """单张任务卡片的样式。

    Args:
        theme: 当前配色。
        category_color: 分类语义色。
        priority_color: 紧急程度语义色。
        is_done: 是否已完成（决定置灰与删除线）。
        is_hovered: 鼠标是否悬停。
        show_priority_bar: 是否显示左侧优先级色条。
    """
    title_color = theme["done"] if is_done else theme["text"]
    decoration = "line-through" if is_done else "none"
    card_background = theme["card_hover"] if is_hovered else theme["card"]
    note_color = theme["done"] if is_done else category_color
    bar_color = priority_color if show_priority_bar else "transparent"
    return f"""
        QFrame#card {{
            background: {card_background};
            border-radius: 12px;
            border: 1px solid {theme['border']};
        }}
        QFrame#pbar {{ background: {bar_color}; border-radius: 1px; }}
        QLabel#title {{
            color: {title_color}; font-size: 14px; font-weight: 500;
            text-decoration: {decoration};
        }}
        QLabel#prio {{
            color: {'#FFFFFF' if not is_done else theme['done']};
            font-size: 11px; font-weight: bold;
            background: {priority_color if not is_done else alpha(priority_color, 0x22)};
            border-radius: 8px; padding: 3px 8px;
        }}
        QPushButton#dot {{
            background: {alpha(theme['accent'], 0x10)};
            border: 1px solid {alpha(theme['accent'], 0x30)};
            border-radius: 11px; color: {theme['accent']};
            font-size: 14px; font-weight: bold;
        }}
        QPushButton#dot:hover {{
            background: {alpha(theme['accent'], 0x22)}; border-color: {theme['accent']};
        }}
        QPushButton#dot:pressed {{ background: {alpha(theme['accent'], 0x35)}; }}
        QLabel#pinmark {{ font-size: 10px; background: transparent; padding: 0px; }}
        QLabel#notePreview {{
            color: {note_color}; font-size: 11px; font-weight: 500;
            background: {alpha(category_color, 0x14 if not is_done else 0x0A)};
            border-left: 3px solid {alpha(category_color, 0xCC if not is_done else 0x55)};
            border-radius: 6px; padding: 2px 6px;
        }}
        QLabel#cat {{
            color: {note_color}; font-size: 11px; font-weight: bold;
            background: {alpha(category_color, 0x18 if not is_done else 0x0C)};
            border: 1px solid {alpha(category_color, 0x28 if not is_done else 0x14)};
            border-radius: 8px; padding: 3px 8px;
        }}
        QLabel#due {{
            color: {theme['sub'] if not is_done else theme['done']}; font-size: 11px;
            background: {theme['panel']}; border: 1px solid {theme['border']};
            border-radius: 8px; padding: 3px 8px;
        }}
        QLabel#due_urgent {{
            color: #FFFFFF; font-size: 11px; font-weight: bold;
            background: {URGENT_COLOR}; border: 1px solid {URGENT_COLOR};
            border-radius: 8px; padding: 3px 8px;
        }}
        QLabel#recur {{
            color: {theme['accent'] if not is_done else theme['done']};
            font-size: 11px; font-weight: bold;
            background: {alpha(theme['accent'], 0x14 if not is_done else 0x0A)};
            border: 1px solid {alpha(theme['accent'], 0x25 if not is_done else 0x12)};
            border-radius: 8px; padding: 3px 8px;
        }}
        QLabel#strongbadge {{
            color: #FFFFFF; font-size: 11px; font-weight: bold;
            background: {theme['accent']}; border: 1px solid {theme['accent']};
            border-radius: 8px; padding: 3px 8px;
        }}
        QPushButton#edit {{
            background: {theme['panel'] if is_hovered else 'transparent'};
            border: {('1px solid ' + theme['border']) if is_hovered else 'none'};
            border-radius: 8px; color: {theme['sub']}; font-size: 13px;
        }}
        QPushButton#edit:hover {{
            color: #FFFFFF; background: {theme['accent']};
            border-color: {theme['accent']};
        }}
        QPushButton#edit:pressed {{ padding-top: 2px; }}
        QPushButton#subbadge {{
            color: {theme['accent']}; font-size: 11px; font-weight: bold;
            background: {alpha(theme['accent'], 0x14)};
            border: 1px solid {alpha(theme['accent'], 0x25)};
            border-radius: 8px; padding: 3px 8px;
        }}
        QPushButton#subbadge:hover {{ background: {alpha(theme['accent'], 0x25)}; }}
        QWidget#subpanel {{ background: transparent; }}
        QPushButton#subitem {{
            color: {theme['sub']}; font-size: 12px; text-align: left;
            background: transparent; border: none; border-radius: 7px; padding: 4px 7px;
        }}
        QPushButton#subitem:hover {{
            color: {theme['accent']}; background: {alpha(theme['accent'], 0x10)};
        }}
        QLabel#thumb {{
            border: 1px solid {theme['border']}; border-radius: 8px;
            background: {theme['panel']};
        }}
        QLabel#thumbmore {{
            color: {theme['sub']}; font-size: 13px; font-weight: 600;
            border: 1px dashed {theme['border']}; border-radius: 8px;
            background: {theme['panel']};
        }}
        QPushButton#thumbbtn {{
            color: {theme['sub']}; font-size: 12px;
            background: {alpha(theme['accent'], 0x0d)};
            border: 1px solid {theme['border']};
            border-radius: 8px; padding: 2px 8px;
        }}
        QPushButton#thumbbtn:hover {{
            color: {theme['accent']}; background: {alpha(theme['accent'], 0x16)};
            border-color: {alpha(theme['accent'], 0x60)};
        }}
    """


def inline_editor_qss(theme: Theme) -> str:
    """列表顶部内联新建行的样式。"""
    combo_selector = "QComboBox#inlinepr, QComboBox#inlinect"
    return f"""
        QWidget#inlinerow {{
            background: {theme['card']};
            border: 1px solid {alpha(theme['accent'], 0x80)};
            border-radius: 13px;
        }}
        QTextEdit#inlineedit, QLineEdit#inlineedit {{
            border: none; background: transparent; font-size: 14px;
            color: {theme['text']};
        }}
        QTextEdit#inlineedit::placeholder {{
            color: {alpha(theme['sub'], 0x80)};
        }}
        QPushButton#inlinedate, QPushButton#inlineok, QPushButton#inlinecancel {{
            border: 1px solid {theme['border']}; border-radius: 8px;
            background: {theme['panel']}; color: {theme['sub']}; font-size: 14px;
        }}
        QPushButton#inlinedate:hover {{
            color: {theme['accent']}; border-color: {theme['accent']};
        }}
        QPushButton#inlineok {{
            color: #FFFFFF; background: {theme['accent']};
            border-color: {theme['accent']}; font-weight: bold;
        }}
        QPushButton#inlineok:hover {{
            background: {theme['accent2']}; border-color: {theme['accent2']};
        }}
        QPushButton#inlinecancel:hover {{
            color: #FFFFFF; background: {DANGER_COLOR}; border-color: {DANGER_COLOR};
        }}
        {combo_selector} {{
            border: 1px solid {theme['border']}; border-radius: 13px;
            background: {theme['panel']}; color: {theme['text']};
            font-size: 11px; padding: 2px 10px;
        }}
        QComboBox#inlinepr:hover, QComboBox#inlinect:hover {{
            border: 1px solid {theme['accent']};
        }}
        QComboBox#inlinepr::drop-down, QComboBox#inlinect::drop-down {{
            border: none; width: 28px; background: transparent;
            subcontrol-origin: padding; subcontrol-position: right center;
        }}
        QComboBox#inlinepr::down-arrow, QComboBox#inlinect::down-arrow {{
            image: none; width: 0; height: 0; border: none; background: transparent;
        }}
        QLabel#inlineimg {{
            background: transparent; border: none;
        }}
        QPushButton#inlineimgclose {{
            border: none; border-radius: 9px;
            background: rgba(0,0,0,0.55); color: #FFFFFF;
            font-size: 11px; font-weight: bold; padding: 0;
        }}
        QPushButton#inlineimgclose:hover {{
            background: {DANGER_COLOR};
        }}
        QComboBox#inlinepr QAbstractItemView, QComboBox#inlinect QAbstractItemView {{
            border: 1px solid {theme['border']}; border-radius: 8px;
            background: {theme['panel']}; color: {theme['text']};
            outline: none; padding: 4px;
            selection-background-color: {theme['accent']}; selection-color: #FFFFFF;
        }}
    """


def toast_qss(theme: Theme) -> str:
    """底部浮动提示条的样式。"""
    return f"""
        QLabel#toast {{
            background: {theme['text']}; color: {theme['panel']};
            border-radius: 10px; padding: 8px 14px;
            font-size: 12px; font-weight: 600;
        }}
    """


def dialog_qss(theme: Theme) -> str:
    """常规弹窗（带系统标题栏）的统一样式。"""
    return f"""
        QDialog {{ background: {theme['panel']}; color: {theme['text']}; }}
        QLabel {{ color: {theme['sub']}; font-size: 12px; font-weight: bold; }}
        QLineEdit, QComboBox, QPlainTextEdit, QTextEdit {{
            background: {theme['card']}; color: {theme['text']};
            border: 1px solid {theme['border']}; border-radius: 10px;
            padding: 8px 11px; font-size: 13px;
        }}
        QLineEdit:hover, QComboBox:hover, QPlainTextEdit:hover, QTextEdit:hover {{
            border-color: {alpha(theme['accent'], 0x80)};
        }}
        QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus {{
            border: 1px solid {theme['accent']}; background: {theme['panel']};
        }}
        QComboBox::drop-down {{ border: none; width: 30px; background: transparent; }}
        QComboBox::down-arrow {{ image: none; width: 0; height: 0; border: none; }}
        QComboBox QAbstractItemView {{
            background: {theme['panel']}; color: {theme['text']};
            selection-background-color: {theme['accent']}; selection-color: #FFFFFF;
            border: 1px solid {theme['border']}; border-radius: 9px;
            outline: none; padding: 4px;
        }}
        QTabWidget::pane {{
            border: 1px solid {theme['border']}; border-radius: 10px; top: -1px;
        }}
        QTabBar::tab {{
            background: transparent; color: {theme['sub']};
            padding: 7px 14px; border-radius: 9px; font-size: 12px; font-weight: 600;
        }}
        QTabBar::tab:selected {{
            background: {alpha(theme['accent'], 0x1C)}; color: {theme['accent']};
        }}
        {_checkbox_qss(theme)}
        QPushButton {{
            background: {theme['card']}; color: {theme['text']};
            border: 1px solid {theme['border']}; border-radius: 10px;
            padding: 8px 16px; font-size: 13px; font-weight: 600;
        }}
        QPushButton:hover {{
            border-color: {theme['accent']}; color: {theme['accent']};
            background: {alpha(theme['accent'], 0x10)};
        }}
        QPushButton:pressed {{ padding-top: 9px; padding-bottom: 7px; }}
        QPushButton:disabled {{
            color: {theme['done']}; background: {theme['border']};
            border-color: {theme['border']};
        }}
        QDialogButtonBox QPushButton {{ min-width: 78px; padding: 9px 18px; }}
        QDialogButtonBox QPushButton:default {{
            background: {theme['accent']}; color: #FFFFFF;
            border: 1px solid {theme['accent']};
        }}
        QDialogButtonBox QPushButton:default:hover {{
            background: {theme['accent2']}; border: 1px solid {theme['accent2']};
            color: #FFFFFF;
        }}
        QListWidget {{
            background: {theme['card']}; color: {theme['text']};
            border: 1px solid {theme['border']}; border-radius: 10px; padding: 4px;
        }}
        QListWidget::item {{ padding: 7px 9px; border-radius: 7px; }}
        QListWidget::item:selected {{
            background: {alpha(theme['accent'], 0x22)}; color: {theme['accent']};
        }}
        QScrollBar:vertical {{ background: transparent; width: 7px; margin: 2px; }}
        QScrollBar::handle:vertical {{
            background: {theme['border']}; border-radius: 3px; min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {theme['sub']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
    """


def surface_dialog_qss(theme: Theme) -> str:
    """无边框弹窗的样式。

    这类弹窗结构是「透明外壳 + 不透明圆角面板(``QFrame#dialogSurface``)」，
    比直接把控件画在透明窗口上跨平台渲染更稳定，不会出现错位与重影。
    """
    return f"""
        QDialog {{ background: transparent; }}
        QFrame#dialogSurface {{
            background: {theme['panel']}; border: 1px solid {theme['border']};
            border-radius: 18px;
        }}
        QLabel {{ color: {theme['text']}; font-size: 13px; }}
        QLabel#dialogTitle {{
            color: {theme['text']}; font-size: 17px; font-weight: 700;
        }}
        QLabel#dialogSubtitle {{
            color: {theme['sub']}; font-size: 11px; font-weight: 400;
        }}
        QLabel#dialogWatermelon {{
            font-size: 22px; background: transparent; padding: 0px;
        }}
        QLabel#expiredBanner {{
            color: {theme['sub']}; font-size: 12px; font-weight: 500;
            background: {theme['card']}; border: 1px solid {theme['border']};
            border-radius: 10px; padding: 8px 12px;
        }}
        QLabel#fieldHint {{
            color: {theme['sub']}; font-size: 11px; font-weight: 400;
        }}
        QFrame#switchFrame {{
            background: {theme['card']}; border: 1px solid {theme['border']};
            border-radius: 12px; padding: 6px;
        }}
        QPushButton#switchOn, QPushButton#switchOff {{
            background: transparent; color: {theme['sub']};
            border: 1px solid {theme['border']};
            border-radius: 9px; padding: 9px 0px; font-size: 13px; font-weight: 600;
        }}
        QPushButton#switchOn:hover, QPushButton#switchOff:hover {{
            border-color: {theme['accent']}; color: {theme['text']};
        }}
        QPushButton#switchOn:checked {{
            background: {theme['accent']}; color: #FFFFFF; border-color: {theme['accent']};
        }}
        QPushButton#switchOff:checked {{
            background: {DANGER_STRONG_COLOR}; color: #FFFFFF; border-color: {DANGER_STRONG_COLOR};
        }}
        QLineEdit, QSpinBox, QComboBox {{
            background: {theme['card']}; color: {theme['text']};
            border: 1px solid {theme['border']}; border-radius: 10px;
            padding: 4px 10px; font-size: 13px;
        }}
        QSpinBox {{
            padding-right: 4px;
        }}
        QSpinBox::up-button, QSpinBox::down-button {{
            width: 0px; height: 0px; border: none; background: transparent;
            subcontrol-origin: border;
        }}
        QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{
            border-color: {alpha(theme['accent'], 0x80)};
        }}
        QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
            border: 1px solid {theme['accent']};
        }}
        QComboBox::drop-down {{ border: none; width: 28px; background: transparent; }}
        QComboBox::down-arrow {{ image: none; width: 0; height: 0; border: none; }}
        QComboBox QAbstractItemView {{
            background: {theme['panel']}; color: {theme['text']};
            selection-background-color: {theme['accent']}; selection-color: #FFFFFF;
            border: 1px solid {theme['border']}; border-radius: 9px;
            outline: none; padding: 4px;
        }}
        {_checkbox_qss(theme)}
        QScrollArea {{ background: transparent; border: none; }}
        QWidget#themeGrid {{ background: transparent; }}
        QPushButton {{
            background: {theme['accent']}; color: #FFFFFF; border: none;
            border-radius: 10px; padding: 9px 18px; font-size: 13px; font-weight: bold;
        }}
        QPushButton:hover {{ background: {theme['accent2']}; }}
        QPushButton#ghost {{
            background: transparent; color: {theme['sub']};
            border: 1px solid {theme['border']}; font-weight: 600;
        }}
        QPushButton#ghost:hover {{
            color: {theme['accent']}; border-color: {theme['accent']};
        }}
        QPushButton#ghost:disabled {{
            color: {theme['done']}; border-color: {theme['border']};
            background: transparent;
        }}
        QPushButton#dangerGhost {{
            color: {DANGER_STRONG_COLOR}; background: transparent; border: none;
            padding: 8px 12px; font-weight: 600;
        }}
        QPushButton#dangerGhost:hover {{
            color: #FFFFFF; background: {DANGER_STRONG_COLOR}; border: none;
        }}
    """


def calendar_qss(theme: Theme) -> str:
    """日期选择弹窗里日历控件的样式。"""
    return f"""
        QLabel#selectedDate {{
            color: {theme['accent']};
            background: {alpha(theme['accent'], 0x18)};
            border: 1px solid {alpha(theme['accent'], 0x35)};
            border-radius: 10px; padding: 6px 10px;
            font-size: 12px; font-weight: 700;
        }}
        QFrame#calendarCard {{
            background: {theme['card']}; border: 1px solid {theme['border']};
            border-radius: 14px;
        }}
        QFrame#timeCard {{
            background: {theme['card']}; border: 1px solid {theme['border']};
            border-radius: 12px;
        }}
        QCalendarWidget {{ background: transparent; color: {theme['text']}; }}
        QCalendarWidget QWidget#qt_calendar_navigationbar {{
            background: transparent; border: none; padding: 4px;
        }}
        QCalendarWidget QToolButton {{
            color: {theme['text']}; background: transparent; border: none;
            border-radius: 9px; min-height: 30px; padding: 2px 9px;
            font-size: 13px; font-weight: 700;
        }}
        QCalendarWidget QToolButton:hover {{
            color: {theme['accent']}; background: {alpha(theme['accent'], 0x18)};
        }}
        /* 月份/年份按钮去掉下拉箭头，避免「七月˅」文字上下错落 */
        QCalendarWidget QToolButton#qt_calendar_monthbutton,
        QCalendarWidget QToolButton#qt_calendar_yearbutton {{
            padding: 2px 14px; margin: 0 2px;
        }}
        QCalendarWidget QToolButton#qt_calendar_monthbutton::menu-indicator,
        QCalendarWidget QToolButton#qt_calendar_yearbutton::menu-indicator {{
            image: none; width: 0; height: 0; subcontrol-position: right center;
        }}
        QCalendarWidget QToolButton#qt_calendar_prevmonth,
        QCalendarWidget QToolButton#qt_calendar_nextmonth {{
            qproperty-icon: none; color: {theme['sub']};
            min-width: 30px; max-width: 30px; padding: 0;
        }}
        QCalendarWidget QToolButton#qt_calendar_prevmonth {{ qproperty-text: "‹"; }}
        QCalendarWidget QToolButton#qt_calendar_nextmonth {{ qproperty-text: "›"; }}
        QCalendarWidget QMenu {{
            background: {theme['panel']}; color: {theme['text']};
            border: 1px solid {theme['border']}; border-radius: 10px; padding: 5px;
        }}
        QCalendarWidget QSpinBox {{
            color: {theme['text']}; background: {theme['panel']};
            selection-background-color: {theme['accent']};
            border: 1px solid {theme['border']}; border-radius: 8px; padding: 4px 8px;
        }}
        QCalendarWidget QAbstractItemView {{
            color: {theme['text']}; background: transparent; border: none;
            outline: none; selection-background-color: transparent;
            selection-color: #FFFFFF; font-size: 12px;
        }}
        QCalendarWidget QAbstractItemView::item {{ border-radius: 9px; padding: 5px; }}
        QCalendarWidget QAbstractItemView::item:hover {{
            color: {theme['accent']}; background: {alpha(theme['accent'], 0x16)};
        }}
        QCalendarWidget QHeaderView, QCalendarWidget QHeaderView::section {{
            background: transparent; color: {theme['sub']}; border: none;
            padding: 5px 0; font-size: 11px; font-weight: 600;
        }}
        QTimeEdit#timeEdit {{
            color: {theme['text']}; background: {theme['panel']};
            border: 1px solid {theme['border']}; border-radius: 9px;
            padding: 6px 10px; font-size: 13px; font-weight: 700;
        }}
        QTimeEdit#timeEdit:focus {{ border-color: {theme['accent']}; }}
        QTimeEdit#timeEdit:disabled {{
            color: {theme['done']}; background: {theme['border']};
        }}
        QDateEdit#timeEdit {{
            color: {theme['text']}; background: {theme['panel']};
            border: 1px solid {theme['border']}; border-radius: 9px;
            padding: 6px 10px; font-size: 13px; font-weight: 700;
        }}
    """


def reminder_card_qss(theme: Theme, accent: str) -> str:
    """提醒弹窗中央卡片的样式。

    Args:
        theme: 当前配色。
        accent: 强调色；紧急提醒会传入警示红。
    """
    return f"""
        QFrame#reminderCard {{
            background: {theme['panel']};
            border: 1px solid {theme['border']};
            border-radius: 18px;
        }}
        QPushButton#reminderOk {{
            background: {accent}; color: #FFFFFF; border: none;
            border-radius: 11px; font-size: 14px; font-weight: bold;
        }}
        QPushButton#reminderOk:hover {{ background: {theme['accent2']}; }}
    """


def note_editor_qss(theme: Theme) -> str:
    """备注输入框：左侧加一条主题色竖线，视觉上和卡片里的备注呼应。"""
    return f"""
        QTextEdit {{
            border: 1px solid {alpha(theme['accent'], 0x66)};
            border-left: 3px solid {theme['accent']};
            border-radius: 8px;
            background: {alpha(theme['accent'], 0x18)};
            color: {theme['text']}; padding: 6px;
        }}
    """


def preview_box_qss(theme: Theme) -> str:
    """批量粘贴的解析预览框样式。"""
    return f"""
        QTextEdit {{
            border: 1px dashed {alpha(theme['accent'], 0x66)};
            border-radius: 8px;
            background: {alpha(theme['accent'], 0x10)};
            color: {theme['sub']}; padding: 6px; font-size: 12px;
        }}
    """


def _checkbox_qss(theme: Theme) -> str:
    """勾选框样式（多处复用）。"""
    return f"""
        QCheckBox {{ color: {theme['text']}; font-size: 12px; spacing: 7px; }}
        QCheckBox::indicator {{
            width: 17px; height: 17px; border-radius: 5px;
            border: 1px solid {theme['border']}; background: {theme['card']};
        }}
        QCheckBox::indicator:hover {{ border-color: {theme['accent']}; }}
        QCheckBox::indicator:checked {{
            background: {theme['accent']}; border-color: {theme['accent']};
        }}
    """
