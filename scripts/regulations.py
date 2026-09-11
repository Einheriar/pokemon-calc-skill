#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Single source of truth for Pokémon Champions regulation identity/order.

A regulation ("M-A" / "M-B" / "M-C") is carried in data as a *string identity*
(for example each Champions patch form is tagged with the regulation that
introduced it). The *ordering* of those identities, the current regulation, and
which regulation each data source currently publishes live only in
``data/regulation_manifest.json`` — never hardcoded per module.

Keeping identity and ordering separate means a future insertion/rename only
edits the manifest, leaving every stored record untouched.
"""

import json
import os
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_DATA_DIR = _SCRIPT_DIR.parent / "data"
MANIFEST_NAME = "regulation_manifest.json"

# Fallback for a stripped install where the manifest is unreadable. Kept in
# sync with data/regulation_manifest.json; the file is authoritative.
_FALLBACK = {
    "schema_version": 1,
    "current": "M-C",
    "regulations": [
        {"id": "M-A", "order": 10},
        {"id": "M-B", "order": 20},
        {"id": "M-C", "order": 30},
    ],
    "sources": {"tournament": "M-C", "ingame": "M-C", "showdown": "M-B"},
}


def _data_dir(data_dir=None) -> Path:
    if data_dir is not None:
        return Path(data_dir)
    return Path(os.environ.get("POKEMON_CALC_DATA_DIR", str(_DEFAULT_DATA_DIR)))


def normalize(reg_id) -> str:
    """Normalize a regulation id to canonical uppercase ('m-c' -> 'M-C')."""
    return str(reg_id or "").strip().upper()


def load_manifest(data_dir=None) -> dict:
    """Load the manifest, falling back to the built-in copy if unreadable."""
    path = _data_dir(data_dir) / MANIFEST_NAME
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("regulations"):
            return data
    except Exception:
        pass
    return json.loads(json.dumps(_FALLBACK))


def ordered(data_dir=None) -> list[dict]:
    """Regulations sorted oldest -> newest by their 'order' value."""
    regs = load_manifest(data_dir).get("regulations", [])
    return sorted(regs, key=lambda r: r.get("order", 0))


def ordered_ids(data_dir=None) -> list[str]:
    return [normalize(r.get("id")) for r in ordered(data_dir)]


def current(data_dir=None) -> str:
    """The newest regulation overall."""
    return normalize(load_manifest(data_dir).get("current"))


def order_of(reg_id, data_dir=None) -> int | None:
    """Ordering key of a regulation, or None when unknown."""
    target = normalize(reg_id)
    for r in load_manifest(data_dir).get("regulations", []):
        if normalize(r.get("id")) == target:
            return r.get("order")
    return None


def rank_of(reg_id, data_dir=None) -> int:
    """0-based position in chronological order; unknown ids sort last."""
    target = normalize(reg_id)
    ids = ordered_ids(data_dir)
    return ids.index(target) if target in ids else len(ids)


def source_regulation(kind: str, data_dir=None) -> str:
    """Regulation a given data source publishes (falls back to current)."""
    sources = load_manifest(data_dir).get("sources", {})
    return normalize(sources.get(kind) or current(data_dir))


def within(reg_id, max_reg_id, data_dir=None) -> bool:
    """Whether reg_id is at or before max_reg_id in regulation order.

    This is the cumulative ("introduced in or before") view used by the
    internal regulation cap; an unknown id is treated as out of range.
    """
    a = order_of(reg_id, data_dir)
    b = order_of(max_reg_id, data_dir)
    if a is None or b is None:
        return False
    return a <= b
