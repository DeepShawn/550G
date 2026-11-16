"""由 idle 帧派生眨眼帧：只重画眼睛区域，头发、身体、位置完全不动。

- blink_closed：用眼睛下方的肤色盖住眼睛，再画一条闭眼弧线（与概念图里睡觉/笑眼的线条同色）。
- blink_half：只盖住眼睛上半部分，并把上睫毛线压到中间。

眼睛位置 EYES 是在 extract_reference_sprites.py 产出的 768×896 idle 帧上量出来的；
如果改了抠图参数导致角色缩放/位置变化，需要重新量。

用法：python tools/make_blink_frames.py --dir assets/pets
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

# (x0, y0, x1, y1, 外眼角方向 -1=左 / +1=右)
EYES = {
    "550g": [(278, 412, 370, 476, -1), (468, 412, 550, 476, +1)],
    "gpt_senpai": [(268, 456, 340, 517, -1), (441, 456, 519, 517, +1)],
}
SS = 4  # 超采样倍数，让手画线条抗锯齿


def _skin(im: Image.Image, eyes) -> tuple:
    """取两眼之间、鼻梁位置的肤色（眼睛正下方有腮红，会偏粉）。"""
    (lx0, ly0, lx1, ly1, _), (rx0, _ry0, _rx1, _ry1, _) = eyes
    cx = (lx1 + rx0) // 2
    cy = ly0 + int((ly1 - ly0) * 0.85)
    patch = np.asarray(im.crop((cx - 6, cy - 4, cx + 6, cy + 4)).convert("RGB")).reshape(-1, 3)
    return tuple(int(v) for v in np.median(patch, axis=0))


def _lash(im: Image.Image, eye, skin) -> tuple:
    """眼内最暗的一小撮像素（睫毛色），再与肤色混合 20%，避免纯黑显得生硬。"""
    x0, y0, x1, y1, _ = eye
    a = np.asarray(im.crop((x0, y0, x1, y1)).convert("RGB")).reshape(-1, 3).astype(int)
    dark = a[np.argsort(a.sum(1))[: max(5, len(a) // 60)]].mean(0)
    return tuple(int(v) for v in dark * 0.8 + np.array(skin) * 0.2)


def _cover(im: Image.Image, eye, color, top_frac: float) -> Image.Image:
    """在眼睛椭圆内（只到 top_frac 高度为止）铺肤色，边缘羽化。"""
    x0, y0, x1, y1, _ = eye
    mask = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(mask)
    pad = 3
    d.ellipse((x0 - pad, y0 - pad, x1 + pad, y1 + pad), fill=255)
    if top_frac < 1.0:
        cut = y0 + (y1 - y0) * top_frac
        d.rectangle((0, cut, im.width, im.height), fill=0)
    mask = mask.filter(ImageFilter.GaussianBlur(1.6))
    layer = Image.new("RGBA", im.size, color + (255,))
    out = im.copy()
    out.paste(layer, (0, 0), mask)
    return out


def _arc(im: Image.Image, pts, color, width: float) -> Image.Image:
    big = Image.new("RGBA", (im.width * SS, im.height * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    d.line([(x * SS, y * SS) for x, y in pts], fill=color + (255,), width=round(width * SS), joint="curve")
    r = width * SS / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x * SS - r, y * SS - r, x * SS + r, y * SS + r), fill=color + (255,))
    small = big.resize(im.size, Image.LANCZOS)
    out = im.copy()
    out.alpha_composite(small)
    return out


def _curve(x0, x1, y, sag, n=24):
    return [(x0 + (x1 - x0) * t, y + sag * 4 * t * (1 - t)) for t in (i / (n - 1) for i in range(n))]


def closed(im: Image.Image, eyes) -> Image.Image:
    out = im
    skin = _skin(im, eyes)
    for e in eyes:
        x0, y0, x1, y1, side = e
        lash = _lash(im, e, skin)
        out = _cover(out, e, skin, 1.0)
        h = y1 - y0
        y = y0 + h * 0.6
        out = _arc(out, _curve(x0 + 8, x1 - 8, y, h * 0.24), lash, 4.0)
        # 外眼角的小睫毛
        ox = x0 + 8 if side < 0 else x1 - 8
        out = _arc(out, [(ox, y), (ox + side * 8, y - 5)], lash, 3.0)
    return out


def half(im: Image.Image, eyes) -> Image.Image:
    out = im
    skin = _skin(im, eyes)
    for e in eyes:
        x0, y0, x1, y1, side = e
        lash = _lash(im, e, skin)
        out = _cover(out, e, skin, 0.5)
        h = y1 - y0
        y = y0 + h * 0.5
        out = _arc(out, _curve(x0 + 4, x1 - 4, y, h * 0.05), lash, 5.0)
        ox = x0 + 4 if side < 0 else x1 - 4
        out = _arc(out, [(ox, y), (ox + side * 9, y - 5)], lash, 3.5)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True, help="含 <pet>/idle.png 的目录")
    args = ap.parse_args()
    for pet, eyes in EYES.items():
        idle = Image.open(args.dir / pet / "idle.png").convert("RGBA")
        closed(idle, eyes).save(args.dir / pet / "blink_closed.png")
        half(idle, eyes).save(args.dir / pet / "blink_half.png")
        print(pet, "blink frames ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
