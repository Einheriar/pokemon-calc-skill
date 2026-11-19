#!/usr/bin/env python3
"""Offline range lookup over user-curated, precomputed Speed references."""
from __future__ import annotations

from bisect import bisect_left, bisect_right
import json
from pathlib import Path


def find_speed_references(data_dir: Path, value: int, radius: int = 5) -> dict:
    """Return every selected configuration in the inclusive numeric window."""
    if type(value) is not int or not 0 <= value <= 10000:
        raise ValueError("速度能力值必须是 0 至 10000 的整数")
    if type(radius) is not int or radius < 0:
        raise ValueError("速度参考范围必须是非负整数")
    with (Path(data_dir) / "speed_tiers.json").open(encoding="utf-8") as stream:
        data = json.load(stream)
    if not isinstance(data, dict) or data.get("schema_version") != 1 or data.get("level") != 50:
        raise ValueError("速度参考数据版本或等级不匹配")
    if not isinstance(data.get("profiles"), dict) or not isinstance(data.get("groups"), dict):
        raise ValueError("速度参考数据缺少配置或速度分组")
    if (any(not isinstance(group, list) for group in data["groups"].values())
            or sum(len(group) for group in data["groups"].values()) != data.get("count")):
        raise ValueError("速度参考数据条数不匹配")
    labels = {code: label for label, code in data["profiles"].items()}
    groups = data["groups"]
    speeds = sorted(int(key) for key in groups)
    if any(not 0 <= speed <= 10000 for speed in speeds):
        raise ValueError("速度参考数据包含无效速度")
    lower, upper = max(0, value - radius), min(10000, value + radius)
    selected = speeds[bisect_left(speeds, lower):bisect_right(speeds, upper)]
    matches = []
    for speed in reversed(selected):
        delta = speed - value
        for name, profile, state in groups[str(speed)]:
            matches.append({
                "speed": speed, "delta": delta,
                "relation": "同速" if delta == 0 else "更快" if delta > 0 else "更慢",
                "name": name, "profile": labels[profile], "condition": state or "基础",
            })
    return {
        "target_speed": value, "range": radius, "lower": lower, "upper": upper,
        "level": data["level"], "regulation": data["regulation"],
        "basis": "effective_speed", "selection": "用户精选参照，不代表使用率分位",
        "match_count": len(matches), "matches": matches,
        "note": "范围内没有已收录的速度线参照；未扩大范围" if not matches else "包含范围边界",
    }
