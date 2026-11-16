"""生成托盘图标；可选生成 v0.2.0 的工程占位角色帧（程序绘制的矢量 Q 版）。

默认只生成 assets/tray.png 与 tray.ico。角色帧自 v0.3.0 起来自概念图（extract_reference_sprites.py）。


这些是**工程占位素材**：用于验证状态机、透明边缘、对齐与打包流程，
画面细节达不到参考图水准，不能当作正式高清立绘交付。

所有表情帧共享同一套身体/头发/服装图层，只替换眼睛、嘴、腮红，
因此画布、头部位置、脚底锚点 (384,848) 在各帧间严格一致。

用法：python tools/make_placeholder_art.py [--out assets] [--sheet preview.png]
需要 PySide6（含 QtSvg）。托盘 ICO 需要 Pillow。
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

W, H = 768, 896
OUTLINE = "#666779"

PALETTES = {
    "550g": {
        "hair_top": "#F4F5FB", "hair_mid": "#E3E6F2", "hair_bot": "#AEB6D0", "hair_shadow": "#B9C0DA",
        "hair_line": "#7D84A3",
        "eye_top": "#2E3E66", "eye_mid": "#5B78B3", "eye_bot": "#A9C4EE", "pupil": "#1D2847",
        "cloth_main": "#FFFFFF", "cloth_shadow": "#DCE4F4", "cloth_accent": "#648ED8",
        "cloth_accent_dark": "#3F65B0", "skirt": "#5A82CF", "skirt_shadow": "#3F63AE",
        "sock": "#3F63AE", "mouth": "#B5566E", "blush": "#F2A3B3",
    },
    "gpt_senpai": {
        "hair_top": "#FBFDF7", "hair_mid": "#E4F2DE", "hair_bot": "#A9D69E", "hair_shadow": "#C5E4BB",
        "hair_line": "#7E9C84",
        "eye_top": "#2F5A3E", "eye_mid": "#5E9B70", "eye_bot": "#B8E2BE", "pupil": "#1E3A28",
        "cloth_main": "#FFFFFF", "cloth_shadow": "#E6EEE4", "cloth_accent": "#9CCB94",
        "cloth_accent_dark": "#6E9F72", "skirt": "#FDFEFC", "skirt_shadow": "#DCE9D8",
        "sock": "#F4F7F2", "mouth": "#C25B6E", "blush": "#F5A6B2",
    },
}

SKIN = "#FFF1EA"
SKIN_SHADOW = "#F6D9CF"

# 眼睛中心
EYE_L = (316, 432)
EYE_R = (452, 432)


def defs(c: dict) -> str:
    return f"""
<defs>
  <linearGradient id="hair" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{c['hair_top']}"/>
    <stop offset="0.45" stop-color="{c['hair_mid']}"/>
    <stop offset="1" stop-color="{c['hair_bot']}"/>
  </linearGradient>
  <linearGradient id="hairBack" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{c['hair_mid']}"/>
    <stop offset="1" stop-color="{c['hair_bot']}"/>
  </linearGradient>
  <linearGradient id="iris" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{c['eye_top']}"/>
    <stop offset="0.55" stop-color="{c['eye_mid']}"/>
    <stop offset="1" stop-color="{c['eye_bot']}"/>
  </linearGradient>
  <linearGradient id="skirt" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{c['skirt']}"/>
    <stop offset="1" stop-color="{c['skirt_shadow']}"/>
  </linearGradient>
  <linearGradient id="cloth" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{c['cloth_main']}"/>
    <stop offset="1" stop-color="{c['cloth_shadow']}"/>
  </linearGradient>
  <radialGradient id="face" cx="0.5" cy="0.42" r="0.62">
    <stop offset="0.7" stop-color="{SKIN}"/>
    <stop offset="1" stop-color="{SKIN_SHADOW}"/>
  </radialGradient>
  <radialGradient id="blush" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="{c['blush']}" stop-opacity="0.9"/>
    <stop offset="1" stop-color="{c['blush']}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="shadow" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#5E6A92" stop-opacity="0.28"/>
    <stop offset="1" stop-color="#5E6A92" stop-opacity="0"/>
  </radialGradient>
</defs>"""


def back_hair(c: dict) -> str:
    # 身后的大片长发，下摆波浪，铺在坐姿身体两侧
    return f"""
