"""跟随主题配色的日历控件。"""

from typing import Optional

from PySide6.QtCore import QDate, QRect, Qt
from PySide6.QtGui import QColor, QPainter, QTextCharFormat
from PySide6.QtWidgets import QCalendarWidget, QToolButton, QWidget

from frontend.theme.palettes import Theme

_MONTH_YEAR_BUTTONS = ("qt_calendar_monthbutton", "qt_calendar_yearbutton")
_SELECTION_SHADOW_ALPHA = 105
_ADJACENT_MONTH_ALPHA = 85
# 一个日历页最多跨 6 周，前后各多留半个月足够覆盖相邻月份的格子
_PAGE_CELL_COUNT = 56
_PAGE_LEAD_DAYS = 14


class ThemedCalendar(QCalendarWidget):
    """选中日期用主题色圆角块 + 投影绘制，相邻月份弱化显示。"""

    def __init__(self, theme: Theme, parent: Optional[QWidget] = None) -> None:
        """
        Args:
            theme: 当前配色。
            parent: 父控件。
        """
        super().__init__(parent)
        self._theme = theme
        self.setVerticalHeaderFormat(QCalendarWidget.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.ShortDayNames)
        self.setGridVisible(False)
        self._flatten_navigation_buttons()
        self.currentPageChanged.connect(lambda *_: self.refresh_page_format())
        self.refresh_page_format()

    def paintCell(self, painter: QPainter, rect: QRect, date: QDate) -> None:  # noqa: N802
        """自绘选中态；非选中日期交给默认实现。"""
        if date != self.selectedDate():
            super().paintCell(painter, rect, date)
            return

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        accent = QColor(self._theme["accent"])

        shadow = QColor(accent)
        shadow.setAlpha(_SELECTION_SHADOW_ALPHA)
        painter.setPen(Qt.NoPen)
        painter.setBrush(shadow)
        painter.drawRoundedRect(rect.adjusted(2, 4, -2, -1), 9, 9)

        painter.setBrush(accent)
        painter.drawRoundedRect(rect.adjusted(3, 1, -3, -4), 8, 8)

        painter.setPen(QColor("#FFFFFF"))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(rect.adjusted(3, 0, -3, -3), Qt.AlignCenter, str(date.day()))
        painter.restore()

    def refresh_page_format(self) -> None:
        """弱化相邻月份日期、用主题色标出今天。"""
        muted_format = QTextCharFormat()
        muted_color = QColor(self._theme["sub"])
        muted_color.setAlpha(_ADJACENT_MONTH_ALPHA)
        muted_format.setForeground(muted_color)

        normal_format = QTextCharFormat()
        normal_format.setForeground(QColor(self._theme["text"]))

        month = self.monthShown()
        year = self.yearShown()
        cursor = QDate(year, month, 1).addDays(-_PAGE_LEAD_DAYS)
        for _ in range(_PAGE_CELL_COUNT):
            fmt = normal_format if cursor.month() == month else muted_format
            self.setDateTextFormat(cursor, fmt)
            cursor = cursor.addDays(1)

        today = QDate.currentDate()
        if today.year() == year and today.month() == month:
            today_format = QTextCharFormat()
            today_format.setForeground(QColor(self._theme["accent"]))
            today_format.setFontWeight(700)
            self.setDateTextFormat(today, today_format)

    def _flatten_navigation_buttons(self) -> None:
        """月/年按钮改成纯文字并去掉下拉箭头。

        默认样式带一个 ``˅`` 指示器，会让「七月」文字在垂直方向错位。
        """
        for button in self.findChildren(QToolButton):
            if button.objectName() in _MONTH_YEAR_BUTTONS:
                button.setToolButtonStyle(Qt.ToolButtonTextOnly)
                button.setPopupMode(QToolButton.InstantPopup)
                button.setArrowType(Qt.NoArrow)
