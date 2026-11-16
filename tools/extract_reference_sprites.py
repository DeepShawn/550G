"""从用户提供的概念图（docs/handoff/resources/user_concept.png）中抠出角色表情贴纸，
生成运行时帧 assets/pets/<id>/<frame>.png（768×896 RGBA，脚底锚点 384,848）。

角色形象与概念图完全一致（直接取自原图像素）。流程：
  1. 按 CELLS 裁出表情格（概念图中部的浅色卡片区，背景接近纯色）；
  2. 放大 ×4：优先 Real-ESRGAN anime_6B（需要 torch 与权重文件），否则 Lanczos；
  3. 在高分辨率上抠图：从格子边缘泛洪填充与背景色接近的像素 → 背景；
     只保留最大的前景连通块（去掉 ?!、爱心、Zzz 等符号，Z 由程序绘制）；
     被包围的背景色小洞也设为透明；边缘按色差给半透明 alpha 并去除背景色污染；
  4. 同一角色所有帧使用同一缩放，水平居中、底边对齐到脚底锚点。

blink_closed / blink_half 由 idle 帧派生（tools/make_blink_frames.py 处理眼睛区域）。

用法（需要 pillow、numpy、scipy；可选 torch）：
  python tools/extract_reference_sprites.py --esrgan RealESRGAN_x4plus_anime_6B.pth
  python tools/make_blink_frames.py --dir assets/pets
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "handoff" / "resources" / "user_concept.png"

# 概念图中表情格的位置 (left, top, right, bottom)，原图 1312×1199 像素坐标
CELLS = {
    "550g": {
        "idle": (14, 624, 188, 786),
        "surprised": (190, 624, 362, 786),
        "sleep": (364, 624, 528, 786),
        "cute": (14, 786, 188, 944),
        "angry": (190, 786, 362, 944),
    },
    "gpt_senpai": {
        "idle": (552, 624, 716, 786),
        "happy": (716, 624, 870, 786),
        "sleep": (868, 624, 1034, 786),
        "cute": (552, 786, 716, 944),
        "confused": (716, 786, 870, 944),
    },
}

CANVAS = (768, 896)
ANCHOR = (384, 848)
MAX_W, MAX_H = 748, 820


# ---------------------------------------------------------------- 放大
def upscale(img: Image.Image, esrgan: Path | None) -> Image.Image:
    if esrgan is not None:
        try:
            return _esrgan_x4(img, esrgan)
        except Exception as e:  # noqa: BLE001
            print("Real-ESRGAN 不可用，改用 Lanczos：", e, file=sys.stderr)
    return img.resize((img.width * 4, img.height * 4), Image.LANCZOS)


_MODEL = None


def _esrgan_x4(img: Image.Image, weights: Path) -> Image.Image:
    import torch
    from torch import nn
    import torch.nn.functional as F

    class RDB(nn.Module):
        def __init__(self, nf=64, gc=32):
            super().__init__()
            self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
            self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
            self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
            self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
            self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, True)

        def forward(self, x):
            x1 = self.lrelu(self.conv1(x))
            x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
            x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
            x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
            x5 = self.conv5(torch.cat((x, x1, x2, x3, x4), 1))
            return x5 * 0.2 + x

    class RRDB(nn.Module):
        def __init__(self, nf=64, gc=32):
            super().__init__()
            self.rdb1, self.rdb2, self.rdb3 = RDB(nf, gc), RDB(nf, gc), RDB(nf, gc)

        def forward(self, x):
            return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x

    class RRDBNet(nn.Module):
        def __init__(self, nb=6, nf=64, gc=32):
            super().__init__()
            self.conv_first = nn.Conv2d(3, nf, 3, 1, 1)
            self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
            self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
            self.conv_last = nn.Conv2d(nf, 3, 3, 1, 1)
            self.lrelu = nn.LeakyReLU(0.2, True)

        def forward(self, x):
            feat = self.conv_first(x)
            feat = feat + self.conv_body(self.body(feat))
            feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode="nearest")))
            feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode="nearest")))
            return self.conv_last(self.lrelu(self.conv_hr(feat)))

    global _MODEL
    if _MODEL is None:
        m = RRDBNet()
        sd = torch.load(str(weights), map_location="cpu", weights_only=True)
        m.load_state_dict(sd.get("params_ema", sd.get("params", sd)), strict=True)
        m.eval()
        _MODEL = m
    x = torch.from_numpy(np.asarray(img.convert("RGB"), dtype=np.float32) / 255.0).permute(2, 0, 1)[None]
    with torch.no_grad():
        y = _MODEL(x).clamp(0, 1)[0].permute(1, 2, 0).numpy()
    return Image.fromarray((y * 255 + 0.5).astype(np.uint8))


# ---------------------------------------------------------------- 抠图
def key_out(img: Image.Image, t_bg: float = 20.0, t_soft: float = 46.0, hole_t: float = 4.5,
            min_hole: int = 2500) -> Image.Image:
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = a.shape
    border = np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((a - bg) ** 2).sum(-1))

    # 1) 与边缘连通、色差小的像素 = 背景
    cand = dist < t_bg
    lab, _ = ndimage.label(cand)
    edge_labels = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    edge_labels = edge_labels[edge_labels > 0]
    bgmask = np.isin(lab, edge_labels)

    # 2) 只保留最大前景连通块（去掉符号）
    fg = ~bgmask
    fl, n = ndimage.label(fg)
    if n > 1:
        sizes = ndimage.sum(fg, fl, range(1, n + 1))
        keep = 1 + int(np.argmax(sizes))
        fg = fl == keep
    fg = ndimage.binary_fill_holes(fg)

    # 3) 角色内部被包围的背景色区域（手臂与身体间的缝）也透明
    holes = fg & (dist < hole_t)
    hl, hn = ndimage.label(holes)
    if hn:
        sizes = ndimage.sum(holes, hl, range(1, hn + 1))
        for i, s in enumerate(sizes, start=1):
            if s >= min_hole:
                fg[hl == i] = False

    # 4) 边缘软化：靠近背景的一圈按色差给 alpha，并去除背景色污染
    alpha = fg.astype(np.float32)
    band = fg & ~ndimage.binary_erosion(fg, iterations=3)
    soft = np.clip((dist - t_bg * 0.35) / (t_soft - t_bg * 0.35), 0.0, 1.0)
    alpha[band] = soft[band]
    alpha = ndimage.gaussian_filter(alpha, 0.6) * fg  # 轻微抗锯齿，仅限前景内
    alpha = np.clip(alpha, 0, 1)
    safe = np.maximum(alpha, 1e-3)[..., None]
    rgb = np.where(alpha[..., None] > 0.02, (a - (1 - alpha[..., None]) * bg) / safe, 0)
    rgb = np.clip(rgb, 0, 255)
    out = np.dstack([rgb, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def bbox(im: Image.Image):
    return im.getchannel("A").point(lambda v: 255 if v > 16 else 0).getbbox()


def place(sprites: dict[str, Image.Image]) -> dict[str, Image.Image]:
    """同一缩放；水平居中、底边落在锚点上。"""
    boxes = {k: bbox(v) for k, v in sprites.items()}
    scale = min(min(MAX_W / (b[2] - b[0]), MAX_H / (b[3] - b[1])) for b in boxes.values())
    out = {}
    for k, im in sprites.items():
        b = boxes[k]
        crop = im.crop(b)
        nw, nh = round(crop.width * scale), round(crop.height * scale)
        crop = crop.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        canvas.alpha_composite(crop, (ANCHOR[0] - nw // 2, ANCHOR[1] - nh))
        out[k] = canvas
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--out", type=Path, default=ROOT / "assets" / "pets")
    ap.add_argument("--meta", type=Path, default=ROOT / "art_source" / "reference_extraction.json")
    ap.add_argument("--esrgan", type=Path)
    args = ap.parse_args()
    src = Image.open(args.src).convert("RGB")
    meta = {"source": str(args.src.relative_to(ROOT)) if args.src.is_relative_to(ROOT) else str(args.src),
            "upscaler": "Real-ESRGAN x4 anime_6B" if args.esrgan else "Lanczos x4", "cells": CELLS}
    for pet, cells in CELLS.items():
        sprites = {}
        for name, box in cells.items():
            cell = src.crop(box)
            big = upscale(cell, args.esrgan)
            sprites[name] = key_out(big)
            print(pet, name, "ok", file=sys.stderr)
        for name, im in place(sprites).items():
            d = args.out / pet
            d.mkdir(parents=True, exist_ok=True)
            im.save(d / f"{name}.png")
    args.meta.parent.mkdir(parents=True, exist_ok=True)
    args.meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print("done", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