<path d="M384 150
  C 220 150 140 260 132 400
  C 124 520 120 610 104 700
  C 96 750 112 800 150 812
  C 170 790 190 800 206 822
  C 230 800 250 812 268 826
  L 500 826
  C 518 812 538 800 562 822
  C 578 800 598 790 618 812
  C 656 800 672 750 664 700
  C 648 610 644 520 636 400
  C 628 260 548 150 384 150 Z"
  fill="url(#hairBack)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M150 560 C 160 640 150 720 168 790" fill="none" stroke="{c['hair_line']}" stroke-width="3" opacity="0.5"/>
<path d="M618 560 C 608 640 618 720 600 790" fill="none" stroke="{c['hair_line']}" stroke-width="3" opacity="0.5"/>
<path d="M196 600 C 200 680 196 740 214 800" fill="none" stroke="{c['hair_line']}" stroke-width="2.5" opacity="0.4"/>
<path d="M572 600 C 568 680 572 740 554 800" fill="none" stroke="{c['hair_line']}" stroke-width="2.5" opacity="0.4"/>
"""


def body_550g(c: dict) -> str:
    return f"""
<!-- 裙子（坐姿铺开） -->
<path d="M226 700 C 214 760 220 810 250 836 L 518 836 C 548 810 554 760 542 700 Z"
  fill="url(#skirt)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M260 712 L 252 830 M 314 716 L 312 834 M 384 718 L 384 836 M 454 716 L 456 834 M 508 712 L 516 830"
  stroke="{c['skirt_shadow']}" stroke-width="4" opacity="0.6"/>
<path d="M232 812 C 300 828 468 828 536 812" fill="none" stroke="#FFFFFF" stroke-width="5" opacity="0.85"/>
<!-- 外套躯干 -->
<path d="M290 560 C 262 600 244 660 236 724 C 300 744 468 744 532 724 C 524 660 506 600 478 560 Z"
  fill="url(#cloth)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M384 590 L 384 738" stroke="{c['cloth_accent']}" stroke-width="7"/>
<path d="M290 562 C 300 610 330 640 384 650 C 438 640 468 610 478 562"
  fill="none" stroke="{c['cloth_accent']}" stroke-width="10" stroke-linecap="round"/>
<path d="M354 600 L 384 640 L 414 600 Z" fill="{c['cloth_accent_dark']}" stroke="{OUTLINE}" stroke-width="3"/>
<!-- 袖子 -->
<path d="M290 580 C 250 600 236 660 260 712 C 280 728 316 720 330 700 C 320 660 316 620 300 586 Z"
  fill="url(#cloth)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M478 580 C 518 600 532 660 508 712 C 488 728 452 720 438 700 C 448 660 452 620 468 586 Z"
  fill="url(#cloth)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M262 704 C 282 718 314 714 328 698" fill="none" stroke="{c['cloth_accent']}" stroke-width="9" stroke-linecap="round"/>
<path d="M506 704 C 486 718 454 714 440 698" fill="none" stroke="{c['cloth_accent']}" stroke-width="9" stroke-linecap="round"/>
"""


def body_gpt(c: dict) -> str:
    return f"""
<!-- 白裙（坐姿铺开，荷叶边） -->
<path d="M222 690 C 206 760 214 812 246 836 L 522 836 C 554 812 562 760 546 690 Z"
  fill="url(#skirt)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M232 820 q 17 18 34 0 q 17 18 34 0 q 17 18 34 0 q 17 18 34 0 q 17 18 34 0 q 17 18 34 0 q 17 18 34 0 q 17 18 34 0"
  fill="#FFFFFF" stroke="{OUTLINE}" stroke-width="3.5" stroke-linejoin="round"/>
<path d="M262 706 L 254 816 M 322 712 L 320 820 M 384 714 L 384 822 M 446 712 L 448 820 M 506 706 L 514 816"
  stroke="{c['skirt_shadow']}" stroke-width="4" opacity="0.8"/>
<!-- 上身 -->
<path d="M296 560 C 268 600 250 660 242 720 C 300 740 468 740 526 720 C 518 660 500 600 472 560 Z"
  fill="url(#cloth)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M300 566 C 320 600 350 612 384 614 C 418 612 448 600 468 566" fill="none"
  stroke="{c['cloth_shadow']}" stroke-width="6"/>
