"""单只角色的透明置顶窗口：绘制、浮动、气泡、命中区域与鼠标输入。

窗口布局（逻辑像素，按缩放 s）：
    ┌──────────── win_w ────────────┐
    │  气泡区 bubble_h（气泡、睡眠 Z） │
    │   ┌──── char_w ────┐            │
    │   │   角色画布      │ char_h     │
    │   └────────────────┘            │
    └────────────────────────────────┘
窗口位置只在拖动、缩放、恢复时改变；呼吸浮动只改变绘制偏移。
"""
from __future__ import annotations

import logging
import math
import os
import random
import time
from typing import Optional

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPainterPath,
                           QPen, QRegion)
from PySide6.QtWidgets import QApplication, QWidget

from . import geometry
from .assets import PetSpec
from .dialogues import DialoguePool
from .frames import FrameSet
from .interaction import RESULT_CLICK, RESULT_DRAG_END, PressTracker
from .state_machine import EVENT_WAKE, SLEEP, PetBrain

log = logging.getLogger(__name__)

BASE_CHAR_W = 240
BASE_CHAR_H = 280
BASE_BUBBLE_H = 84
BASE_SIDE_PAD = 22
FLOAT_PERIOD_S = 3.2
FRAME_INTERVAL_MS = 40  # 25 FPS
FONT_FAMILIES = ["Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC",
                 "Source Han Sans SC", "sans-serif"]

USE_HIT_MASK = os.environ.get("DESKTOP_PETS_NO_MASK", "") != "1"


def monotonic() -> float:
    return time.monotonic()


