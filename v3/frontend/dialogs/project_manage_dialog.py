"""项目管理弹窗：重命名或删除整个项目。"""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.services.project_service import ProjectService
from frontend.theme.palettes import Theme
from frontend.theme.qss import dialog_qss


class ProjectManageDialog(QDialog):
    """列出全部项目，支持重命名与删除。

    改动会直接落到后端；调用方在弹窗关闭后刷新界面即可。
    """

    def __init__(
        self,
        theme: Theme,
        projects: ProjectService,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            projects: 项目服务。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._projects = projects
        self._changed = False
        self._renamed: dict[str, str] = {}
        self._deleted: list[str] = []

        self.setWindowTitle("管理项目")
        self.setMinimumWidth(360)
        self.setStyleSheet(dialog_qss(theme))
        self._build()

    @property
    def changed(self) -> bool:
        """是否发生了改动（调用方据此决定要不要刷新）。"""
        return self._changed

    @property
    def renamed(self) -> dict[str, str]:
        """本次重命名映射 ``{旧名: 新名}``。"""
        return dict(self._renamed)

    @property
    def deleted(self) -> list[str]:
        """本次被删除的项目名。"""
        return list(self._deleted)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        """搭出弹窗内容。"""
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(10)

        names = self._projects.names()
        if not names:
            body.addWidget(QLabel("暂无项目，先用「添加待办」新建吧～"))
            buttons = QDialogButtonBox(QDialogButtonBox.Ok)
            buttons.accepted.connect(self.accept)
            body.addWidget(buttons)
            return

        body.addWidget(QLabel("选中一个项目后可重命名或删除："))
        self._list = QListWidget()
        self._reload_list()
        body.addWidget(self._list)

        row = QHBoxLayout()
        rename_button = QPushButton("✎ 重命名")
        rename_button.setObjectName("secondarybtn")
        rename_button.clicked.connect(self._rename_selected)
        row.addWidget(rename_button, 1)

        delete_button = QPushButton("🗑 删除项目")
        delete_button.setObjectName("secondarybtn")
        delete_button.clicked.connect(self._delete_selected)
        row.addWidget(delete_button, 1)
        body.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

    def _reload_list(self) -> None:
        """按后端当前状态重建项目列表。"""
        self._list.clear()
        for name in self._projects.names():
            summary = self._projects.summary(name)
            item = QListWidgetItem(f"{name}   （{summary.done}/{summary.total}）")
            item.setData(Qt.UserRole, name)
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    # ------------------------------------------------------------------ 交互
    def _selected_project(self) -> Optional[str]:
        """当前选中的项目名。"""
        item = self._list.currentItem()
        return item.data(Qt.UserRole) if item is not None else None

    def _rename_selected(self) -> None:
        """重命名选中项目。"""
        name = self._selected_project()
        if not name:
            return
        new_name, confirmed = QInputDialog.getText(
            self, "重命名项目", "新的项目名称：", text=name
        )
        new_name = (new_name or "").strip()
        if not confirmed or not new_name or new_name == name:
            return
        if self._projects.rename(name, new_name):
            self._renamed[name] = new_name
            self._changed = True
            # 就地刷新而不是关窗：_renamed / _deleted 本就是设计成能装多条的，
            # 一次操作就 accept() 的话，改第二个项目还得把弹窗再打开一遍
            self._reload_list()

    def _delete_selected(self) -> None:
        """删除选中项目及其下全部待办。"""
        name = self._selected_project()
        if not name:
            return
        summary = self._projects.summary(name)
        confirm = QMessageBox(self)
        confirm.setWindowTitle("删除项目")
        confirm.setText(
            f"确定删除项目「{name}」吗？\n"
            f"该项目下 {summary.total} 条待办将一并删除，不可恢复。"
        )
        confirm.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        confirm.setDefaultButton(QMessageBox.No)
        if confirm.exec() != QMessageBox.Yes:
            return
        if self._projects.delete(name):
            self._deleted.append(name)
            self._changed = True
            self._reload_list()
