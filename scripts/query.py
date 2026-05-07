#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pokemon encyclopedia query tool (Phase 1).
Loads consolidated JSON data and answers lookup queries.

Usage:
    python query.py pokemon <name>          # Full pokemon info
    python query.py move <name>             # Move info
    python query.py ability <name>          # Ability info
    python query.py type <atk> <def>        # Type effectiveness
    python query.py stats <name>            # Base stats
    python query.py weak <name>             # Weakness / resistance
    python query.py learnset <name>         # Learnable moves (level/tm/egg/tutor)
    python query.py evo <name>              # Evolution chain
    python query.py pokedex <name>          # Pokedex entries
    python query.py profile <name>          # Profile + prototype + detail
    python query.py find-move <move_name>   # Reverse: pokemon that learn a move
    python query.py preset <pokemon>        # List presets for a pokemon
    python query.py preset <pokemon> <name> # Get specific preset config
"""

import io
import json
import sys
from pathlib import Path
from typing import Any

from normalize import get_suggestions, normalize_name

# Force UTF-8 stdout/stderr on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

_pokemon_data: dict[str, Any] | None = None
_moves_data: dict[str, Any] | None = None
_abilities_data: dict[str, Any] | None = None
_index_data: dict[str, Any] | None = None
_type_chart: dict[str, dict[str, float]] | None = None


def _load_json(name: str) -> Any:
    path = DATA_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data() -> None:
    global _pokemon_data, _moves_data, _abilities_data, _index_data, _type_chart
    if _pokemon_data is None:
        _pokemon_data = _load_json("pokemon.json")
        _moves_data = _load_json("moves.json")
        _abilities_data = _load_json("abilities.json")
        _index_data = _load_json("name_index.json")
        _type_chart = _load_json("type_chart.json")


_setdex_data: dict[str, Any] | None = None


def _load_setdex() -> dict[str, Any]:
    global _setdex_data
    if _setdex_data is None:
        path = DATA_DIR / "setdex.json"
        with open(path, "r", encoding="utf-8") as f:
            _setdex_data = json.load(f)
    return _setdex_data


def _resolve_preset(pokemon_name: str, preset_name: str | None = None) -> dict[str, Any] | None:
    """Resolve preset by pokemon name (zh or en) and optional preset name.
    
    Returns dict with presets list, or specific preset config.
    """
    load_data()
    setdex = _load_setdex()
    
    # Try direct match (English name)
    pokemon_en = None
    if pokemon_name in setdex:
        pokemon_en = pokemon_name
    else:
        # Use resolve_pokemon to get the English name from Chinese name
        resolved = resolve_pokemon(pokemon_name)
        if resolved:
            _, data, _ = resolved
            pokemon_en = data.get("name_en", "")
    
    if not pokemon_en or pokemon_en not in setdex:
        return None
    
    presets = setdex[pokemon_en]
    if preset_name is None:
        return {"pokemon_en": pokemon_en, "presets": list(presets.keys())}
    
    if preset_name not in presets:
        return None
    
    return {"pokemon_en": pokemon_en, "preset_name": preset_name, "config": presets[preset_name]}


def _apply_preset_to_override(override: dict[str, Any], pokemon_en: str) -> dict[str, Any]:
    """If override contains 'preset' key, merge preset config with override.
    
    Preset fields are used as base, override fields take precedence.
    Filters out fields not supported by the Pokemon model (e.g. moves).
    """
    preset_name = override.pop("preset", None)
    if preset_name is None:
        return override
    
    setdex = _load_setdex()
    if pokemon_en not in setdex:
        return override
    
    presets = setdex[pokemon_en]
    if preset_name not in presets:
        return override
    
    # Fields that Pokemon model accepts; discard setdex-specific fields like 'moves'
    _VALID_PK_FIELDS = {
        "name", "name_en", "level", "base_stats", "evs", "ivs",
        "nature", "ability", "item", "types", "tera_type",
        "is_terastalize", "boosts", "current_hp", "max_hp",
        "status", "weight", "is_dynamax", "can_evolve",
        "raw_stats", "stats",
    }
    
    preset_config = {k: v for k, v in presets[preset_name].items() if k in _VALID_PK_FIELDS}
    # User override takes precedence over preset
    preset_config.update(override)
    return preset_config


def cmd_preset(pokemon_name: str, preset_name: str = "") -> dict[str, Any]:
    """List presets for a pokemon, or get a specific preset config."""
    resolved = _resolve_preset(pokemon_name, preset_name or None)
    if not resolved:
        if preset_name:
            return {"error": f"Preset '{preset_name}' not found for '{pokemon_name}'."}
        return {"error": f"No presets found for '{pokemon_name}'."}
    
    if "presets" in resolved:
        return {
            "pokemon": pokemon_name,
            "pokemon_en": resolved["pokemon_en"],
            "presets": resolved["presets"],
            "count": len(resolved["presets"]),
        }
    return {
        "pokemon": pokemon_name,
        "pokemon_en": resolved["pokemon_en"],
        "preset_name": resolved["preset_name"],
        "config": resolved["config"],
    }


def _to_fullwidth(s: str) -> str:
    """Convert halfwidth ASCII letters/digits to fullwidth."""
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


def _find_form_index(name: str, data: dict[str, Any]) -> int:
    """Find the form index matching the given name (which may contain a form suffix).

    Examples:
        name='超级喷火龙Ｙ', data with forms=['喷火龙', '超级喷火龙Ｘ', '超级喷火龙Ｙ', ...] -> 2
        name='喷火龙', data with forms=['喷火龙', ...] -> 0
        name='胡地', data with forms=['胡地', '超级胡地'] -> 0
    Returns 0 if no specific form is matched.
    """
    forms = data.get("forms", [])
    if not forms:
        return 0

    # Direct match against any form name
    for idx, form in enumerate(forms):
        form_name = form.get("name", "")
        if form_name and name == form_name:
            return idx

    # Partial suffix match: if input ends with a form name suffix
    for idx, form in enumerate(forms):
        form_name = form.get("name", "")
        if form_name and len(form_name) > 1 and name.endswith(form_name):
            return idx

    # Try with fullwidth normalization on input
    name_fw = _to_fullwidth(name)
    for idx, form in enumerate(forms):
        form_name = form.get("name", "")
        if form_name and name_fw == form_name:
            return idx
        if form_name and len(form_name) > 1 and name_fw.endswith(form_name):
            return idx

    return 0


def resolve_pokemon(name: str) -> tuple[str, Any, int] | None:
    """Return (stem, data, form_index) for a pokemon by zh or en name.

    form_index is the index into data['forms'] matching the requested form.
    """
    load_data()
    name = normalize_name(name, "pokemon")

    # Try exact match first
    stem = _index_data["pokemon"].get(name) or _index_data["pokemon_forms"].get(name)

    # Try case-insensitive match in pokemon base names
    if not stem:
        for k, v in _index_data["pokemon"].items():
            if k.lower() == name.lower():
                stem = v
                break

    # Try case-insensitive match in pokemon form aliases
    if not stem:
        for k, v in _index_data.get("pokemon_forms", {}).items():
            if k.lower() == name.lower():
                stem = v
                break

    # Try fullwidth-normalized version (e.g. "超级喷火龙Y" -> "超级喷火龙Ｙ")
    if not stem:
        name_fw = _to_fullwidth(name)
        stem = _index_data["pokemon"].get(name_fw) or _index_data.get("pokemon_forms", {}).get(name_fw)

    if not stem:
        return None

    data = _pokemon_data.get(stem)
    if not data:
        return None

    form_index = _find_form_index(name, data)
    return stem, data, form_index


def resolve_move(name: str) -> tuple[str, Any] | None:
    """Return (stem, data) for a move by zh or en name."""
    load_data()
    name = normalize_name(name, "moves")
    stem = _index_data["moves"].get(name)
    if not stem:
        for k, v in _index_data["moves"].items():
            if k.lower() == name.lower():
                stem = v
                break
    if not stem:
        return None
    return stem, _moves_data.get(stem)


def resolve_ability(name: str) -> tuple[str, Any] | None:
    """Return (stem, data) for an ability by zh or en name."""
    load_data()
    name = normalize_name(name, "abilities")
    stem = _index_data["abilities"].get(name)
    if not stem:
        for k, v in _index_data["abilities"].items():
            if k.lower() == name.lower():
                stem = v
                break
    if not stem:
        return None
    return stem, _abilities_data.get(stem)


def resolve_item(name: str) -> str | None:
    """Return English canonical name for an item by zh, ja, or en name."""
    load_data()
    name = normalize_name(name, "items")
    items = _index_data.get("items", {})
    en = items.get(name)
    if not en:
        for k, v in items.items():
            if k.lower() == name.lower():
                en = v
                break
    return en


def cmd_item(name: str) -> dict[str, Any]:
    """Lookup item by any language name. Returns canonical English name."""
    en = resolve_item(name)
    if not en:
        candidates = list(_index_data.get("items", {}).keys())
        suggestions = get_suggestions(name, candidates, n=3)
        err: dict[str, Any] = {"error": f"Item '{name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    return {"name_en": en}


def cmd_pokemon(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        candidates = list(_index_data.get("pokemon", {}).keys()) + list(_index_data.get("pokemon_forms", {}).keys())
        suggestions = get_suggestions(name, candidates, n=3)
        err: dict[str, Any] = {"error": f"Pokemon '{name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    stem, data, _form_idx = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "pokedex_id": data.get("pokedex_id"),
        "description": data.get("description"),
        "forms": [
            {
                "name": f.get("name"),
                "types": f.get("types"),
                "abilities": [a["name"] for a in f.get("abilities", [])],
                "category": f.get("category"),
                "height": f.get("height"),
                "weight": f.get("weight"),
                "catch_rate": f.get("catch_rate"),
                "egg_groups": f.get("egg_groups"),
            }
            for f in data.get("forms", [])
        ],
        "stats": data.get("stats"),
        "evolution_chains": data.get("evolution_chains"),
        "mega_evolution": data.get("mega_evolution"),
    }


def cmd_move(name: str, *_extra: str) -> dict[str, Any]:
    resolved = resolve_move(name)
    if not resolved:
        candidates = list(_index_data.get("moves", {}).keys())
        suggestions = get_suggestions(name, candidates, n=3)
        err: dict[str, Any] = {"error": f"Move '{name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    stem, data = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "type": data.get("type"),
        "category": data.get("category"),
        "power": data.get("power"),
        "accuracy": data.get("accuracy"),
        "pp": data.get("pp"),
        "range": data.get("range"),
        "description": data.get("description"),
        "intro": data.get("intro"),
        "effect": data.get("effect"),
        "additional_effect": data.get("additional_effect"),
        "move_changes": data.get("move_changes"),
    }


def cmd_ability(name: str) -> dict[str, Any]:
    resolved = resolve_ability(name)
    if not resolved:
        candidates = list(_index_data.get("abilities", {}).keys())
        suggestions = get_suggestions(name, candidates, n=3)
        err: dict[str, Any] = {"error": f"Ability '{name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    stem, data = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "introduction": data.get("introduction"),
        "effect": data.get("effect"),
        "basic_info": data.get("basic_info"),
    }


def cmd_type(atk: str, dfn: str) -> dict[str, Any]:
    load_data()
    chart = _type_chart
    if atk not in chart:
        return {"error": f"Attack type '{atk}' not found. Valid types: {list(chart.keys())}"}
    row = chart[atk]
    if dfn not in row:
        return {"error": f"Defense type '{dfn}' not found. Valid types: {list(row.keys())}"}
    return {
        "attack_type": atk,
        "defense_type": dfn,
        "multiplier": row[dfn],
        "description": _describe_multiplier(row[dfn]),
    }


def _describe_multiplier(v: float) -> str:
    if v == 0:
        return "无效"
    if v == 0.25:
        return "效果很差（1/4）"
    if v == 0.5:
        return "效果不太好（1/2）"
    if v == 1:
        return "效果一般"
    if v == 2:
        return "效果拔群（2倍）"
    if v == 4:
        return "效果绝佳（4倍）"
    return f"倍率 {v}"


def cmd_stats(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        return {"error": f"Pokemon '{name}' not found."}
    stem, data, _form_idx = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "stats": data.get("stats"),
        "total": [
            {"form": s["form"], "total": sum(int(v) for v in s["data"].values())}
            for s in data.get("stats", [])
        ],
    }


def cmd_weak(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        return {"error": f"Pokemon '{name}' not found."}
    stem, data, _form_idx = resolved
    weaknesses: list[dict[str, Any]] = []
    for te in data.get("type_effectiveness", []):
        form = te.get("form") or "一般"
        types = te.get("types", [])
        weak = [e for e in te.get("data", []) if float(e["damage"]) > 1]
        resist = [e for e in te.get("data", []) if float(e["damage"]) < 1 and float(e["damage"]) > 0]
        immune = [e for e in te.get("data", []) if float(e["damage"]) == 0]
        weaknesses.append({
            "form": form,
            "types": types,
            "weak": [{"type": e["type"], "multiplier": e["damage"]} for e in weak],
            "resist": [{"type": e["type"], "multiplier": e["damage"]} for e in resist],
            "immune": [{"type": e["type"]} for e in immune],
        })
    return {"name_zh": data.get("name_zh"), "name_en": data.get("name_en"), "effectiveness": weaknesses}


def cmd_learnset(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        return {"error": f"Pokemon '{name}' not found."}
    stem, data, _form_idx = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "learnable_moves": data.get("learnable_moves", []),
        "machine_moves": data.get("machine_moves", []),
        "egg_moves": data.get("egg_moves", []),
        "tutor_moves": data.get("tutor_moves", []),
    }


def cmd_evo(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        return {"error": f"Pokemon '{name}' not found."}
    stem, data, _form_idx = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "evolution_chains": data.get("evolution_chains", []),
        "mega_evolution": data.get("mega_evolution", []),
    }


def cmd_pokedex(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        return {"error": f"Pokemon '{name}' not found."}
    stem, data, _form_idx = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "pokedex_entries": data.get("pokedex_entries", []),
    }


def cmd_profile(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        return {"error": f"Pokemon '{name}' not found."}
    stem, data, _form_idx = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "description": data.get("description"),
        "profile": data.get("profile"),
        "prototype": data.get("prototype"),
        "detail": data.get("detail"),
        "names": data.get("names"),
    }


def _iter_moves(pdata: dict[str, Any]):
    """Yield (move_dict, source_category) for all moves in a pokemon entry."""
    for category in ("learnable_moves", "machine_moves", "egg_moves", "tutor_moves"):
        for form_block in pdata.get(category, []):
            if isinstance(form_block, dict) and "data" in form_block:
                for move in form_block["data"]:
                    if isinstance(move, dict):
                        yield move, category


def cmd_find_move(move_name: str) -> dict[str, Any]:
    """Find all pokemon that can learn a given move."""
    load_data()
    move_stem = _index_data["moves"].get(move_name)
    if not move_stem:
        for k, v in _index_data["moves"].items():
            if k.lower() == move_name.lower():
                move_stem = v
                break
    move_data = _moves_data.get(move_stem) if move_stem else None
    move_zh = move_data.get("name_zh") if move_data else move_name

    result: list[dict[str, str]] = []
    for stem, pdata in _pokemon_data.items():
        for move, category in _iter_moves(pdata):
            if move.get("name") == move_zh:
                result.append({
                    "name_zh": pdata.get("name_zh"),
                    "name_en": pdata.get("name_en"),
                    "pokedex_id": pdata.get("pokedex_id"),
                    "method": _get_method_name(move, category),
                })
                break
    return {"move": move_zh, "count": len(result), "pokemon": result}


def _get_method_name(entry: dict[str, Any], category: str) -> str:
    if category == "learnable_moves" and "level" in entry:
        return f"升级 ({entry['level']})"
    if category == "machine_moves":
        return "TM"
    if category == "egg_moves":
        return "遗传"
    if category == "tutor_moves":
        return "教学"
    return "未知"


def _make_pokemon_from_data(data: dict[str, Any], overrides: dict[str, Any] | None = None, form_index: int = 0) -> dict[str, Any]:
    """Build a Pokemon dict suitable for damage.py from pokedex data."""
    forms = data.get("forms", [{}])
    form = forms[form_index] if form_index < len(forms) and forms else forms[0] if forms else {}
    stats_list = data.get("stats", [])
    # Try to find stats matching the form name, fallback to form_index or first
    stats = {}
    if stats_list:
        target_form_name = form.get("name", "")
        for s in stats_list:
            if s.get("form") == target_form_name:
                stats = s.get("data", {})
                break
        if not stats:
            if form_index < len(stats_list):
                stats = stats_list[form_index].get("data", {})
            else:
                stats = stats_list[0].get("data", {})
    # Convert string stats to int
    base_stats = {k: int(v) for k, v in stats.items()}
    types = form.get("types", [])
    abilities = form.get("abilities", [])
    ability = abilities[0].get("name", "") if abilities else ""

    pk = {
        "name": data.get("name_zh", ""),
        "name_en": data.get("name_en", ""),
        "level": 50,
        "base_stats": base_stats,
        "types": types,
        "ability": ability,
        "item": "",
        "nature": "勤奋",
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "boosts": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "status": None,
        "is_terastalize": False,
        "tera_type": None,
        "is_dynamax": False,
        "weight": 0.0,
    }
    if overrides:
        pk.update(overrides)
    return pk


def _make_move_from_data(data: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a Move dict suitable for damage.py from move data."""
    power_str = str(data.get("power", "0"))
    try:
        power = int(power_str)
    except ValueError:
        power = 0
    # Parse hits: can be int or string like "multi"
    hits_raw = data.get("hits", 1)
    try:
        hits = int(hits_raw)
    except (ValueError, TypeError):
        hits = 1
    move = {
        "name": data.get("name_en", ""),
        "name_zh": data.get("name_zh", ""),
        "base_power": power,
        "type": data.get("type", "一般"),
        "category": data.get("category", "Physical"),
        "accuracy": 100,
        "hits": hits,
        "is_crit": False,
        "makes_contact": data.get("makes_contact", False),
        "has_recoil": data.get("has_recoil", False),
        "is_punch": data.get("is_punch", False),
        "is_sound": data.get("is_sound", False),
        "is_slice": data.get("is_slice", False),
        "is_wind": data.get("is_wind", False),
        "is_bullet": data.get("is_bullet", False),
        "ignores_burn": data.get("ignores_burn", False),
        "is_spread": data.get("is_spread", False),
        "is_ohko": data.get("is_ohko", False),
        "is_z": data.get("is_z", False),
        "ignores_screens": data.get("ignores_screens", False),
        "deals_physical_damage": data.get("deals_physical_damage", False),
    }
    if overrides:
        move.update(overrides)
    return move


