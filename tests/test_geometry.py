from app import geometry as g

PRIMARY = (0, 0, 1920, 1040)
LEFT = (-1280, 0, 1280, 984)  # 左侧副屏，负坐标


def test_negative_coords_on_left_screen_are_visible():
    r = (-800, 300, 240, 280)
    assert g.is_mostly_visible(r, [PRIMARY, LEFT])
    assert g.ensure_visible(r, [PRIMARY, LEFT], PRIMARY, (100, 100)) == (-800, 300)


def test_offscreen_after_unplug_moves_to_primary():
    r = (-800, 300, 240, 280)
    assert g.ensure_visible(r, [PRIMARY], PRIMARY, (1500, 700)) == (1500, 700)


def test_mostly_offscreen_is_not_visible():
    r = (1800, 900, 240, 280)  # 只有一小角在屏幕内
    assert not g.is_mostly_visible(r, [PRIMARY])


def test_fallback_is_clamped_into_primary():
    assert g.ensure_visible((5000, 5000, 240, 280), [PRIMARY], PRIMARY, (1900, 1030)) == (1680, 760)


def test_settle_after_drag_clamps_into_own_screen():
    # 中心在左屏，越过左屏左边缘
    assert g.settle_after_drag((-1300, 100, 240, 280), [PRIMARY, LEFT], PRIMARY) == (-1280, 100)
    # 跨屏拖到主屏底部之外
    assert g.settle_after_drag((500, 900, 240, 280), [PRIMARY, LEFT], PRIMARY) == (500, 760)


def test_default_positions_side_by_side_bottom_right():
    a = g.default_position(0, (284, 280), PRIMARY, spacing=0, count=2)
    b = g.default_position(1, (284, 280), PRIMARY, spacing=0, count=2)
    assert a[1] == b[1] == 1040 - 280 - g.SAFE_MARGIN
    assert b[0] - a[0] == 284
    assert b[0] + 284 == 1920 - g.SAFE_MARGIN


def test_clamp_when_area_too_small():
    assert g.clamp_into((50, 50, 500, 500), (0, 0, 300, 300)) == (0, 0)
