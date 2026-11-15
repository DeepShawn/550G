"""用户配置：JSON，原子写入，损坏或版本不支持时回退默认值。

配置写在用户目录（QStandardPaths.AppConfigLocation），绝不写到安装目录。
本模块不依赖 Qt，路径由调用方传入，便于测试。
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
SCALES = (0.75, 1.0, 1.25, 1.5)
DEFAULT_SCALE = 1.0
COORD_LIMIT = 100_000  # 超出这个范围的坐标视为损坏


@dataclass
class PetSettings:
    x: Optional[int] = None  # 角色区域左上角（逻辑像素，可为负）
    y: Optional[int] = None
    scale: float = DEFAULT_SCALE

    def to_dict(self) -> dict:
        d: dict = {"scale": self.scale}
        if self.x is not None and self.y is not None:
            d["x"] = self.x
            d["y"] = self.y
        return d

    @classmethod
    def from_dict(cls, d: object) -> "PetSettings":
        s = cls()
        if not isinstance(d, dict):
            return s
        x, y = d.get("x"), d.get("y")
        if (isinstance(x, int) and isinstance(y, int) and not isinstance(x, bool)
                and not isinstance(y, bool) and abs(x) < COORD_LIMIT and abs(y) < COORD_LIMIT):
            s.x, s.y = x, y
        sc = d.get("scale")
        if isinstance(sc, (int, float)) and not isinstance(sc, bool):
            # 只接受预设档位，避免巨型或零尺寸窗口
            nearest = min(SCALES, key=lambda v: abs(v - float(sc)))
            if abs(nearest - float(sc)) < 0.01:
                s.scale = nearest
        return s


@dataclass
class Settings:
    pets: Dict[str, PetSettings] = field(default_factory=dict)
    first_run_hint_shown: bool = False
    auto_sleep: bool = True
    load_problem: Optional[str] = None  # 仅运行期，用于日志/提示，不写盘

    def pet(self, pet_id: str) -> PetSettings:
        if pet_id not in self.pets:
            self.pets[pet_id] = PetSettings()
        return self.pets[pet_id]

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "first_run_hint_shown": self.first_run_hint_shown,
            "auto_sleep": self.auto_sleep,
            "pets": {k: v.to_dict() for k, v in self.pets.items()},
        }

    @classmethod
    def from_dict(cls, d: object) -> "Settings":
        s = cls()
        if not isinstance(d, dict):
            s.load_problem = "配置根节点不是对象"
            return s
        ver = d.get("schema_version")
        if ver != SCHEMA_VERSION:
            s.load_problem = f"不支持的配置版本: {ver!r}"
            return s
        s.first_run_hint_shown = bool(d.get("first_run_hint_shown", False))
        s.auto_sleep = bool(d.get("auto_sleep", True))
        pets = d.get("pets", {})
        if isinstance(pets, dict):
            for k, v in pets.items():
                if isinstance(k, str):
                    s.pets[k] = PetSettings.from_dict(v)
        return s


def load(path: Path) -> Settings:
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        log.warning("配置文件损坏，使用默认值：%s (%s)", path, e)
        s = Settings()
        s.load_problem = f"配置文件损坏: {e}"
        _backup_broken(path)
        return s
    s = Settings.from_dict(data)
    if s.load_problem:
        log.warning("配置不可用，使用默认值：%s (%s)", path, s.load_problem)
        _backup_broken(path)
    return s


def _backup_broken(path: Path) -> None:
    try:
        os.replace(path, path.with_suffix(path.suffix + ".broken"))
    except OSError:
        pass


def save(settings: Settings, path: Path) -> bool:
    """临时文件 + os.replace 原子替换。失败只记录日志，不抛出。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".settings-", suffix=".tmp", dir=str(path.parent))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(settings.to_dict(), f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return True
    except OSError as e:
        log.error("保存配置失败：%s (%s)", path, e)
        return False
