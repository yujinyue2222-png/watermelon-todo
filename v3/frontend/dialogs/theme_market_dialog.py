"""主题市场：卡片网格浏览配色，点一下立刻生效。"""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from frontend.dialogs.diy_color_dialog import DiyColorDialog
from frontend.dialogs.surface import build_surface, surface_body
from frontend.theme.qss import surface_dialog_qss
from frontend.theme.theme_manager import ThemeManager
from frontend.widgets.flow_layout import FlowLayout
from frontend.widgets.theme_card import ThemeCard


class ThemeMarketDialog(QDialog):
    """浏览并应用主题，同时提供 DIY 配色与背景图入口。"""

    def __init__(
        self,
        themes: ThemeManager,
        pick_background: Callable[[], None],
        clear_background: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            themes: 主题管理器。
            pick_background: 打开「选择背景图」的回调（涉及文件对话框，由主窗口提供）。
            clear_background: 清除背景图的回调。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._themes = themes
        self._pick_background = pick_background
        self._clear_background = clear_background
        self._cards: list[ThemeCard] = []

        self.setWindowTitle("主题市场")
        self.setMinimumSize(560, 480)
        self.setModal(True)
        self._build()
        self._apply_style()

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        """搭出弹窗内容。"""
        surface = build_surface(self, self._themes.current)
        body = surface_body(surface, spacing=12)

        body.addLayout(self._build_header())

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.NoFrame)
        self._rebuild_grid()
        body.addWidget(self._scroll, 1)

        body.addLayout(self._build_footer())

    def _build_header(self) -> QHBoxLayout:
        """标题 + 当前主题名。"""
        header = QHBoxLayout()
        header.setSpacing(8)

        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("🎨 主题市场")
        title.setObjectName("dialogTitle")
        subtitle = QLabel("点击卡片即时预览，选中后点「完成」即可")
        subtitle.setObjectName("dialogSubtitle")
        titles.addWidget(title)
        titles.addWidget(subtitle)
        header.addLayout(titles)
        header.addStretch()

        self._current_label = QLabel(f"当前：{self._themes.current_name}")
        header.addWidget(self._current_label, 0, Qt.AlignVCenter)
        return header

    def _build_footer(self) -> QHBoxLayout:
        """DIY / 背景图 / 完成。"""
        footer = QHBoxLayout()
        footer.setSpacing(8)

        diy_button = QPushButton("🎛  DIY 配色…")
        diy_button.setObjectName("ghost")
        diy_button.setCursor(Qt.PointingHandCursor)
        diy_button.clicked.connect(self._open_diy)
        footer.addWidget(diy_button)

        upload_button = QPushButton("🖼  上传背景图片…")
        upload_button.setObjectName("ghost")
        upload_button.setCursor(Qt.PointingHandCursor)
        upload_button.clicked.connect(self._on_pick_background)
        footer.addWidget(upload_button)

        self._clear_button = QPushButton("🗑  清除背景图片")
        self._clear_button.setObjectName("ghost")
        self._clear_button.setCursor(Qt.PointingHandCursor)
        self._clear_button.clicked.connect(self._on_clear_background)
        footer.addWidget(self._clear_button)
        footer.addStretch()

        done_button = QPushButton("完成")
        done_button.setCursor(Qt.PointingHandCursor)
        done_button.clicked.connect(self.accept)
        footer.addWidget(done_button)

        self._sync_clear_button()
        return footer

    def _rebuild_grid(self) -> None:
        """重建主题卡片网格。"""
        # 用 takeWidget 先把旧容器的所有权拿回来。直接 setWidget 的话 Qt 会
        # 顺手把旧 widget 删掉，之后再碰 previous 就是在用一个已析构的 C++ 对象
        previous = self._scroll.takeWidget()
        container = QWidget()
        container.setObjectName("themeGrid")
        grid = FlowLayout(container, margin=6, horizontal_spacing=14, vertical_spacing=14)

        self._cards = []
        for name in self._themes.showcase_names():
            card = ThemeCard(
                name=name,
                theme=self._themes.theme_of(name),
                selected=name == self._themes.current_name,
            )
            card.clicked.connect(self._apply_theme)
            self._cards.append(card)
            grid.addWidget(card)

        self._scroll.setWidget(container)
        if previous is not None:
            previous.deleteLater()

    # ------------------------------------------------------------------ 交互
    def _apply_theme(self, name: str) -> None:
        """应用某套主题并同步卡片选中态。"""
        self._themes.apply(name)
        for card in self._cards:
            card.set_selected(card.name == self._themes.current_name)
        self._current_label.setText(f"当前：{self._themes.current_name}")
        self._apply_style()

    def _open_diy(self) -> None:
        """打开 DIY 配色，关闭后刷新网格。"""
        DiyColorDialog(self._themes, self).exec()
        self._rebuild_grid()
        self._current_label.setText(f"当前：{self._themes.current_name}")
        self._apply_style()

    def _on_pick_background(self) -> None:
        """选择背景图。"""
        self._pick_background()
        self._sync_clear_button()

    def _on_clear_background(self) -> None:
        """清除背景图。"""
        self._clear_background()
        self._sync_clear_button()

    def _sync_clear_button(self) -> None:
        """没有背景图时禁用清除按钮。"""
        self._clear_button.setEnabled(bool(self._themes.background_image))

    def _apply_style(self) -> None:
        """主题变了，弹窗自身也要跟着换配色。"""
        theme = self._themes.current
        self.setStyleSheet(surface_dialog_qss(theme))
        self._current_label.setStyleSheet(
            f"color: {theme['accent']}; font-size: 12px; font-weight: bold;"
        )
