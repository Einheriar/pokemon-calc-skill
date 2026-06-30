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
    python query.py filter-moves            # Filter moves by type/category/power
    python query.py preset <pokemon>        # List presets for a pokemon
    python query.py preset <pokemon> <name> # Get specific preset config
"""

import io
import json
from models import Pokemon, Move, Field
import os
import sys
from pathlib import Path
from typing import Any

from normalize import get_suggestions, normalize_name

# Force UTF-8 stdout/stderr on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
# Allow overriding data directory via environment variable (useful when installed as a standalone skill)
DATA_DIR = Path(os.environ.get("POKEMON_CALC_DATA_DIR", SCRIPT_DIR.parent / "data"))

_pokemon_data: dict[str, Any] | None = None
_moves_data: dict[str, Any] | None = None
_abilities_data: dict[str, Any] | None = None
_index_data: dict[str, Any] | None = None
_type_chart: dict[str, dict[str, float]] | None = None
_champions_patches: dict[str, Any] | None = None


def _load_json(name: str) -> Any:
    path = DATA_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data() -> None:
    global _pokemon_data, _moves_data, _abilities_data, _index_data, _type_chart
    if _pokemon_data is not None:
        return
    _pokemon_data = _load_json("pokemon.json")
    _moves_data = _load_json("moves.json")
    _abilities_data = _load_json("abilities.json")
    _index_data = _load_json("name_index.json")
    _type_chart = _load_json("type_chart.json")
    # Merge Champions name_index patch
    patches = _load_champions_patches()
    if patches and "name_index" in patches:
        for category in ("pokemon", "moves"):
            if category in _index_data and category in patches["name_index"]:
                _index_data[category].update(patches["name_index"][category])


def _load_champions_patches() -> dict[str, Any]:
    """Load Champions patch files. Returns dict with keys: pokemon, moves, learnset, name_index."""
    global _champions_patches
    if _champions_patches is not None:
        return _champions_patches
    patches = {"pokemon": {}, "moves": {}, "learnset": {}, "name_index": {"pokemon": {}, "moves": {}}}
    patch_files = {
        "pokemon": "champions_pokemon_patch.json",
        "moves": "champions_moves_patch.json",
        "learnset": "champions_learnset_patch.json",
        "name_index": "champions_name_index_patch.json",
    }
    for key, filename in patch_files.items():
        path = DATA_DIR / filename
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if key == "name_index":
                    patches["name_index"]["pokemon"].update(data.get("pokemon", {}))
                    patches["name_index"]["moves"].update(data.get("moves", {}))
                else:
                    patches[key] = data
            except Exception:
                pass  # Silently ignore missing/corrupt patch files
    _champions_patches = patches
    return _champions_patches


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
        "nature", "ability", "ability_zh", "item", "types", "tera_type",
        "is_terastalize", "boosts", "current_hp", "max_hp",
        "status", "weight", "is_dynamax", "can_evolve",
        "raw_stats", "stats",
    }

    preset_config = {k: v for k, v in presets[preset_name].items() if k in _VALID_PK_FIELDS}
    # User override takes precedence over preset
    preset_config.update(override)
    return preset_config


# Fields allowed for auto-preset fallback (evs/nature/ivs only; item/ability excluded)
_AUTO_PRESET_FIELDS = {"evs", "nature", "ivs"}


def _score_preset(preset_config: dict[str, Any], user_override: dict[str, Any]) -> int:
    """Score how well a preset matches the user's partial specification."""
    score = 0
    # Nature match
    if user_override.get("nature") and user_override.get("nature") == preset_config.get("nature"):
        score += 10
    # EV field matches
    user_evs = user_override.get("evs", {})
    preset_evs = preset_config.get("evs", {})
    for stat, val in user_evs.items():
        if preset_evs.get(stat) == val:
            score += 5
    return score


def _apply_auto_preset_to_override(override: dict[str, Any], pokemon_en: str) -> tuple[dict[str, Any], str | None]:
    """If user partially specified config, auto-match best preset from setdex.

    Only evs/nature/ivs are filled from preset; item/ability/tera_type are excluded.
    Returns (updated_override, matched_preset_name_or_None).
    """
    # Skip if user already provided "preset" key (explicit preset takes precedence)
    if "preset" in override:
        return override, None

    setdex = _load_setdex()
    if pokemon_en not in setdex:
        return override, None

    presets = setdex[pokemon_en]
    if not presets:
        return override, None

    best_preset_name: str | None = None
    best_score = -1
    for preset_name, preset_config in presets.items():
        score = _score_preset(preset_config, override)
        if score > best_score:
            best_score = score
            best_preset_name = preset_name

    if best_preset_name is None or best_score <= 0:
        return override, None

    preset_config = presets[best_preset_name]
    # Fill only missing fields from the allowed whitelist
    for field in _AUTO_PRESET_FIELDS:
        if field not in override and field in preset_config:
            override[field] = preset_config[field]
        # For dict fields (evs, ivs), merge at key level so user-specified keys take precedence
        elif field in override and field in preset_config and isinstance(override[field], dict) and isinstance(preset_config[field], dict):
            merged = dict(preset_config[field])  # Start with preset values
            merged.update(override[field])       # User values override
            override[field] = merged

    return override, best_preset_name


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


def _apply_champions_pokemon_patch(stem: str, data: dict[str, Any]) -> dict[str, Any]:
    """Apply Champions patch to a pokemon data entry if available."""
    patches = _load_champions_patches()
    if not patches or stem not in patches.get("pokemon", {}):
        return data
    patch = patches["pokemon"][stem]
    # Deep copy to avoid mutating original
    merged = json.loads(json.dumps(data))
    # Merge forms: replace by index order, append if patch has more forms than original
    if "forms" in patch:
        orig_forms = merged.get("forms", [])
        for i, raw_pform in enumerate(patch["forms"]):
            pform = json.loads(json.dumps(raw_pform))  # deep copy
            # Normalize abilities from string list to object list
            abilities = pform.get("abilities")
            if isinstance(abilities, list) and abilities and isinstance(abilities[0], str):
                pform["abilities"] = [{"name": a} for a in abilities]
            if i < len(orig_forms):
                orig_forms[i].update(pform)
            else:
                orig_forms.append(pform)
        merged["forms"] = orig_forms
    # Merge stats: replace by index order, append if patch has more stats than original
    if "stats" in patch:
        orig_stats = merged.get("stats", [])
        for i, pstat in enumerate(patch["stats"]):
            if i < len(orig_stats):
                orig_stats[i].update(pstat)
            else:
                orig_stats.append(pstat)
        merged["stats"] = orig_stats
    # Merge any other top-level fields
    for key, value in patch.items():
        if key not in ("forms", "stats"):
            merged[key] = value
    return merged


