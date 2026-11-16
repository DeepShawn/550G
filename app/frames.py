"""角色帧加载、缺帧回退、按缩放与 DPR 缓存的位图，以及基于 alpha 的命中区域。"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from PySide6.QtCore import QPoint, QSize, Qt
from PySide6.QtGui import QBitmap, QImage, QPainter, QPixmap, QRegion

from .assets import ALL_FRAMES, OPTIONAL_FRAMES, REQUIRED_FRAMES, AssetError, PetSpec

log = logging.getLogger(__name__)

ALPHA_HIT_THRESHOLD = 24  # 低于该 alpha 的像素视为透明（不拦截鼠标）


class FrameSet:
    def __init__(self, spec: PetSpec):
        self.spec = spec
        self.images: Dict[str, QImage] = {}
        self.fallbacks: Dict[str, str] = {}  # 缺失帧 -> 实际使用的帧
        self.problems: List[str] = []
        self._pix_cache: Dict[Tuple[str, int, int, float], QPixmap] = {}
        self._tops: Dict[str, float] = {}
        self._load()

    def _load(self) -> None:
        idle_path = self.spec.frame_path("idle")
        idle = QImage(str(idle_path))
        if idle.isNull():
            raise AssetError(f"{self.spec.name} 的必需帧 idle 缺失或无法读取：{idle_path}")
        idle = idle.convertToFormat(QImage.Format_ARGB32_Premultiplied)
        self.images["idle"] = idle
        for name in ALL_FRAMES + tuple(f for f, _ in self.spec.extras):
            if name == "idle":
                continue
            path = self.spec.frame_path(name)
            img = QImage(str(path))
            if img.isNull():
                self.fallbacks[name] = "idle"
                if name in OPTIONAL_FRAMES or name not in ALL_FRAMES:
                    log.info("%s 可选帧 %s 不存在，眨眼时跳过", self.spec.name, name)
                else:
                    msg = f"{self.spec.name} 必需帧 {name} 缺失（{path}），回退为 idle"
                    self.problems.append(msg)
                    log.warning(msg)
                continue
            if img.size() != idle.size():
                msg = (f"{self.spec.name} 帧 {name} 尺寸 {img.width()}x{img.height()} 与 idle "
                       f"{idle.width()}x{idle.height()} 不一致，已按 idle 画布缩放")
                self.problems.append(msg)
                log.warning(msg)
                img = img.scaled(idle.size(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
            self.images[name] = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)

    def content_top(self, frame: str) -> float:
        """该帧不透明内容顶边占画布高度的比例（用于把气泡贴近头顶）。"""
        name = self.resolve(frame)
        top = self._tops.get(name)
        if top is None:
            img = self.images[name]
            a = img.convertToFormat(QImage.Format_Alpha8)
            bpl, h, w = a.bytesPerLine(), a.height(), a.width()
            data = bytes(a.constBits())  # type: ignore[arg-type]
            top = 0
            for y in range(h):
                if max(data[y * bpl: y * bpl + w]) > 32:
                    top = y
                    break
            self._tops[name] = top = top / h
        return top

    @property
    def source_size(self) -> QSize:
        return self.images["idle"].size()

    def resolve(self, frame: str) -> str:
        if frame in self.images:
            return frame
        return self.fallbacks.get(frame, "idle")

    def missing_required(self) -> List[str]:
        return [f for f in REQUIRED_FRAMES if f not in self.images]

    def pixmap(self, frame: str, size: QSize, dpr: float) -> QPixmap:
        """返回已按 逻辑尺寸×DPR 高质量缩放好的位图，避免 paintEvent 里重复缩放。"""
        name = self.resolve(frame)
        key = (name, size.width(), size.height(), round(dpr, 3))
        pm = self._pix_cache.get(key)
        if pm is None:
            phys = QSize(max(1, round(size.width() * dpr)), max(1, round(size.height() * dpr)))
            img = self.images[name].scaled(phys, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm = QPixmap.fromImage(img)
            pm.setDevicePixelRatio(dpr)
            self._pix_cache[key] = pm
        return pm

    def clear_cache(self) -> None:
        self._pix_cache.clear()

    def hit_region(self, size: QSize, float_px: int, dilate_px: int = 3) -> QRegion:
        """所有帧 alpha 的并集，按浮动范围和少量膨胀扩展后转为区域（逻辑像素）。"""
        w, h = size.width(), size.height()
        union = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        union.fill(Qt.transparent)
        p = QPainter(union)
        for img in self.images.values():
            p.drawImage(0, 0, img.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        p.end()
        grown = QImage(w, h, QImage.Format_ARGB32_Premultiplied)
        grown.fill(Qt.transparent)
        p = QPainter(grown)
        step = max(1, dilate_px)
        for dy in range(-float_px - dilate_px, float_px + dilate_px + 1, step):
            for dx in range(-dilate_px, dilate_px + 1, step):
                p.drawImage(QPoint(dx, dy), union)
        p.end()
        # 阈值化：alpha >= ALPHA_HIT_THRESHOLD 的像素属于命中区域
        mono = _threshold_alpha(grown.convertToFormat(QImage.Format_Alpha8))
        return QRegion(QBitmap.fromImage(mono))


def _threshold_alpha(alpha8: QImage) -> QImage:
    w, h = alpha8.width(), alpha8.height()
    bpl_in = alpha8.bytesPerLine()
    bpl_out = ((w + 31) // 32) * 4  # 单色图每行按 32 位对齐
    src = bytes(alpha8.constBits())  # type: ignore[arg-type]
    dst = bytearray(bpl_out * h)
    thr = ALPHA_HIT_THRESHOLD
    for y in range(h):
        row = src[y * bpl_in: y * bpl_in + w]
        base = y * bpl_out
        for x in range(w):
            if row[x] >= thr:
                dst[base + (x >> 3)] |= 1 << (x & 7)
    out = QImage(bytes(dst), w, h, bpl_out, QImage.Format_MonoLSB)
    out.setColorCount(2)
    out.setColor(0, 0xFFFFFFFF)  # 0 = 白 = 区域外
    out.setColor(1, 0xFF000000)  # 1 = 黑 = 区域内（QBitmap 规则）
    return out.copy()
