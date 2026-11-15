"""离线预设对白。每个类别使用“洗牌袋”轮播，避免连续重复。"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

CATEGORIES = ("greeting", "click", "cute", "sleep", "wake")


class DialoguePool:
    def __init__(self, lines: Dict[str, List[str]], rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self.lines = {k: [s for s in v if isinstance(s, str) and s.strip()] for k, v in lines.items()}
        self._bags: Dict[str, List[str]] = {}
        self._last: Dict[str, str] = {}

    def pick(self, category: str) -> str:
        pool = self.lines.get(category) or self.lines.get("click") or ["……"]
        bag = self._bags.get(category)
        if not bag:
            bag = list(pool)
            self.rng.shuffle(bag)
            # 新一轮的第一句不要与上一轮最后一句相同
            if len(bag) > 1 and bag[-1] == self._last.get(category):
                bag[0], bag[-1] = bag[-1], bag[0]
            self._bags[category] = bag
        line = bag.pop()
        self._last[category] = line
        return line


def load_dialogues(path: Path) -> Dict[str, DialoguePool]:
    """读取 dialogues.json；失败时返回空字典（调用方使用内置兜底对白）。"""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        pets = data["pets"]
        return {pid: DialoguePool({c: list(v.get(c, [])) for c in CATEGORIES}) for pid, v in pets.items()}
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        log.error("对白文件读取失败：%s (%s)", path, e)
        return {}
