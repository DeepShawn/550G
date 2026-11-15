"""单实例：QLockFile 防止重复启动，QLocalServer 让第二次启动通知已有实例“显示全部”。

流程：
1. 先尝试连接本地服务器；连上就发送 show 并退出（已有实例负责恢复显示）。
2. 连不上则获取锁文件（QLockFile 依据 PID 自动处理陈旧锁）。
3. 拿到锁后清理残留的同名服务器并开始监听。
4. 若锁被占用但又连不上服务器（另一个实例正在启动），短暂重试后放弃并提示。
"""
from __future__ import annotations

import getpass
import hashlib
import logging
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QLockFile, QObject
from PySide6.QtNetwork import QLocalServer, QLocalSocket

log = logging.getLogger(__name__)

MSG_SHOW = b"show\n"


def server_name(app_name: str) -> str:
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = "user"
    h = hashlib.sha1(user.encode("utf-8", "replace")).hexdigest()[:10]
    return f"{app_name}-{h}"


def notify_existing(name: str, timeout_ms: int = 500) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(name)
    if not sock.waitForConnected(timeout_ms):
        return False
    sock.write(MSG_SHOW)
    sock.flush()
    sock.waitForBytesWritten(timeout_ms)
    sock.disconnectFromServer()
    return True


class SingleInstance(QObject):
    def __init__(self, app_name: str, lock_dir: Path, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.name = server_name(app_name)
        lock_dir.mkdir(parents=True, exist_ok=True)
        self.lock = QLockFile(str(lock_dir / f"{app_name}.lock"))
        self.lock.setStaleLockTime(0)  # 只按 PID 判断陈旧锁，不按时间
        self.server: Optional[QLocalServer] = None
        self.on_show: Optional[Callable[[], None]] = None

    def acquire(self, attempts: int = 6) -> str:
        """返回 'primary'（本实例负责运行）/'notified'（已通知旧实例）/'failed'。"""
        for i in range(attempts):
            if notify_existing(self.name):
                log.info("已有实例在运行，已通知其显示全部")
                return "notified"
            if self.lock.tryLock(200):
                QLocalServer.removeServer(self.name)  # 清理崩溃残留
                self.server = QLocalServer(self)
                self.server.setSocketOptions(QLocalServer.UserAccessOption)
                if not self.server.listen(self.name):
                    log.warning("本地服务器监听失败：%s", self.server.errorString())
                else:
                    self.server.newConnection.connect(self._on_connection)
                return "primary"
            if self.lock.error() == QLockFile.LockFailedError:
                # 可能是陈旧锁但 PID 被复用，或另一实例正在启动；尝试清理后重试
                if i >= 2:
                    self.lock.removeStaleLockFile()
            log.info("锁被占用，重试 %d/%d", i + 1, attempts)
        return "failed"

    def _on_connection(self) -> None:
        assert self.server is not None
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.readyRead.connect(lambda s=sock: self._read(s))
            sock.disconnected.connect(sock.deleteLater)
            if sock.bytesAvailable():
                self._read(sock)

    def _read(self, sock: QLocalSocket) -> None:
        data = bytes(sock.readAll())
        if MSG_SHOW.strip() in data and self.on_show:
            log.info("收到第二次启动请求，显示全部")
            self.on_show()

    def release(self) -> None:
        if self.server:
            self.server.close()
        if self.lock.isLocked():
            self.lock.unlock()
