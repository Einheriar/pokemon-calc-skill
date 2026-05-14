#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Input normalization layer for pokemon-calc.

Maps aliases/short names to canonical names used by the index.
Only depends on Python standard library (difflib).
"""

import json
from pathlib import Path
from typing import Any
import difflib

_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_DIR = _SCRIPT_DIR.parent / "data"

_aliases_data: dict[str, dict[str, str]] | None = None

_TYPE_EN_TO_ZH: dict[str, str] = {
    "normal": "一般",
    "fighting": "格斗",
    "flying": "飞行",
    "poison": "毒",
    "ground": "地面",
    "rock": "岩石",
    "bug": "虫",
    "ghost": "幽灵",
    "steel": "钢",
    "fire": "火",
    "water": "水",
    "grass": "草",
    "electric": "电",
    "psychic": "超能力",
    "ice": "冰",
    "dragon": "龙",
    "dark": "恶",
    "fairy": "妖精",
}

_TYPE_ZH_SET: set[str] = set(_TYPE_EN_TO_ZH.values())


def _to_fullwidth(s: str) -> str:
    """Convert halfwidth ASCII letters/digits to fullwidth.

    Used for pokemon form suffixes like Y/X -> Ｙ/Ｘ.
    """
    result = []
    for ch in s:
        code = ord(ch)
        if 0x30 <= code <= 0x39:          # 0-9  -> ０-９
            result.append(chr(code + 0xFEE0))
        elif 0x41 <= code <= 0x5A:        # A-Z  -> Ａ-Ｚ
            result.append(chr(code + 0xFEE0))
        elif 0x61 <= code <= 0x7A:        # a-z  -> ａ-ｚ
            result.append(chr(code + 0xFEE0))
        else:
            result.append(ch)
    return "".join(result)


def _load_aliases() -> dict[str, dict[str, str]]:
    """Load alias mappings from aliases.json with global caching."""
    global _aliases_data
    if _aliases_data is None:
        path = _DATA_DIR / "aliases.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                _aliases_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            _aliases_data = {"pokemon": {}, "moves": {}, "abilities": {}, "items": {}, "natures": {}}
    # _aliases_data is always set above
    return _aliases_data  # type: ignore[return-value]


def normalize_name(name: str, entity_type: str) -> str:
    """Normalize a user-provided name to its canonical form.

    Args:
        name: Raw input name (may be alias, mixed case, halfwidth).
        entity_type: One of 'pokemon', 'moves', 'abilities', 'items', 'natures'.

    Returns:
        Canonical name if a mapping exists, otherwise the original name
        (case-preserved so downstream case-insensitive matching still works).
    """
    aliases = _load_aliases()
    alias_map = aliases.get(entity_type, {})

    # For pokemon, also apply fullwidth normalization before alias lookup
    lookup_name = name
    if entity_type == "pokemon":
        lookup_name = _to_fullwidth(name)

    # Try exact alias match first (case-sensitive)
    canonical = alias_map.get(lookup_name)
    if canonical:
        return canonical

    # Try lowercase alias match (case-insensitive)
    canonical = alias_map.get(lookup_name.lower())
    if canonical:
        return canonical

    # Also try lowercase on the original name (without fullwidth) for non-pokemon
    if entity_type != "pokemon":
        canonical = alias_map.get(name.lower())
        if canonical:
            return canonical

    # No alias found; return the original name unchanged
    return name


def normalize_type_name(name: str) -> str:
    """Normalize a user-provided type name to its canonical Chinese form.

    Args:
        name: Raw input name (may be English or Chinese, full or abbreviated).

    Returns:
        Chinese canonical name if the input is recognized;
        otherwise returns the original name unchanged.
    """
    # If already canonical Chinese, return as-is
    if name in _TYPE_ZH_SET:
        return name
    # Try English lookup (case-insensitive)
    canonical = _TYPE_EN_TO_ZH.get(name.lower())
    if canonical:
        return canonical
    # Fuzzy match for Chinese abbreviations (e.g. "超能" -> "超能力")
    import difflib
    close = difflib.get_close_matches(name, _TYPE_ZH_SET, n=1, cutoff=0.6)
    if close:
        return close[0]
    return name


def get_suggestions(name: str, candidates: list[str], n: int = 3) -> list[str]:
    """Return up to n closest string matches using difflib.

    Args:
        name: The user-provided (misspelled) name.
        candidates: List of valid canonical names to compare against.
        n: Maximum number of suggestions to return.

    Returns:
        Ordered list of closest candidate names.
    """
    # difflib.get_close_matches returns best matches first
    matches = difflib.get_close_matches(name, candidates, n=n, cutoff=0.4)
    return matches
