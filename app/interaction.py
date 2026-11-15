"""点击与拖动的判定（纯逻辑，坐标均为全局逻辑像素 (x, y) 元组）。

按下时只记录位置；移动距离超过阈值才进入拖动；释放时若从未拖动才算一次单击。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

Point = Tuple[int, int]

RESULT_NONE = None
RESULT_CLICK = "click"
RESULT_DRAG_END = "drag_end"


@dataclass
class PressTracker:
    threshold: int = 4
    press_global: Optional[Point] = None
    press_window: Optional[Point] = None
    dragging: bool = False

    @property
    def active(self) -> bool:
        return self.press_global is not None

    def press(self, global_pos: Point, window_pos: Point) -> None:
        self.press_global = global_pos
        self.press_window = window_pos
        self.dragging = False

    def move(self, global_pos: Point) -> Optional[Point]:
        """返回新的窗口左上角；未进入拖动时返回 None。"""
        if self.press_global is None or self.press_window is None:
            return None
        dx = global_pos[0] - self.press_global[0]
        dy = global_pos[1] - self.press_global[1]
        if not self.dragging:
            # 与 Qt 的 startDragDistance 一致，使用曼哈顿长度
            if abs(dx) + abs(dy) < self.threshold:
                return None
            self.dragging = True
        return (self.press_window[0] + dx, self.press_window[1] + dy)

    def release(self) -> Optional[str]:
        if self.press_global is None:
            return RESULT_NONE
        result = RESULT_DRAG_END if self.dragging else RESULT_CLICK
        self.cancel()
        return result

    def cancel(self) -> None:
        self.press_global = None
        self.press_window = None
        self.dragging = False
