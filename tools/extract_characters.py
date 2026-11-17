"""从用户参考图 v2（docs/handoff/resources/user_concept_v2.png，1402×1122）抠出两位角色的待机帧。

角色像素直接取自参考图，不重新绘制。流程：
  1. isnet-anime 动漫人物分割模型得到前景 alpha（气泡、星星、!!、?、底部工具条自动排除）；
  2. 分离两人：x < SPLIT_LO 属于 550G，x > SPLIT_HI 属于前辈GPT，中间重叠带按色相判断
     （550G 灰白/薰衣草色偏蓝，前辈GPT 薄荷色偏绿，平滑后取较大者）；
  3. 一方头发盖住另一方留下的小缺口，用该角色自身周围颜色补齐；
  4. 半透明边缘去除背景的浅蓝色污染；
  5. 两人用同一缩放（保持参考图中的相对大小）放进 768×896 画布，水平居中、底边对齐脚底锚点 (384,848)。

然后运行 tools/make_expression_frames.py 由 idle 派生 眨眼/卖萌/睡觉 帧。

依赖：pillow numpy scipy onnxruntime；模型 isnet-anime.onnx（rembg 发布页，SHA-256 f15622d8…6e99）。
用法：python tools/extract_characters.py --model isnet-anime.onnx
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
SRC = ROOT / "docs" / "handoff" / "resources" / "user_concept_v2.png"
SPLIT_LO, SPLIT_HI = 680, 830  # 两人头发交叠的横向范围（原图像素）
CANVAS = (768, 896)
ANCHOR = (384, 848)
MAX_W, MAX_H = 748, 820


def segment(im: Image.Image, model: Path) -> np.ndarray:
    import onnxruntime as ort
    x = np.asarray(im.resize((1024, 1024), Image.LANCZOS), dtype=np.float32)
    x = x / max(float(x.max()), 1e-6)
    x = (x - np.array([0.485, 0.456, 0.406], dtype=np.float32))
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    sess = ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])
    pred = sess.run(None, {sess.get_inputs()[0].name: x})[0][0, 0]
    pred = (pred - pred.min()) / max(float(pred.max() - pred.min()), 1e-6)
    a = Image.fromarray((pred * 255).astype(np.uint8)).resize(im.size, Image.LANCZOS)
    a = np.asarray(a, dtype=np.float32) / 255.0
    # 压掉极淡的噪声，略微收紧过渡带
    return np.clip((a - 0.06) / 0.88, 0.0, 1.0)


def normalized_blur(rgb: np.ndarray, w: np.ndarray, sigma: float) -> np.ndarray:
    num = np.stack([ndimage.gaussian_filter(rgb[..., c] * w, sigma) for c in range(3)], -1)
    den = ndimage.gaussian_filter(w, sigma)[..., None]
    return num / np.maximum(den, 1e-4)


def split_owner(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """返回布尔数组：True = 550G，False = 前辈GPT（只对前景有意义）。"""
    h, w = alpha.shape
    xs = np.arange(w)[None, :].repeat(h, 0)
    # 实测：550G 头发 r≈g、b 明显更高；前辈GPT 头发 g 比 r 高 5～8、g≈b。
    # 综合分数 (g-b) + 2(g-r)：550G 约 -12，前辈GPT 约 +7～+15。
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    score = (g - b) + 2.0 * (g - r)
    sm = ndimage.gaussian_filter(score * alpha, 3) / np.maximum(ndimage.gaussian_filter(alpha, 3), 1e-3)
    owner = xs < (SPLIT_LO + SPLIT_HI) / 2
    band = (xs >= SPLIT_LO) & (xs <= SPLIT_HI)
    owner[band] = sm[band] < 0.0
    # 只保留与各自主体相连的部分，去掉带内的零碎误判
    fg = alpha > 0.05
    for want in (True, False):
        m = fg & (owner == want)
        lab, n = ndimage.label(m)
        if n > 1:
            sizes = ndimage.sum(m, lab, range(1, n + 1))
            main = 1 + int(np.argmax(sizes))
            stray = m & (lab != main)
            owner[stray] = not want
    return owner


def cut(rgb: np.ndarray, alpha: np.ndarray, mine: np.ndarray, bg: np.ndarray) -> Image.Image:
    a = alpha * mine
    # 被另一人头发遮住而留下的封闭缺口：用自身周围颜色补齐
    solid = a > 0.5
    holes = ndimage.binary_fill_holes(solid) & ~solid & (alpha > 0.5)
    col = rgb.copy()
    if holes.any():
        fill = normalized_blur(rgb, solid.astype(np.float32), 3.0)
        col[holes] = fill[holes]
        a = np.where(holes, 1.0, a)
    # 只保留主体：在较高阈值上取最大连通块，再允许其周围 6px 的半透明过渡
    core = a > 0.35
    # 两人交叠带里撕开的细发丝：开运算去掉，边缘更干净
    h, w = a.shape
    band = np.zeros_like(core)
    band[:, SPLIT_LO - 10:SPLIT_HI + 10] = True
    opened = ndimage.binary_opening(core, iterations=3)
    core = np.where(band, opened, core)
    lab, n = ndimage.label(core)
    if n > 1:
        sizes = ndimage.sum(core, lab, range(1, n + 1))
        core = lab == 1 + int(np.argmax(sizes))
    reach = ndimage.binary_dilation(core, iterations=6)
    reach = np.where(band, ndimage.binary_dilation(core, iterations=2), reach)
    a = a * reach
    a = np.where(a < 0.12, 0.0, a)  # 去掉地面阴影等极淡区域
    # 边缘颜色：半透明像素直接借用内部实色（避免背景色或阴影带来的暗边/浅蓝边）
    wsolid = (a > 0.6).astype(np.float32)
    inner = normalized_blur(col, wsolid, 2.5)
    support = ndimage.gaussian_filter(wsolid, 2.5)
    edge = (a > 0) & (a < 0.85) & (support > 0.08)  # 附近没有实色像素时保留原色，避免变黑
    col[edge] = inner[edge]
    col[a <= 0] = 0
    out = np.dstack([np.clip(col, 0, 255), np.clip(a, 0, 1) * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=SRC)
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=ROOT / "assets" / "pets")
    ap.add_argument("--meta", type=Path, default=ROOT / "art_source" / "reference_extraction.json")
    args = ap.parse_args()

    im = Image.open(args.src).convert("RGB")
    rgb = np.asarray(im, dtype=np.float32)
    alpha = segment(im, args.model)
    bg = normalized_blur(rgb, (alpha < 0.02).astype(np.float32), 12.0)  # 每个像素处的背景色估计
    owner = split_owner(rgb, alpha)

    sprites = {"550g": cut(rgb, alpha, owner.astype(np.float32), bg),
               "gpt_senpai": cut(rgb, alpha, (~owner).astype(np.float32), bg)}
    boxes = {k: v.getchannel("A").point(lambda p: 255 if p > 12 else 0).getbbox() for k, v in sprites.items()}
    scale = min(min(MAX_W / (b[2] - b[0]), MAX_H / (b[3] - b[1])) for b in boxes.values())
    for pid, sp in sprites.items():
        b = boxes[pid]
        crop = sp.crop(b)
        nw, nh = round(crop.width * scale), round(crop.height * scale)
        crop = crop.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
        canvas.alpha_composite(crop, (ANCHOR[0] - nw // 2, ANCHOR[1] - nh))
        d = args.out / pid
        d.mkdir(parents=True, exist_ok=True)
        canvas.save(d / "idle.png")
        print(pid, "bbox", b, "scale", round(scale, 3), file=sys.stderr)
    args.meta.parent.mkdir(parents=True, exist_ok=True)
    args.meta.write_text(json.dumps({
        "source": str(args.src.relative_to(ROOT)) if args.src.is_relative_to(ROOT) else str(args.src),
        "segmentation": "isnet-anime (rembg release v0.0.0)",
        "split_band_px": [SPLIT_LO, SPLIT_HI],
        "source_bbox": boxes, "scale": scale, "canvas": CANVAS, "anchor": ANCHOR,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