<!-- 胸前浅绿蝴蝶结 -->
<path d="M384 624 L 350 604 L 352 644 Z M 384 624 L 418 604 L 416 644 Z" fill="{c['cloth_accent']}"
  stroke="{OUTLINE}" stroke-width="3" stroke-linejoin="round"/>
<circle cx="384" cy="624" r="9" fill="{c['cloth_accent_dark']}" stroke="{OUTLINE}" stroke-width="3"/>
<path d="M378 632 L 368 668 M 390 632 L 400 668" stroke="{c['cloth_accent']}" stroke-width="5" stroke-linecap="round"/>
<!-- 泡泡袖 -->
<path d="M296 574 C 248 584 230 640 254 700 C 276 722 318 716 332 694 C 324 650 318 610 306 580 Z"
  fill="url(#cloth)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M472 574 C 520 584 538 640 514 700 C 492 722 450 716 436 694 C 444 650 450 610 462 580 Z"
  fill="url(#cloth)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M256 696 q 10 10 20 2 q 10 10 20 2 q 10 10 20 2 q 8 8 16 -4" fill="none" stroke="{OUTLINE}" stroke-width="3"/>
<path d="M512 696 q -10 10 -20 2 q -10 10 -20 2 q -10 10 -20 2 q -8 8 -16 -4" fill="none" stroke="{OUTLINE}" stroke-width="3"/>
"""


def hands_feet(c: dict) -> str:
    return f"""
<!-- 鞋 -->
<ellipse cx="330" cy="830" rx="40" ry="20" fill="{c['sock']}" stroke="{OUTLINE}" stroke-width="5"/>
<ellipse cx="438" cy="830" rx="40" ry="20" fill="{c['sock']}" stroke="{OUTLINE}" stroke-width="5"/>
<ellipse cx="320" cy="824" rx="14" ry="5" fill="#FFFFFF" opacity="0.55"/>
<ellipse cx="428" cy="824" rx="14" ry="5" fill="#FFFFFF" opacity="0.55"/>
<!-- 放在膝前的小手 -->
<ellipse cx="350" cy="722" rx="30" ry="24" fill="{SKIN}" stroke="{OUTLINE}" stroke-width="5"/>
<ellipse cx="418" cy="722" rx="30" ry="24" fill="{SKIN}" stroke="{OUTLINE}" stroke-width="5"/>
<path d="M340 712 q 6 10 0 20 M 428 712 q -6 10 0 20" fill="none" stroke="{SKIN_SHADOW}" stroke-width="3"/>
"""


def head(c: dict) -> str:
    return f"""
<!-- 脸 -->
<path d="M220 380 C 220 250 300 196 384 196 C 468 196 548 250 548 380
  C 548 490 470 546 384 546 C 298 546 220 490 220 380 Z"
  fill="url(#face)" stroke="{OUTLINE}" stroke-width="5"/>
"""


def front_hair_550g(c: dict) -> str:
    return f"""
<!-- 刘海 -->
<path d="M196 420 C 176 250 268 150 384 148 C 506 146 600 240 578 420
  C 566 380 552 352 534 330 C 530 360 520 380 506 396 C 496 356 478 326 456 304
  C 450 336 436 360 418 376 C 412 340 400 312 384 296 C 368 322 352 346 330 364
  C 330 336 322 314 312 300 C 290 330 270 360 262 396 C 250 372 244 350 242 326
  C 220 350 206 386 196 420 Z"
  fill="url(#hair)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M300 210 C 330 196 360 190 390 192" fill="none" stroke="#FFFFFF" stroke-width="10" stroke-linecap="round" opacity="0.8"/>
<path d="M440 206 C 470 214 496 230 512 248" fill="none" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" opacity="0.7"/>
<path d="M384 296 C 380 270 372 248 356 230 M 456 304 C 452 280 444 262 430 246" fill="none" stroke="{c['hair_line']}" stroke-width="3" opacity="0.55"/>
<!-- 呆毛 -->
<path d="M386 150 C 370 110 380 84 412 76 C 396 96 396 120 404 146 Z" fill="url(#hair)" stroke="{OUTLINE}" stroke-width="4.5" stroke-linejoin="round"/>
<!-- 侧发（脸前） -->
<path d="M204 380 C 188 470 196 560 178 660 C 200 650 214 630 222 600 C 232 640 240 680 236 720
  C 262 680 268 600 258 520 C 252 470 240 430 232 400 Z"
  fill="url(#hair)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M564 380 C 580 470 572 560 590 660 C 568 650 554 630 546 600 C 536 640 528 680 532 720
  C 506 680 500 600 510 520 C 516 470 528 430 536 400 Z"
  fill="url(#hair)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<!-- 蓝色小鲸鱼发饰 -->
