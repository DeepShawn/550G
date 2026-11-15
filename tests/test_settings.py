import json

from app import settings as s


def test_roundtrip(tmp_path):
    p = tmp_path / "cfg" / "settings.json"
    st = s.Settings()
    st.pet("550g").x, st.pet("550g").y, st.pet("550g").scale = -900, 120, 1.25
    st.first_run_hint_shown = True
    assert s.save(st, p)
    st2 = s.load(p)
    assert st2.pet("550g").x == -900 and st2.pet("550g").scale == 1.25
    assert st2.first_run_hint_shown and st2.load_problem is None
    assert not list(p.parent.glob(".settings-*"))  # 无残留临时文件


def test_missing_file_defaults(tmp_path):
    st = s.load(tmp_path / "nope.json")
    assert st.pets == {} and st.load_problem is None


def test_corrupt_file_falls_back_and_backs_up(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text("{not json", encoding="utf-8")
    st = s.load(p)
    assert st.load_problem and st.pets == {}
    assert (tmp_path / "settings.json.broken").exists()


def test_unsupported_version(tmp_path):
    p = tmp_path / "settings.json"
    p.write_text(json.dumps({"schema_version": 99, "pets": {"550g": {"x": 1, "y": 2}}}), encoding="utf-8")
    st = s.load(p)
    assert st.load_problem and st.pets == {}


def test_bad_values_rejected():
    st = s.Settings.from_dict({"schema_version": 1, "pets": {
        "a": {"x": 10**9, "y": 5, "scale": 37},
        "b": {"x": True, "y": 1, "scale": 0},
        "c": {"x": 3, "y": 4, "scale": 0.75},
    }})
    assert st.pets["a"].x is None and st.pets["a"].scale == 1.0
    assert st.pets["b"].x is None and st.pets["b"].scale == 1.0
    assert (st.pets["c"].x, st.pets["c"].scale) == (3, 0.75)
