"""应用引导。

负责启动阶段那些「只做一次」的事：单实例检测、字体、图标、主窗口、
全局快捷键、后台检查更新。业务逻辑一律不放这里。
"""

from __future__ import annotations

import ctypes
import logging
from typing import Optional, Sequence

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMessageBox

from backend.api import TodoBackend
from backend.core.constants import (
    APP_NAME,
    APP_VERSION,
    SINGLE_INSTANCE_KEY,
    WINDOWS_APP_MUTEX,
)
from backend.core.platform_info import IS_MACOS, IS_WINDOWS
from backend.services.update_service import ReleaseInfo
from frontend.widgets.icons import app_icon
from frontend.windows.main_window import MainWindow

logger = logging.getLogger(__name__)

UPDATE_CHECK_DELAY_MS = 3000
_CONNECT_TIMEOUT_MS = 300
_SUMMON_FALLBACK_MS = 200

# 各平台自带的中文字体，避免缺字显示成方框
_FONT_FAMILIES = {
    "windows": ("微软雅黑", "Microsoft YaHei"),
    "macos": ("PingFang SC", "苹方-简", "Heiti SC", "STHeiti"),
    "linux": ("Noto Sans CJK SC", "WenQuanYi Micro Hei", "Sans Serif"),
}
_FONT_POINT_SIZE = 10


class UpdateCheckWorker(QThread):
    """后台线程里查询新版本。

    Signals:
        found: 发现新版本，携带 :class:`~backend.services.update_service.ReleaseInfo`。
    """

    found = Signal(object)

    def __init__(self, backend: TodoBackend, parent=None) -> None:
        super().__init__(parent)
        self._backend = backend

    def run(self) -> None:
        """执行检查；无更新或失败时什么都不做。"""
        release = self._backend.updates.check()
        if release is not None:
            self.found.emit(release)


def run_app(argv: Optional[Sequence[str]] = None) -> int:
    """启动图形界面。

    Args:
        argv: 命令行参数。

    Returns:
        进程退出码。
    """
    app = QApplication(list(argv or []))
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setWindowIcon(app_icon())
    # 关掉最后一个窗口不退出：点 ✕ 是缩到托盘
    app.setQuitOnLastWindowClosed(False)
    _claim_windows_mutex()
    _apply_font(app)

    server = _acquire_single_instance()
    if server is None:
        logger.info("已有实例在运行，唤起它并退出本次启动")
        return 0

    backend = TodoBackend()
    window = MainWindow(backend)
    window.show()
    window.register_hotkey()

    _bind_single_instance(server, window)
    if IS_MACOS:
        # macOS 上点 Dock 图标只会激活应用，Qt 不会自动把隐藏的窗口显示出来，
        # 这里补上，让 Dock 点击与托盘/悬浮球单击行为一致
        app.applicationStateChanged.connect(
            lambda state: _summon_if_hidden(window, state)
        )

    QTimer.singleShot(UPDATE_CHECK_DELAY_MS, lambda: _start_update_check(backend, window))
    return app.exec()


def _summon_if_hidden(window: MainWindow, state) -> None:
    """应用被激活且主窗口不可见时，把它召回前台。"""
    if state == Qt.ApplicationActive and not window.isVisible():
        window.summon_to_front()


def _apply_font(app: QApplication) -> None:
    """设置界面字体。"""
    if IS_WINDOWS:
        families = _FONT_FAMILIES["windows"]
    elif IS_MACOS:
        families = _FONT_FAMILIES["macos"]
    else:
        families = _FONT_FAMILIES["linux"]
    font = QFont()
    font.setFamilies(list(families))
    font.setPointSize(_FONT_POINT_SIZE)
    app.setFont(font)


def _claim_windows_mutex() -> None:
    """创建 Windows 命名互斥体。

    安装包（Inno Setup 的 ``AppMutex``）靠它判断程序是否在运行，
    覆盖安装时才能可靠地请求关闭旧版，避免卡在 “Closing applications...”。
    名称必须与打包脚本里的一致。
    """
    if not IS_WINDOWS:
        return
    try:
        # 存到模块属性上，防止被 GC 回收导致互斥体提前释放
        global _windows_mutex_handle
        _windows_mutex_handle = ctypes.windll.kernel32.CreateMutexW(
            None, False, WINDOWS_APP_MUTEX
        )
    except (AttributeError, OSError) as exc:
        logger.debug("创建命名互斥体失败：%s", exc)


def _acquire_single_instance() -> Optional[QLocalServer]:
    """单实例检测。

    用 QLocalServer/QLocalSocket 而不是共享内存：它能区分「真有实例在运行」
    （能连上）和「上次异常退出留下的死套接字」（连不上则清理重建），
    避免残留导致程序再也打不开。

    Returns:
        监听中的服务；已有实例在运行时返回 None（并已通知对方唤起窗口）。
    """
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_KEY)
    if probe.waitForConnected(_CONNECT_TIMEOUT_MS):
        probe.write(b"show")
        probe.flush()
        probe.waitForBytesWritten(_CONNECT_TIMEOUT_MS)
        probe.abort()
        return None
    probe.abort()

    QLocalServer.removeServer(SINGLE_INSTANCE_KEY)  # 清理可能残留的旧服务
    server = QLocalServer()
    if not server.listen(SINGLE_INSTANCE_KEY):
        logger.warning("单实例服务监听失败：%s", server.errorString())
    return server


def _bind_single_instance(server: QLocalServer, window: MainWindow) -> None:
    """再次启动程序时，把已运行的窗口召回前台。"""

    def on_new_connection() -> None:
        socket = server.nextPendingConnection()
        if socket is None:
            return

        def handle() -> None:
            socket.readAll()
            window.summon_to_front()
            socket.disconnectFromServer()

        socket.readyRead.connect(handle)
        # 兜底：即使没收到数据，稍后也召回一次
        QTimer.singleShot(_SUMMON_FALLBACK_MS, window.summon_to_front)

    server.newConnection.connect(on_new_connection)
    # 服务对象挂到窗口上，保证生命周期与窗口一致
    window._single_instance_server = server  # noqa: SLF001


def _start_update_check(backend: TodoBackend, window: MainWindow) -> None:
    """启动后台版本检查。"""
    worker = UpdateCheckWorker(backend, window)
    worker.found.connect(lambda release: _prompt_update(release, window))
    worker.start()
    # 保留引用，避免线程对象被回收
    window._update_worker = worker  # noqa: SLF001


def _prompt_update(release: ReleaseInfo, window: MainWindow) -> None:
    """提示有新版本可下载。"""
    text = f"发现新版本 {release.version}（当前 {APP_VERSION}）。\n\n是否前往下载页更新？"
    notes = release.short_notes()
    if notes:
        text += f"\n\n更新说明：\n{notes}"

    box = QMessageBox(window)
    box.setWindowTitle(f"{APP_NAME} · 检查更新")
    box.setIcon(QMessageBox.Information)
    box.setText(text)
    box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    box.button(QMessageBox.Yes).setText("去下载")
    box.button(QMessageBox.No).setText("以后再说")
    if box.exec() == QMessageBox.Yes:
        QDesktopServices.openUrl(QUrl(release.page_url))