<g transform="translate(486 262) rotate(-12)">
  <path d="M-46 8 C -46 -22 -16 -36 12 -32 C 36 -28 50 -10 48 10 C 46 28 22 36 -6 34 C -30 32 -46 26 -46 8 Z"
    fill="{c['cloth_accent']}" stroke="{c['cloth_accent_dark']}" stroke-width="4"/>
  <path d="M46 4 C 60 -8 70 -6 74 -18 C 76 -2 70 10 74 22 C 64 16 56 16 46 14 Z" fill="{c['cloth_accent']}" stroke="{c['cloth_accent_dark']}" stroke-width="4" stroke-linejoin="round"/>
  <circle cx="-22" cy="0" r="5" fill="#1D2847"/>
  <circle cx="-4" cy="-14" r="5" fill="#FFFFFF" opacity="0.7"/>
  <circle cx="14" cy="-18" r="3.5" fill="#FFFFFF" opacity="0.7"/>
  <path d="M-30 14 q 6 5 12 0" fill="none" stroke="#1D2847" stroke-width="3" stroke-linecap="round"/>
</g>
"""


def front_hair_gpt(c: dict) -> str:
    return f"""
<path d="M196 420 C 178 250 270 150 384 148 C 500 146 594 244 574 420
  C 562 384 548 356 532 336 C 526 366 514 386 500 400 C 492 362 476 334 452 312
  C 446 344 432 368 414 380 C 406 346 396 320 382 302 C 368 330 350 352 328 368
  C 326 340 318 318 306 304 C 288 332 272 364 264 398 C 252 374 246 352 244 330
  C 222 354 206 388 196 420 Z"
  fill="url(#hair)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M296 214 C 326 198 358 192 392 194" fill="none" stroke="#FFFFFF" stroke-width="10" stroke-linecap="round" opacity="0.85"/>
<path d="M436 206 C 468 214 494 232 510 252" fill="none" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" opacity="0.75"/>
<path d="M382 302 C 378 276 370 252 354 234 M 452 312 C 448 286 440 266 426 250" fill="none" stroke="{c['hair_line']}" stroke-width="3" opacity="0.5"/>
<path d="M380 150 C 362 112 374 88 404 84 C 390 102 390 124 398 148 Z" fill="url(#hair)" stroke="{OUTLINE}" stroke-width="4.5" stroke-linejoin="round"/>
<!-- 侧发：下段渐变到浅绿 -->
<path d="M204 380 C 186 480 198 580 172 690 C 196 682 212 660 222 628 C 230 672 236 714 230 756
  C 260 712 268 620 258 530 C 252 476 240 432 232 400 Z"
  fill="url(#hair)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<path d="M564 380 C 582 480 570 580 596 690 C 572 682 556 660 546 628 C 538 672 532 714 538 756
  C 508 712 500 620 510 530 C 516 476 528 432 536 400 Z"
  fill="url(#hair)" stroke="{OUTLINE}" stroke-width="5" stroke-linejoin="round"/>
<!-- 白花发饰 + 缎带 -->
<g transform="translate(500 262)">
  <path d="M10 26 C 22 60 14 92 4 112 M 22 22 C 42 52 44 84 40 104" fill="none" stroke="#DCE9F4" stroke-width="9" stroke-linecap="round"/>
  <path d="M10 26 C 22 60 14 92 4 112 M 22 22 C 42 52 44 84 40 104" fill="none" stroke="{OUTLINE}" stroke-width="2" stroke-linecap="round" opacity="0.5"/>
  <g stroke="{OUTLINE}" stroke-width="3.5" fill="#FFFFFF">
    <ellipse cx="0" cy="-26" rx="17" ry="24"/>
    <ellipse cx="0" cy="-26" rx="17" ry="24" transform="rotate(72)"/>
    <ellipse cx="0" cy="-26" rx="17" ry="24" transform="rotate(144)"/>
    <ellipse cx="0" cy="-26" rx="17" ry="24" transform="rotate(216)"/>
    <ellipse cx="0" cy="-26" rx="17" ry="24" transform="rotate(288)"/>
  </g>
  <circle cx="0" cy="0" r="11" fill="#F6D774" stroke="{OUTLINE}" stroke-width="3"/>
  <ellipse cx="-30" cy="22" rx="16" ry="8" fill="{c['cloth_accent']}" stroke="{OUTLINE}" stroke-width="3" transform="rotate(-30 -30 22)"/>
