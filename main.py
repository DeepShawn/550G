"""550G × 前辈GPT Windows 双人桌宠 —— 启动入口。

开发运行：python main.py
常用参数：
  --version              打印版本后退出
  --data-dir DIR         使用指定目录保存配置与日志（测试/便携用）
  --reset-settings       忽略并覆盖已有配置
  --smoke-test REPORT    冒烟自检：启动、操作两只角色、写 JSON 报告后自动退出
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from pathlib import Path


def parse_args(argv):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("--version", action="store_true")
    ap.add_argument("--data-dir", type=Path)
    ap.add_argument("--reset-settings", action="store_true")
    ap.add_argument("--smoke-test", type=Path, metavar="REPORT")
    ap.add_argument("--smoke-seconds", type=float, default=4.0)
    # Qt 自己的参数（如 -platform）交给 QApplication
    return ap.parse_known_args(argv)


def main(argv=None) -> int:
    args, qt_args = parse_args(sys.argv[1:] if argv is None else argv)
    from app.version import APP_DISPLAY_NAME, APP_NAME, ORG_NAME, version_string

    if args.version:
        print(f"{APP_NAME} {version_string()}")
        return 0

    from PySide6.QtCore import QCoreApplication, QStandardPaths, Qt
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication, QMessageBox

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    QCoreApplication.setOrganizationName(ORG_NAME)
    QCoreApplication.setApplicationName(APP_NAME)
    QCoreApplication.setApplicationVersion(version_string())
    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setQuitOnLastWindowClosed(False)

    smoke = args.smoke_test is not None
    if args.data_dir:
        cfg_dir = log_dir = args.data_dir
    elif smoke:
        cfg_dir = log_dir = Path(tempfile.mkdtemp(prefix="pets550g-smoke-"))
    else:
        cfg_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppConfigLocation))
        log_dir = Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / "logs"

    from app import logging_setup
    log_path = logging_setup.setup_logging(log_dir)
    log = logging.getLogger("main")

    def show_error(title: str, text: str) -> None:
        log.error("%s: %s", title, text)
        if not smoke and QApplication.instance() is not None:
            QMessageBox.critical(None, title, text)

    logging_setup.install_excepthook(show_error)

    # ---- 单实例 ----
    from app.single_instance import SingleInstance
    inst = None
    if not smoke:
        inst = SingleInstance(APP_NAME, cfg_dir)
        r = inst.acquire()
        if r == "notified":
            return 0
        if r == "failed":
            show_error("无法启动", "另一个桌宠实例正在启动或无响应。请稍候再试；\n"
                                   "如仍失败，请在任务管理器结束 DesktopPets550G 后重新打开。")
            return 1

    # ---- 资源 ----
    from app import settings as settings_mod
    from app.assets import AssetError, load_manifest, resource_root
    from app.dialogues import load_dialogues
    try:
        manifest = load_manifest()
    except AssetError as e:
        show_error("资源缺失", f"{e}\n\n请重新解压完整的程序目录。")
        return 2
    root = resource_root()
    dialogues = load_dialogues(root / "dialogues.json")
    icon = QIcon(str(root / "tray.ico")) if (root / "tray.ico").is_file() else QIcon(str(root / "tray.png"))
    if icon.isNull():
        log.warning("托盘图标缺失：%s", root / "tray.ico")
    app.setWindowIcon(icon)

    settings_path = cfg_dir / "settings.json"
    st = settings_mod.Settings() if args.reset_settings else settings_mod.load(settings_path)
    if smoke:
        st.first_run_hint_shown = True

    from app.controller import AppController, env_force_no_tray
    try:
        ctl = AppController(app, manifest, st, settings_path, dialogues, icon, log_path=log_path,
                            force_no_tray=env_force_no_tray())
    except AssetError as e:
        show_error("资源缺失", f"{e}\n\n请重新解压完整的程序目录。")
        return 2
    if inst is not None:
        inst.on_show = ctl.show_all
    ctl.start()
    log.info("配置：%s；日志：%s；资源：%s", settings_path, log_path, root)

    if smoke:
        from PySide6.QtCore import QTimer
        report = {"ok": False}

        def run_smoke():
            report.update(_smoke_checks(ctl, settings_path))
            ctl.quit()

        QTimer.singleShot(int(args.smoke_seconds * 1000), run_smoke)
        code = app.exec()
        report["exit_code"] = code
        report["version"] = version_string()
        report["platform"] = QGuiApplication.platformName()
        args.smoke_test.parent.mkdir(parents=True, exist_ok=True)
        args.smoke_test.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report.get("ok") else 3

    code = app.exec()
    if inst is not None:
        inst.release()
    return code


def _smoke_checks(ctl, settings_path: Path) -> dict:
    """在真实事件循环中执行的自检。只证明程序逻辑可运行，不等于桌面实机验收。"""
    from app.pet_window import monotonic
    from app.state_machine import CUTE, IDLE, SLEEP
    checks = {}
    pets = ctl.pets
    checks["two_pets"] = len(pets) == 2
    checks["both_visible_at_start"] = all(p.isVisible() for p in pets)
    checks["required_frames_present"] = all(not p.frames.missing_required() for p in pets)
    checks["no_asset_problems"] = not ctl.asset_problems
    a, b = pets
    pb = b.pos()
    a.trigger_click()
    checks["click_cute_and_bubble"] = a.brain.state == CUTE and bool(a.brain.bubble_text)
    checks["click_independent"] = b.brain.state != CUTE or b.brain.state_started != a.brain.state_started
    b.set_state(SLEEP)
    b.trigger_click()
    checks["wake_from_sleep"] = b.brain.state == CUTE
    a.set_state(IDLE)
    ctl.hide_pet(a)
    checks["hide_one"] = not a.isVisible() and b.isVisible()
    ctl.show_all()
    checks["show_all"] = all(p.isVisible() for p in pets)
    ctl.set_scale(a, 1.25)
    checks["scale_change"] = abs(a.scale - 1.25) < 1e-6
    checks["positions_unchanged_by_click"] = b.pos() == pb
    checks["save_settings"] = ctl.save_now() and settings_path.is_file()
    checks["tray_or_panel"] = ctl.tray is not None or ctl.panel is not None
    checks["monotonic"] = monotonic() > 0
    return {"ok": all(checks.values()), "checks": checks,
            "entry": "tray" if ctl.tray is not None else "panel"}


if __name__ == "__main__":
    # 冻结包没有控制台时，sys.stdout/stderr 可能为 None
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")  # noqa: SIM115
    sys.exit(main())
