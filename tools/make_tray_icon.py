"""用两位角色 idle 帧的头像合成托盘/程序图标 assets/tray.png 与多尺寸 assets/tray.ico。

用法：python tools/make_tray_icon.py   （需要 pillow；在 make_expression_frames.py 之后运行）
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
PETS = ROOT / "assets" / "pets"
# 头像在 768×896 idle 帧中的裁切框（含头发和发饰）
HEADS = {"550g": (330, 330, 640, 640), "gpt_senpai": (130, 260, 440, 570)}
SIZE = 256


def rounded_bg() -> Image.Image:
    bg = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    grad = Image.new("RGBA", (SIZE, SIZE))
    px = grad.load()
    a, b = (106, 150, 238), (125, 184, 168)  # 550G 蓝 → 前辈GPT 绿
    for x in range(SIZE):
        for y in range(SIZE):
            t = (x + y) / (2 * SIZE)
            px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3)) + (255,)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((4, 4, SIZE - 5, SIZE - 5), radius=58, fill=255)
    bg.paste(grad, (0, 0), mask)
    ring = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(ring).rounded_rectangle((8, 8, SIZE - 9, SIZE - 9), radius=54, outline=(255, 255, 255, 150),
                                           width=6)
    bg.alpha_composite(ring)
    return bg


def head(pid: str, d: int) -> Image.Image:
    im = Image.open(PETS / pid / "idle.png").convert("RGBA").crop(HEADS[pid]).resize((d, d), Image.LANCZOS)
    disc = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    m = Image.new("L", (d, d), 0)
    ImageDraw.Draw(m).ellipse((0, 0, d - 1, d - 1), fill=255)
    white = Image.new("RGBA", (d, d), (255, 255, 255, 255))
    disc.paste(white, (0, 0), m)
    disc.alpha_composite(im)
    out = Image.new("RGBA", (d, d), (0, 0, 0, 0))
    out.paste(disc, (0, 0), m)
    ImageDraw.Draw(out).ellipse((1, 1, d - 2, d - 2), outline=(255, 255, 255, 255), width=5)
    return out


def main() -> int:
    icon = rounded_bg()
    d = 150
    icon.alpha_composite(head("gpt_senpai", d), (SIZE - d - 14, 30))
    icon.alpha_composite(head("550g", d), (14, SIZE - d - 30))
    icon.save(ROOT / "assets" / "tray.png")
    icon.save(ROOT / "assets" / "tray.ico", format="ICO",
              sizes=[(s, s) for s in (16, 20, 24, 32, 48, 64, 128, 256)])
    print("icon ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