def _apply_field_overrides(field: Any, overrides: dict[str, Any]) -> None:
    """Apply JSON overrides to a Field dataclass instance."""
    for k, v in overrides.items():
        if hasattr(field, k):
            setattr(field, k, v)


def cmd_optimize(
    attacker_name: str,
    move_name: str,
    defender_name: str,
    goal: str = "ko",
    target: str = "ohko",
    threshold: str = "guaranteed",
    *extra_args: str,
) -> dict[str, Any]:
    """Optimize EV allocation for a given battle scenario.

    goal: ko | survive | survive_bulk
    target: ohko | 2hko | 3hko | survive | survive_2hko
    threshold: guaranteed | likely

    Examples:
        python query.py optimize 喷火龙 喷射火焰 水箭龟 ko ohko
        python query.py optimize 喷火龙 喷射火焰 水箭龟 survive survive guaranteed
    """
    from ev_optimizer import optimize_evs

    resolved_att = resolve_pokemon(attacker_name)
    resolved_def = resolve_pokemon(defender_name)
    resolved_move = resolve_move(move_name)
    if not resolved_att:
        load_data()
        candidates = list(_index_data.get("pokemon", {}).keys()) + list(_index_data.get("pokemon_forms", {}).keys())
        suggestions = get_suggestions(attacker_name, candidates, n=3)
        err: dict[str, Any] = {"error": f"Attacker '{attacker_name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    if not resolved_def:
        load_data()
        candidates = list(_index_data.get("pokemon", {}).keys()) + list(_index_data.get("pokemon_forms", {}).keys())
        suggestions = get_suggestions(defender_name, candidates, n=3)
        err = {"error": f"Defender '{defender_name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    if not resolved_move:
        load_data()
        candidates = list(_index_data.get("moves", {}).keys())
        suggestions = get_suggestions(move_name, candidates, n=3)
        err = {"error": f"Move '{move_name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err

    _, att_data, att_form_idx = resolved_att
    _, def_data, def_form_idx = resolved_def
    _, move_data = resolved_move

    def _strip_quotes(s: str) -> str:
        return s.strip().strip("'\"'")

    try:
        att_override = json.loads(_strip_quotes(extra_args[0])) if len(extra_args) > 0 and extra_args[0] else {}
    except json.JSONDecodeError:
        att_override = {}
    try:
        def_override = json.loads(_strip_quotes(extra_args[1])) if len(extra_args) > 1 and extra_args[1] else {}
    except json.JSONDecodeError:
        def_override = {}
    try:
        field_override = json.loads(_strip_quotes(extra_args[2])) if len(extra_args) > 2 and extra_args[2] else {}
    except json.JSONDecodeError:
        field_override = {}

    att_dict = _make_pokemon_from_data(att_data, att_override, form_index=att_form_idx)
    def_dict = _make_pokemon_from_data(def_data, def_override, form_index=def_form_idx)
    move_dict = _make_move_from_data(move_data)

    from models import Pokemon, Move, Field
    attacker = Pokemon(**att_dict)
    defender = Pokemon(**def_dict)
    move = Move(**move_dict)
    field = Field()
    _apply_field_overrides(field, field_override)

    return optimize_evs(attacker, defender, move, field, goal=goal, target=target, threshold=threshold)  # type: ignore[arg-type]


def cmd_calc(attacker_name: str, move_name: str, defender_name: str, *extra_args: str) -> dict[str, Any]:
    """Quick damage calculation using default Lv50 stats.
    
    Optional extra_args: JSON overrides for attacker, move, defender, field.
    Example:
        python query.py calc 喷火龙 喷射火焰 水箭龟
        python query.py calc 喷火龙 喷射火焰 水箭龟 '{"evs":{"sp_attack":252}}' '{}' '{"evs":{"sp_defense":252}}'
        python query.py calc 喷火龙 喷射火焰 水箭龟 '{"evs":{"sp_attack":252}}' '{}' '{}' '{"weather":"Sun"}'
    """
    import json
    from damage import calculate_damage
    from models import Pokemon, Move, Field

    resolved_att = resolve_pokemon(attacker_name)
    resolved_def = resolve_pokemon(defender_name)
    resolved_move = resolve_move(move_name)
    if not resolved_att:
        load_data()
        candidates = list(_index_data.get("pokemon", {}).keys()) + list(_index_data.get("pokemon_forms", {}).keys())
        suggestions = get_suggestions(attacker_name, candidates, n=3)
        err: dict[str, Any] = {"error": f"Attacker '{attacker_name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    if not resolved_def:
        load_data()
        candidates = list(_index_data.get("pokemon", {}).keys()) + list(_index_data.get("pokemon_forms", {}).keys())
        suggestions = get_suggestions(defender_name, candidates, n=3)
        err = {"error": f"Defender '{defender_name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    if not resolved_move:
        load_data()
        candidates = list(_index_data.get("moves", {}).keys())
        suggestions = get_suggestions(move_name, candidates, n=3)
        err = {"error": f"Move '{move_name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err

    _, att_data, att_form_idx = resolved_att
    _, def_data, def_form_idx = resolved_def
    _, move_data = resolved_move

    def _strip_quotes(s: str) -> str:
        return s.strip().strip("'\"'")

    # Parse optional overrides from extra args
    try:
        att_override = json.loads(_strip_quotes(extra_args[0])) if len(extra_args) > 0 and extra_args[0] else {}
    except json.JSONDecodeError:
        att_override = {}
    try:
        move_override = json.loads(_strip_quotes(extra_args[1])) if len(extra_args) > 1 and extra_args[1] else {}
    except json.JSONDecodeError:
        move_override = {}
    try:
        def_override = json.loads(_strip_quotes(extra_args[2])) if len(extra_args) > 2 and extra_args[2] else {}
    except json.JSONDecodeError:
        def_override = {}
    try:
        field_override = json.loads(_strip_quotes(extra_args[3])) if len(extra_args) > 3 and extra_args[3] else {}
    except json.JSONDecodeError:
        field_override = {}

    # Apply presets if specified in overrides
    att_override = _apply_preset_to_override(att_override, att_data.get("name_en", ""))
    def_override = _apply_preset_to_override(def_override, def_data.get("name_en", ""))

    att_dict = _make_pokemon_from_data(att_data, att_override, form_index=att_form_idx)
    def_dict = _make_pokemon_from_data(def_data, def_override, form_index=def_form_idx)
    move_dict = _make_move_from_data(move_data, move_override)

    attacker = Pokemon(**att_dict)
    defender = Pokemon(**def_dict)
    move = Move(**move_dict)
    field = Field()
    _apply_field_overrides(field, field_override)

    # Ensure current_hp reflects max_hp when not explicitly overridden
    if attacker.current_hp == 0:
        attacker.current_hp = attacker.max_hp
    if defender.current_hp == 0:
        defender.current_hp = defender.max_hp

    result = calculate_damage(attacker, defender, move, field, gen=9)

    # KO chance
    from ko_chance import get_ko_chance_text, squash_multihit
    ko_text = get_ko_chance_text(result.damage, move, defender, field)

    # Multi-hit total damage (for moves like Dual Wingbeat)
    total_damage_rolls: list[int] = []
    if move.hits > 1:
        total_damage_rolls = squash_multihit(result.damage, move.hits)

    # Build attacker / defender summary for transparency
    # Extract all abilities from the first form
    att_forms = att_data.get("forms", [{}])
    att_first_form = att_forms[0] if att_forms else {}
    att_all_abilities = [a.get("name", "") for a in att_first_form.get("abilities", [])]

    def_forms = def_data.get("forms", [{}])
    def_first_form = def_forms[0] if def_forms else {}
    def_all_abilities = [a.get("name", "") for a in def_first_form.get("abilities", [])]

    attacker_info = {
        "name_zh": attacker.name,
        "name_en": att_data.get("name_en", ""),
        "types": attacker.types,
        "base_stats": attacker.base_stats,
        "stats": attacker.raw_stats,
        "ability": attacker.ability,
        "all_abilities": att_all_abilities,
        "nature": attacker.nature,
        "item": attacker.item,
        "evs": attacker.evs,
        "ivs": attacker.ivs,
        "level": attacker.level,
    }
    defender_info = {
        "name_zh": defender.name,
        "name_en": def_data.get("name_en", ""),
        "types": defender.types,
        "base_stats": defender.base_stats,
        "stats": defender.raw_stats,
        "ability": defender.ability,
        "all_abilities": def_all_abilities,
        "nature": defender.nature,
        "item": defender.item,
        "evs": defender.evs,
        "ivs": defender.ivs,
        "level": defender.level,
        "current_hp": defender.current_hp,
        "max_hp": defender.max_hp,
    }

    response: dict[str, Any] = {
        "attacker": attacker_name,
        "move": move_name,
        "defender": defender_name,
        "damage_range": [result.min_damage, result.max_damage],
        "damage_rolls": result.damage,
        "description": result.description,
        "is_critical": result.is_critical,
        "type_effectiveness": result.type_effectiveness,
        "stab_applied": result.stab_applied,
        "burn_applied": result.burn_applied,
        "ko_chance": ko_text,
        "attacker_info": attacker_info,
        "defender_info": defender_info,
    }
    if move.hits > 1:
        response["total_damage_range"] = [min(total_damage_rolls), max(total_damage_rolls)]
        response["total_damage_rolls"] = total_damage_rolls
        response["move_hits"] = move.hits

    return response


def cmd_compute_stats(
    base_stats_json: str,
    evs_json: str = "{}",
    ivs_json: str = "{}",
    nature: str = "勤奋",
    level: str = "50",
) -> dict[str, Any]:
    """Compute final stats (ability values) from base stats + evs + ivs + nature + level."""
    import json
    from damage import calc_hp_stat, calc_raw_stat, get_nature_modifier

    def _strip_quotes(s: str) -> str:
        return s.strip().strip("'\"'")

    try:
        base_stats = json.loads(_strip_quotes(base_stats_json))
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid base_stats JSON"}

    try:
        evs = json.loads(_strip_quotes(evs_json)) if evs_json else {}
    except (json.JSONDecodeError, TypeError):
        evs = {}

    try:
        ivs = json.loads(_strip_quotes(ivs_json)) if ivs_json else {}
    except (json.JSONDecodeError, TypeError):
        ivs = {}

    try:
        level_int = int(level)
    except (ValueError, TypeError):
        level_int = 50

    raw_stats: dict[str, int] = {}
    for stat_key, base in base_stats.items():
        ev = evs.get(stat_key, 0)
        iv = ivs.get(stat_key, 31)
        if stat_key == "hp":
            raw = calc_hp_stat(base, iv, ev, level_int)
        else:
            raw = calc_raw_stat(base, iv, ev, level_int)
            nature_mod = get_nature_modifier(nature, stat_key)
            raw = int(raw * nature_mod)
        raw_stats[stat_key] = raw

    return {
        "level": level_int,
        "nature": nature,
        "base_stats": base_stats,
        "evs": evs,
        "ivs": ivs,
        "stats": raw_stats,
    }


def cmd_calc_raw(
    attacker_json: str,
    move_json: str,
    defender_json: str,
    field_json: str = "{}",
) -> dict[str, Any]:
    """Pure parameter-driven damage calculation.

    All Pokemon / Move / Field data is passed directly as JSON.
    No name resolution or data lookup is performed.
    The attacker_json and defender_json MUST contain a 'stats' field
    with the final ability values (e.g. {"hp": 153, "attack": 90, ...}).
    """
    import json
    from damage import calculate_damage, get_modified_stat
    from models import Pokemon, Move, Field
    from ko_chance import get_ko_chance_text, squash_multihit

    def _strip_quotes(s: str) -> str:
        return s.strip().strip("'\"'")

    try:
        att_dict = json.loads(_strip_quotes(attacker_json))
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid attacker JSON"}

    try:
        move_dict = json.loads(_strip_quotes(move_json))
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid move JSON"}

    try:
        def_dict = json.loads(_strip_quotes(defender_json))
    except (json.JSONDecodeError, TypeError):
        return {"error": "Invalid defender JSON"}

    try:
        field_dict = json.loads(_strip_quotes(field_json)) if field_json else {}
    except (json.JSONDecodeError, TypeError):
        field_dict = {}

    # Validate required fields
    if "stats" not in att_dict:
        return {"error": "attacker_json missing required field: stats"}
    if "stats" not in def_dict:
        return {"error": "defender_json missing required field: stats"}

    # Set raw_stats from the provided stats (bypasses compute_raw_stats in calculate_damage)
    att_dict["raw_stats"] = att_dict["stats"]
    def_dict["raw_stats"] = def_dict["stats"]

    # Apply boost modifications to get effective stats
    att_boosts = att_dict.get("boosts", {})
    def_boosts = def_dict.get("boosts", {})
    att_dict["stats"] = {
        k: get_modified_stat(v, att_boosts.get(k, 0))
        for k, v in att_dict["raw_stats"].items()
    }
    def_dict["stats"] = {
        k: get_modified_stat(v, def_boosts.get(k, 0))
        for k, v in def_dict["raw_stats"].items()
    }

    # Ensure HP fields are set
    if att_dict.get("max_hp", 0) == 0:
        att_dict["max_hp"] = att_dict["raw_stats"].get("hp", 0)
    if att_dict.get("current_hp", 0) == 0:
        att_dict["current_hp"] = att_dict["max_hp"]

    if def_dict.get("max_hp", 0) == 0:
        def_dict["max_hp"] = def_dict["raw_stats"].get("hp", 0)
    if def_dict.get("current_hp", 0) == 0:
        def_dict["current_hp"] = def_dict["max_hp"]

    # Auto-fill is_spread from moves.json if not explicitly provided
    if "is_spread" not in move_dict:
        move_name = move_dict.get("name") or move_dict.get("name_zh", "")
        if move_name:
            resolved = resolve_move(move_name)
            if resolved:
                _, move_data = resolved
                if "is_spread" in move_data:
                    move_dict["is_spread"] = move_data["is_spread"]

    # Build objects
    try:
        attacker = Pokemon(**att_dict)
        move = Move(**move_dict)
        defender = Pokemon(**def_dict)
        field = Field(**field_dict)
    except TypeError as e:
        return {"error": f"Failed to build battle objects: {e}"}

    # Calculate damage
    result = calculate_damage(attacker, defender, move, field, gen=9)

    # KO chance
    ko_text = get_ko_chance_text(result.damage, move, defender, field)

    # Multi-hit total damage
    total_damage_rolls: list[int] = []
    if move.hits > 1:
        total_damage_rolls = squash_multihit(result.damage, move.hits)

    # Build response
    attacker_info = {
        "name_zh": attacker.name,
        "name_en": attacker.name_en,
        "types": attacker.types,
        "ability": attacker.ability,
        "nature": attacker.nature,
        "item": attacker.item,
        "stats": attacker.raw_stats,
        "evs": attacker.evs,
        "ivs": attacker.ivs,
        "level": attacker.level,
        "current_hp": attacker.current_hp,
        "max_hp": attacker.max_hp,
    }
    defender_info = {
        "name_zh": defender.name,
        "name_en": defender.name_en,
        "types": defender.types,
        "ability": defender.ability,
        "nature": defender.nature,
        "item": defender.item,
        "stats": defender.raw_stats,
        "evs": defender.evs,
        "ivs": defender.ivs,
        "level": defender.level,
        "current_hp": defender.current_hp,
        "max_hp": defender.max_hp,
    }

    response: dict[str, Any] = {
        "attacker": attacker.name,
        "move": move.name,
        "defender": defender.name,
        "damage_range": [result.min_damage, result.max_damage],
        "damage_rolls": result.damage,
        "description": result.description,
        "is_critical": result.is_critical,
        "type_effectiveness": result.type_effectiveness,
        "stab_applied": result.stab_applied,
        "burn_applied": result.burn_applied,
        "ko_chance": ko_text,
        "attacker_info": attacker_info,
        "defender_info": defender_info,
    }
    if move.hits > 1:
        response["total_damage_range"] = [min(total_damage_rolls), max(total_damage_rolls)]
        response["total_damage_rolls"] = total_damage_rolls
        response["move_hits"] = move.hits

    return response


COMMANDS: dict[str, Any] = {
    "pokemon": cmd_pokemon,
    "move": cmd_move,
    "ability": cmd_ability,
    "item": cmd_item,
    "type": cmd_type,
    "stats": cmd_stats,
    "weak": cmd_weak,
    "learnset": cmd_learnset,
    "evo": cmd_evo,
    "pokedex": cmd_pokedex,
    "profile": cmd_profile,
    "find-move": cmd_find_move,
    "preset": cmd_preset,
    "calc": cmd_calc,
    "calc-raw": cmd_calc_raw,
    "compute-stats": cmd_compute_stats,
    "optimize": cmd_optimize,
}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1]
    if cmd not in COMMANDS:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return 1

    func = COMMANDS[cmd]
    args = sys.argv[2:]
    try:
        result = func(*args)
    except TypeError as e:
        print(f"Argument error for '{cmd}': {e}")
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
