import random

import pytest

from app.state_machine import (BLINK, CUTE, EVENT_CLICK, EVENT_WAKE, IDLE, SLEEP, PetBrain,
                               TimingConfig)


def brain(**kw):
    t = TimingConfig(**kw)
    return PetBrain(timing=t, rng=random.Random(1), now=0.0)


def test_starts_idle_and_blink_scheduled_in_range():
    b = brain()
    assert b.state == IDLE and b.frame() == "idle"
    assert 3.0 <= b.next_blink_at <= 7.0


def test_blink_sequence_and_return_to_idle():
    b = brain()
    t0 = b.next_blink_at
    b.update(t0 + 0.01)
    assert b.state == BLINK and b.frame() == "blink_half"
    b.update(t0 + 0.08)
    assert b.frame() == "blink_closed"
    b.update(t0 + 0.16)
    assert b.frame() == "blink_half"
    b.update(t0 + 0.30)
    assert b.state == IDLE and b.frame() == "idle"
    assert b.next_blink_at > t0 + 0.18


def test_click_goes_cute_then_idle():
    b = brain()
    assert b.click(1.0) == EVENT_CLICK
    assert b.state == CUTE and b.frame() == "cute"
    b.update(2.9)
    assert b.state == CUTE
    b.update(3.01)
    assert b.state == IDLE


def test_no_blink_during_cute():
    b = brain(blink_interval=(3.0, 3.0))
    b.click(2.5)  # cute until 4.5, blink would be due at 3.0
    for t in (3.0, 3.05, 3.1, 4.0):
        b.update(t)
        assert b.state == CUTE


def test_auto_sleep_after_inactivity_and_blink_does_not_wake():
    b = brain(sleep_after_inactivity=10.0)
    b.update(10.5)
    assert b.state == SLEEP
    for t in range(11, 60):
        b.update(float(t))
        assert b.state == SLEEP and b.frame() == "sleep"


def test_click_wakes_sleep():
    b = brain()
    b.set_manual(SLEEP, 1.0)
    b.update(500.0)
    assert b.state == SLEEP
    assert b.click(501.0) == EVENT_WAKE
    assert b.state == CUTE


def test_manual_sleep_not_left_automatically():
    b = brain(sleep_after_inactivity=5.0)
    b.set_manual(SLEEP, 1.0)
    b.update(1000.0)
    assert b.state == SLEEP


def test_manual_idle_reschedules_blink():
    b = brain()
    b.set_manual(SLEEP, 1.0)
    b.set_manual(IDLE, 2.0)
    assert b.state == IDLE and b.next_blink_at >= 5.0


def test_manual_overrides_blink():
    b = brain()
    t0 = b.next_blink_at
    b.update(t0 + 0.01)
    assert b.state == BLINK
    b.set_manual(CUTE, t0 + 0.02)
    assert b.state == CUTE


def test_sleep_wins_when_blink_and_sleep_coincide():
    b = brain(blink_interval=(10.0, 10.0), sleep_after_inactivity=10.0)
    b.update(10.05)
    assert b.state == SLEEP


def test_large_time_jump_settles_correctly():
    b = brain(sleep_after_inactivity=180.0)
    b.click(1.0)
    b.update(10_000.0)
    assert b.state == SLEEP


def test_drag_interaction_resets_idle_timer():
    b = brain(sleep_after_inactivity=10.0)
    b.note_interaction(9.0)
    b.update(15.0)
    assert b.state != SLEEP
    b.update(19.5)
    assert b.state == SLEEP


def test_bubble_expires():
    b = brain()
    b.say("hi", 1.0)
    b.update(4.9)
    assert b.bubble_text == "hi"
    b.update(5.01)
    assert b.bubble_text == ""


def test_pause_resume_shifts_deadlines():
    b = brain(sleep_after_inactivity=10.0)
    b.say("x", 1.0)
    b.click(1.0)
    b.pause(2.0)
    b.update(1000.0)  # 隐藏期间不推进
    assert b.state == CUTE
    b.resume(1000.0)
    b.update(1000.5)
    assert b.state == CUTE and b.bubble_text == "x"
    b.update(1001.1)
    assert b.state == IDLE
    b.update(1008.0)
    assert b.state != SLEEP  # 空闲计时也被平移


def test_two_brains_independent():
    a, c = brain(), brain()
    a.click(1.0)
    a.say("A", 1.0)
    c.update(1.0)
    assert c.state == IDLE and c.bubble_text == ""


def test_unknown_manual_state_raises():
    with pytest.raises(ValueError):
        brain().set_manual("dance", 0.0)


def test_timing_from_dict_validates():
    t = TimingConfig.from_dict({"blink_interval_seconds": [5, 1], "cute_seconds": 3,
                                "sleep_after_inactivity_seconds": "x",
                                "blink_sequence": [{"frame": "blink_closed", "duration_ms": 120}]})
    assert t.blink_interval == (3.0, 7.0)
    assert t.cute_seconds == 3
    assert t.sleep_after_inactivity == 180.0
    assert t.blink_sequence == (("blink_closed", 0.12),)
