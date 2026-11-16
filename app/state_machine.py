"""无 UI 的角色状态机。

所有时间都由调用方传入（单调时钟秒数），因此可以在单元测试里精确驱动。
每只角色持有自己的 PetBrain 实例，状态、对白和计时互不影响。

状态：idle / blink / cute / sleep。
- blink 只能从 idle 自动进入，序列 half→closed→half，结束回 idle；
- cute 由单击或手动触发，持续 cute_seconds 后回 idle；
- sleep 由空闲超时或手动触发，只有单击或手动切换才会离开；
- 隐藏时 pause()，显示时 resume()，暂停期间的时间不计入任何截止时间。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Callable, Optional

IDLE = "idle"
BLINK = "blink"
CUTE = "cute"
SLEEP = "sleep"
EMOTE = "emote"  # 额外表情（惊讶/生气/开心/疑惑…），帧名由 emote_frame 指定，定时回到 idle
STATES = (IDLE, BLINK, CUTE, SLEEP)

# 帧名称与素材文件名一致
FRAME_IDLE = "idle"
FRAME_BLINK_HALF = "blink_half"
FRAME_BLINK_CLOSED = "blink_closed"
FRAME_CUTE = "cute"
FRAME_SLEEP = "sleep"


@dataclass
class TimingConfig:
    blink_interval: tuple[float, float] = (3.0, 7.0)
    # (帧名, 持续秒)；blink_half 是可选帧，缺帧时由渲染层回退
    blink_sequence: tuple[tuple[str, float], ...] = (
        (FRAME_BLINK_HALF, 0.04),
        (FRAME_BLINK_CLOSED, 0.10),
        (FRAME_BLINK_HALF, 0.04),
    )
    cute_seconds: float = 2.0
    bubble_seconds: float = 4.0
    sleep_after_inactivity: float = 180.0  # <=0 表示关闭自动睡眠

    @classmethod
    def from_dict(cls, d: dict) -> "TimingConfig":
        cfg = cls()
        if not isinstance(d, dict):
            return cfg
        try:
            lo, hi = d.get("blink_interval_seconds", cfg.blink_interval)
            lo, hi = float(lo), float(hi)
            if 0.5 <= lo <= hi <= 120:
                cfg.blink_interval = (lo, hi)
        except (TypeError, ValueError):
            pass
        seq = d.get("blink_sequence")
        if isinstance(seq, list) and seq:
            try:
                parsed = tuple((str(s["frame"]), float(s["duration_ms"]) / 1000.0) for s in seq)
                if all(0 < dur <= 2 for _, dur in parsed):
                    cfg.blink_sequence = parsed
            except (KeyError, TypeError, ValueError):
                pass
        for key, attr, lo, hi in (
            ("cute_seconds", "cute_seconds", 0.2, 30),
            ("bubble_seconds", "bubble_seconds", 0.5, 60),
            ("sleep_after_inactivity_seconds", "sleep_after_inactivity", -1, 24 * 3600),
        ):
            if key in d:
                try:
                    v = float(d[key])
                    if lo <= v <= hi:
                        setattr(cfg, attr, v)
                except (TypeError, ValueError):
                    pass
        return cfg

    @property
    def blink_total(self) -> float:
        return sum(d for _, d in self.blink_sequence)


# click() 的返回值，告诉 UI 该说哪类对白
EVENT_CLICK = "click"
EVENT_WAKE = "wake"


@dataclass
class PetBrain:
    timing: TimingConfig = field(default_factory=TimingConfig)
    rng: random.Random = field(default_factory=random.Random)
    now: float = 0.0

    state: str = IDLE
    state_started: float = 0.0
    state_until: Optional[float] = None
    next_blink_at: float = 0.0
    last_interaction: float = 0.0
    manual_sleep: bool = False
    emote_frame: str = ""

    bubble_text: str = ""
    bubble_until: Optional[float] = None

    paused_at: Optional[float] = None
    # 状态变化回调 (old, new, reason)
    on_state_change: Optional[Callable[[str, str, str], None]] = None

    def __post_init__(self) -> None:
        self.reset(self.now)

    # ---- 基础 ----
    def reset(self, now: float) -> None:
        self.now = now
        self.state = IDLE
        self.state_started = now
        self.state_until = None
        self.last_interaction = now
        self.manual_sleep = False
        self.bubble_text = ""
        self.bubble_until = None
        self.paused_at = None
        self._schedule_blink(now)

    def _schedule_blink(self, now: float) -> None:
        lo, hi = self.timing.blink_interval
        self.next_blink_at = now + self.rng.uniform(lo, hi)

    def _set_state(self, new: str, now: float, until: Optional[float], reason: str) -> None:
        old = self.state
        self.state = new
        self.state_started = now
        self.state_until = until
        if new == IDLE:
            self._schedule_blink(now)
        if new != SLEEP:
            self.manual_sleep = False
        if self.on_state_change and old != new:
            self.on_state_change(old, new, reason)

    # ---- 时间推进 ----
    def update(self, now: float) -> bool:
        """推进到 now。返回可见内容（帧或气泡）是否可能变化。"""
        if self.paused_at is not None:
            return False
        if now < self.now:  # 单调时钟不应倒退；防御性处理
            now = self.now
        before = (self.frame(), self.bubble_text)
        self.now = now

        if self.bubble_until is not None and now >= self.bubble_until:
            self.bubble_text = ""
            self.bubble_until = None

        # 循环处理，以便一次较大的时间跳跃也能落到正确状态（不会积压 timer）
        for _ in range(8):
            if self.state in (BLINK, CUTE, EMOTE) and self.state_until is not None and now >= self.state_until:
                self._set_state(IDLE, self.state_until, None, "timeout")
                continue
            if self.state == IDLE:
                sa = self.timing.sleep_after_inactivity
                if sa > 0 and now - self.last_interaction >= sa:
                    self._set_state(SLEEP, max(self.state_started, self.last_interaction + sa), None, "inactivity")
                    continue
                if now >= self.next_blink_at:
                    start = self.next_blink_at
                    end = start + self.timing.blink_total
                    if end <= now:
                        # 整个眨眼都在跳跃区间内，直接安排下一次
                        self._schedule_blink(now)
                        continue
                    self._set_state(BLINK, start, end, "auto_blink")
                    continue
            break
        return before != (self.frame(), self.bubble_text) or self.state == BLINK

    def frame(self) -> str:
        if self.state == BLINK:
            t = self.now - self.state_started
            acc = 0.0
            for name, dur in self.timing.blink_sequence:
                acc += dur
                if t < acc:
                    return name
            return FRAME_IDLE
        if self.state == CUTE:
            return FRAME_CUTE
        if self.state == SLEEP:
            return FRAME_SLEEP
        if self.state == EMOTE:
            return self.emote_frame or FRAME_IDLE
        return FRAME_IDLE

    # ---- 用户事件 ----
    def note_interaction(self, now: float) -> None:
        """拖动等非点击操作：只重置空闲计时，不改变表情。"""
        self.update(now)
        self.last_interaction = now

    def click(self, now: float) -> str:
        """左键单击。睡眠中则唤醒；之后进入 cute。返回对白类别。"""
        self.update(now)
        event = EVENT_WAKE if self.state == SLEEP else EVENT_CLICK
        self.last_interaction = now
        self._set_state(CUTE, now, now + self.timing.cute_seconds, "click")
        return event

    def set_manual(self, state: str, now: float) -> None:
        """右键菜单手动切换。手动操作优先于任何自动动作。"""
        if state not in STATES:
            raise ValueError(f"unknown state: {state}")
        self.update(now)
        self.last_interaction = now
        if state == IDLE:
            self._set_state(IDLE, now, None, "manual")
        elif state == BLINK:
            self._set_state(BLINK, now, now + self.timing.blink_total, "manual")
        elif state == CUTE:
            self._set_state(CUTE, now, now + self.timing.cute_seconds, "manual")
        elif state == SLEEP:
            self._set_state(SLEEP, now, None, "manual")
            self.manual_sleep = True

    def emote(self, frame: str, now: float, seconds: Optional[float] = None) -> str:
        """显示一个额外表情帧一段时间（默认 cute_seconds 的 1.5 倍）后回 idle。

        与 click() 一样会唤醒睡眠；返回对白类别（睡眠中为 wake，否则为表情名）。"""
        self.update(now)
        event = EVENT_WAKE if self.state == SLEEP else frame
        self.last_interaction = now
        self.emote_frame = frame
        dur = seconds if seconds is not None else self.timing.cute_seconds * 1.5
        self._set_state(EMOTE, now, now + dur, "emote")
        return event

    def say(self, text: str, now: float, seconds: Optional[float] = None) -> None:
        self.bubble_text = text
        self.bubble_until = now + (seconds if seconds is not None else self.timing.bubble_seconds)

    def clear_bubble(self) -> None:
        self.bubble_text = ""
        self.bubble_until = None

    # ---- 隐藏/显示 ----
    def pause(self, now: float) -> None:
        if self.paused_at is None:
            self.update(now)
            self.paused_at = now

    def resume(self, now: float) -> None:
        """恢复时把所有截止时间整体平移暂停时长，等于重建时间基准。"""
        if self.paused_at is None:
            return
        delta = max(0.0, now - self.paused_at)
        self.paused_at = None
        self.now = now
        self.state_started += delta
        if self.state_until is not None:
            self.state_until += delta
        if self.bubble_until is not None:
            self.bubble_until += delta
        self.next_blink_at += delta
        self.last_interaction += delta
