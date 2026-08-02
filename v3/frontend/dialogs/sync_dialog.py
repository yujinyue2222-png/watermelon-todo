"""多端同步设置弹窗。

同步码就是身份凭证：本机默认生成一串随机码，在另一台设备上填同一个码，
两边的待办就会自动合并。所以界面上把「复制同步码」做得最显眼。
"""

from __future__ import annotations

import datetime
import logging
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.core.constants import SYNC_TIMEOUT_SECONDS
from backend.models.app_config import SyncSettings
from backend.sync.client import SyncClient, SyncError
from backend.sync.identity import generate_sync_code, is_valid_sync_code
from frontend.theme.palettes import Theme
from frontend.theme.qss import dialog_qss

logger = logging.getLogger(__name__)

_CODE_ECHO_LENGTH = 6


@dataclass
class SyncDialogResult:
    """用户确认后的同步设置。"""

    settings: SyncSettings
    should_sync_now: bool = True


class _HealthWorker(QThread):
    """后台探测服务是否可用，避免点「测试连接」时界面卡住。

    Signals:
        succeeded: 探测成功，携带服务端概况文本。
        failed: 探测失败，携带原因。
    """

    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, server_url: str, access_token: str, parent=None) -> None:
        super().__init__(parent)
        self._server_url = server_url
        self._access_token = access_token

    def run(self) -> None:
        """执行一次健康检查。"""
        try:
            payload = SyncClient(self._server_url, self._access_token).health()
        except SyncError as exc:
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # noqa: BLE001
            # 兜底：异常逃出 run() 的话两个信号都不会发，
            # 状态栏会永远停在「正在连接…」
            logger.exception("健康检查出现未预期的异常")
            self.failed.emit(str(exc))
            return
        detail = (
            f"连接正常 · 服务端 v{payload.get('version', '?')}"
            f" · 已存 {payload.get('tasks', 0)} 条待办"
        )
        self.succeeded.emit(detail)


