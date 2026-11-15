from app.interaction import RESULT_CLICK, RESULT_DRAG_END, PressTracker


def test_click_without_move():
    t = PressTracker(threshold=4)
    t.press((100, 100), (10, 10))
    assert t.release() == RESULT_CLICK


def test_small_jitter_is_still_click():
    t = PressTracker(threshold=4)
    t.press((100, 100), (10, 10))
    assert t.move((101, 102)) is None
    assert t.release() == RESULT_CLICK


def test_drag_beyond_threshold_moves_and_no_click():
    t = PressTracker(threshold=4)
    t.press((100, 100), (10, 10))
    assert t.move((110, 95)) == (20, 5)
    # 一旦进入拖动，回到阈值内也继续跟随
    assert t.move((101, 100)) == (11, 10)
    assert t.release() == RESULT_DRAG_END


def test_negative_coordinates():
    t = PressTracker(threshold=4)
    t.press((-1500, 200), (-1600, 100))
    assert t.move((-1520, 210)) == (-1620, 110)


def test_release_without_press_and_cancel():
    t = PressTracker()
    assert t.release() is None
    t.press((0, 0), (0, 0))
    t.cancel()
    assert not t.active and t.release() is None
