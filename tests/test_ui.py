"""Qt 层测试（offscreen）。只能证明逻辑与事件路由，不能替代 Windows 桌面实机验收。"""
import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app import settings as settings_mod
from app.assets import load_manifest, resource_root
from app.controller import AppController
from app.dialogues import load_dialogues
from app.state_machine import CUTE, IDLE, SLEEP


@pytest.fixture
def ctl(qapp, tmp_path):
    root = resource_root()
    c = AppController(qapp, load_manifest(root), settings_mod.Settings(), tmp_path / "settings.json",
                      load_dialogues(root / "dialogues.json"), QIcon(str(root / "tray.png")),
                      force_no_tray=True)
    c.settings.first_run_hint_shown = True
    c.start()
    yield c
    for p in c.pets:
        p.hide()
        p.deleteLater()
    if c.panel:
        c.panel.deleteLater()


def face_point(pet):
    # 角色脸部中心（窗口局部坐标）
    return pet.char_origin + QPoint(pet.char_w // 2, int(pet.char_h * 0.45))


def test_click_triggers_once_without_moving(ctl, qtbot):
    a, b = ctl.pets
    pos = a.pos()
    qtbot.mouseClick(a, Qt.LeftButton, pos=face_point(a))
    assert a.brain.state == CUTE and a.brain.bubble_text
    assert a.pos() == pos
    assert b.brain.state == IDLE


def test_press_alone_does_not_talk(ctl, qtbot):
    a = ctl.pets[0]
    a.brain.clear_bubble()
    qtbot.mousePress(a, Qt.LeftButton, pos=face_point(a))
    assert a.brain.bubble_text == "" and a.brain.state == IDLE
    qtbot.mouseRelease(a, Qt.LeftButton, pos=face_point(a))
    assert a.brain.state == CUTE


def test_drag_moves_only_one_and_no_dialogue(ctl, qtbot):
    a, b = ctl.pets
    a.brain.clear_bubble()
    pb = b.pos()
    pa = a.pos()
    fp = face_point(a)
    # 直接驱动 tracker（offscreen 平台下 mouseMove 的全局坐标不可靠）
    gp = a.mapToGlobal(fp)
    a.tracker.press((gp.x(), gp.y()), (a.x(), a.y()))
    new = a.tracker.move((gp.x() - 60, gp.y() - 40))
    a.move(QPoint(*new))
    qtbot.mouseRelease(a, Qt.LeftButton, pos=fp)
    assert a.brain.bubble_text == "" and a.brain.state != CUTE
    assert a.pos() != pa
    assert b.pos() == pb


def test_transparent_corner_not_hit(ctl):
    a = ctl.pets[0]
    a.brain.clear_bubble()
    assert not a.hit_test(QPoint(1, a.height() - 2))
    assert a.hit_test(face_point(a))


def test_hide_show_and_no_tray_panel(ctl):
    a, b = ctl.pets
    assert ctl.panel is not None and ctl.panel.isVisible()
    ctl.hide_all()
    assert not a.isVisible() and not b.isVisible()
    assert not a.timer.isActive()  # 隐藏时停止重绘
    ctl.show_pet(b)
    assert b.isVisible() and not a.isVisible()
    ctl.show_all()
    assert a.isVisible() and a.timer.isActive()


def test_cannot_hide_last_entry_without_tray_or_panel(ctl):
    ctl.panel.hide()
    ctl.panel = None
    ctl.hide_all()
    assert all(p.isVisible() for p in ctl.pets)
    a, b = ctl.pets
    ctl.hide_pet(a)
    assert not a.isVisible()
    ctl.hide_pet(b)
    assert b.isVisible()


def test_manual_states_and_independence(ctl):
    a, b = ctl.pets
    a.set_state(SLEEP)
    assert a.brain.state == SLEEP and b.brain.state == IDLE
    a.trigger_click()
    assert a.brain.state == CUTE


def test_scale_keeps_feet_anchor_and_saves(ctl, tmp_path):
    a = ctl.pets[0]
    scr = QApplication.primaryScreen().availableGeometry()
    a.set_char_pos(scr.center() - QPoint(120, 140))  # 远离屏幕边缘，避免被约束
    x, y, w, h = a.char_rect()
    foot = (x + w / 2, y + h)
    ctl.set_scale(a, 1.25)
    x2, y2, w2, h2 = a.char_rect()
    assert w2 == 300 and h2 == 350
    assert abs((x2 + w2 / 2) - foot[0]) <= 1 and abs((y2 + h2) - foot[1]) <= 1
    assert ctl.save_now()
    st = settings_mod.load(tmp_path / "settings.json")
    assert st.pet("550g").scale == 1.25


def test_positions_restore_from_settings(qapp, tmp_path):
    root = resource_root()
    st = settings_mod.Settings()
    scr = QApplication.primaryScreen().availableGeometry()
    st.pet("550g").x, st.pet("550g").y = scr.x() + 50, scr.y() + 60
    st.pet("gpt_senpai").x, st.pet("gpt_senpai").y = 99999 - 1, 5  # 离屏
    c = AppController(qapp, load_manifest(root), st, tmp_path / "s.json",
                      load_dialogues(root / "dialogues.json"), QIcon(), force_no_tray=True)
    c.place_initial()
    a, b = c.pets
    assert a.char_rect()[:2] == (scr.x() + 50, scr.y() + 60)
    bx, by, bw, bh = b.char_rect()
    assert scr.contains(bx, by) and scr.contains(bx + bw - 1, by + bh - 1)
    for p in c.pets:
        p.deleteLater()
    c.panel.deleteLater()


def test_bubble_fits_window_with_long_text(ctl):
    a = ctl.pets[0]
    a.say("这是一句非常非常长的中文对白，用来检查气泡在窗口里会不会被截断或者越界显示。" * 2)
    r = a.bubble_rect()
    assert r.left() >= 0 and r.top() >= 0 and r.right() < a.width()


def test_menu_emote(ctl):
    from app.state_machine import EMOTE
    a, b = ctl.pets
    a.play_emote("surprised")
    assert a.brain.state == EMOTE and a.brain.frame() == "surprised" and a.brain.bubble_text
    assert b.brain.state != EMOTE
