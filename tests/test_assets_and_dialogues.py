import json
import random
import shutil
from pathlib import Path

import pytest

from app.assets import REQUIRED_FRAMES, AssetError, check_assets, load_manifest, resource_root
from app.dialogues import DialoguePool, load_dialogues

ROOT = resource_root()


def test_resource_root_independent_of_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resource_root() == ROOT
    assert (resource_root() / "pets.json").is_file()


def test_manifest_has_two_pets_with_all_required_frames():
    m = load_manifest(ROOT)
    assert [p.id for p in m.pets] == ["550g", "gpt_senpai"]
    for pid, (req, _opt) in check_assets(m).items():
        assert req == [], pid


def test_missing_manifest_raises(tmp_path):
    with pytest.raises(AssetError):
        load_manifest(tmp_path)


def test_dialogues_cover_all_categories():
    d = load_dialogues(ROOT / "dialogues.json")
    assert set(d) == {"550g", "gpt_senpai"}
    for pool in d.values():
        for c in ("greeting", "click", "cute", "sleep", "wake"):
            assert pool.lines[c], c


def test_pool_no_immediate_repeat_across_rounds():
    p = DialoguePool({"click": ["a", "b", "c"]}, rng=random.Random(3))
    seq = [p.pick("click") for _ in range(30)]
    assert all(x != y for x, y in zip(seq, seq[1:]))
    assert set(seq) == {"a", "b", "c"}


def test_pool_missing_category_falls_back():
    p = DialoguePool({"click": ["x"]})
    assert p.pick("wake") == "x"


def test_bad_dialogue_file(tmp_path):
    f = tmp_path / "d.json"
    f.write_text("[]", encoding="utf-8")
    assert load_dialogues(f) == {}


def make_asset_copy(tmp_path: Path, drop: list[str]) -> Path:
    dst = tmp_path / "assets"
    shutil.copytree(ROOT, dst)
    for rel in drop:
        (dst / rel).unlink()
    return dst


def test_frameset_fallbacks(qapp, tmp_path):
    from app.frames import FrameSet
    root = make_asset_copy(tmp_path, ["pets/550g/blink_half.png", "pets/550g/cute.png"])
    spec = load_manifest(root).by_id("550g")
    fs = FrameSet(spec)
    assert fs.resolve("blink_half") == "idle"
    assert fs.resolve("cute") == "idle"
    assert fs.missing_required() == ["cute"]
    assert any("cute" in p for p in fs.problems)
    assert not any("blink_half" in p for p in fs.problems)  # 可选帧不算问题


def test_frameset_missing_idle_raises(qapp, tmp_path):
    from app.frames import FrameSet
    root = make_asset_copy(tmp_path, ["pets/gpt_senpai/idle.png"])
    with pytest.raises(AssetError):
        FrameSet(load_manifest(root).by_id("gpt_senpai"))


def test_hit_region_excludes_transparent_corners(qapp):
    from PySide6.QtCore import QPoint, QSize
    from app.frames import FrameSet
    fs = FrameSet(load_manifest(ROOT).by_id("550g"))
    reg = fs.hit_region(QSize(240, 280), 3)
    assert reg.contains(QPoint(120, 140))  # 脸
    assert not reg.contains(QPoint(2, 2))
    assert not reg.contains(QPoint(237, 2))


def test_frames_same_canvas():
    from PIL import Image
    m = load_manifest(ROOT)
    for spec in m.pets:
        sizes = {Image.open(spec.frame_path(f)).size for f in REQUIRED_FRAMES}
        assert sizes == {tuple(spec.canvas_px)}


def test_extras_optional_and_valid_if_declared():
    m = load_manifest(ROOT)
    for spec in m.pets:
        for frame, label in spec.extras:
            assert spec.frame_path(frame).is_file(), frame
            assert label
        assert spec.badge in ("", "heart", "clover")


def test_frameset_loads_declared_extra(qapp, tmp_path):
    import json as _json
    from app.frames import FrameSet
    root = make_asset_copy(tmp_path, [])
    shutil.copy(root / "pets/550g/cute.png", root / "pets/550g/wave.png")
    data = _json.loads((root / "pets.json").read_text(encoding="utf-8"))
    data["pets"][0]["extras"] = [{"frame": "wave", "label": "挥手"}, {"frame": "missing", "label": "缺"}]
    (root / "pets.json").write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
    spec = load_manifest(root).by_id("550g")
    assert spec.extras == (("wave", "挥手"), ("missing", "缺"))
    fs = FrameSet(spec)
    assert fs.resolve("wave") == "wave"
    assert fs.resolve("missing") == "idle"  # 额外表情缺帧回退，不算必需帧问题
    assert not fs.problems
