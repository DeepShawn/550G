"""日志：写到用户目录 logs/app.log（轮转），并捕获未处理异常。"""
from __future__ import annotations

import logging
import logging.handlers
import platform
import sys
import threading
from pathlib import Path
from typing import Optional

from .version import APP_NAME, version_string

log = logging.getLogger("app")
_log_file: Optional[Path] = None


def log_file() -> Optional[Path]:
    return _log_file


def setup_logging(log_dir: Path, level: int = logging.INFO) -> Optional[Path]:
    global _log_file
    root = logging.getLogger()
    root.setLevel(level)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        _log_file = log_dir / "app.log"
        fh = logging.handlers.RotatingFileHandler(_log_file, maxBytes=512 * 1024, backupCount=3,
                                                  encoding="utf-8")
        fh.setFormatter(fmt)
        root.addHandler(fh)
    except OSError:
        _log_file = None
    if sys.stderr is not None:  # windowed 冻结包没有 stderr
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)
    log.info("%s %s 启动；Python %s；%s %s", APP_NAME, version_string(), platform.python_version(),
             platform.system(), platform.release())
    return _log_file


def install_excepthook(show_error) -> None:
    """show_error(title, text) 由 UI 层提供，用于弹出可读错误。"""

    def hook(exc_type, exc, tb):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("未处理异常", exc_info=(exc_type, exc, tb))
        try:
            where = f"\n\n日志：{_log_file}" if _log_file else ""
            show_error("桌宠出错了", f"{exc_type.__name__}: {exc}{where}")
        except Exception:  # noqa: BLE001 - 错误提示本身不能再抛
            pass

    sys.excepthook = hook
    threading.excepthook = lambda args: hook(args.exc_type, args.exc_value, args.exc_traceback)
