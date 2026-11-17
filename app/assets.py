"""资源路径解析与角色清单。

- resource_root() 不依赖当前工作目录：源码运行时是仓库 assets/，
  PyInstaller 冻结后是随包的 assets/（sys._MEIPASS 下）。
- 帧图像加载放在 pet_window/frames 中（需要 Qt），本模块只做路径与清单校验。
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REQUIRED_FRAMES = ("idle", "blink_closed", "cute", "sleep")
OPTIONAL_FRAMES = ("blink_half",)
ALL_FRAMES = REQUIRED_FRAMES + OPTIONAL_FRAMES


class AssetError(Exception):
    """必需资源缺失或损坏，程序无法正常显示角色。"""


def resource_root() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "assets"
    return Path(__file__).resolve().parent.parent / "assets"


@dataclass
class PetSpec:
    id: str
    name: str
    subtitle: str
    theme: str  # 主题色 #RRGGBB
    frames_dir: Path
    canvas_px: Tuple[int, int] = (768, 896)
    anchor_px: Tuple[int, int] = (384, 848)
    placeholder: bool = True
    # 额外表情：[(帧名, 菜单标签)]，可选；缺帧时回退 idle
    extras: Tuple[Tuple[str, str], ...] = ()
    badge: str = ""  # 气泡名字后的小图标：heart / clover / 空

    def frame_path(self, frame: str) -> Path:
        return self.frames_dir / f"{frame}.png"

    def missing_frames(self) -> Tuple[List[str], List[str]]:
        """返回 (缺失的必需帧, 缺失的可选帧)。"""
        req = [f for f in REQUIRED_FRAMES if not self.frame_path(f).is_file()]
        opt = [f for f in OPTIONAL_FRAMES if not self.frame_path(f).is_file()]
        return req, opt


@dataclass
class Manifest:
    pets: List[PetSpec]
    animation: dict = field(default_factory=dict)
    root: Path = field(default_factory=resource_root)

    def by_id(self, pet_id: str) -> Optional[PetSpec]:
        return next((p for p in self.pets if p.id == pet_id), None)


def load_manifest(root: Optional[Path] = None) -> Manifest:
    root = root or resource_root()
    path = root / "pets.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise AssetError(f"找不到角色清单：{path}")
    except (OSError, ValueError) as e:
        raise AssetError(f"角色清单无法读取：{path}（{e}）")
    pets: List[PetSpec] = []
    try:
        for p in data["pets"]:
            pets.append(PetSpec(
                id=str(p["id"]),
                name=str(p["name"]),
                subtitle=str(p.get("subtitle", "")),
                theme=str(p.get("theme", "#648ED8")),
                frames_dir=root / str(p["frames_dir"]),
                canvas_px=tuple(p.get("canvas_px", (768, 896))),  # type: ignore[arg-type]
                anchor_px=tuple(p.get("anchor_px", (384, 848))),  # type: ignore[arg-type]
                placeholder=bool(p.get("placeholder", True)),
                badge=str(p.get("badge", "")),
                extras=tuple((str(e["frame"]), str(e.get("label", e["frame"])))
                             for e in p.get("extras", [])),
            ))
    except (KeyError, TypeError) as e:
        raise AssetError(f"角色清单格式错误：{path}（{e}）")
    if not pets:
        raise AssetError(f"角色清单为空：{path}")
    return Manifest(pets=pets, animation=data.get("animation", {}), root=root)


def check_assets(manifest: Manifest) -> Dict[str, Tuple[List[str], List[str]]]:
    return {p.id: p.missing_frames() for p in manifest.pets}
