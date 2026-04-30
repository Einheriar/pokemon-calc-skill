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
"""

import io
import json
import sys
from pathlib import Path
from typing import Any

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


def resolve_pokemon(name: str) -> tuple[str, Any] | None:
    """Return (stem, data) for a pokemon by zh or en name."""
    load_data()
    stem = _index_data["pokemon"].get(name) or _index_data["pokemon_forms"].get(name)
    if not stem:
        for k, v in _index_data["pokemon"].items():
            if k.lower() == name.lower():
                stem = v
                break
    if not stem:
        return None
    return stem, _pokemon_data.get(stem)


def resolve_move(name: str) -> tuple[str, Any] | None:
    """Return (stem, data) for a move by zh or en name."""
    load_data()
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
        return {"error": f"Item '{name}' not found."}
    return {"name_en": en}


def cmd_pokemon(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        return {"error": f"Pokemon '{name}' not found."}
    stem, data = resolved
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
        return {"error": f"Move '{name}' not found."}
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
        return {"error": f"Ability '{name}' not found."}
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
    stem, data = resolved
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
    stem, data = resolved
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
    stem, data = resolved
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
    stem, data = resolved
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
    stem, data = resolved
    return {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "pokedex_entries": data.get("pokedex_entries", []),
    }


def cmd_profile(name: str) -> dict[str, Any]:
    resolved = resolve_pokemon(name)
    if not resolved:
        return {"error": f"Pokemon '{name}' not found."}
    stem, data = resolved
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


def _make_pokemon_from_data(data: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a Pokemon dict suitable for damage.py from pokedex data."""
    # Use the first form by default
    forms = data.get("forms", [{}])
    form = forms[0] if forms else {}
    stats_list = data.get("stats", [])
    stats = stats_list[0].get("data", {}) if stats_list else {}
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
        return {"error": f"Attacker '{attacker_name}' not found."}
    if not resolved_def:
        return {"error": f"Defender '{defender_name}' not found."}
    if not resolved_move:
        return {"error": f"Move '{move_name}' not found."}

    _, att_data = resolved_att
    _, def_data = resolved_def
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

    att_dict = _make_pokemon_from_data(att_data, att_override)
    def_dict = _make_pokemon_from_data(def_data, def_override)
    move_dict = _make_move_from_data(move_data)

    from models import Pokemon, Move, Field
    attacker = Pokemon(**att_dict)
    defender = Pokemon(**def_dict)
    move = Move(**move_dict)
    field = Field()

    return optimize_evs(attacker, defender, move, field, goal=goal, target=target, threshold=threshold)  # type: ignore[arg-type]


def cmd_calc(attacker_name: str, move_name: str, defender_name: str, *extra_args: str) -> dict[str, Any]:
    """Quick damage calculation using default Lv50 stats.
    
    Optional extra_args: JSON overrides for attacker, move, defender.
    Example:
        python query.py calc 喷火龙 喷射火焰 水箭龟
        python query.py calc 喷火龙 喷射火焰 水箭龟 '{"evs":{"sp_attack":252}}' '{}' '{"evs":{"sp_defense":252}}'
    """
    import json
    from damage import calculate_damage
    from models import Pokemon, Move, Field

    resolved_att = resolve_pokemon(attacker_name)
    resolved_def = resolve_pokemon(defender_name)
    resolved_move = resolve_move(move_name)
    if not resolved_att:
        return {"error": f"Attacker '{attacker_name}' not found."}
    if not resolved_def:
        return {"error": f"Defender '{defender_name}' not found."}
    if not resolved_move:
        return {"error": f"Move '{move_name}' not found."}

    _, att_data = resolved_att
    _, def_data = resolved_def
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

    att_dict = _make_pokemon_from_data(att_data, att_override)
    def_dict = _make_pokemon_from_data(def_data, def_override)
    move_dict = _make_move_from_data(move_data, move_override)

    attacker = Pokemon(**att_dict)
    defender = Pokemon(**def_dict)
    move = Move(**move_dict)
    field = Field()

    result = calculate_damage(attacker, defender, move, field, gen=9)

    # KO chance
    from ko_chance import get_ko_chance_text
    ko_text = get_ko_chance_text(result.damage, move, defender, field)

    return {
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
    }


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
    "calc": cmd_calc,
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