class PetWindow(QWidget):
    clicked = Signal()
    drag_finished = Signal()
    menu_requested = Signal(QPoint)
    visibility_changed = Signal(bool)

    def __init__(self, spec: PetSpec, frames: FrameSet, brain: PetBrain, dialogues: DialoguePool,
                 scale: float = 1.0, float_px: float = 2.5):
        super().__init__(None)
        self.spec = spec
        self.frames = frames
        self.brain = brain
        self.dialogues = dialogues
        self.theme = QColor(spec.theme)
        self.base_float_px = float_px
        self.scale = scale
        self.tracker = PressTracker(threshold=max(2, QApplication.startDragDistance()))
        self._phase0 = random.random() * FLOAT_PERIOD_S
        self._last_mask_key = None
        self._bubble_shift = 0
        self._dpr = 1.0
        self._screen_hooked = False

        self.setWindowTitle(spec.name)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
                            | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setMouseTracking(False)
        self.setToolTip("")

        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.CoarseTimer)
        self.timer.setInterval(FRAME_INTERVAL_MS)
        self.timer.timeout.connect(self.tick)

        self._apply_layout()

    # ------------------------------------------------------------------ 布局
    def _apply_layout(self) -> None:
        s = self.scale
        self.char_w = round(BASE_CHAR_W * s)
        self.char_h = round(BASE_CHAR_H * s)
        self.bubble_h = max(64, round(BASE_BUBBLE_H * s))
        self.side_pad = round(BASE_SIDE_PAD * s)
        self.win_w = self.char_w + 2 * self.side_pad
        self.win_h = self.bubble_h + self.char_h
        self.char_origin = QPoint(self.side_pad, self.bubble_h)
        self.float_px = self.base_float_px * s
        self.setFixedSize(self.win_w, self.win_h)
        self._hit_region: Optional[QRegion] = None
        self._last_mask_key = None
        self.frames.clear_cache()
        self._bubble_font = QFont()
        self._bubble_font.setFamilies(FONT_FAMILIES)
        self._bubble_font.setPointSizeF(max(8.0, 9.5 * min(s, 1.25)))
        self._name_font = QFont(self._bubble_font)
        self._name_font.setBold(True)

    @property
    def char_size(self) -> QSize:
        return QSize(self.char_w, self.char_h)

    def char_pos(self) -> QPoint:
        return self.pos() + self.char_origin

    def char_rect(self) -> tuple[int, int, int, int]:
        p = self.char_pos()
        return (p.x(), p.y(), self.char_w, self.char_h)

    def set_char_pos(self, p: QPoint) -> None:
        self.move(p - self.char_origin)
        self._update_bubble_shift()

    def set_scale(self, scale: float) -> None:
        if abs(scale - self.scale) < 1e-6:
            return
        # 以脚底中心为锚点缩放，角色不会“跳走”
        old = self.char_rect()
        foot_x = old[0] + old[2] / 2
        foot_y = old[1] + old[3]
        self.scale = scale
        self._apply_layout()
        self.set_char_pos(QPoint(round(foot_x - self.char_w / 2), round(foot_y - self.char_h)))
        self.settle_on_screen()
        self._update_mask(force=True)
        self.update()

    def settle_on_screen(self) -> None:
        screens = [_rect_t(s.availableGeometry()) for s in QGuiApplication.screens()]
        primary = QGuiApplication.primaryScreen()
        if not screens or primary is None:
            return
        x, y = geometry.settle_after_drag(self.char_rect(), screens, _rect_t(primary.availableGeometry()))
        self.set_char_pos(QPoint(x, y))

    # ------------------------------------------------------------------ 动画
    def tick(self) -> None:
        now = monotonic()
        self.brain.update(now)
        self._update_mask()
        self.update()

    def float_offset(self, now: float) -> float:
        if self.tracker.dragging:
            return 0.0
        amp = self.float_px * (0.4 if self.brain.state == SLEEP else 1.0)
        return math.sin(2 * math.pi * (now + self._phase0) / FLOAT_PERIOD_S) * amp

    # ------------------------------------------------------------------ 对白/动作
    def trigger_click(self) -> None:
        now = monotonic()
        extras = [f for f, _ in self.spec.extras]
        if self.brain.state != SLEEP and extras and random.random() < 0.25:
            # 偶尔用额外表情回应单击，让反应更丰富
            frame = random.choice(extras)
            self.brain.emote(frame, now)
            text = self.dialogues.pick(frame)
        else:
            event = self.brain.click(now)
            if event == EVENT_WAKE:
                text = self.dialogues.pick("wake")
            else:
                text = self.dialogues.pick("cute" if random.random() < 0.25 else "click")
        self.say(text)
        self.clicked.emit()

    def play_emote(self, frame: str) -> None:
        """右键菜单触发额外表情。"""
        event = self.brain.emote(frame, monotonic())
        self.say(self.dialogues.pick("wake" if event == EVENT_WAKE else frame))

    def say(self, text: str, seconds: Optional[float] = None) -> None:
        self.brain.say(text, monotonic(), seconds)
        self._update_bubble_shift()
        self._update_mask()
        self.update()

    def set_state(self, state: str) -> None:
        self.brain.set_manual(state, monotonic())
        if state == SLEEP:
            self.say(self.dialogues.pick("sleep"))
        self._update_mask()
        self.update()

    # ------------------------------------------------------------------ 显示/隐藏
    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        if not self._screen_hooked and self.windowHandle() is not None:
            self.windowHandle().screenChanged.connect(self._on_screen_changed)
            self._screen_hooked = True
        self._refresh_dpr()
        self.brain.resume(monotonic())
        self._update_mask(force=True)
        self.timer.start()
        self.visibility_changed.emit(True)

    def hideEvent(self, e) -> None:  # noqa: N802
        super().hideEvent(e)
        self.timer.stop()
        self.tracker.cancel()
        self.brain.pause(monotonic())
        self.visibility_changed.emit(False)

    def _refresh_dpr(self) -> None:
        dpr = self.devicePixelRatioF()
        if abs(dpr - self._dpr) > 1e-3:
            self._dpr = dpr
            self.frames.clear_cache()

    def _on_screen_changed(self, _screen) -> None:
        self._refresh_dpr()
        self._update_bubble_shift()
        self.update()

    # ------------------------------------------------------------------ 命中区域
    def _ensure_hit_region(self) -> QRegion:
        if self._hit_region is None:
            self._hit_region = self.frames.hit_region(self.char_size, math.ceil(self.float_px))
        return self._hit_region

    def _update_mask(self, force: bool = False) -> None:
        if not USE_HIT_MASK:
            return
        bubble = self.bubble_rect() if self.brain.bubble_text else None
        sleeping = self.brain.state == SLEEP
        key = (bubble.getRect() if bubble else None, sleeping, self.win_w, self.win_h)
        if not force and key == self._last_mask_key:
            return
        self._last_mask_key = key
        region = QRegion(self._ensure_hit_region()).translated(self.char_origin)
        if bubble is not None:
            region = region.united(QRegion(bubble.adjusted(-3, -3, 3, 14)))
        if sleeping:
            region = region.united(QRegion(self.z_rect()))
        self.setMask(region)

    def hit_test(self, local: QPoint) -> bool:
        """窗口内某点是否属于角色/气泡（拦截鼠标）。"""
        if self.brain.bubble_text and self.bubble_rect().adjusted(-3, -3, 3, 14).contains(local):
            return True
        return self._ensure_hit_region().contains(local - self.char_origin)

    # ------------------------------------------------------------------ 绘制
    def bubble_rect(self) -> QRect:
        text = self.brain.bubble_text
        max_w = self.win_w - 8
        pad_x, pad_y = round(10 * min(self.scale, 1.2)), round(6 * min(self.scale, 1.2))
        fm = QFontMetrics(self._bubble_font)
        fmn = QFontMetrics(self._name_font)
        text_rect = fm.boundingRect(QRect(0, 0, max_w - 2 * pad_x, 1000), Qt.TextWordWrap, text)
        lines_h = min(text_rect.height(), fm.lineSpacing() * 3)
        w = max(text_rect.width(), fmn.horizontalAdvance(self.spec.name)) + 2 * pad_x
        w = min(max_w, max(w, round(90 * self.scale)))
        h = fmn.lineSpacing() + lines_h + 2 * pad_y
        cx = self.char_origin.x() + self.char_w // 2
        x = min(max(4, cx - w // 2), self.win_w - 4 - w)
        # 气泡底边贴近当前帧头顶（帧顶部有透明留白，睡姿更低）
        head_y = self.char_origin.y() + round(self.frames.content_top(self.brain.frame()) * self.char_h)
        bottom = max(self.bubble_h - 10, head_y - round(6 * self.scale)) + self._bubble_shift
        top = max(2, bottom - h)  # 文字太多时向下压到头顶，不被窗口裁掉
        return QRect(x, top, w, h)

    def z_rect(self) -> QRect:
        s = self.scale
        # 睡姿头顶右上方
        head_y = self.char_origin.y() + round(self.frames.content_top("sleep") * self.char_h)
        size = round(78 * s)
        return QRect(self.char_origin.x() + round(self.char_w * 0.70), max(0, head_y - size + round(20 * s)),
                     size, size)

    def _update_bubble_shift(self) -> None:
        """气泡会超出屏幕顶部时，把它下移到角色头部上方的可见范围内。"""
        self._bubble_shift = 0
        scr = self.screen()
        if scr is None:
            return
        avail = scr.availableGeometry()
        top_global = self.y() + 2
        if top_global < avail.top():
            self._bubble_shift = min(avail.top() - top_global, round(self.char_h * 0.55))

    def paintEvent(self, e) -> None:  # noqa: N802
        now = monotonic()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.transparent)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)

        dy = self.float_offset(now)
        pm = self.frames.pixmap(self.brain.frame(), self.char_size, self._dpr or self.devicePixelRatioF())
        # 位图按保持纵横比缩放，水平居中、底部对齐（脚底锚点不动）
        lw = pm.width() / pm.devicePixelRatio()
        lh = pm.height() / pm.devicePixelRatio()
        x = self.char_origin.x() + (self.char_w - lw) / 2
        y = self.char_origin.y() + (self.char_h - lh) + dy
        p.drawPixmap(QPointF(x, y), pm)

        if self.brain.state == SLEEP:
            self._paint_z(p, now)
        if self.brain.bubble_text:
            self._paint_bubble(p)
        p.end()

    def _paint_z(self, p: QPainter, now: float) -> None:
        r = self.z_rect()
        f = QFont()
        f.setFamilies(FONT_FAMILIES)
        f.setBold(True)
        for i in range(3):
            t = ((now * 0.45) + i / 3.0) % 1.0
            size = (11 + 7 * i) * self.scale
            f.setPixelSize(max(8, round(size)))
            p.setFont(f)
            alpha = int(255 * math.sin(math.pi * t))
            c = QColor(self.theme)
            c.setAlpha(alpha)
            p.setPen(c)
            px = r.left() + r.width() * (0.10 + 0.28 * i)
            py = r.bottom() - r.height() * (0.15 + 0.6 * t) - 6 * i * self.scale
            p.drawText(QPointF(px, py), "Z" if i == 2 else "z")

    def _paint_bubble(self, p: QPainter) -> None:
        r = QRectF(self.bubble_rect())
        radius = 10 * min(self.scale, 1.2)
        path = QPainterPath()
        path.addRoundedRect(r, radius, radius)
        tail_x = min(max(r.left() + 18, self.char_origin.x() + self.char_w * 0.5), r.right() - 18)
        tail = QPainterPath()
        tail.moveTo(tail_x - 7 * self.scale, r.bottom() - 1)
        tail.lineTo(tail_x + 1, r.bottom() + 9 * self.scale)
        tail.lineTo(tail_x + 7 * self.scale, r.bottom() - 1)
        tail.closeSubpath()
        path = path.united(tail)
        border = QColor(self.theme)
        border.setAlpha(170)
        p.setPen(QPen(border, 1.5))
        p.setBrush(QColor(255, 255, 255, 242))
        p.drawPath(path)

        pad_x = round(10 * min(self.scale, 1.2))
        pad_y = round(6 * min(self.scale, 1.2))
        inner = r.adjusted(pad_x, pad_y, -pad_x, -pad_y)
        fmn = QFontMetrics(self._name_font)
        p.setFont(self._name_font)
        p.setPen(self.theme.darker(115))
        p.drawText(QRectF(inner.left(), inner.top(), inner.width(), fmn.lineSpacing()),
                   Qt.AlignLeft | Qt.AlignVCenter, self.spec.name)
        p.setFont(self._bubble_font)
        p.setPen(QColor(55, 62, 82))
        body = QRectF(inner.left(), inner.top() + fmn.lineSpacing(), inner.width(),
                      inner.height() - fmn.lineSpacing())
        p.drawText(body, Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap, self.brain.bubble_text)

    # ------------------------------------------------------------------ 输入
    def mousePressEvent(self, e) -> None:  # noqa: N802
        local = e.position().toPoint()
        if not self.hit_test(local):
            e.ignore()
            return
        if e.button() == Qt.LeftButton:
            gp = e.globalPosition().toPoint()
            self.tracker.press((gp.x(), gp.y()), (self.x(), self.y()))
        elif e.button() == Qt.RightButton:
            self.tracker.cancel()
            self.menu_requested.emit(e.globalPosition().toPoint())
        e.accept()

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if not self.tracker.active:
            return
        if not (e.buttons() & Qt.LeftButton):
            self.tracker.cancel()
            return
        gp = e.globalPosition().toPoint()
        new = self.tracker.move((gp.x(), gp.y()))
        if new is not None:
            self.move(QPoint(*new))
            self.brain.note_interaction(monotonic())

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.LeftButton:
            return
        result = self.tracker.release()
        if result == RESULT_CLICK:
            self.trigger_click()
        elif result == RESULT_DRAG_END:
            self.settle_on_screen()
            self._update_bubble_shift()
            self.drag_finished.emit()

    def event(self, e) -> bool:
        if e.type() in (QEvent.UngrabMouse, QEvent.WindowDeactivate) and self.tracker.dragging:
            # 鼠标捕获丢失：结束拖动但仍保存位置
            self.tracker.cancel()
            self.settle_on_screen()
            self.drag_finished.emit()
        return super().event(e)


def _rect_t(r: QRect) -> tuple[int, int, int, int]:
    return (r.x(), r.y(), r.width(), r.height())