def _apply_champions_move_patch(name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Apply Champions patch to a move data entry if available."""
    patches = _load_champions_patches()
    if not patches or name not in patches.get("moves", {}):
        return data
    patch = patches["moves"][name]
    merged = data.copy()
    merged.update(patch)
    return merged


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

    data = _apply_champions_pokemon_patch(stem, data)
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
    data = _moves_data.get(stem)
    if data is None:
        return None
    patched = _apply_champions_move_patch(stem, data)
    if patched is data:
        zh_name = data.get("name_zh", "")
        if zh_name:
            patched = _apply_champions_move_patch(zh_name, data)
    return stem, patched


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


# ---------------------------------------------------------------------------
# Item effects lookup
# ---------------------------------------------------------------------------

# Maps English and Chinese item names to their effect descriptions.
# Used by cmd_item() to return human-readable effect info.
_ITEM_EFFECTS: dict[str, tuple[str, str]] = {
    # Elemental boost items (1.2x)
    "Mystic Water": ("携带后，水属性招式威力提升20%", "属性增强道具"),
    "神秘水滴": ("携带后，水属性招式威力提升20%", "属性增强道具"),
    "Charcoal": ("携带后，火属性招式威力提升20%", "属性增强道具"),
    "木炭": ("携带后，火属性招式威力提升20%", "属性增强道具"),
    "Miracle Seed": ("携带后，草属性招式威力提升20%", "属性增强道具"),
    "奇迹种子": ("携带后，草属性招式威力提升20%", "属性增强道具"),
    "Magnet": ("携带后，电属性招式威力提升20%", "属性增强道具"),
    "磁铁": ("携带后，电属性招式威力提升20%", "属性增强道具"),
    "Never-Melt Ice": ("携带后，冰属性招式威力提升20%", "属性增强道具"),
    "NeverMeltIce": ("携带后，冰属性招式威力提升20%", "属性增强道具"),
    "不融冰": ("携带后，冰属性招式威力提升20%", "属性增强道具"),
    "Black Belt": ("携带后，格斗属性招式威力提升20%", "属性增强道具"),
    "黑带": ("携带后，格斗属性招式威力提升20%", "属性增强道具"),
    "Poison Barb": ("携带后，毒属性招式威力提升20%", "属性增强道具"),
    "毒针": ("携带后，毒属性招式威力提升20%", "属性增强道具"),
    "Soft Sand": ("携带后，地面属性招式威力提升20%", "属性增强道具"),
    "柔软沙子": ("携带后，地面属性招式威力提升20%", "属性增强道具"),
    "Sharp Beak": ("携带后，飞行属性招式威力提升20%", "属性增强道具"),
    "锐利鸟嘴": ("携带后，飞行属性招式威力提升20%", "属性增强道具"),
    "Twisted Spoon": ("携带后，超能力属性招式威力提升20%", "属性增强道具"),
    "TwistedSpoon": ("携带后，超能力属性招式威力提升20%", "属性增强道具"),
    "弯曲的汤匙": ("携带后，超能力属性招式威力提升20%", "属性增强道具"),
    "Silver Powder": ("携带后，虫属性招式威力提升20%", "属性增强道具"),
    "SilverPowder": ("携带后，虫属性招式威力提升20%", "属性增强道具"),
    "银色粉": ("携带后，虫属性招式威力提升20%", "属性增强道具"),
    "Hard Stone": ("携带后，岩石属性招式威力提升20%", "属性增强道具"),
    "硬石头": ("携带后，岩石属性招式威力提升20%", "属性增强道具"),
    "Spell Tag": ("携带后，幽灵属性招式威力提升20%", "属性增强道具"),
    "诅咒之符": ("携带后，幽灵属性招式威力提升20%", "属性增强道具"),
    "Dragon Fang": ("携带后，龙属性招式威力提升20%", "属性增强道具"),
    "龙之牙": ("携带后，龙属性招式威力提升20%", "属性增强道具"),
    "Black Glasses": ("携带后，恶属性招式威力提升20%", "属性增强道具"),
    "BlackGlasses": ("携带后，恶属性招式威力提升20%", "属性增强道具"),
    "黑色眼镜": ("携带后，恶属性招式威力提升20%", "属性增强道具"),
    "Metal Coat": ("携带后，钢属性招式威力提升20%", "属性增强道具"),
    "金属膜": ("携带后，钢属性招式威力提升20%", "属性增强道具"),
    "Silk Scarf": ("携带后，一般属性招式威力提升20%", "属性增强道具"),
    "丝绸围巾": ("携带后，一般属性招式威力提升20%", "属性增强道具"),
    "Fairy Feather": ("携带后，妖精属性招式威力提升20%", "属性增强道具"),

    # Category boost items (1.1x)
    "Muscle Band": ("携带后，物理招式威力提升10%", "分类增强道具"),
    "力量头带": ("携带后，物理招式威力提升10%", "分类增强道具"),
    "Wise Glasses": ("携带后，特殊招式威力提升10%", "分类增强道具"),
    "博识眼镜": ("携带后，特殊招式威力提升10%", "分类增强道具"),

    # Choice items (1.5x)
    "Choice Band": ("携带后，物理攻击提升50%，但只能使用上场后使出的第一个招式", "讲究道具"),
    "讲究头带": ("携带后，物理攻击提升50%，但只能使用上场后使出的第一个招式", "讲究道具"),
    "Choice Specs": ("携带后，特殊攻击提升50%，但只能使用上场后使出的第一个招式", "讲究道具"),
    "讲究眼镜": ("携带后，特殊攻击提升50%，但只能使用上场后使出的第一个招式", "讲究道具"),
    "Choice Scarf": ("携带后，速度提升50%，但只能使用上场后使出的第一个招式", "讲究道具"),
    "讲究围巾": ("携带后，速度提升50%，但只能使用上场后使出的第一个招式", "讲究道具"),

    # Life Orb / Expert Belt
    "Life Orb": ("携带后，招式威力提升30%，但攻击时会损失少量HP", "威力增强道具"),
    "生命宝珠": ("携带后，招式威力提升30%，但攻击时会损失少量HP", "威力增强道具"),
    "Expert Belt": ("携带后，效果拔群的招式威力额外提升20%", "威力增强道具"),
    "达人带": ("携带后，效果拔群的招式威力额外提升20%", "威力增强道具"),

    # Survival items
    "Focus Sash": ("携带后，满HP时受到一击濒死的攻击可以保留1HP（一次性）", "保命道具"),
    "气势披带": ("携带后，满HP时受到一击濒死的攻击可以保留1HP（一次性）", "保命道具"),
    "Focus Band": ("携带后，受到濒死攻击时有10%概率保留1HP", "保命道具"),
    "气势头带": ("携带后，受到濒死攻击时有10%概率保留1HP", "保命道具"),

    # Recovery items
    "Leftovers": ("携带后，每回合结束时回复少量HP", "回复道具"),
    "吃剩的东西": ("携带后，每回合结束时回复少量HP", "回复道具"),

    # Defensive items
    "Assault Vest": ("携带后，特殊防御提升50%，但无法使用变化招式", "防御道具"),
    "突击背心": ("携带后，特殊防御提升50%，但无法使用变化招式", "防御道具"),
    "Eviolite": ("携带后，可以进化的宝可梦的防御和特殊防御提升50%", "防御道具"),
    "进化奇石": ("携带后，可以进化的宝可梦的防御和特殊防御提升50%", "防御道具"),
    "Heavy-Duty Boots": ("携带后，不受撒菱、毒菱和隐形岩等场地伤害", "防御道具"),
    "厚底靴": ("携带后，不受撒菱、毒菱和隐形岩等场地伤害", "防御道具"),

    # Type-resist berries (halve super-effective moves)
    "Occa Berry": ("携带后，受到效果拔群的火属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "巧可果": ("携带后，受到效果拔群的火属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗火果": ("携带后，受到效果拔群的火属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Passho Berry": ("携带后，受到效果拔群的水属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "烛木果": ("携带后，受到效果拔群的水属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗水果": ("携带后，受到效果拔群的水属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Wacan Berry": ("携带后，受到效果拔群的电属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "罗子果": ("携带后，受到效果拔群的电属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗电果": ("携带后，受到效果拔群的电属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Rindo Berry": ("携带后，受到效果拔群的草属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "番荔果": ("携带后，受到效果拔群的草属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗草果": ("携带后，受到效果拔群的草属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Yache Berry": ("携带后，受到效果拔群的冰属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "腰木果": ("携带后，受到效果拔群的冰属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗冰果": ("携带后，受到效果拔群的冰属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Chople Berry": ("携带后，受到效果拔群的格斗属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "棱瓜果": ("携带后，受到效果拔群的格斗属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗斗果": ("携带后，受到效果拔群的格斗属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Kebia Berry": ("携带后，受到效果拔群的毒属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗毒果": ("携带后，受到效果拔群的毒属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Shuca Berry": ("携带后，受到效果拔群的地面属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "葫苏果": ("携带后，受到效果拔群的地面属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗地果": ("携带后，受到效果拔群的地面属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Coba Berry": ("携带后，受到效果拔群的飞行属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "乐芭果": ("携带后，受到效果拔群的飞行属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗飞果": ("携带后，受到效果拔群的飞行属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Payapa Berry": ("携带后，受到效果拔群的超能力属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "芭亚果": ("携带后，受到效果拔群的超能力属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗超果": ("携带后，受到效果拔群的超能力属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Tanga Berry": ("携带后，受到效果拔群的虫属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "莲蒲果": ("携带后，受到效果拔群的虫属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗虫果": ("携带后，受到效果拔群的虫属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Charti Berry": ("携带后，受到效果拔群的岩石属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "霹霹果": ("携带后，受到效果拔群的岩石属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗岩果": ("携带后，受到效果拔群的岩石属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Kasib Berry": ("携带后，受到效果拔群的幽灵属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "佛柑果": ("携带后，受到效果拔群的幽灵属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗鬼果": ("携带后，受到效果拔群的幽灵属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Haban Berry": ("携带后，受到效果拔群的龙属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "烛龙果": ("携带后，受到效果拔群的龙属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗龙果": ("携带后，受到效果拔群的龙属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Colbur Berry": ("携带后，受到效果拔群的恶属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "罗望果": ("携带后，受到效果拔群的恶属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "刺耳果": ("携带后，受到效果拔群的恶属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗恶果": ("携带后，受到效果拔群的恶属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Babiri Berry": ("携带后，受到效果拔群的钢属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "穹犀果": ("携带后，受到效果拔群的钢属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗钢果": ("携带后，受到效果拔群的钢属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Roseli Berry": ("携带后，受到效果拔群的妖精属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "香罗果": ("携带后，受到效果拔群的妖精属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗仙果": ("携带后，受到效果拔群的妖精属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "Chilan Berry": ("携带后，受到效果拔群的一般属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "投鲜果": ("携带后，受到效果拔群的一般属性招式攻击时，伤害减半（一次性）", "抗性树果"),
    "抗一般果": ("携带后，受到效果拔群的一般属性招式攻击时，伤害减半（一次性）", "抗性树果"),

    # Other notable items
    "Clear Amulet": ("携带后，能力不会被对手降低", "能力保护道具"),
    "清净坠饰": ("携带后，能力不会被对手降低", "能力保护道具"),
    "Covert Cloak": ("携带后，不会受到招式的追加效果影响", "能力保护道具"),
    "密探斗篷": ("携带后，不会受到招式的追加效果影响", "能力保护道具"),
    "Rocky Helmet": ("携带后，受到接触类招式攻击时，攻击方会受到少量伤害", "反伤道具"),
    "凸凸头盔": ("携带后，受到接触类招式攻击时，攻击方会受到少量伤害", "反伤道具"),
    "Safety Goggles": ("携带后，不受粉末类招式和天气伤害影响", "防御道具"),
    "防尘护目镜": ("携带后，不受粉末类招式和天气伤害影响", "防御道具"),
    "Weakness Policy": ("携带后，受到效果拔群攻击时，攻击和特殊攻击提升", "强化道具"),
    "弱点保险": ("携带后，受到效果拔群攻击时，攻击和特殊攻击提升", "强化道具"),
    "Booster Energy": ("携带后，携带驱劲能量特性（古代活性/夸克充能）的宝可梦首次出场时会提升最高能力", "特性联动道具"),
    "驱劲能量": ("携带后，携带驱劲能量特性（古代活性/夸克充能）的宝可梦首次出场时会提升最高能力", "特性联动道具"),
}


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
    """Lookup item by any language name. Returns canonical English name and effect."""
    en = resolve_item(name)
    if not en:
        candidates = list(_index_data.get("items", {}).keys())
        suggestions = get_suggestions(name, candidates, n=3)
        err: dict[str, Any] = {"error": f"Item '{name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    result: dict[str, Any] = {"name_en": en}
    # Try English name first, then the original input name
    effect_info = _ITEM_EFFECTS.get(en)
    if not effect_info:
        effect_info = _ITEM_EFFECTS.get(name)
    if effect_info:
        result["effect"] = effect_info[0]
        result["category"] = effect_info[1]
    else:
        result["effect"] = ""
        result["category"] = ""
    return result


def _get_champions_learnset(stem: str) -> list[str]:
    """Get Champions learnset for a pokemon stem if available."""
    patches = _load_champions_patches()
    if patches and stem in patches.get("learnset", {}):
        return patches["learnset"][stem]
    return []


def _find_pokemon_by_types(type_filters: list[str]) -> dict[str, Any]:
    """Find all pokemon whose primary/secondary types match all given filters."""
    load_data()
    from normalize import normalize_type_name

    normalized_filters = [normalize_type_name(t) for t in type_filters]
    valid_types = list(_type_chart.keys())
    for t in normalized_filters:
        if t not in valid_types:
            return {"error": f"Type '{t}' not found. Valid types: {sorted(valid_types)}"}

    matches: list[dict[str, Any]] = []
    for stem, data in _pokemon_data.items():
        for form in data.get("forms", []):
            form_types = form.get("types", [])
            if not form_types:
                continue
            # Match: all filter types must be present in the form's types
            if all(ft in form_types for ft in normalized_filters):
                matches.append({
                    "name": form.get("name") or data.get("name_zh"),
                    "name_en": data.get("name_en"),
                    "pokedex_id": data.get("pokedex_id"),
                    "types": form_types,
                    "form_name": form.get("name"),
                })

    # Deduplicate by name
    seen = set()
    deduped = []
    for m in matches:
        key = m["name"]
        if key not in seen:
            seen.add(key)
            deduped.append(m)

    return {
        "query_types": normalized_filters,
        "count": len(deduped),
        "results": deduped,
    }


def cmd_pokemon(name: str = "", type_filters: list[str] | None = None) -> dict[str, Any]:
    if type_filters:
        return _find_pokemon_by_types(type_filters)

    resolved = resolve_pokemon(name)
    if not resolved:
        candidates = list(_index_data.get("pokemon", {}).keys()) + list(_index_data.get("pokemon_forms", {}).keys())
        suggestions = get_suggestions(name, candidates, n=3)
        err: dict[str, Any] = {"error": f"Pokemon '{name}' not found."}
        if suggestions:
            err["suggestions"] = suggestions
        return err
    stem, data, _form_idx = resolved
    forms = data.get("forms", [])
    result: dict[str, Any] = {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "pokedex_id": data.get("pokedex_id"),
        "description": data.get("description"),
        "forms": [
            {
                "name": f.get("name"),
                "types": f.get("types"),
                "abilities": list(dict.fromkeys(
                    a["name"] if isinstance(a, dict) else a for a in f.get("abilities", [])
                )),
                "category": f.get("category"),
                "height": f.get("height"),
                "weight": f.get("weight"),
                "catch_rate": f.get("catch_rate"),
                "egg_groups": f.get("egg_groups"),
            }
            for f in forms
        ],
        "stats": data.get("stats"),
        "evolution_chains": data.get("evolution_chains"),
        "mega_evolution": data.get("mega_evolution"),
        "_data_source": data.get("_data_source", "gen9"),
    }
    # Prompt LLM to disambiguate when multiple forms exist
    if len(forms) > 1:
        form_names = [f.get("name", "") for f in forms]
        result["form_selection_note"] = (
            f"该宝可梦存在 {len(forms)} 种形态：{', '.join(form_names)}。"
            "请在 calc / optimize 的 override 中传入 'form_name' 字段以指定具体形态。"
        )
    return result


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
        "_data_source": data.get("_data_source", "gen9"),
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


def cmd_type(atk: str, dfn: str = "") -> dict[str, Any]:
    load_data()
    chart = _type_chart
    # Normalize type names (supports English input like "Psychic" -> "超能力")
    from normalize import normalize_type_name

    atk = normalize_type_name(atk)
    if atk not in chart:
        return {"error": f"Type '{atk}' not found. Valid types: {list(chart.keys())}"}

    if dfn:
        # Backward-compatible: point-to-point query
        dfn = normalize_type_name(dfn)
        row = chart[atk]
        if dfn not in row:
            return {"error": f"Defense type '{dfn}' not found. Valid types: {list(row.keys())}"}
        return {
            "attack_type": atk,
            "defense_type": dfn,
            "multiplier": row[dfn],
            "description": _describe_multiplier(row[dfn]),
        }

    # Aggregate query: only one type provided
    # Offensive profile (atk as attacker)
    offensive_row = chart[atk]
    offensive: dict[str, list[str]] = {
        "super_effective": [t for t, m in offensive_row.items() if m > 1],
        "not_very_effective": [t for t, m in offensive_row.items() if 0 < m < 1],
        "no_effect": [t for t, m in offensive_row.items() if m == 0],
    }

    # Defensive profile (atk as defender)
    defensive: dict[str, list[str]] = {
        "weak_to": [t for t, row in chart.items() if row[atk] > 1],
        "resists": [t for t, row in chart.items() if 0 < row[atk] < 1],
        "immune_to": [t for t, row in chart.items() if row[atk] == 0],
    }

    return {
        "type": atk,
        "mode": "aggregate",
        "offensive": offensive,
        "defensive": defensive,
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
    champions_moves = _get_champions_learnset(stem)
    if champions_moves:
        # Champions patch provides a flat list of move names
        formatted = [{"name": m} for m in champions_moves]
        return {
            "name_zh": data.get("name_zh"),
            "name_en": data.get("name_en"),
            "learnable_moves": [{"form": "", "data": formatted}],
            "machine_moves": [],
            "egg_moves": [],
            "tutor_moves": [],
            "_data_source": "champions",
        }
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


def _iter_moves(pdata: dict[str, Any], stem: str = ""):
    """Yield (move_dict, source_category) for all moves in a pokemon entry.
    If Champions learnset patch exists for stem, yield from patch instead.
    """
    champions_moves = _get_champions_learnset(stem)
    if champions_moves:
        for move_name in champions_moves:
            yield {"name": move_name}, "learnable_moves"
        return
    for category in ("learnable_moves", "machine_moves", "egg_moves", "tutor_moves"):
        for form_block in pdata.get(category, []):
            if isinstance(form_block, dict) and "data" in form_block:
                for move in form_block["data"]:
                    if isinstance(move, dict):
                        yield move, category


def cmd_find_move(move_name: str, source: str = "") -> dict[str, Any]:
    """Find all pokemon that can learn a given move.

    Optional source filter: "champions" | "gen9"
    """
    load_data()
    move_stem = _index_data["moves"].get(move_name)
    if not move_stem:
        for k, v in _index_data["moves"].items():
            if k.lower() == move_name.lower():
                move_stem = v
                break
    move_data = _moves_data.get(move_stem) if move_stem else None
    if move_data is not None:
        move_data = _apply_champions_move_patch(move_stem, move_data)
    move_zh = move_data.get("name_zh") if move_data else move_name

    result: list[dict[str, Any]] = []
    for stem, pdata in _pokemon_data.items():
        # Apply Champions patch to determine data_source for filtering
        merged_pdata = _apply_champions_pokemon_patch(stem, pdata)
        data_source = merged_pdata.get("_data_source", "gen9")

        # Apply source filter
        if source == "champions" and data_source != "champions":
            continue
        if source == "gen9" and data_source == "champions":
            continue

        for move, category in _iter_moves(pdata, stem=stem):
            if move.get("name") == move_zh:
                forms = merged_pdata.get("forms", [{}])
                first_form_types = forms[0].get("types", []) if forms else []
                result.append({
                    "name_zh": pdata.get("name_zh"),
                    "name_en": pdata.get("name_en"),
                    "pokedex_id": pdata.get("pokedex_id"),
                    "method": _get_method_name(move, category),
                    "types": first_form_types,
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


def cmd_filter_moves(
    type_filters: list[str] | None = None,
    category_filters: list[str] | None = None,
    min_power: int | None = None,
    max_power: int | None = None,
) -> dict[str, Any]:
    """Filter moves by type, category, and/or power range.

    Multiple filters within the same dimension use OR logic;
    different dimensions use AND logic.

    Args:
        type_filters: List of type names (zh or en).
                      Moves matching ANY listed type are included.
        category_filters: List of categories (zh: 物理/特殊/变化 or
                          en: Physical/Special/Status).
                          Moves matching ANY listed category are included.
        min_power: Minimum base power (inclusive). Non-numeric power values
                   (e.g. status moves marked "—") are treated as 0.
        max_power: Maximum base power (inclusive). If None, no upper bound.
    """
    load_data()

    from normalize import normalize_type_name

    valid_types = set(_type_chart.keys()) if _type_chart else set()

    # Normalize type names
    normalized_types: set[str] = set()
    if type_filters:
        for t in type_filters:
            nt = normalize_type_name(t)
            if nt in valid_types:
                normalized_types.add(nt)
            else:
                # Try direct lowercase match for edge cases
                for vt in valid_types:
                    if vt.lower() == t.lower():
                        normalized_types.add(vt)
                        break
                else:
                    return {"error": f"Invalid type '{t}'. Valid types: {sorted(valid_types)}"}

    # Normalize category names to Chinese
    _CATEGORY_MAP: dict[str, str] = {
        "physical": "物理",
        "special": "特殊",
        "status": "变化",
        "物理": "物理",
        "特殊": "特殊",
        "变化": "变化",
    }
    normalized_categories: set[str] = set()
    if category_filters:
        for c in category_filters:
            key = c.lower()
            if key in _CATEGORY_MAP:
                normalized_categories.add(_CATEGORY_MAP[key])
            else:
                return {
                    "error": (
                        f"Unknown category '{c}'. "
                        "Valid: Physical/Special/Status or 物理/特殊/变化"
                    )
                }

    results: list[dict[str, Any]] = []

    for stem, data in _moves_data.items():
        # Apply Champions patch if available
        patched = _apply_champions_move_patch(stem, data)
        if not patched:
            continue
        data = patched

        # Type filter (OR within dimension)
        if normalized_types:
            move_type = data.get("type", "")
            if move_type not in normalized_types:
                continue

        # Category filter (OR within dimension)
        if normalized_categories:
            move_category = data.get("category", "")
            if move_category not in normalized_categories:
                continue

        # Power filter
        if min_power is not None or max_power is not None:
            power_str = str(data.get("power", "0"))
            try:
                power = int(power_str)
            except ValueError:
                power = 0

            if min_power is not None and power < min_power:
                continue
            if max_power is not None and power > max_power:
                continue

        results.append({
            "name_zh": data.get("name_zh", ""),
            "name_en": data.get("name_en", ""),
            "type": data.get("type", ""),
            "category": data.get("category", ""),
            "power": data.get("power", ""),
            "accuracy": data.get("accuracy", ""),
            "pp": data.get("pp", ""),
            "description": data.get("description", ""),
        })

    # Sort by power descending, then by Chinese name ascending
    def _sort_key(entry: dict[str, Any]) -> tuple[int, str]:
        p = entry.get("power", "")
        try:
            power_val = int(p)
        except (ValueError, TypeError):
            power_val = 0
        return (-power_val, entry.get("name_zh", ""))

    results.sort(key=_sort_key)

    return {
        "count": len(results),
        "filters": {
            "types": sorted(normalized_types),
            "categories": sorted(normalized_categories),
            "min_power": min_power,
            "max_power": max_power,
        },
        "results": results,
    }


def _derive_mega_stone(form_name: str) -> str:
    """Derive the Mega Stone name from a Mega form name.

    Rules:
        - "超级喷火龙Ｙ" -> "喷火龙进化石Ｙ"
        - "超级胡地"     -> "胡地进化石"
        - "原始盖欧卡"   -> "原始回归宝珠"
    """
    if form_name.startswith("原始"):
        return "原始回归宝珠"
    if form_name.startswith("超级"):
        base = form_name[2:]  # Strip "超级" prefix
        # Handle X/Y suffixes like 喷火龙Ｘ / 喷火龙Ｙ
        if base.endswith("Ｘ") or base.endswith("Ｙ"):
            return base[:-1] + "进化石" + base[-1]
        return base + "进化石"
    return ""


def _apply_setup_moves(attacker, defender, field, setup_moves: list[str]) -> None:
    """Apply stat_changes from setup moves to attacker state and field.

    Reads moves.json for each setup move and applies structured stat changes.
    This eliminates LLM dependency on move effect knowledge.
    """
    for move_name in setup_moves:
        move_data = _moves_data.get(move_name)
        if not move_data:
            continue
        stat_changes = move_data.get("stat_changes")
        if not stat_changes:
            continue

        # Apply self boosts
        if "self" in stat_changes:
            for stat, change in stat_changes["self"].items():
                attacker.boosts[stat] = attacker.boosts.get(stat, 0) + change

        # Apply weather
        if "weather" in stat_changes:
            field.weather = stat_changes["weather"]

        # Apply terrain
        if "terrain" in stat_changes:
            field.terrain = stat_changes["terrain"]

        # Apply opponent debuffs
        if "opponent" in stat_changes:
            for stat, change in stat_changes["opponent"].items():
                defender.boosts[stat] = defender.boosts.get(stat, 0) + change

        # Apply heal
        if "heal" in stat_changes:
            heal_target = stat_changes["heal"].get("target", "self")
            ratio = stat_changes["heal"].get("ratio", 0)
            if heal_target == "self" and attacker.max_hp > 0:
                heal_amount = int(attacker.max_hp * ratio)
                attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal_amount)


def _resolve_ability_to_en(ability_name: str) -> str:
    """Resolve an ability name (zh or en) to its English canonical name."""
    if not ability_name:
        return ""
    # Already English
    if ability_name.isascii():
        return ability_name
    load_data()
    if _abilities_data is not None:
        info = _abilities_data.get(ability_name)
        if info:
            return info.get("name_en", ability_name)
    return ability_name


def _resolve_ability_to_zh(ability_name: str) -> str:
    """Resolve an ability name (zh or en) to its Chinese canonical name."""
    if not ability_name:
        return ""
    # Already Chinese
    if not ability_name.isascii():
        return ability_name
    load_data()
    if _abilities_data is not None:
        for zh_name, info in _abilities_data.items():
            if info.get("name_en") == ability_name:
                return zh_name
    return ability_name


def _resolve_gender(form: dict[str, Any]) -> str:
    """Extract gender from a form's gender_ratio field.

    Returns "M" for male-only, "F" for female-only, "" for mixed or unknown.
    Rivalry only cares about the three-way comparison (M/F/neither).
    """
    gr = form.get("gender_ratio", {})
    if not isinstance(gr, dict):
        return ""
    male = gr.get("male", -1)
    female = gr.get("female", -1)
    if male == 100 and female == 0:
        return "M"
    if male == 0 and female == 100:
        return "F"
    if male == 0 and female == 0:
        return ""       # genderless
    return ""           # mixed ratio — needs LLM override


def _make_pokemon_from_data(data: dict[str, Any], overrides: dict[str, Any] | None = None, form_index: int = 0) -> dict[str, Any]:
    """Build a Pokemon dict suitable for damage.py from pokedex data."""
    forms = data.get("forms", [{}])
    # Allow override by explicit form_name (e.g. "洗翠的样子")
    if overrides and "form_name" in overrides:
        target = overrides["form_name"]
        for idx, f in enumerate(forms):
            if f.get("name") == target:
                form_index = idx
                break
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
    # Handle gen9 string format vs gen8/Champions dict format
    if abilities and isinstance(abilities[0], str):
        ability_zh = abilities[0]
    elif abilities and isinstance(abilities[0], dict):
        ability_zh = abilities[0].get("name", "")
    else:
        ability_zh = ""

    ability = _resolve_ability_to_en(ability_zh)
    form_name = form.get("name", "")
    is_mega = form_name.startswith("超级") or form_name.startswith("原始")

    default_item = ""
    if is_mega:
        default_item = _derive_mega_stone(form_name)

    # Build display name: combine regional prefix with base name for descriptive forms
    name_zh = data.get("name_zh", "")
    if not form_name or form_name == name_zh:
        display_name = name_zh
    elif name_zh in form_name:
        # form_name already contains base name, e.g. "超级喷火龙Ｙ"
        display_name = form_name
    elif "的样子" in form_name:
        # Descriptive form name like "洗翠的样子", "阿罗拉的样子"
        prefix = form_name.replace("的样子", "")
        display_name = prefix + name_zh
    else:
        display_name = form_name

    pk = {
        "name": display_name,
        "name_en": data.get("name_en", ""),
        "level": 50,
        "base_stats": base_stats,
        "types": types,
        "ability": ability,          # English (engine layer)
        "ability_zh": ability_zh,    # Chinese (display layer)
        "item": default_item,
        "nature": "勤奋",
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "boosts": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "status": None,
        "is_terastalize": False,
        "tera_type": None,
        "is_dynamax": False,
        "weight": 0.0,
        "gender": _resolve_gender(form),
        "_data_source": data.get("_data_source", "gen9"),
        "is_unobtainable": is_mega and data.get("_data_source", "gen9") == "gen9",
    }
    if overrides:
        pk.update(overrides)
    # Post-override: ensure ability is in English for the damage engine
    overridden_ability = pk.get("ability", "")
    pk["ability"] = _resolve_ability_to_en(overridden_ability)
    # Sync ability_zh with the final ability
    if overrides and "ability" in overrides:
        pk["ability_zh"] = _resolve_ability_to_zh(overridden_ability) or pk.get("ability_zh", "")
    # Filter out fields not supported by the Pokemon dataclass
    _VALID_PK_FIELDS = {
        "name", "name_en", "level", "base_stats", "evs", "ivs",
        "nature", "ability", "ability_zh", "item", "types", "tera_type",
        "is_terastalize", "boosts", "current_hp", "max_hp",
        "status", "weight", "is_dynamax", "can_evolve",
        "ability_on", "fainted_allies",
        "gender",
        "raw_stats", "stats",
    }
    pk = {k: v for k, v in pk.items() if k in _VALID_PK_FIELDS}
    return pk


def _make_move_from_data(data: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a Move dict suitable for damage.py from move data."""
    _MOVE_CATEGORY_ZH_TO_EN: dict[str, str] = {
        "物理": "Physical",
        "特殊": "Special",
        "变化": "Status",
    }
    # English → Chinese type mapping: moves.json has mixed EN/ZH types (~55% EN),
    # but damage.py compares against Chinese strings (e.g. "火", not "Fire").
    _MOVE_TYPE_EN_TO_ZH: dict[str, str] = {
        "Normal": "一般", "Fire": "火", "Water": "水", "Electric": "电",
        "Grass": "草", "Ice": "冰", "Fighting": "格斗", "Poison": "毒",
        "Ground": "地面", "Flying": "飞行", "Psychic": "超能力", "Bug": "虫",
        "Rock": "岩石", "Ghost": "幽灵", "Dragon": "龙", "Dark": "恶",
        "Steel": "钢", "Fairy": "妖精",
    }
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
        "type": _MOVE_TYPE_EN_TO_ZH.get(data.get("type", "一般"), data.get("type", "一般")),
        "category": _MOVE_CATEGORY_ZH_TO_EN.get(data.get("category", ""), "Physical"),
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
        "fainted_allies": 0,
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
    mode: str = "ev",
    *extra_args: str,
) -> dict[str, Any]:
    """Optimize EV allocation for a given battle scenario.

    goal: ko | survive | survive_bulk
    target: ohko | 2hko | 3hko | survive | survive_2hko
    threshold: guaranteed | likely

    Examples:
        python query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko
        python query.py optimize 喷火龙 喷射火焰 水箭龟 --goal survive --target survive --threshold guaranteed
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

    # Remove extra metadata before passing to model constructors
    att_dict.pop("_data_source", None)
    att_dict.pop("is_unobtainable", None)
    def_dict.pop("_data_source", None)
    def_dict.pop("is_unobtainable", None)

    from models import Pokemon, Move, Field
    attacker = Pokemon(**att_dict)
    defender = Pokemon(**def_dict)
    move = Move(**move_dict)
    field = Field()
    _apply_field_overrides(field, field_override)

    return optimize_evs(attacker, defender, move, field, goal=goal, target=target, threshold=threshold, mode=mode)  # type: ignore[arg-type]


def cmd_calc(attacker_name: str, move_name: str, defender_name: str, *extra_args: str) -> dict[str, Any]:
    """Quick damage calculation using default Lv50 stats.

    Optional extra_args: JSON overrides for attacker, move, defender, field.
    (Used by legacy positional callers; argparse callers pass overrides as named args.)
    Example:
        python query.py calc 喷火龙 喷射火焰 水箭龟
        python query.py calc 喷火龙 喷射火焰 水箭龟 --att_ov '{"evs":{"sp_attack":252}}' --field_ov '{"weather":"Sun"}'
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

    # Remember if user explicitly specified a preset before _apply_preset_to_override pops it
    att_has_explicit_preset = "preset" in att_override
    def_has_explicit_preset = "preset" in def_override

    # Apply presets if specified in overrides
    att_override = _apply_preset_to_override(att_override, att_data.get("name_en", ""))
    def_override = _apply_preset_to_override(def_override, def_data.get("name_en", ""))

    # Auto-match preset for partially specified configs (evs/nature/ivs only)
    if not att_has_explicit_preset:
        att_override, att_auto_preset = _apply_auto_preset_to_override(
            att_override, att_data.get("name_en", "")
        )
    else:
        att_auto_preset = None
    if not def_has_explicit_preset:
        def_override, def_auto_preset = _apply_auto_preset_to_override(
            def_override, def_data.get("name_en", "")
        )
    else:
        def_auto_preset = None

    att_dict = _make_pokemon_from_data(att_data, att_override, form_index=att_form_idx)
    def_dict = _make_pokemon_from_data(def_data, def_override, form_index=def_form_idx)
    move_dict = _make_move_from_data(move_data, move_override)

    # Extract setup_moves and extra metadata before passing to model constructors
    setup_moves = att_dict.pop("setup_moves", [])
    att_extra = {
        "_data_source": att_dict.pop("_data_source", "gen9"),
        "is_unobtainable": att_dict.pop("is_unobtainable", False),
    }
    def_extra = {
        "_data_source": def_dict.pop("_data_source", "gen9"),
        "is_unobtainable": def_dict.pop("is_unobtainable", False),
    }

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

    # Apply setup moves (e.g., Nasty Plot, Swords Dance) if specified in att_override
    setup_moves = att_override.get("setup_moves", [])
    if setup_moves:
        _apply_setup_moves(attacker, defender, field, setup_moves)

    result = calculate_damage(attacker, defender, move, field, gen=9)

    # KO chance
    from ko_chance import get_ko_chance_text, squash_multihit
    ko_text = get_ko_chance_text(result.damage, move, defender, field)

    # Multi-hit total damage (for moves like Dual Wingbeat)
    total_damage_rolls: list[int] = []
    if move.hits > 1:
        total_damage_rolls = squash_multihit(result.damage, move.hits)

    # Build attacker / defender summary for transparency
    # Extract all abilities from the *selected* form (not always forms[0])
    att_forms = att_data.get("forms", [{}])
    att_selected_form = att_forms[att_form_idx] if att_forms and att_form_idx < len(att_forms) else (att_forms[0] if att_forms else {})
    att_all_abilities = list(dict.fromkeys(
        a.get("name", "") if isinstance(a, dict) else a
        for a in att_selected_form.get("abilities", [])
    ))

    def_forms = def_data.get("forms", [{}])
    def_selected_form = def_forms[def_form_idx] if def_forms and def_form_idx < len(def_forms) else (def_forms[0] if def_forms else {})
    def_all_abilities = list(dict.fromkeys(
        a.get("name", "") if isinstance(a, dict) else a
        for a in def_selected_form.get("abilities", [])
    ))

    attacker_info = {
        "name_zh": attacker.name,
        "name_en": att_data.get("name_en", ""),
        "types": attacker.types,
        "base_stats": attacker.base_stats,
        "stats": attacker.raw_stats,
        "ability": attacker.ability_zh,
        "all_abilities": att_all_abilities,
        "nature": attacker.nature,
        "item": attacker.item,
        "evs": attacker.evs,
        "ivs": attacker.ivs,
        "level": attacker.level,
        "current_hp": attacker.current_hp,
        "max_hp": attacker.max_hp,
        "_data_source": att_extra.get("_data_source", "gen9"),
        "is_unobtainable": att_extra.get("is_unobtainable", False),
    }
    defender_info = {
        "name_zh": defender.name,
        "name_en": def_data.get("name_en", ""),
        "types": defender.types,
        "base_stats": defender.base_stats,
        "stats": defender.raw_stats,
        "ability": defender.ability_zh,
        "all_abilities": def_all_abilities,
        "nature": defender.nature,
        "item": defender.item,
        "evs": defender.evs,
        "ivs": defender.ivs,
        "level": defender.level,
        "current_hp": defender.current_hp,
        "max_hp": defender.max_hp,
        "_data_source": def_extra.get("_data_source", "gen9"),
        "is_unobtainable": def_extra.get("is_unobtainable", False),
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
        "_data_source": attacker_info.get("_data_source", "gen9"),
    }
    if att_auto_preset:
        response["attacker_auto_preset"] = att_auto_preset
    if def_auto_preset:
        response["defender_auto_preset"] = def_auto_preset
    if attacker_info.get("is_unobtainable") or defender_info.get("is_unobtainable"):
        response["warning"] = "该形态在当前对战环境中不可用，以下结果为理论计算"
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
        "ability": attacker.ability_zh,
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
        "ability": defender.ability_zh,
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