</g>
"""


# ---------------------------------------------------------------- 表情
def eye_open(cx: int, cy: int, c: dict, mirror: bool) -> str:
    s = -1 if mirror else 1
    return f"""
<ellipse cx="{cx}" cy="{cy + 4}" rx="38" ry="48" fill="#FFFFFF"/>
<ellipse cx="{cx}" cy="{cy + 6}" rx="34" ry="44" fill="url(#iris)" stroke="{c['pupil']}" stroke-width="3"/>
<ellipse cx="{cx}" cy="{cy + 12}" rx="17" ry="22" fill="{c['pupil']}" opacity="0.85"/>
<ellipse cx="{cx}" cy="{cy + 34}" rx="20" ry="9" fill="#FFFFFF" opacity="0.35"/>
<ellipse cx="{cx - 13 * s}" cy="{cy - 12}" rx="11" ry="13" fill="#FFFFFF"/>
<circle cx="{cx + 14 * s}" cy="{cy + 22}" r="5.5" fill="#FFFFFF"/>
<path d="M{cx - 46 * s} {cy - 18} C {cx - 26 * s} {cy - 44} {cx + 26 * s} {cy - 48} {cx + 46 * s} {cy - 22}
  L {cx + 56 * s} {cy - 30}" fill="none" stroke="{OUTLINE}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M{cx - 26 * s} {cy + 52} C {cx - 8 * s} {cy + 56} {cx + 8 * s} {cy + 56} {cx + 22 * s} {cy + 52}"
  fill="none" stroke="{OUTLINE}" stroke-width="3" stroke-linecap="round" opacity="0.7"/>
"""


def eye_half(cx: int, cy: int, c: dict, mirror: bool) -> str:
    s = -1 if mirror else 1
    # 下半个虹膜 + 压低的上眼睑（用肤色眼睑覆盖上半部分，避免依赖 clipPath）
    return f"""
<ellipse cx="{cx}" cy="{cy + 14}" rx="36" ry="34" fill="#FFFFFF"/>
<ellipse cx="{cx}" cy="{cy + 16}" rx="33" ry="31" fill="url(#iris)" stroke="{c['pupil']}" stroke-width="3"/>
<ellipse cx="{cx}" cy="{cy + 18}" rx="16" ry="16" fill="{c['pupil']}" opacity="0.85"/>
<path d="M{cx - 50} {cy - 40} L {cx + 50} {cy - 40} L {cx + 50} {cy + 12} C {cx + 20} {cy + 4} {cx - 20} {cy + 4} {cx - 50} {cy + 12} Z" fill="{SKIN}"/>
<circle cx="{cx + 14 * s}" cy="{cy + 28}" r="4.5" fill="#FFFFFF"/>
<path d="M{cx - 44 * s} {cy + 12} C {cx - 20 * s} {cy + 2} {cx + 20 * s} {cy + 2} {cx + 46 * s} {cy + 10}
  L {cx + 54 * s} {cy + 4}" fill="none" stroke="{OUTLINE}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M{cx - 24 * s} {cy + 50} C {cx - 8 * s} {cy + 54} {cx + 8 * s} {cy + 54} {cx + 20 * s} {cy + 50}"
  fill="none" stroke="{OUTLINE}" stroke-width="3" stroke-linecap="round" opacity="0.7"/>
"""


def eye_closed(cx: int, cy: int, c: dict, mirror: bool) -> str:
    s = -1 if mirror else 1
    return f"""
<path d="M{cx - 40 * s} {cy + 14} C {cx - 18 * s} {cy + 36} {cx + 18 * s} {cy + 36} {cx + 42 * s} {cy + 12}"
  fill="none" stroke="{OUTLINE}" stroke-width="7.5" stroke-linecap="round"/>
