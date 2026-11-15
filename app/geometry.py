"""多屏坐标约束（纯函数）。矩形使用 (x, y, w, h)，逻辑像素，可为负坐标。"""
from __future__ import annotations

from typing import Iterable, Optional, Sequence, Tuple

Rect = Tuple[int, int, int, int]
Point = Tuple[int, int]

SAFE_MARGIN = 24


def intersect_area(a: Rect, b: Rect) -> int:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[0] + a[2], b[0] + b[2])
    y2 = min(a[1] + a[3], b[1] + b[3])
    if x2 <= x1 or y2 <= y1:
        return 0
    return (x2 - x1) * (y2 - y1)


def contains_point(r: Rect, p: Point) -> bool:
    return r[0] <= p[0] < r[0] + r[2] and r[1] <= p[1] < r[1] + r[3]


def center(r: Rect) -> Point:
    return (r[0] + r[2] // 2, r[1] + r[3] // 2)


def is_mostly_visible(rect: Rect, screens: Iterable[Rect], min_fraction: float = 0.5) -> bool:
    """角色主要区域（默认一半以上面积）落在某个屏幕可用区域内才算可见。

    注意：不能用 x<0 判断离屏——左侧副屏的坐标本来就是负的。
    """
    area = rect[2] * rect[3]
    if area <= 0:
        return False
    best = max((intersect_area(rect, s) for s in screens), default=0)
    return best >= area * min_fraction


def clamp_into(rect: Rect, area: Rect) -> Point:
    """把 rect 平移到 area 内（area 放不下时左上对齐）。返回新的左上角。"""
    x = min(max(rect[0], area[0]), area[0] + area[2] - rect[2])
    y = min(max(rect[1], area[1]), area[1] + area[3] - rect[3])
    x = max(x, area[0])
    y = max(y, area[1])
    return (x, y)


def screen_for(rect: Rect, screens: Sequence[Rect]) -> Optional[Rect]:
    """返回包含 rect 中心的屏幕；没有则返回相交面积最大的屏幕；都不相交返回 None。"""
    c = center(rect)
    for s in screens:
        if contains_point(s, c):
            return s
    best = None
    best_area = 0
    for s in screens:
        a = intersect_area(rect, s)
        if a > best_area:
            best, best_area = s, a
    return best


def default_position(index: int, size: Tuple[int, int], primary: Rect, spacing: int = 16,
                     count: int = 2) -> Point:
    """主屏右下角并排摆放；index 0 在左。"""
    w, h = size
    total = count * w + (count - 1) * spacing
    x0 = primary[0] + primary[2] - total - SAFE_MARGIN
    y = primary[1] + primary[3] - h - SAFE_MARGIN
    x = x0 + index * (w + spacing)
    return clamp_into((x, y, w, h), primary)


def ensure_visible(rect: Rect, screens: Sequence[Rect], primary: Rect, fallback: Point) -> Point:
    """若角色主要区域不可见，返回主屏上的安全位置；否则保持原位。"""
    if screens and is_mostly_visible(rect, screens):
        return (rect[0], rect[1])
    return clamp_into((fallback[0], fallback[1], rect[2], rect[3]), primary)


def settle_after_drag(rect: Rect, screens: Sequence[Rect], primary: Rect) -> Point:
    """拖动结束：把角色收回到其所在（或最接近）屏幕的可用区域内。"""
    target = screen_for(rect, screens) or primary
    return clamp_into(rect, target)
