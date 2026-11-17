"""由 idle 帧派生其他表情：只改眼睛、嘴和腮红，头发、身体、位置完全不动。

参考图 v2 每位角色只有一个姿势，因此：
  blink_half   上半眼睑盖住，睫毛线压到中间
  blink_closed 闭眼弧线
  cute         ^ ^ 笑眼 + 明显腮红 + 笑嘴
  sleep        放松的闭眼（下垂弧线 + 小睫毛）+ 小嘴（Z 由程序绘制）

FACES 里的坐标是在 tools/extract_characters.py 产出的 768×896 idle 帧上量的；
改了抠图缩放/位置后需要重新量。

用法：python tools/make_expression_frames.py --dir assets/pets
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FACES = {
    "550g": {
        # (x0, y0, x1, y1, 外眼角方向)：先左眼后右眼
        "eyes": [(345, 512, 440, 574, -1), (528, 477, 608, 537, +1)],
        "mouth": (505, 578, 9, 6),  # 中心 x, y, 半宽, 半高
        "cute_mouth": "smile",
        "sleep_mouth": "small",
    },
    "gpt_senpai": {
        "eyes": [(175, 437, 253, 509, -1), (335, 411, 402, 484, +1)],
        "mouth": (305, 525, 14, 11),
        "cute_mouth": "open_smile",
        "sleep_mouth": "small",
    },
}
SS = 4  # 超采样倍数
MOUTH_COLOR = (205, 108, 124)
MOUTH_DARK = (150, 70, 92)
MOUTH_FILL = (238, 140, 152)
BLUSH = (246, 150, 165)


def _skin(im: Image.Image, eyes) -> tuple:
    """两眼之间、鼻梁处的肤色（眼睛正下方有腮红会偏粉）。"""
    (lx0, ly0, lx1, ly1, _), (rx0, *_rest) = eyes
    cx = (lx1 + rx0) // 2
    cy = ly0 + int((ly1 - ly0) * 0.85)
    patch = np.asarray(im.crop((cx - 6, cy - 4, cx + 6, cy + 4)).convert("RGB")).reshape(-1, 3)
    return tuple(int(v) for v in np.median(patch, axis=0))


def _lash(im: Image.Image, eye, skin) -> tuple:
    x0, y0, x1, y1, _ = eye
    a = np.asarray(im.crop((x0, y0, x1, y1)).convert("RGB")).reshape(-1, 3).astype(int)
    dark = a[np.argsort(a.sum(1))[: max(5, len(a) // 60)]].mean(0)
    return tuple(int(v) for v in dark * 0.85 + np.array(skin) * 0.15)


def _cover_ellipse(im: Image.Image, box, color, top_frac: float = 1.0, pad: int = 4) -> Image.Image:
    x0, y0, x1, y1 = box
    mask = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((x0 - pad, y0 - pad, x1 + pad, y1 + pad), fill=255)
    if top_frac < 1.0:
        d.rectangle((0, y0 + (y1 - y0) * top_frac, im.width, im.height), fill=0)
    mask = mask.filter(ImageFilter.GaussianBlur(2.0))
    out = im.copy()
    out.paste(Image.new("RGBA", im.size, color + (255,)), (0, 0), mask)
    # 只在原本不透明的地方生效，不改轮廓
    out.putalpha(im.getchannel("A"))
    return out


def _draw(im: Image.Image, fn) -> Image.Image:
    big = Image.new("RGBA", (im.width * SS, im.height * SS), (0, 0, 0, 0))
    fn(ImageDraw.Draw(big), SS)
    out = im.copy()
    out.alpha_composite(big.resize(im.size, Image.LANCZOS))
    return out


def _poly(d, pts, color, width, k):
    d.line([(x * k, y * k) for x, y in pts], fill=color + (255,), width=round(width * k), joint="curve")
    r = width * k / 2
    for x, y in (pts[0], pts[-1]):
        d.ellipse((x * k - r, y * k - r, x * k + r, y * k + r), fill=color + (255,))


def _curve(x0, x1, y, sag, n=28):
    return [(x0 + (x1 - x0) * t, y + sag * 4 * t * (1 - t)) for t in (i / (n - 1) for i in range(n))]


def _blush(im: Image.Image, eyes, strength: float) -> Image.Image:
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for x0, y0, x1, y1, _ in eyes:
        cx, cy = (x0 + x1) / 2, y1 + (y1 - y0) * 0.22
        rx, ry = (x1 - x0) * 0.42, (y1 - y0) * 0.18
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=BLUSH + (int(255 * strength),))
    layer = layer.filter(ImageFilter.GaussianBlur(10))
    a = np.asarray(layer.getchannel("A"), dtype=np.float32) * (np.asarray(im.getchannel("A")) / 255.0)
    layer.putalpha(Image.fromarray(a.astype(np.uint8)))
    out = im.copy()
    out.alpha_composite(layer)
    return out


def _mouth(im: Image.Image, face, kind: str, skin) -> Image.Image:
    cx, cy, rw, rh = face["mouth"]
    out = _cover_ellipse(im, (cx - rw, cy - rh, cx + rw, cy + rh), skin, pad=3)

    def draw(d, k):
        if kind == "smile":
            _poly(d, _curve(cx - 9, cx + 9, cy - 2, 6), MOUTH_COLOR, 2.6, k)
        elif kind == "open_smile":
            pts = [(cx - 13 + 26 * t, cy - 5 + 15 * 4 * t * (1 - t)) for t in (i / 20 for i in range(21))]
            d.polygon([(x * k, y * k) for x, y in pts], fill=MOUTH_FILL + (255,), outline=MOUTH_DARK + (255,),
                      width=round(2.2 * k))
        elif kind == "small":
            d.ellipse(((cx - 6) * k, (cy - 4) * k, (cx + 6) * k, (cy + 5) * k), fill=MOUTH_FILL + (255,),
                      outline=MOUTH_DARK + (255,), width=round(1.8 * k))
    return _draw(out, draw)


def blink_closed(im, face):
    eyes = face["eyes"]
    skin = _skin(im, eyes)
    out = im
    for e in eyes:
        x0, y0, x1, y1, side = e
        lash = _lash(im, e, skin)
        out = _cover_ellipse(out, (x0, y0, x1, y1), skin)
        h = y1 - y0
        y = y0 + h * 0.6

        def draw(d, k, x0=x0, x1=x1, y=y, h=h, side=side, lash=lash):
            _poly(d, _curve(x0 + 6, x1 - 6, y, h * 0.22), lash, 4.5, k)
            ox = x0 + 6 if side < 0 else x1 - 6
            _poly(d, [(ox, y), (ox + side * 9, y - 6)], lash, 3.2, k)
        out = _draw(out, draw)
    return out


def blink_half(im, face):
    eyes = face["eyes"]
    skin = _skin(im, eyes)
    out = im
    for e in eyes:
        x0, y0, x1, y1, side = e
        lash = _lash(im, e, skin)
        out = _cover_ellipse(out, (x0, y0, x1, y1), skin, top_frac=0.5)
        h = y1 - y0
        y = y0 + h * 0.5

        def draw(d, k, x0=x0, x1=x1, y=y, h=h, side=side, lash=lash):
            _poly(d, _curve(x0 + 3, x1 - 3, y, h * 0.05), lash, 5.5, k)
            ox = x0 + 3 if side < 0 else x1 - 3
            _poly(d, [(ox, y), (ox + side * 10, y - 6)], lash, 3.8, k)
        out = _draw(out, draw)
    return out


def cute(im, face):
    eyes = face["eyes"]
    skin = _skin(im, eyes)
    out = im
    for e in eyes:
        x0, y0, x1, y1, side = e
        lash = _lash(im, e, skin)
        out = _cover_ellipse(out, (x0, y0, x1, y1), skin)
        h = y1 - y0
        y = y0 + h * 0.62

        def draw(d, k, x0=x0, x1=x1, y=y, h=h, lash=lash):
            _poly(d, _curve(x0 + 10, x1 - 10, y, -h * 0.42), lash, 5.5, k)  # ^ 笑眼
        out = _draw(out, draw)
    out = _blush(out, eyes, 0.5)
    return _mouth(out, face, face["cute_mouth"], skin)


def sleep(im, face):
    eyes = face["eyes"]
    skin = _skin(im, eyes)
    out = im
    for e in eyes:
        x0, y0, x1, y1, side = e
        lash = _lash(im, e, skin)
        out = _cover_ellipse(out, (x0, y0, x1, y1), skin)
        h = y1 - y0
        y = y0 + h * 0.7

        def draw(d, k, x0=x0, x1=x1, y=y, h=h, lash=lash):
            _poly(d, _curve(x0 + 8, x1 - 8, y, h * 0.16), lash, 4.2, k)
            for t in (0.3, 0.5, 0.7):  # 下睫毛
                x = x0 + 8 + (x1 - x0 - 16) * t
                yy = y + h * 0.16 * 4 * t * (1 - t)
                _poly(d, [(x, yy), (x + (t - 0.5) * 6, yy + 6)], lash, 2.2, k)
        out = _draw(out, draw)
    out = _blush(out, eyes, 0.25)
    return _mouth(out, face, face["sleep_mouth"], skin)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, required=True, help="含 <pet>/idle.png 的目录")
    args = ap.parse_args()
    for pet, face in FACES.items():
        idle = Image.open(args.dir / pet / "idle.png").convert("RGBA")
        for name, fn in (("blink_half", blink_half), ("blink_closed", blink_closed), ("cute", cute),
                         ("sleep", sleep)):
            fn(idle, face).save(args.dir / pet / f"{name}.png")
        print(pet, "expression frames ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