<path d="M{cx + 42 * s} {cy + 12} l {10 * s} -8 M {cx - 40 * s} {cy + 14} l {-8 * s} -4"
  fill="none" stroke="{OUTLINE}" stroke-width="5" stroke-linecap="round"/>
"""


def eye_happy(cx: int, cy: int, c: dict, mirror: bool) -> str:
    # ^ ^ 笑眼
    return f"""
<path d="M{cx - 36} {cy + 26} C {cx - 22} {cy - 14} {cx + 22} {cy - 14} {cx + 36} {cy + 26}"
  fill="none" stroke="{OUTLINE}" stroke-width="9" stroke-linecap="round"/>
"""


def eye_sleep(cx: int, cy: int, c: dict, mirror: bool) -> str:
    s = -1 if mirror else 1
    return f"""
<path d="M{cx - 38 * s} {cy + 24} C {cx - 16 * s} {cy + 38} {cx + 16 * s} {cy + 38} {cx + 40 * s} {cy + 24}"
  fill="none" stroke="{OUTLINE}" stroke-width="7" stroke-linecap="round"/>
<path d="M{cx - 6 * s} {cy + 35} l {-3 * s} 9 M {cx + 12 * s} {cy + 34} l {2 * s} 9 M {cx + 28 * s} {cy + 30} l {6 * s} 8"
  fill="none" stroke="{OUTLINE}" stroke-width="3.5" stroke-linecap="round"/>
"""


def blush(c: dict, strength: float, lines: bool) -> str:
    out = f"""
<ellipse cx="282" cy="492" rx="40" ry="20" fill="url(#blush)" opacity="{strength}"/>
<ellipse cx="486" cy="492" rx="40" ry="20" fill="url(#blush)" opacity="{strength}"/>
"""
    if lines:
        out += f"""
<path d="M266 498 l 8 -14 M 280 500 l 8 -14 M 294 500 l 8 -14 M 474 500 l 8 -14 M 488 500 l 8 -14 M 502 498 l 8 -14"
  stroke="#E07A90" stroke-width="3.5" stroke-linecap="round"/>
"""
    return out


def mouth(kind: str, c: dict) -> str:
    m = c["mouth"]
    if kind == "neutral":
        return f'<path d="M370 506 C 378 512 390 512 398 506" fill="none" stroke="{m}" stroke-width="5" stroke-linecap="round"/>'
    if kind == "smile":
        return f'<path d="M364 502 C 374 516 394 516 404 502" fill="none" stroke="{m}" stroke-width="5" stroke-linecap="round"/>'
    if kind == "open_smile":
        return (f'<path d="M354 498 C 360 538 408 538 414 498 Z" fill="{m}" stroke="{OUTLINE}" stroke-width="4" stroke-linejoin="round"/>'
                f'<path d="M366 522 C 376 512 392 512 402 522 C 394 532 374 532 366 522 Z" fill="#F29BA9"/>')
    if kind == "wavy":  # 害羞的波浪嘴
        return (f'<path d="M352 510 q 8 -10 16 0 q 8 10 16 0 q 8 -10 16 0 q 8 10 16 0" fill="none" stroke="{m}" '
                f'stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>')
    if kind == "sleep_o":
        return f'<ellipse cx="384" cy="512" rx="9" ry="7" fill="{m}" stroke="{OUTLINE}" stroke-width="3"/>'
    raise ValueError(kind)


def face(frame: str, pet: str, c: dict) -> str:
    eyes = {"idle": eye_open, "blink_half": eye_half, "blink_closed": eye_closed,
            "cute": eye_happy, "sleep": eye_sleep}[frame]
    # mirror=True 时眼尾在 -x 侧（画面左），即左眼外侧
    out = eyes(*EYE_L, c, True) + eyes(*EYE_R, c, False)
    idle_mouth = "neutral" if pet == "550g" else "smile"
    if frame in ("idle", "blink_half", "blink_closed"):
        out += blush(c, 0.45, False) + mouth(idle_mouth, c)
    elif frame == "cute":
        out += blush(c, 1.0, True) + mouth("wavy" if pet == "550g" else "open_smile", c)
    elif frame == "sleep":
        out += blush(c, 0.55, False) + mouth("sleep_o", c)
    return out


def svg(pet: str, frame: str) -> str:
    c = PALETTES[pet]
    body = body_550g(c) if pet == "550g" else body_gpt(c)
    fh = front_hair_550g(c) if pet == "550g" else front_hair_gpt(c)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
{defs(c)}
<ellipse cx="384" cy="846" rx="250" ry="26" fill="url(#shadow)"/>
{back_hair(c)}
{body}
{hands_feet(c)}
{head(c)}
{face(frame, pet, c)}
{fh}
</svg>"""


