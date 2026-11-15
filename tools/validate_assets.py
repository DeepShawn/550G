"""素材检查：尺寸、RGBA、透明边距、各帧对齐（不透明区域底边/中心）以及预览拼图。

用法：python tools/validate_assets.py [--sheet preview.png] [--release]
--release 时任何必需帧缺失、或 pets.json 标记 placeholder=true 都会以非零退出，
防止把占位素材当正式素材发布。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.assets import ALL_FRAMES, REQUIRED_FRAMES, load_manifest  # noqa: E402


def bbox_alpha(im: Image.Image, thr: int = 16):
    a = im.getchannel("A").point(lambda v: 255 if v >= thr else 0)
    return a.getbbox()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", type=Path)
    ap.add_argument("--release", action="store_true")
    args = ap.parse_args()
    m = load_manifest(ROOT / "assets")
    errors, warnings = [], []
    sheet_rows = []
    for spec in m.pets:
        row = []
        ref = None
        for f in ALL_FRAMES:
            p = spec.frame_path(f)
            if not p.is_file():
                (errors if f in REQUIRED_FRAMES else warnings).append(f"{spec.id}/{f}.png 缺失")
                continue
            im = Image.open(p)
            if im.mode != "RGBA":
                errors.append(f"{spec.id}/{f}.png 不是 RGBA（{im.mode}）")
                im = im.convert("RGBA")
            if im.size != tuple(spec.canvas_px):
                errors.append(f"{spec.id}/{f}.png 尺寸 {im.size} ≠ {tuple(spec.canvas_px)}")
            bb = bbox_alpha(im)
            if bb is None:
                errors.append(f"{spec.id}/{f}.png 全透明")
                continue
            l, t, r, b = bb
            if l < 8 or t < 8 or r > im.width - 8 or b > im.height - 8:
                warnings.append(f"{spec.id}/{f}.png 边距不足 bbox={bb}")
            corners = [im.getpixel((0, 0))[3], im.getpixel((im.width - 1, im.height - 1))[3]]
            if any(corners):
                errors.append(f"{spec.id}/{f}.png 角落不透明，可能带底色")
            if ref is None:
                ref = bb
            else:
                # 表情只改五官：轮廓包围盒的底边与左右应几乎不变（脚底锚点不跳）
                if abs(bb[3] - ref[3]) > 2 or abs(bb[0] - ref[0]) > 4 or abs(bb[2] - ref[2]) > 4:
                    errors.append(f"{spec.id}/{f}.png 与 idle 轮廓不对齐 {bb} vs {ref}")
            row.append((f, im))
        sheet_rows.append((spec, row))
        if spec.placeholder:
            msg = f"{spec.id} 仍是占位素材（pets.json placeholder=true）"
            (errors if args.release else warnings).append(msg)

    if args.sheet:
        cw, ch = 256, 299
        cols = max(len(r) for _, r in sheet_rows)
        sheet = Image.new("RGBA", (cols * cw * 2, len(sheet_rows) * (ch + 24)), (255, 255, 255, 255))
        d = ImageDraw.Draw(sheet)
        for ri, (spec, row) in enumerate(sheet_rows):
            for ci, (f, im) in enumerate(row):
                for bi, bg in enumerate([(255, 255, 255, 255), (52, 56, 68, 255)]):
                    x = (ci * 2 + bi) * cw
                    y = ri * (ch + 24)
                    tile = Image.new("RGBA", (cw, ch), bg)
                    tile.alpha_composite(im.resize((cw, ch), Image.LANCZOS))
                    sheet.paste(tile, (x, y))
                    d.text((x + 6, y + ch + 4), f"{spec.id}/{f}", fill=(40, 40, 40, 255))
        sheet.convert("RGB").save(args.sheet)
        print("预览：", args.sheet)

    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    print("OK" if not errors else f"{len(errors)} 个错误")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