class SyncDialog(QDialog):
    """配置服务器地址与同步码。"""

    def __init__(
        self,
        theme: Theme,
        settings: SyncSettings,
        parent: Optional[QWidget] = None,
    ) -> None:
        """
        Args:
            theme: 当前配色。
            settings: 当前同步设置（不会被直接修改）。
            parent: 父窗口。
        """
        super().__init__(parent)
        self._theme = theme
        self._settings = settings
        self._worker: Optional[_HealthWorker] = None

        self.setWindowTitle("多端同步")
        self.setMinimumWidth(430)
        self.setStyleSheet(dialog_qss(theme))
        self._build()

    @classmethod
    def edit(
        cls,
        parent: QWidget,
        theme: Theme,
        settings: SyncSettings,
    ) -> Optional[SyncDialogResult]:
        """弹窗修改同步设置；取消返回 None。"""
        dialog = cls(theme, settings, parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.result_value

    @property
    def result_value(self) -> SyncDialogResult:
        """收集界面上的设置。"""
        updated = SyncSettings(
            enabled=self._enable_box.isChecked(),
            server_url=self._server_input.text().strip(),
            user_id=self._code_input.text().strip(),
            access_token=self._token_input.text().strip(),
            cursor=self._settings.cursor,
            last_sync_at=self._settings.last_sync_at,
            last_error=self._settings.last_error,
        )
        # 换了同步码等于换了一份数据，游标必须归零，否则会漏掉对方已有的历史
        if updated.user_id != self._settings.user_id:
            updated.cursor = 0
            updated.last_error = ""
        return SyncDialogResult(settings=updated, should_sync_now=updated.is_configured)

    # ------------------------------------------------------------------ 构建
    def _build(self) -> None:
        """搭出弹窗内容。"""
        body = QVBoxLayout(self)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(10)

        intro = QLabel(
            "在多台设备上填写同一个同步码，待办就会自动合并。\n"
            "断网时照常使用，联网后自动补齐。"
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color: {self._theme['sub']}; font-weight: normal;")
        body.addWidget(intro)

        self._enable_box = QCheckBox("启用多端同步")
        self._enable_box.setChecked(self._settings.enabled)
        body.addWidget(self._enable_box)

        body.addWidget(QLabel("服务器地址"))
        self._server_input = QLineEdit(self._settings.server_url)
        self._server_input.setPlaceholderText("http://47.120.58.231:52121")
        body.addWidget(self._server_input)

        body.addWidget(QLabel("同步码（换设备时把它抄过去）"))
        code_row = QHBoxLayout()
        code_row.setSpacing(8)
        self._code_input = QLineEdit(self._settings.user_id)
        self._code_input.setPlaceholderText("点右侧「生成」得到一个随机同步码")
        code_row.addWidget(self._code_input, 1)

        generate_button = QPushButton("生成")
        generate_button.setCursor(Qt.PointingHandCursor)
        generate_button.setToolTip("生成一个新的随机同步码")
        generate_button.clicked.connect(self._generate_code)
        code_row.addWidget(generate_button)

        copy_button = QPushButton("复制")
        copy_button.setCursor(Qt.PointingHandCursor)
        copy_button.setToolTip("复制同步码，去另一台设备粘贴")
        copy_button.clicked.connect(self._copy_code)
        code_row.addWidget(copy_button)
        body.addLayout(code_row)

        warning = QLabel("⚠ 同步码就是密码：谁拿到它就能读写你的待办，别公开分享。")
        warning.setWordWrap(True)
        warning.setStyleSheet(f"color: {self._theme['accent']}; font-weight: normal;")
        body.addWidget(warning)

        body.addWidget(QLabel("访问令牌（服务端未开启就留空）"))
        self._token_input = QLineEdit(self._settings.access_token)
        self._token_input.setPlaceholderText("可选")
        body.addWidget(self._token_input)

        status_row = QHBoxLayout()
        status_row.setSpacing(8)
        test_button = QPushButton("测试连接")
        test_button.setCursor(Qt.PointingHandCursor)
        test_button.clicked.connect(self._test_connection)
        status_row.addWidget(test_button)
        self._status_label = QLabel(self._initial_status())
        self._status_label.setWordWrap(True)
        self._status_label.setStyleSheet(
            f"color: {self._theme['sub']}; font-weight: normal;"
        )
        status_row.addWidget(self._status_label, 1)
        body.addLayout(status_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("保存")
        buttons.button(QDialogButtonBox.Cancel).setText("取消")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        body.addWidget(buttons)

    def _initial_status(self) -> str:
        """打开弹窗时显示的状态。"""
        if self._settings.last_error:
            return f"上次同步失败：{self._settings.last_error}"
        if self._settings.last_sync_at:
            moment = datetime.datetime.fromtimestamp(self._settings.last_sync_at / 1000)
            return f"上次同步：{moment:%Y-%m-%d %H:%M}"
        return "尚未同步过"

    # ------------------------------------------------------------------ 交互
    def _generate_code(self) -> None:
        """生成新的同步码。"""
        self._code_input.setText(generate_sync_code())
        self._status_label.setText("已生成新同步码，记得在其他设备上填同一个")

    def _copy_code(self) -> None:
        """把同步码复制到剪贴板。"""
        code = self._code_input.text().strip()
        if not code:
            self._status_label.setText("同步码还是空的")
            return
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            self._status_label.setText("剪贴板不可用")
            return
        clipboard.setText(code)
        self._status_label.setText(f"已复制（…{code[-_CODE_ECHO_LENGTH:]}）")

    def _test_connection(self) -> None:
        """探测服务器是否可用。"""
        server_url = self._server_input.text().strip()
        if not server_url:
            self._status_label.setText("请先填写服务器地址")
            return
        if self._worker is not None and self._worker.isRunning():
            return

        self._status_label.setText("正在连接…")
        worker = _HealthWorker(server_url, self._token_input.text().strip(), self)
        worker.succeeded.connect(self._status_label.setText)
        worker.failed.connect(lambda message: self._status_label.setText(f"连接失败：{message}"))
        worker.start()
        self._worker = worker

    def _on_accept(self) -> None:
        """校验后关闭。"""
        if not self._enable_box.isChecked():
            self.accept()  # 关掉同步时不必校验其余字段
            return
        server_url = self._server_input.text().strip()
        if not server_url:
            self._status_label.setText("请填写服务器地址")
            return
        # 少了协议头的地址会让 urllib 抛 ValueError，之后每次同步都在后台静默失败
        if not server_url.startswith(("http://", "https://")):
            self._status_label.setText("服务器地址需以 http:// 或 https:// 开头")
            return
        if not is_valid_sync_code(self._code_input.text().strip()):
            self._status_label.setText("同步码需为 6-64 位字母/数字/-/_，可点「生成」")
            return
        self.accept()

    def reject(self) -> None:
        """关闭前等后台探测线程收尾，避免窗口销毁后线程还在跑。"""
        if self._worker is not None and self._worker.isRunning():
            # 要等得比 HTTP 超时更久，否则线程还在跑对象就可能先被销毁
            self._worker.wait(SYNC_TIMEOUT_SECONDS * 1000 + 1000)
        super().reject()