FRAMES = ("idle", "blink_half", "blink_closed", "cute", "sleep")


def render_png(svg_text: str, out: Path) -> None:
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    if not r.isValid():
        raise RuntimeError(f"invalid svg for {out}")
    img = QImage(W, H, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    r.render(p)
    p.end()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not img.save(str(out), "PNG"):
        raise RuntimeError(f"cannot save {out}")


def tray_svg() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<defs>
 <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#648ED8"/><stop offset="1" stop-color="#81AF88"/>
 </linearGradient>
</defs>
<rect x="8" y="8" width="240" height="240" rx="60" fill="url(#g)"/>
<rect x="8" y="8" width="240" height="240" rx="60" fill="none" stroke="#FFFFFF" stroke-opacity="0.6" stroke-width="8"/>
<circle cx="92" cy="140" r="56" fill="#F4F5FB"/>
<circle cx="164" cy="140" r="56" fill="#F3FBEF"/>
<path d="M44 132 C 44 90 70 66 92 66 C 114 66 140 90 140 132 C 120 114 110 108 92 116 C 74 108 64 114 44 132 Z" fill="#DCE1F0"/>
<path d="M116 132 C 116 90 142 66 164 66 C 186 66 212 90 212 132 C 192 114 182 108 164 116 C 146 108 136 114 116 132 Z" fill="#CDE8C4"/>
<circle cx="76" cy="148" r="9" fill="#2E3E66"/><circle cx="108" cy="148" r="9" fill="#2E3E66"/>
<path d="M148 150 q 8 -10 16 0" fill="none" stroke="#2F5A3E" stroke-width="7" stroke-linecap="round"/>
<path d="M172 150 q 8 -10 16 0" fill="none" stroke="#2F5A3E" stroke-width="7" stroke-linecap="round"/>
<path d="M128 214 C 112 200 98 192 98 180 C 98 170 112 166 128 180 C 144 166 158 170 158 180 C 158 192 144 200 128 214 Z" fill="#F28CA0" stroke="#FFFFFF" stroke-width="5"/>
</svg>"""


def make_tray(out_dir: Path) -> None:
    tmp = out_dir / "tray.png"
    render_svg_size(tray_svg(), tmp, 256)
    try:
        from PIL import Image
    except ImportError:
        print("Pillow 未安装，只生成 tray.png（ICO 未生成）", file=sys.stderr)
        return
    im = Image.open(tmp).convert("RGBA")
    sizes = [(s, s) for s in (16, 20, 24, 32, 48, 64, 128, 256)]
    im.save(out_dir / "tray.ico", format="ICO", sizes=sizes)


def render_svg_size(svg_text: str, out: Path, size: int) -> None:
    from PySide6.QtCore import QByteArray, Qt
    from PySide6.QtGui import QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer
    r = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    img = QImage(size, size, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    r.render(p)
    p.end()
    img.save(str(out), "PNG")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent.parent / "assets")
    ap.add_argument("--keep-svg", type=Path, help="同时把源 SVG 写到该目录（原始绘制文件）")
    ap.add_argument("--frames-out", type=Path,
                    help="把占位角色帧写到该目录（默认不生成：正式帧来自概念图，见 extract_reference_sprites.py）")
    args = ap.parse_args()
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QGuiApplication
    _app = QGuiApplication.instance() or QGuiApplication([])
    for pet in PALETTES if args.frames_out else ():
        for frame in FRAMES:
            text = svg(pet, frame)
            render_png(text, args.frames_out / pet / f"{frame}.png")
            if args.keep_svg:
                d = args.keep_svg / pet
                d.mkdir(parents=True, exist_ok=True)
                (d / f"{frame}.svg").write_text(text, encoding="utf-8")
    make_tray(args.out)
    print("done:", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
