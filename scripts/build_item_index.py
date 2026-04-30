#!/usr/bin/env python3
"""Build item name index from pokemon-dataset-zh item_list.json."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET_DIR = ROOT.parent / "pokemon-dataset-zh" / "data"
DATA_DIR = ROOT / "data"


def _walk_items(node: dict | list, result: dict[str, str]) -> None:
    """Recursively walk item_list.json and collect name_zh -> name_en."""
    if isinstance(node, list):
        for child in node:
            _walk_items(child, result)
        return
    if not isinstance(node, dict):
        return
    if node.get("type") == "item":
        zh = node.get("name_zh")
        en = node.get("name_en")
        ja = node.get("name_ja")
        if zh and en:
            result[zh] = en
        if ja and en and ja not in result:
            result[ja] = en
        # Also map official Chinese berry names
        return
    for children in node.get("children", []):
        _walk_items(children, result)


def build() -> dict[str, str]:
    item_path = DATASET_DIR / "item_list.json"
    with open(item_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    result: dict[str, str] = {}
    _walk_items(data, result)
    return result


def main() -> int:
    items = build()
    print(f"Collected {len(items)} item name mappings.")

    index_path = DATA_DIR / "name_index.json"
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)

    index["items"] = items
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Updated {index_path} with items index.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
