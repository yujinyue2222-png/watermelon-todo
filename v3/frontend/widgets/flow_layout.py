"""自动换行的流式布局。"""

from typing import Optional

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout, QLayoutItem, QWidget


class FlowLayout(QLayout):
    """标签放不下时自动换到下一行，避免撑爆父容器。

    用于任务卡片上的标签区（分类/截止/循环/提醒）与主题市场的卡片网格。
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        margin: int = 0,
        horizontal_spacing: int = 6,
        vertical_spacing: int = 4,
    ) -> None:
        """
        Args:
            parent: 父控件。
            margin: 四周留白。
            horizontal_spacing: 同一行内相邻项的间距。
            vertical_spacing: 行间距。
        """
        super().__init__(parent)
        self._items: list[QLayoutItem] = []
        self._horizontal_spacing = horizontal_spacing
        self._vertical_spacing = vertical_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    # -------------------------------------------------- QLayout 必须实现的接口
    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 (Qt 命名)
        """加入一个布局项。"""
        self._items.append(item)

    def count(self) -> int:
        """布局项数量。"""
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        """取第 index 个布局项。"""
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        """移除并返回第 index 个布局项。"""
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:  # noqa: N802
        """不主动扩展。"""
        return Qt.Orientations(Qt.Orientation(0))

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        """高度依赖宽度。"""
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        """给定宽度下需要的高度。"""
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        """实际摆放子项。"""
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QSize:  # noqa: N802
        """建议尺寸。"""
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        """最小尺寸。"""
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(
            margins.left() + margins.right(), margins.top() + margins.bottom()
        )
        return size

    # ------------------------------------------------------------------ 内部
    def _do_layout(self, rect: QRect, test_only: bool) -> int:
        """逐项摆放并在越界时换行。

        Args:
            rect: 可用区域。
            test_only: 为 True 时只计算高度、不真正移动控件。

        Returns:
            布局占用的总高度（含上下边距）。
        """
        # 必须把边距抠掉再摆放：minimumSize() 已经把边距算进去了，
        # 这里不算的话两边对不上，控件会贴边、报出的高度也会偏小被裁掉
        margins = self.contentsMargins()
        area = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x = area.x()
        y = area.y()
        line_height = 0
        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + self._horizontal_spacing
            if next_x - self._horizontal_spacing > area.right() and line_height > 0:
                x = area.x()
                y += line_height + self._vertical_spacing
                next_x = x + hint.width() + self._horizontal_spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()
