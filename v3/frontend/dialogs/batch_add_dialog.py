"""项目待办的添加弹窗。

两个分页：

- **批量粘贴**：一行一条，支持从 Excel 直接粘贴，实时显示解析结果；
- **单个填写**：一条待办配齐截止时间与备注。

两页数据互相隔离，切来切去不会丢已输入的内容。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.models.enums import Priority
from backend.services.batch_parser import parse_batch_text
from backend.services.task_service import TaskDraft
from frontend.dialogs.due_picker_dialog import DuePickerDialog, Schedule
from frontend.theme.palettes import Theme
from frontend.theme.qss import dialog_qss, note_editor_qss, preview_box_qss
from frontend.widgets.combo_box import ThemedComboBox

NEW_PROJECT_LABEL = "➕ 新建项目…"

_PASTE_PLACEHOLDER = (
    "示例：\n"
    "完成周报｜P1｜08-05｜补充关键数据\n"
    "对齐需求｜明天\n"
    "评审设计稿\n"
    "每行一条待办，竖线分隔：内容｜优先级｜日期｜备注"
)
_PREVIEW_EMPTY_HINT = "（在上方输入后这里显示解析结果）"
_PASTE_HEIGHT = 150
_PREVIEW_HEIGHT = 96
_NOTE_HEIGHT = 90


@dataclass
class BatchAddResult:
    """添加弹窗的结果。"""

    project: str
    drafts: list[TaskDraft] = field(default_factory=list)
    from_batch_tab: bool = True


@dataclass
class FormMemory:
    """上次使用的分类与紧急程度，下次打开时自动回填。"""

    category: str = ""
    priority: str = ""


class DuplicateChoice:
    """检测到重名待办时用户的选择。"""

    SKIP = "skip"
    ADD = "add"
    CANCEL = "cancel"

    @classmethod
    def ask(cls, parent: QWidget, theme: Theme, count: int) -> str:
        """弹出三选一确认框。

        Args:
            parent: 父窗口。
            theme: 当前配色。
            count: 重名条数。

        Returns:
            :data:`SKIP`、:data:`ADD` 或 :data:`CANCEL`。
        """
        dialog = QDialog(parent)
        dialog.setWindowTitle("检测到重复")
        dialog.setStyleSheet(dialog_qss(theme))
        dialog.setMinimumWidth(300)

        body = QVBoxLayout(dialog)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(12)

        message = QLabel(f"检测到 {count} 条与现有待办同名，如何处理？")
        message.setWordWrap(True)
        message.setStyleSheet(f"color: {theme['text']};")
        body.addWidget(message)

        chosen = {"value": cls.CANCEL}
        row = QHBoxLayout()
        row.setSpacing(8)
        for label, value in (("跳过重复", cls.SKIP), ("继续新增", cls.ADD), ("取消", cls.CANCEL)):
            button = QPushButton(label)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(
                lambda _=False, picked=value: (
                    chosen.update(value=picked),
                    dialog.accept(),
                )
            )
            row.addWidget(button, 1)
        body.addLayout(row)

        dialog.exec()
        return chosen["value"]


class BatchAddDialog(QDialog):
    """给项目批量或单条添加待办。"""

    def __init__(
        self,
        theme: Theme,
        categories: Sequence[str],
        existing_projects: Sequence[str],
        active_project: str = "",
        memory: Optional[FormMemory] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            categories: 可选分类。
            existing_projects: 已有项目名。
            active_project: 当前正在看的项目，默认选中它。
            memory: 上次的分类/紧急程度。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._memory = memory or FormMemory()
        self._single_schedule = Schedule()

        self.setWindowTitle("添加待办")
        self.setMinimumWidth(380)
        self.setStyleSheet(dialog_qss(theme))
        self._build(categories, existing_projects, active_project)

    # ------------------------------------------------------------------ 结果
    @property
    def project_name(self) -> str:
        """用户选择或新建的项目名。"""
        if self._project_picker.currentText() == NEW_PROJECT_LABEL:
            return self._new_project_input.text().strip()
        return self._project_picker.currentText().strip()

    @property
    def memory(self) -> FormMemory:
        """本次使用的分类与紧急程度，供下次打开回填。"""
        return FormMemory(
            category=self._category_picker.currentText(),
            priority=self._priority_picker.currentText(),
        )

    def collect(self) -> BatchAddResult:
        """把界面内容整理成待创建的待办列表。

        Returns:
            结果对象；``drafts`` 为空说明用户没填有效内容。
        """
        project = self.project_name
        category = self._category_picker.currentText()
        priority = self._priority_picker.currentText()
        from_batch = self._tabs.currentIndex() == 0

        if not from_batch:
            text = self._single_text_input.text().strip()
            drafts = []
            if text:
                drafts.append(
                    TaskDraft(
                        text=text,
                        category=category,
                        due=self._single_schedule.due,
                        priority=priority,
                        recur=self._single_schedule.recur,
                        recur_end=self._single_schedule.recur_end,
                        remind=self._single_schedule.remind,
                        note=self._single_note_input.toPlainText().strip(),
                        project=project,
                    )
                )
            return BatchAddResult(project=project, drafts=drafts, from_batch_tab=False)

        drafts = [
            TaskDraft(
                text=parsed.text,
                category=category,
                due=parsed.due,
                priority=parsed.priority or priority,
                note=parsed.note,
                project=project,
            )
            for parsed in parse_batch_text(self._paste_input.toPlainText())
        ]
        return BatchAddResult(project=project, drafts=drafts, from_batch_tab=True)

    # ------------------------------------------------------------------ 构建
    def _build(
        self,
        categories: Sequence[str],
        existing_projects: Sequence[str],
        active_project: str,
    ) -> None:
        """搭出弹窗内容。"""
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(10)

        body.addWidget(QLabel("项目名称"))
        body.addWidget(self._build_project_picker(existing_projects, active_project))
        body.addWidget(self._new_project_input)
        self._sync_new_project_visibility()

        body.addLayout(self._build_pickers(categories))

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_paste_page(), "📥 批量粘贴")
        self._tabs.addTab(self._build_single_page(), "✏️ 单个填写")
        self._tabs.setCurrentIndex(0)
        body.addWidget(self._tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("添加")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

    def _build_project_picker(
        self,
        existing_projects: Sequence[str],
        active_project: str,
    ) -> QWidget:
        """项目名：下拉选已有，或选「新建」后展开输入框。"""
        self._project_picker = ThemedComboBox()
        self._project_picker.addItem(NEW_PROJECT_LABEL)
        self._project_picker.addItems(list(existing_projects))

        self._new_project_input = QLineEdit()
        self._new_project_input.setPlaceholderText("输入新项目名，例如：2026-W30 本周项目")

        if active_project and active_project in existing_projects:
            self._project_picker.setCurrentText(active_project)
        elif existing_projects:
            self._project_picker.setCurrentIndex(1)

        self._project_picker.currentIndexChanged.connect(
            lambda _=None: self._sync_new_project_visibility()
        )
        return self._project_picker

    def _build_pickers(self, categories: Sequence[str]) -> QHBoxLayout:
        """分类 + 紧急程度（带上次记忆）。"""
        row = QHBoxLayout()
        row.setSpacing(10)

        category_column = QVBoxLayout()
        category_column.setSpacing(4)
        category_column.addWidget(QLabel("分类"))
        self._category_picker = ThemedComboBox()
        self._category_picker.addItems(list(categories))
        if self._memory.category in categories:
            self._category_picker.setCurrentText(self._memory.category)
        category_column.addWidget(self._category_picker)
        row.addLayout(category_column, 1)

        priority_column = QVBoxLayout()
        priority_column.setSpacing(4)
        priority_column.addWidget(QLabel("紧急程度"))
        self._priority_picker = ThemedComboBox()
        self._priority_picker.addItems(list(Priority.ORDER))
        self._priority_picker.setCurrentText(
            self._memory.priority
            if self._memory.priority in Priority.ORDER
            else Priority.DEFAULT
        )
        priority_column.addWidget(self._priority_picker)
        row.addLayout(priority_column, 1)
        return row

    def _build_paste_page(self) -> QWidget:
        """批量粘贴分页。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        self._paste_input = QTextEdit()
        self._paste_input.setPlaceholderText(_PASTE_PLACEHOLDER)
        self._paste_input.setMinimumHeight(_PASTE_HEIGHT)
        self._paste_input.setTabChangesFocus(True)
        self._paste_input.textChanged.connect(self._refresh_preview)
        layout.addWidget(self._paste_input)

        hint = QLabel(
            "格式：内容 | 优先级 | 日期 | 备注（后三项都可省略）\n"
            "· 优先级：" + " / ".join(Priority.ORDER) + "\n"
            "· 日期：08-05、2026-08-05、明天、周五 等\n"
            "· 第2列不是优先级词时当备注；支持从 Excel 直接粘贴（Tab 分列）"
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {self._theme['sub']}; font-weight: normal;")
        layout.addWidget(hint)

        layout.addWidget(QLabel("解析预览"))
        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setFixedHeight(_PREVIEW_HEIGHT)
        self._preview.setStyleSheet(preview_box_qss(self._theme))
        layout.addWidget(self._preview)

        self._priority_picker.currentTextChanged.connect(
            lambda _=None: self._refresh_preview()
        )
        self._refresh_preview()
        return page

    def _build_single_page(self) -> QWidget:
        """单个填写分页。"""
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("待办内容"))
        self._single_text_input = QLineEdit()
        self._single_text_input.setPlaceholderText("这条待办要做什么？")
        layout.addWidget(self._single_text_input)

        layout.addWidget(QLabel("截止日期"))
        due_row = QHBoxLayout()
        due_row.setSpacing(8)
        self._single_due_button = QPushButton("📅  点击选择日期")
        self._single_due_button.setCursor(Qt.PointingHandCursor)
        self._single_due_button.clicked.connect(self._pick_single_schedule)
        due_row.addWidget(self._single_due_button, 1)

        clear_button = QPushButton("清除")
        clear_button.setCursor(Qt.PointingHandCursor)
        clear_button.clicked.connect(self._clear_single_due)
        due_row.addWidget(clear_button)
        layout.addLayout(due_row)

        layout.addWidget(QLabel("备注（可选）"))
        self._single_note_input = QTextEdit()
        self._single_note_input.setPlaceholderText("记录进行中的注意事项…")
        self._single_note_input.setFixedHeight(_NOTE_HEIGHT)
        self._single_note_input.setStyleSheet(note_editor_qss(self._theme))
        layout.addWidget(self._single_note_input)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ 交互
    def _sync_new_project_visibility(self) -> None:
        """只有选了「新建项目」才展开输入框。"""
        self._new_project_input.setVisible(
            self._project_picker.currentText() == NEW_PROJECT_LABEL
        )

    def _pick_single_schedule(self) -> None:
        """单条待办的日期弹窗。"""
        picked = DuePickerDialog.pick(self, self._theme, self._single_schedule)
        if picked is None:
            return
        self._single_schedule = picked
        self._single_due_button.setText(
            f"📅  {picked.due}" if picked.due else "📅  点击选择日期"
        )

    def _clear_single_due(self) -> None:
        """清除单条待办的截止日期。"""
        self._single_schedule.due = ""
        self._single_due_button.setText("📅  点击选择日期")

    def _refresh_preview(self) -> None:
        """实时展示批量文本的解析结果。"""
        default_priority = self._priority_picker.currentText()
        lines = []
        for parsed in parse_batch_text(self._paste_input.toPlainText()):
            segments = [parsed.text, parsed.priority or f"{default_priority}(默认)"]
            if parsed.due:
                segments.append("📅" + parsed.due)
            if parsed.note:
                segments.append("📝" + parsed.note)
            lines.append("· " + "　".join(segments))

        if lines:
            self._preview.setPlainText(f"共 {len(lines)} 条：\n" + "\n".join(lines))
        else:
            self._preview.setPlainText(_PREVIEW_EMPTY_HINT)