def _get_ko_prob(
    damage: list[int],
    hp: int,
    max_hp: int,
) -> float:
    """Return single-hit KO probability (0.0 ~ 1.0) with no hazards/berries/eot."""
    from ko_chance import _get_ko_chance

    return _get_ko_chance(
        damage=damage,
        multihit=False,
        hp=hp,
        eot=0,
        hits=1,
        max_hp=max_hp,
        toxic_counter=0,
        has_sitrus=False,
        has_figy=False,
        gluttony=False,
        ripen=1,
    )


def _find_survivability_bp(
    attacker: Pokemon,
    defender: Pokemon,
    field: Field,
    category: str,
    max_bp: int = 500,
    safe_threshold: float = 0.15,
    def_boosts: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Binary search for safe_bp and absolute_safe_bp."""
    from models import Move
    from damage import calculate_damage, get_modified_stat

    # Apply defender boost overrides before the binary search
    if def_boosts:
        for stat, change in def_boosts.items():
            defender.boosts[stat] = defender.boosts.get(stat, 0) + change

    # Recalculate defender.stats from raw_stats + boosts (survivability bypasses compute_raw_stats)
    if defender.raw_stats:
        for stat_key, raw in defender.raw_stats.items():
            defender.stats[stat_key] = get_modified_stat(raw, defender.boosts.get(stat_key, 0))

    lo, hi = 1, max_bp

    def _test(bp: int) -> tuple[list[int], float]:
        move = Move(
            name="Test",
            base_power=bp,
            type="Normal",
            category=category,
            accuracy=100,
            hits=1,
            is_spread=False,
        )
        result = calculate_damage(attacker, defender, move, field, gen=9)
        ko_prob = _get_ko_prob(result.damage, defender.current_hp, defender.max_hp)
        return result.damage, ko_prob

    # Safe line (KO prob < safe_threshold)
    _, safe_ko_hi = _test(hi)
    if safe_ko_hi < safe_threshold:
        safe_bp = hi
    else:
        _, safe_ko_lo = _test(lo)
        if safe_ko_lo >= safe_threshold:
            safe_bp = 0
        else:
            l, h = lo, hi
            while l < h:
                mid = (l + h) // 2
                _, ko_prob = _test(mid)
                if ko_prob < safe_threshold:
                    l = mid + 1
                else:
                    h = mid
            safe_bp = l - 1

    # Absolute safe line (KO prob == 0)
    _, abs_ko_hi = _test(hi)
    if abs_ko_hi == 0.0:
        abs_safe_bp = hi
    else:
        _, abs_ko_lo = _test(lo)
        if abs_ko_lo > 0.0:
            abs_safe_bp = 0
        else:
            l, h = lo, hi
            while l < h:
                mid = (l + h) // 2
                _, ko_prob = _test(mid)
                if ko_prob == 0.0:
                    l = mid + 1
                else:
                    h = mid
            abs_safe_bp = l - 1

    # Get damage ranges for reporting
    safe_dr = [0, 0]
    if safe_bp > 0:
        safe_damage, _ = _test(safe_bp)
        safe_dr = [min(safe_damage), max(safe_damage)]

    abs_dr = [0, 0]
    if abs_safe_bp > 0:
        abs_damage, _ = _test(abs_safe_bp)
        abs_dr = [min(abs_damage), max(abs_damage)]

    return {
        "safe_bp": safe_bp,
        "absolute_safe_bp": abs_safe_bp,
        "safe_damage_range": safe_dr,
        "absolute_safe_damage_range": abs_dr,
    }


def cmd_survivability(
    defender_name: str,
    attacker_stat: int,
    category: str,
    def_ov: str = "{}",
    field_ov: str = "{}",
    setup_moves: list[str] | None = None,
) -> dict[str, Any]:
    """Reverse survivability lookup: find max unboosted BP a defender can survive.

    Args:
        defender_name: Pokemon name (zh/en) or JSON with raw_stats.
        attacker_stat: Attacker's attack or sp_attack stat value.
        category: "Physical" or "Special".
        def_ov: JSON override for defender (e.g. raw_stats, boosts, setup_moves).
        field_ov: JSON override for field (e.g. format).
        setup_moves: Optional list of defender setup moves to apply as boosts.

    Returns:
        dict with safe_bp, absolute_safe_bp, defender info, etc.
    """
    import json


    # Parse overrides
    try:
        def_override = json.loads(def_ov) if def_ov else {}
    except (json.JSONDecodeError, TypeError):
        def_override = {}
    try:
        field_override = json.loads(field_ov) if field_ov else {}
    except (json.JSONDecodeError, TypeError):
        field_override = {}

    # Extract setup moves and boosts from defender override
    setup_moves = def_override.pop("setup_moves", setup_moves) or []
    def_boosts = def_override.pop("boosts", {})

    # Build virtual attacker (only relevant attack stat set, no STAB, no item, no ability)
    raw_stats = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    if category == "Physical":
        raw_stats["attack"] = attacker_stat
    else:
        raw_stats["sp_attack"] = attacker_stat

    # Use Fire type to avoid STAB with Normal-type move (ensuring "no boost" calculation)
    attacker = Pokemon(
        name="VirtualAttacker",
        name_en="VirtualAttacker",
        level=50,
        types=["Fire"],
        stats=raw_stats,
        raw_stats=raw_stats,
        ability="",
        ability_zh="",
        nature="Hardy",
        item="",
        current_hp=0,
        max_hp=0,
    )

    # Build defender
    defender_data: dict[str, Any] = {}
    try:
        maybe_json = json.loads(defender_name)
        if isinstance(maybe_json, dict) and "raw_stats" in maybe_json:
            defender_data = maybe_json
            defender_name = defender_data.get("name", "Defender")
    except (json.JSONDecodeError, TypeError):
        pass

    if not defender_data:
        resolved = resolve_pokemon(defender_name)
        if resolved:
            _, data, form_idx = resolved
            pk_info = _make_pokemon_from_data(data, form_index=form_idx)
            defender_data = {
                "name": pk_info.get("name", defender_name),
                "name_en": pk_info.get("name_en", ""),
                "types": pk_info.get("types", ["Normal"]),
                "base_stats": pk_info.get("base_stats", {}),
            }
        else:
            return {"error": f"Defender '{defender_name}' not found."}

    # 1. Compute default Lv.50 stats first (from base_stats), if not already present
    if "stats" not in defender_data and "raw_stats" not in defender_data:
        base_stats = defender_data.get("base_stats", {})
        if base_stats:
            from damage import calc_hp_stat, calc_raw_stat, get_nature_modifier
            stats = {}
            for stat_key, base in base_stats.items():
                if stat_key == "hp":
                    stats[stat_key] = calc_hp_stat(base, 31, 0, 50)
                else:
                    raw = calc_raw_stat(base, 31, 0, 50)
                    stats[stat_key] = int(raw * get_nature_modifier("Hardy", stat_key))
            defender_data["stats"] = stats

    # 2. Merge user overrides: user-specified fields override defaults, rest keep default Lv.50 values
    user_raw_stats = def_override.get("raw_stats", {})
    if user_raw_stats:
        default_stats = defender_data.get("stats", {})
        merged_stats = default_stats.copy()
        merged_stats.update(user_raw_stats)
        defender_data["raw_stats"] = merged_stats
    user_stats = def_override.get("stats", {})
    if user_stats:
        default_stats = defender_data.get("stats", {})
        merged_stats = default_stats.copy()
        merged_stats.update(user_stats)
        defender_data["stats"] = merged_stats

    if "stats" not in defender_data and "raw_stats" not in defender_data:
        return {"error": f"No stats available for defender '{defender_name}'."}

    stats = defender_data.get("raw_stats") or defender_data.get("stats", {})
    hp = stats.get("hp", 0)
    defender = Pokemon(
        name=defender_data.get("name", defender_name),
        name_en=defender_data.get("name_en", "Defender"),
        level=50,
        types=defender_data.get("types", ["Normal"]),
        stats=stats,
        raw_stats=stats,
        ability="",
        ability_zh="",
        nature="Hardy",
        item="",
        current_hp=hp,
        max_hp=hp,
    )

    # Build field
    field = Field()
    for k, v in field_override.items():
        if hasattr(field, k):
            setattr(field, k, v)
    if not getattr(field, "format", None):
        field.format = "Doubles"

    # Apply defender setup moves (e.g., Calm Mind, Iron Defense) before searching BP
    if setup_moves:
        _apply_setup_moves(defender, attacker, field, setup_moves)

    result = _find_survivability_bp(
        attacker, defender, field, category, def_boosts=def_boosts
    )

    return {
        "defender": {
            "name_zh": defender.name,
            "name_en": defender.name_en,
            "hp": defender.current_hp,
            "defense": defender.raw_stats.get("defense", 0),
            "sp_defense": defender.raw_stats.get("sp_defense", 0),
            "level": 50,
        },
        "attacker_stat": attacker_stat,
        "category": category,
        "format": field.format,
        "defender_boosts": dict(defender.boosts),
        "safe_bp": result["safe_bp"],
        "absolute_safe_bp": result["absolute_safe_bp"],
        "safe_damage_range": result["safe_damage_range"],
        "absolute_safe_damage_range": result["absolute_safe_damage_range"],
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
    "filter-moves": cmd_filter_moves,
    "preset": cmd_preset,
    "calc": cmd_calc,
    "calc-raw": cmd_calc_raw,
    "compute-stats": cmd_compute_stats,
    "optimize": cmd_optimize,
    "survivability": cmd_survivability,
}


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    cmd = sys.argv[1]

    # Named-argument commands: use argparse
    if cmd in ("calc", "optimize", "calc-raw", "compute-stats", "find-move", "pokemon", "filter-moves", "survivability"):
        import argparse

        parser = argparse.ArgumentParser(description="Pokemon Calc CLI")
        subparsers = parser.add_subparsers(dest="command")

        # pokemon
        pokemon_parser = subparsers.add_parser("pokemon", help="Pokemon info or type-filtered search")
        pokemon_parser.add_argument("name", nargs="?", default="", help="Pokemon name (optional if --type is used)")
        pokemon_parser.add_argument("--type", dest="type_filters", action="append", default=[], help="Filter by type (can specify multiple, e.g. --type 超能 --type 恶)")

        # calc
        calc_parser = subparsers.add_parser("calc", help="Quick damage calculation")
        calc_parser.add_argument("attacker", help="Attacker Pokemon name")
        calc_parser.add_argument("move", help="Move name")
        calc_parser.add_argument("defender", help="Defender Pokemon name")
        calc_parser.add_argument("--att_ov", default="{}", help="Attacker override JSON")
        calc_parser.add_argument("--move_ov", default="{}", help="Move override JSON")
        calc_parser.add_argument("--def_ov", default="{}", help="Defender override JSON")
        calc_parser.add_argument("--field_ov", default="{}", help="Field override JSON")
        calc_parser.add_argument("--att_ov_file", default=None, help="Path to attacker override JSON file (takes precedence over --att_ov)")
        calc_parser.add_argument("--move_ov_file", default=None, help="Path to move override JSON file (takes precedence over --move_ov)")
        calc_parser.add_argument("--def_ov_file", default=None, help="Path to defender override JSON file (takes precedence over --def_ov)")
        calc_parser.add_argument("--field_ov_file", default=None, help="Path to field override JSON file (takes precedence over --field_ov)")

        # optimize
        opt_parser = subparsers.add_parser("optimize", help="EV / SP optimization")
        opt_parser.add_argument("attacker", help="Attacker Pokemon name")
        opt_parser.add_argument("move", help="Move name")
        opt_parser.add_argument("defender", help="Defender Pokemon name")
        opt_parser.add_argument("--goal", default="ko", help="Optimization goal")
        opt_parser.add_argument("--target", default="ohko", help="Optimization target")
        opt_parser.add_argument("--threshold", default="guaranteed", help="Threshold")
        opt_parser.add_argument("--mode", default="ev", help="Optimization mode: ev (Gen9) or sp (Champions Stat Points)")
        opt_parser.add_argument("--att_ov", default="{}", help="Attacker override JSON")
        opt_parser.add_argument("--def_ov", default="{}", help="Defender override JSON")
        opt_parser.add_argument("--field_ov", default="{}", help="Field override JSON")
        opt_parser.add_argument("--att_ov_file", default=None, help="Path to attacker override JSON file (takes precedence over --att_ov)")
        opt_parser.add_argument("--def_ov_file", default=None, help="Path to defender override JSON file (takes precedence over --def_ov)")
        opt_parser.add_argument("--field_ov_file", default=None, help="Path to field override JSON file (takes precedence over --field_ov)")

        # calc-raw
        raw_parser = subparsers.add_parser("calc-raw", help="Pure parameter-driven damage calculation")
        raw_parser.add_argument("--att", required=True, help="Attacker JSON")
        raw_parser.add_argument("--move", required=True, dest="move_json", help="Move JSON")
        raw_parser.add_argument("--def", required=True, dest="defender_json", help="Defender JSON")
        raw_parser.add_argument("--field", default="{}", help="Field JSON")

        # compute-stats
        stats_parser = subparsers.add_parser("compute-stats", help="Compute ability values")
        stats_parser.add_argument("base_stats", help="Base stats JSON")
        stats_parser.add_argument("--evs", default="{}", help="EVs JSON")
        stats_parser.add_argument("--ivs", default="{}", help="IVs JSON")
        stats_parser.add_argument("--nature", default="勤奋", help="Nature name (Chinese or English)")
        stats_parser.add_argument("--level", default="50", help="Level")

        # find-move
        findmove_parser = subparsers.add_parser("find-move", help="Find all pokemon that can learn a given move")
        findmove_parser.add_argument("move", help="Move name")
        findmove_parser.add_argument("--source", default="", help="Data source filter: champions | gen9")

        # filter-moves
        filter_parser = subparsers.add_parser("filter-moves", help="Filter moves by type, category, and/or power")
        filter_parser.add_argument("--type", dest="type_filters", action="append", default=[], help="Filter by type (can specify multiple)")
        filter_parser.add_argument("--category", dest="category_filters", action="append", default=[], help="Filter by category (物理/特殊/变化 or Physical/Special/Status)")
        filter_parser.add_argument("--min-power", type=int, default=None, help="Minimum base power (inclusive)")
        filter_parser.add_argument("--max-power", type=int, default=None, help="Maximum base power (inclusive)")

        # survivability
        surv_parser = subparsers.add_parser("survivability", help="Reverse survivability: max unboosted BP defender can survive")
        surv_parser.add_argument("defender", help="Defender Pokemon name or JSON with raw_stats")
        surv_parser.add_argument("attacker_stat", type=int, help="Attacker's attack/sp_attack stat value")
        surv_parser.add_argument("category", help="Physical or Special")
        surv_parser.add_argument("--def_ov", default="{}", help="Defender override JSON (supports boosts, setup_moves, raw_stats)")
        surv_parser.add_argument("--def_ov_file", default=None, help="Path to defender override JSON file (takes precedence over --def_ov)")
        surv_parser.add_argument("--field_ov", default="{}", help="Field override JSON")
        surv_parser.add_argument("--field_ov_file", default=None, help="Path to field override JSON file (takes precedence over --field_ov)")

        args = parser.parse_args()

        # If *_ov_file is provided, read file content and override the JSON string args.
        # File-based input takes precedence over inline JSON.
        def _read_file_or_default(path: str | None, default: str) -> str:
            if path is None:
                return default
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception as e:
                print(f"Error reading override file '{path}': {e}")
                return default

        args.att_ov = _read_file_or_default(getattr(args, "att_ov_file", None), getattr(args, "att_ov", "{}"))
        args.move_ov = _read_file_or_default(getattr(args, "move_ov_file", None), getattr(args, "move_ov", "{}"))
        args.def_ov = _read_file_or_default(getattr(args, "def_ov_file", None), getattr(args, "def_ov", "{}"))
        args.field_ov = _read_file_or_default(getattr(args, "field_ov_file", None), getattr(args, "field_ov", "{}"))

        try:
            if cmd == "calc":
                result = cmd_calc(
                    args.attacker,
                    args.move,
                    args.defender,
                    args.att_ov,
                    args.move_ov,
                    args.def_ov,
                    args.field_ov,
                )
            elif cmd == "optimize":
                result = cmd_optimize(
                    args.attacker,
                    args.move,
                    args.defender,
                    args.goal,
                    args.target,
                    args.threshold,
                    args.mode,
                    args.att_ov,
                    args.def_ov,
                    args.field_ov,
                )
            elif cmd == "pokemon":
                if args.type_filters:
                    result = cmd_pokemon(type_filters=args.type_filters)
                else:
                    result = cmd_pokemon(name=args.name)
            elif cmd == "compute-stats":
                result = cmd_compute_stats(
                    args.base_stats,
                    args.evs,
                    args.ivs,
                    args.nature,
                    args.level,
                )
            elif cmd == "find-move":
                result = cmd_find_move(
                    args.move,
                    args.source,
                )
            elif cmd == "survivability":
                result = cmd_survivability(
                    args.defender,
                    args.attacker_stat,
                    args.category,
                    args.def_ov,
                    args.field_ov,
                )
            elif cmd == "filter-moves":
                result = cmd_filter_moves(
                    type_filters=args.type_filters or None,
                    category_filters=args.category_filters or None,
                    min_power=args.min_power,
                    max_power=args.max_power,
                )
            else:  # calc-raw
                result = cmd_calc_raw(
                    args.att,
                    args.move_json,
                    args.defender_json,
                    args.field,
                )
        except TypeError as e:
            print(f"Argument error for '{cmd}': {e}")
            return 1

        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    # Phase 1 commands: legacy positional-arg routing
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
