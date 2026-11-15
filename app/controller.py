"""应用控制器：两只角色、托盘/控制窗口、菜单路由、位置持久化、多屏校验与退出。"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, QPoint, QTimer
from PySide6.QtGui import QAction, QActionGroup, QGuiApplication, QIcon
from PySide6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton,
                               QSystemTrayIcon, QVBoxLayout, QWidget)

from . import geometry
from . import settings as settings_mod
from .assets import Manifest
from .dialogues import DialoguePool
from .frames import FrameSet
from .pet_window import PetWindow, monotonic
from .state_machine import BLINK, CUTE, IDLE, SLEEP, PetBrain, TimingConfig
from .version import APP_DISPLAY_NAME, version_string

log = logging.getLogger(__name__)

STATE_LABELS = [(IDLE, "待机"), (BLINK, "眨眼"), (CUTE, "卖萌"), (SLEEP, "睡觉")]
SCALE_LABELS = [(0.75, "小 (75%)"), (1.0, "中 (100%)"), (1.25, "大 (125%)"), (1.5, "特大 (150%)")]

FALLBACK_LINES = {"greeting": ["你好！"], "click": ["……嗯？"], "cute": ["嘿嘿。"],
                  "sleep": ["Zzz……"], "wake": ["醒啦。"]}


class ControlPanel(QWidget):
    """系统托盘不可用时的常驻控制窗口（普通窗口，出现在任务栏），保证总有恢复入口。"""

    def __init__(self, ctl: "AppController"):
        super().__init__(None)
        self.ctl = ctl
        self.setWindowTitle(f"{APP_DISPLAY_NAME} · 控制")
        lay = QVBoxLayout(self)
        tip = QLabel("系统托盘不可用，使用此窗口控制桌宠。\n关闭此窗口会最小化，不会退出。")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        row = QHBoxLayout()
        for text, fn in (("显示全部", ctl.show_all), ("隐藏全部", ctl.hide_all),
                         ("恢复位置", ctl.restore_all_positions)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row.addWidget(b)
        lay.addLayout(row)
        row2 = QHBoxLayout()
        for text, fn in (("关于", ctl.show_about), ("退出", ctl.quit)):
            b = QPushButton(text)
            b.clicked.connect(fn)
            row2.addWidget(b)
        lay.addLayout(row2)
        self.setWindowIcon(ctl.icon)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.ctl.quitting:
            e.accept()
            return
        e.ignore()
        self.showMinimized()


class AppController(QObject):
    def __init__(self, app: QApplication, manifest: Manifest, settings: settings_mod.Settings,
                 settings_path: Path, dialogues: Dict[str, DialoguePool], icon: QIcon,
                 log_path: Optional[Path] = None, force_no_tray: bool = False):
        super().__init__(app)
        self.app = app
        self.manifest = manifest
        self.settings = settings
        self.settings_path = settings_path
        self.log_path = log_path
        self.icon = icon
        self.quitting = False
        self.timing = TimingConfig.from_dict(manifest.animation)
        self._configured_sleep = self.timing.sleep_after_inactivity
        float_px = float(manifest.animation.get("idle_float_logical_px", 2.5))

        self.pets: List[PetWindow] = []
        self.asset_problems: List[str] = []
        for spec in manifest.pets:
            frames = FrameSet(spec)  # idle 缺失时抛出 AssetError，由 main 报告
            self.asset_problems.extend(frames.problems)
            brain = PetBrain(timing=TimingConfig.from_dict(manifest.animation), now=monotonic())
            pool = dialogues.get(spec.id) or DialoguePool(FALLBACK_LINES)
            ps = settings.pet(spec.id)
            pet = PetWindow(spec, frames, brain, pool, scale=ps.scale, float_px=float_px)
            pet.drag_finished.connect(self.schedule_save)
            pet.menu_requested.connect(lambda pos, p=pet: self._pet_menus[p.spec.id].popup(pos))
            pet.visibility_changed.connect(lambda _v: self._refresh_menus())
            self.pets.append(pet)
        self.apply_auto_sleep(settings.auto_sleep)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(600)
        self._save_timer.timeout.connect(self.save_now)

        self._revalidate_timer = QTimer(self)
        self._revalidate_timer.setSingleShot(True)
        self._revalidate_timer.setInterval(400)
        self._revalidate_timer.timeout.connect(self.revalidate_positions)

        # 菜单与动作需要稳定的生命周期：全部挂在 self 上，避免被回收
        self._pet_menus: Dict[str, QMenu] = {p.spec.id: self._build_pet_menu(p) for p in self.pets}
        self.tray: Optional[QSystemTrayIcon] = None
        self.panel: Optional[ControlPanel] = None
        tray_ok = QSystemTrayIcon.isSystemTrayAvailable() and not force_no_tray
        if tray_ok:
            self._build_tray()
        else:
            log.warning("系统托盘不可用，改用控制窗口")
            self.panel = ControlPanel(self)

        app.screenAdded.connect(self._on_screen_added)
        app.screenRemoved.connect(lambda _s: self._revalidate_timer.start())
        app.primaryScreenChanged.connect(lambda _s: self._revalidate_timer.start())
        for s in app.screens():
            s.availableGeometryChanged.connect(lambda _g: self._revalidate_timer.start())
        app.aboutToQuit.connect(self._on_about_to_quit)

    # ------------------------------------------------------------------ 启动
    def start(self) -> None:
        self.place_initial()
        for pet in self.pets:
            pet.show()
            pet.say(pet.dialogues.pick("greeting"))
        if self.panel is not None:
            self.panel.show()
        if self.asset_problems:
            log.warning("资源问题：%s", "；".join(self.asset_problems))
        if not self.settings.first_run_hint_shown:
            QTimer.singleShot(1500, self._first_run_hint)

    def _first_run_hint(self) -> None:
        if self.tray is not None:
            self.tray.showMessage(
                APP_DISPLAY_NAME,
                "左键点击说话，按住拖动；右键角色打开菜单。\n"
                "隐藏后可在任务栏托盘（或“显示隐藏的图标”^ 区域）找回，双击托盘图标显示两只。",
                self.icon, 8000)
        self.settings.first_run_hint_shown = True
        self.schedule_save()

    def _screens(self) -> List[tuple]:
        return [_rect_t(s.availableGeometry()) for s in QGuiApplication.screens()]

    def _primary(self) -> tuple:
        ps = QGuiApplication.primaryScreen()
        return _rect_t(ps.availableGeometry()) if ps else (0, 0, 1280, 720)

    def default_char_pos(self, pet: PetWindow) -> QPoint:
        idx = self.pets.index(pet)
        size = (max(p.win_w for p in self.pets), max(p.char_h for p in self.pets))
        x, y = geometry.default_position(idx, size, self._primary(), spacing=0, count=len(self.pets))
        # default_position 以窗口宽排布，这里换算成角色区域坐标
        return QPoint(x + pet.side_pad + (size[0] - pet.win_w) // 2, y + (size[1] - pet.char_h))

    def place_initial(self) -> None:
        screens, primary = self._screens(), self._primary()
        for pet in self.pets:
            ps = self.settings.pet(pet.spec.id)
            fb = self.default_char_pos(pet)
            if ps.x is None or ps.y is None:
                pet.set_char_pos(fb)
                continue
            rect = (ps.x, ps.y, pet.char_w, pet.char_h)
            x, y = geometry.ensure_visible(rect, screens, primary, (fb.x(), fb.y()))
            if (x, y) != (ps.x, ps.y):
                log.info("%s 保存的位置不可见，已移回主屏", pet.spec.name)
            pet.set_char_pos(QPoint(x, y))

    def revalidate_positions(self) -> None:
        """显示器拔插/工作区变化后，把不可见的角色移回主屏。"""
        screens, primary = self._screens(), self._primary()
        moved = False
        for pet in self.pets:
            fb = self.default_char_pos(pet)
            x, y = geometry.ensure_visible(pet.char_rect(), screens, primary, (fb.x(), fb.y()))
            if (x, y) != pet.char_rect()[:2]:
                pet.set_char_pos(QPoint(x, y))
                moved = True
        if moved:
            log.info("显示器布局变化，已重新校验角色位置")
            self.schedule_save()

    def _on_screen_added(self, screen) -> None:
        screen.availableGeometryChanged.connect(lambda _g: self._revalidate_timer.start())
        self._revalidate_timer.start()

    # ------------------------------------------------------------------ 动作
    def other_pets(self, pet: PetWindow) -> List[PetWindow]:
        return [p for p in self.pets if p is not pet]

    def show_pet(self, pet: PetWindow) -> None:
        if not pet.isVisible():
            fb = self.default_char_pos(pet)
            x, y = geometry.ensure_visible(pet.char_rect(), self._screens(), self._primary(), (fb.x(), fb.y()))
            pet.set_char_pos(QPoint(x, y))
            pet.show()
        pet.raise_()

    def can_hide_last_entry(self) -> bool:
        """托盘和控制窗口都没有时，禁止隐藏最后一只可见角色。"""
        return self.tray is not None or self.panel is not None

    def hide_pet(self, pet: PetWindow) -> None:
        visible = [p for p in self.pets if p.isVisible()]
        if visible == [pet] and not self.can_hide_last_entry():
            return
        pet.hide()
        self._maybe_hint_hidden()

    def show_all(self) -> None:
        for p in self.pets:
            self.show_pet(p)

    def hide_all(self) -> None:
        if not self.can_hide_last_entry():
            return
        for p in self.pets:
            p.hide()
        self._maybe_hint_hidden()

    def _maybe_hint_hidden(self) -> None:
        if self.tray is not None and not any(p.isVisible() for p in self.pets):
            self.tray.showMessage(APP_DISPLAY_NAME, "桌宠已隐藏。双击托盘图标或在托盘菜单中选择“显示全部”。",
                                  self.icon, 4000)

    def restore_position(self, pet: PetWindow) -> None:
        pet.set_char_pos(self.default_char_pos(pet))
        self.show_pet(pet)
        self.schedule_save()

    def restore_all_positions(self) -> None:
        for p in self.pets:
            self.restore_position(p)

    def set_scale(self, pet: PetWindow, scale: float) -> None:
        pet.set_scale(scale)
        self.settings.pet(pet.spec.id).scale = scale
        self.schedule_save()

    def apply_auto_sleep(self, enabled: bool) -> None:
        self.settings.auto_sleep = enabled
        for p in self.pets:
            p.brain.timing.sleep_after_inactivity = self._configured_sleep if enabled else 0
            p.brain.last_interaction = monotonic()

    # ------------------------------------------------------------------ 菜单
    def _add_pet_actions(self, menu: QMenu, pet: PetWindow) -> None:
        menu.addAction("说句话", pet.trigger_click)
        sm = menu.addMenu("表情 / 动作")
        for st, label in STATE_LABELS:
            sm.addAction(label, lambda st=st, p=pet: p.set_state(st))
        zm = menu.addMenu("大小")
        group = QActionGroup(zm)
        group.setExclusive(True)
        for sc, label in SCALE_LABELS:
            a = zm.addAction(label)
            a.setCheckable(True)
            a.setData(sc)
            group.addAction(a)
            a.triggered.connect(lambda _c=False, sc=sc, p=pet: self.set_scale(p, sc))
        zm.aboutToShow.connect(lambda zm=zm, p=pet: [a.setChecked(abs(a.data() - p.scale) < 1e-6)
                                                      for a in zm.actions()])
        zm._group = group  # type: ignore[attr-defined]  # 持有引用

    def _build_pet_menu(self, pet: PetWindow) -> QMenu:
        m = QMenu()
        title = m.addAction(f"{pet.spec.name}  ·  {pet.spec.subtitle}")
        title.setEnabled(False)
        m.addSeparator()
        self._add_pet_actions(m, pet)
        m.addSeparator()
        m.addAction("隐藏这只", lambda p=pet: self.hide_pet(p))
        others: List[QAction] = []
        for o in self.other_pets(pet):
            a = m.addAction(f"显示 {o.spec.name}", lambda o=o: self.show_pet(o))
            a.setData(o.spec.id)
            others.append(a)
        m.addAction("显示全部", self.show_all)
        m.addAction("恢复位置", lambda p=pet: self.restore_position(p))
        m.addSeparator()
        m.addAction("关于…", self.show_about)
        m.addAction("退出桌宠", self.quit)

        def refresh():
            for a in others:
                o = next(p for p in self.pets if p.spec.id == a.data())
                a.setEnabled(not o.isVisible())
        m.aboutToShow.connect(refresh)
        return m

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip(f"{APP_DISPLAY_NAME} {version_string()}")
        m = QMenu()
        self._tray_toggle: Dict[str, QAction] = {}
        for pet in self.pets:
            sm = m.addMenu(pet.spec.name)
            t = sm.addAction("隐藏", lambda p=pet: self.hide_pet(p) if p.isVisible() else self.show_pet(p))
            self._tray_toggle[pet.spec.id] = t
            sm.addAction("恢复位置", lambda p=pet: self.restore_position(p))
            sm.addSeparator()
            self._add_pet_actions(sm, pet)
        m.addSeparator()
        m.addAction("显示全部", self.show_all)
        m.addAction("隐藏全部", self.hide_all)
        m.addAction("恢复主屏位置", self.restore_all_positions)
        m.addSeparator()
        self._auto_sleep_action = m.addAction("空闲自动睡觉")
        self._auto_sleep_action.setCheckable(True)
        self._auto_sleep_action.setChecked(self.settings.auto_sleep)
        self._auto_sleep_action.toggled.connect(lambda on: (self.apply_auto_sleep(on), self.schedule_save()))
        m.addSeparator()
        m.addAction("关于…", self.show_about)
        m.addAction("退出", self.quit)
        m.aboutToShow.connect(self._refresh_menus)
        self._tray_menu = m
        self.tray.setContextMenu(m)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _refresh_menus(self) -> None:
        if self.tray is None:
            return
        for pet in self.pets:
            self._tray_toggle[pet.spec.id].setText("隐藏" if pet.isVisible() else "显示")

    def _on_tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            # 单击/双击托盘都显示全部（Windows 上单击更符合直觉）
            self.show_all()

    def show_about(self) -> None:
        cfg = self.settings_path
        lines = [
            f"{APP_DISPLAY_NAME}",
            f"版本 {version_string()}",
            "",
            "双角色 · 透明置顶 · 独立拖动 · 点击对白 · 待机/眨眼/卖萌/睡觉",
            "离线预设对白，不联网，不读取你的文件。",
            "",
            f"配置：{cfg}",
            f"日志：{self.log_path or '（不可用）'}",
        ]
        if any(p.spec.placeholder for p in self.manifest.pets):
            lines += ["", "注意：当前角色图为程序生成的工程占位素材，正式高清立绘尚未完成。"]
        QMessageBox.information(None, "关于", "\n".join(lines))

    # ------------------------------------------------------------------ 持久化/退出
    def schedule_save(self) -> None:
        self._save_timer.start()

    def save_now(self) -> bool:
        for pet in self.pets:
            ps = self.settings.pet(pet.spec.id)
            x, y, _w, _h = pet.char_rect()
            ps.x, ps.y, ps.scale = x, y, pet.scale
        return settings_mod.save(self.settings, self.settings_path)

    def quit(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        log.info("退出")
        self._save_timer.stop()
        for p in self.pets:
            p.timer.stop()
        self.save_now()
        if self.tray is not None:
            self.tray.hide()
        for p in self.pets:
            p.close()
        if self.panel is not None:
            self.panel.close()
        self.app.quit()

    def _on_about_to_quit(self) -> None:
        if not self.quitting:
            self.quitting = True
            self.save_now()
            if self.tray is not None:
                self.tray.hide()


def _rect_t(r) -> tuple:
    return (r.x(), r.y(), r.width(), r.height())


def env_force_no_tray() -> bool:
    return os.environ.get("DESKTOP_PETS_FORCE_NO_TRAY", "") == "1"
