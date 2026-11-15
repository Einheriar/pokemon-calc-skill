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
    python query.py usage [--top N]         # Meta usage ranking (pokecamp.cc)
    python query.py usage <name>            # Pokemon's common moves/items/teammates
    python query.py teams                   # Recent tournament teams (top 12)
    python query.py teams <N|pokemon>       # Team detail / filter by pokemon
"""

import io
import json
import re
from models import Pokemon, Move, Field
import os
import sys
from pathlib import Path
from typing import Any

from normalize import get_suggestions, normalize_ja, normalize_name
from engine_enums import (
    NATURE_ZH_TO_EN,
    TYPE_EN_TO_ZH,
    TYPE_ZH_TO_EN,
    VALID_NATURES_EN,
    VALID_STATUS_EN,
    VALID_TYPES_EN,
    resolve_nature_en,
    resolve_tera_type_en,
    resolve_type_en,
)

import pokecamp_source as pcs
import regulations

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
_items_data: dict[str, Any] | None = None
_ja_index: dict[str, dict[str, Any]] | None = None
_champions_patches: dict[str, Any] | None = None
# Internal cumulative regulation cap (see _visible_form). None = newest
# regulation in data/regulation_manifest.json, i.e. show every form.
_regulation_cap: str | None = None


def set_regulation_cap(reg_id: str | None) -> str:
    """Set the cumulative regulation view for form/learnset visibility.

    This is an internal switch: it only hides forms (and their learnsets) that
    were introduced *after* the given regulation. It never affects damage
    calculation or legality. Returns the normalized effective cap.
    """
    global _regulation_cap
    _regulation_cap = regulations.normalize(reg_id) or None
    return _regulation_cap or regulations.current(DATA_DIR)


def get_regulation_cap() -> str:
    """Effective regulation cap (explicit value or the manifest's current)."""
    return _regulation_cap or regulations.current(DATA_DIR)


def _visible_form(form: dict[str, Any]) -> bool:
    """Whether a patch form is within the current (cumulative) regulation view.

    Forms without a regulation tag are always visible, so older patch files
    keep working unchanged.
    """
    reg = regulations.normalize(form.get("regulation"))
    if not reg:
        return True
    if _regulation_cap is None:
        return True
    return regulations.within(reg, _regulation_cap, DATA_DIR)


def _load_json(name: str) -> Any:
    path = DATA_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def load_data() -> None:
    global _pokemon_data, _moves_data, _abilities_data, _index_data, _type_chart, _items_data
    if _pokemon_data is not None:
        return
    _pokemon_data = _load_json("pokemon.json")
    _moves_data = _load_json("moves.json")
    _abilities_data = _load_json("abilities.json")
    _index_data = _load_json("name_index.json")
    _type_chart = _load_json("type_chart.json")
    _items_data = _load_json("items.json")
    # Merge Champions name_index patch
    patches = _load_champions_patches()
    if patches and "name_index" in patches:
        for category in ("pokemon", "moves"):
            if category in _index_data and category in patches["name_index"]:
                _index_data[category].update(patches["name_index"][category])


def _build_ja_index() -> dict[str, dict[str, Any]]:
    """Lazy ja -> entity mapping built at runtime from data files (phase3 Step 0 方案 b).

    不引入第三份名字数据源：pokemon 取 pokemon.json 的 name_ja -> 主键 stem，
    abilities 取 abilities.json 的 name_ja -> 规范中文名；items 复用 name_index
    items 段既有的日文键（resolve_item 原生支持）。键与查找输入两侧统一过
    normalize_ja 后精确匹配。ja 名撞车时值为 list（同名多实体），resolve 视为
    歧义 MISS，由 cmd 层走 error+候选路径，不静默择一。
    """
    global _ja_index
    if _ja_index is not None:
        return _ja_index
    ja: dict[str, dict[str, Any]] = {"pokemon": {}, "abilities": {}, "items": {}, "moves": {}}

    def put(section: str, name: str, target: Any) -> None:
        key = normalize_ja(name)
        if not key:
            return
        existing = ja[section].get(key)
        if existing is None:
            ja[section][key] = target
        elif isinstance(existing, list):
            if target not in existing:
                existing.append(target)
        elif existing != target:
            ja[section][key] = [existing, target]

    for stem, data in _pokemon_data.items():
        name_ja = data.get("name_ja")
        if name_ja:
            put("pokemon", name_ja, stem)
    for zh, data in _abilities_data.items():
        name_ja = data.get("name_ja")
        if name_ja:
            put("abilities", name_ja, zh)
    # 招式第二批（moves name_ja 经 phase2 Step 1 补完 + 交叉验证后接入）
    for stem, mv in _moves_data.items():
        name_ja = mv.get("name_ja")
        if name_ja:
            put("moves", name_ja, stem)
    _ja_index = ja
    return _ja_index


def _ja_lookup(section: str, name: str) -> Any | None:
    """Exact ja match after deterministic normalization; list values are ambiguous."""
    idx = _build_ja_index()[section]
    hit = idx.get(normalize_ja(name))
    if isinstance(hit, list):
        return None  # ambiguous ja name -> miss with candidates at cmd layer
    return hit


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
    load_errors = False
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
                    # Metadata keys (leading underscore) carry the schema version
                    # and are not data entries.
                    patches[key] = {k: v for k, v in data.items()
                                    if not str(k).startswith("_")}
                    patches.setdefault("schema_version", {}).setdefault(
                        key, data.get("_schema_version", 1))
            except json.JSONDecodeError as e:
                # Corrupt patch must be distinguishable from "no patch":
                # warn loudly and flag, never silently degrade the layer.
                print(f"warning: champions patch {filename} JSON 解析失败，已跳过: {e}",
                      file=sys.stderr)
                load_errors = True
            except OSError as e:
                print(f"warning: champions patch {filename} 读取失败，已跳过: {e}",
                      file=sys.stderr)
                load_errors = True
    if load_errors:
        patches["_load_error"] = True
    _champions_patches = patches
    return _champions_patches


def _champions_patch_load_error() -> bool:
    """True when any champions patch file existed but failed to parse/read."""
    return bool(_load_champions_patches().get("_load_error"))


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
        "form_name",
    }

    preset_config = {k: v for k, v in presets[preset_name].items() if k in _VALID_PK_FIELDS}
    # User override takes precedence over preset
    preset_config.update(override)
    return preset_config


# Fields allowed for auto-preset fallback (evs/nature/ivs only; ability only when
# the override is completely empty; item only via _AUTO_ITEM_WHITELIST).
# NOTE: form_name is deliberately NOT auto-filled — asking about 水箭龟 must stay
# base Blastoise, never silently become 超级水箭龟. A preset's form_name only
# applies when the user explicitly references that preset.
_AUTO_PRESET_FIELDS = {"evs", "nature", "ivs"}

# Pure damage-boosting items eligible for auto-preset fill. Judgment/trigger items
# (Sitrus Berry, Focus Sash, resist berries, Weakness Policy, ...) and non-damage
# items (Choice Scarf) are excluded on purpose: any auto-filled item is an
# assumption the answer must declare (calc reports it as attacker_auto_item /
# defender_auto_item).
_AUTO_ITEM_WHITELIST = {
    "Life Orb", "Choice Band", "Choice Specs",
    "Expert Belt", "Muscle Band", "Wise Glasses",
}

# Stat-investment inputs. When the user supplies ANY of these, the given values
# are treated as the complete EV plan: no preset fill (unspecified stats stay at
# 0 EV / neutral nature), and no auto_preset is reported.
_EV_SPEC_FIELDS = {"evs", "sps", "raw_stats", "stats"}


# Direction scoring thresholds
_DIRECTION_HIGH_EV = 200  # User input strong enough to infer a direction


def _infer_direction(evs: dict[str, int], nature: str | None = None) -> set[str]:
    """Infer build direction from partial EVs and nature.

    Returns a set of direction tags: physical, special, bulky, fast, mixed.
    """
    directions: set[str] = set()
    atk = evs.get("attack", 0)
    spa = evs.get("sp_attack", 0)
    hp = evs.get("hp", 0)
    defense = evs.get("defense", 0)
    spd = evs.get("sp_defense", 0)
    spe = evs.get("speed", 0)

    if spa >= _DIRECTION_HIGH_EV and spa >= atk:
        directions.add("special")
    if atk >= _DIRECTION_HIGH_EV and atk >= spa:
        directions.add("physical")
    if hp >= _DIRECTION_HIGH_EV or defense >= _DIRECTION_HIGH_EV or spd >= _DIRECTION_HIGH_EV:
        directions.add("bulky")
    if spe >= _DIRECTION_HIGH_EV:
        directions.add("fast")

    # Nature hints
    if nature:
        nature_lower = nature.lower()
        if nature_lower in ("modest", "timid", "mild", "quiet", "rash"):
            directions.add("special")
        elif nature_lower in ("adamant", "jolly", "naughty", "lonely", "brave"):
            directions.add("physical")
        if nature_lower in ("timid", "jolly", "naive", "hasty"):
            directions.add("fast")
        if nature_lower in ("bold", "impish", "calm", "careful", "sassy", "relaxed"):
            directions.add("bulky")

    if not directions:
        directions.add("balanced")
    return directions


def _preset_directions(evs: dict[str, int]) -> set[str]:
    """Infer preset direction from its EV spread."""
    directions: set[str] = set()
    atk = evs.get("attack", 0)
    spa = evs.get("sp_attack", 0)
    hp = evs.get("hp", 0)
    defense = evs.get("defense", 0)
    spd = evs.get("sp_defense", 0)
    spe = evs.get("speed", 0)

    # Output direction: whichever offensive stat is highest (and meaningfully invested)
    if spa > atk and spa >= 100:
        directions.add("special")
    elif atk > spa and atk >= 100:
        directions.add("physical")
    elif atk >= 100 and spa >= 100:
        directions.add("mixed")

    if hp >= 100 or defense >= 100 or spd >= 100:
        directions.add("bulky")
    if spe >= 100:
        directions.add("fast")
    if not directions:
        directions.add("balanced")
    return directions


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

    # Direction alignment: reward presets that match the user's build intent
    user_dirs = _infer_direction(user_evs, user_override.get("nature"))
    preset_dirs = _preset_directions(preset_evs)
    overlap = user_dirs & preset_dirs
    if "physical" in overlap or "special" in overlap or "mixed" in overlap:
        score += 15
    if "bulky" in overlap:
        score += 10
    if "fast" in overlap:
        score += 8

    return score


def _apply_auto_preset_to_override(override: dict[str, Any], pokemon_en: str) -> tuple[dict[str, Any], str | None, str | None]:
    """Auto-match best preset from setdex for the given pokemon.

    Preset priority tiers first: only presets at the highest ``priority`` value
    are candidates (ladder-meta presets carry priority 1; legacy sets default
    to 0). Within the tier the usual EV/direction scoring picks the winner.

    evs/nature/ivs are filled from the preset; item only when it is in
    _AUTO_ITEM_WHITELIST (pure damage boosters — reported via the returned
    auto_item so answers can declare the assumption). The preset's form_name is
    never auto-applied: the form the user asked about always wins. When the user
    provides no config at all (empty override), the matched preset's ability is
    also used so the default form ability does not silently override the
    intended competitive ability.

    If the user provides any stat-investment field (evs/sps/raw_stats/stats), the
    preset is skipped entirely: partial EV specs mean "exactly these investments",
    so unspecified stats stay at 0 EV and nature stays neutral.

    Returns (updated_override, matched_preset_name_or_None, auto_item_en_or_None).
    """
    # Skip if user already provided "preset" key (explicit preset takes precedence)
    if "preset" in override:
        return override, None, None

    # Partial stat specification = explicit build intent: never merge preset EVs
    # into it (e.g. "32 HP SP Incineroar" must stay 32 HP / 0 everywhere else).
    if any(k in _EV_SPEC_FIELDS for k in override):
        return override, None, None

    setdex = _load_setdex()
    if pokemon_en not in setdex:
        return override, None, None

    presets = setdex[pokemon_en]
    if not presets:
        return override, None, None

    # For empty overrides, default to the most invested preset (highest total EVs).
    # If the user has specified any build-related field, do not force the preset's ability.
    _BUILD_FIELDS = {"evs", "sps", "nature", "ivs", "ability", "ability_zh", "item",
                     "item_zh", "tera_type", "is_terastalize", "boosts", "status",
                     "level", "raw_stats", "stats", "current_hp", "max_hp"}
    is_empty_override = not any(k in _BUILD_FIELDS for k in override)

    # Priority tier: only presets at the highest priority compete (newer
    # ladder-meta sets outrank legacy sets regardless of direction score).
    top_priority = max(p.get("priority", 0) for p in presets.values())

    best_preset_name: str | None = None
    best_score = -1
    best_total_evs = -1
    for preset_name, preset_config in presets.items():
        if preset_config.get("priority", 0) != top_priority:
            continue
        score = _score_preset(preset_config, override)
        total_evs = sum(preset_config.get("evs", {}).values())
        # Prefer higher score; tie-break by total EVs for empty overrides, else first
        if score > best_score or (is_empty_override and score == best_score and total_evs > best_total_evs):
            best_score = score
            best_total_evs = total_evs
            best_preset_name = preset_name

    if best_preset_name is None:
        return override, None, None

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

    # When the user provided no config at all, also adopt the preset's ability so that
    # the default form ability does not replace the competitive intended ability.
    if is_empty_override and "ability" not in override and preset_config.get("ability"):
        override["ability"] = preset_config["ability"]

    # Item: auto-fill only whitelisted pure damage boosters; everything else
    # (recovery berries, sashes, conditional items) keeps the no-item baseline.
    auto_item: str | None = None
    preset_item = preset_config.get("item")
    if preset_item and "item" not in override and "item_zh" not in override \
            and preset_item in _AUTO_ITEM_WHITELIST:
        override["item"] = preset_item
        auto_item = preset_item

    return override, best_preset_name, auto_item


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


def _apply_champions_pokemon_patch(stem: str, data: dict[str, Any]) -> dict[str, Any]:
    """Apply Champions patch to a pokemon data entry if available."""
    patches = _load_champions_patches()
    if not patches or stem not in patches.get("pokemon", {}):
        return data
    patch = patches["pokemon"][stem]
    # Deep copy to avoid mutating original
    merged = json.loads(json.dumps(data))
    # Regulation tag per form, so the cumulative cap can also hide base-data
    # forms that the patch knows were introduced later (e.g. a "Z" Mega that
    # already exists in the reference data yet belongs to a newer regulation).
    patch_form_regulation = {
        f.get("name"): f.get("regulation")
        for f in patch.get("forms", []) if f.get("name")
    }
    # Merge forms BY NAME: the patch (built from champout) carries repo-standard
    # form names, so name matching is equivalent to the historical index-based
    # merge while staying correct even if form order ever changes between the
    # repo data and a future patch rebuild. Unmatched patch forms are appended.
    if "forms" in patch:
        orig_forms = merged.get("forms", [])
        forms_by_name: dict[str, int] = {}
        for idx, f in enumerate(orig_forms):
            fname = f.get("name", "")
            if fname and fname not in forms_by_name:
                forms_by_name[fname] = idx
        for raw_pform in patch["forms"]:
            pform = json.loads(json.dumps(raw_pform))  # deep copy
            # Skip forms introduced after the cumulative regulation cap (the
            # internal --regulation view). Untagged forms are always visible.
            if not _visible_form(pform):
                continue
            # Normalize abilities from string list to object list
            abilities = pform.get("abilities")
            if isinstance(abilities, list) and abilities and isinstance(abilities[0], str):
                pform["abilities"] = [{"name": a} for a in abilities]
            idx = forms_by_name.get(pform.get("name", ""))
            if idx is not None:
                orig_forms[idx].update(pform)
            else:
                orig_forms.append(pform)
        # Drop base-data forms the patch tags as outside the cap.
        if _regulation_cap is not None:
            kept = []
            for f in orig_forms:
                reg = regulations.normalize(patch_form_regulation.get(f.get("name", "")))
                if reg and not regulations.within(reg, _regulation_cap, DATA_DIR):
                    continue
                kept.append(f)
            orig_forms = kept
        merged["forms"] = orig_forms
    # Merge stats BY LABEL NAME (see forms note above). The reference stats list
    # is generation-labelled ('一般', '第六世代起', ...), so most Champions
    # entries are appended rather than updated in place; the consumer
    # (_make_pokemon_from_data) matches stats by form name first, so appended
    # form-labelled entries take precedence over the generation ones.
    if "stats" in patch:
        orig_stats = merged.get("stats", [])
        stats_by_label: dict[str, int] = {}
        for idx, s in enumerate(orig_stats):
            lbl = s.get("form", "")
            if lbl and lbl not in stats_by_label:
                stats_by_label[lbl] = idx
        for raw_pstat in patch["stats"]:
            pstat = json.loads(json.dumps(raw_pstat))  # deep copy
            if not _visible_form(pstat):
                continue
            idx = stats_by_label.get(pstat.get("form", ""))
            if idx is not None:
                orig_stats[idx].update(pstat)
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

    # Halfwidth/English form suffix: "Mega Charizard X" ends with X — match
    # forms whose (Chinese) name carries the fullwidth letter Ｘ/Ｙ/Ｚ.
    suffix_m = re.search(r"([XYZxyz])$", name.strip())
    if suffix_m:
        suffix_full = chr(ord(suffix_m.group(1).upper()) + 0xFEE0)
        for idx, form in enumerate(forms):
            form_name = form.get("name", "")
            if form_name.endswith(suffix_full):
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

    # English form-suffix fallback: "Charizard X" -> "Mega Charizard X".
    # Only succeeds when the constructed name is a real form index key, so
    # there is no false-positive risk for names that merely end in X/Y.
    if not stem:
        m = re.match(r"^(mega\s+)?(.+?)\s+([xy])$", name.strip(), re.IGNORECASE)
        if m:
            base, suffix = m.group(2).strip(), m.group(3).upper()
            candidates = [f"{base} {suffix}"]
            if not m.group(1):
                candidates.insert(0, f"Mega {base} {suffix}")
            forms_lower = {k.lower(): k for k in _index_data.get("pokemon_forms", {})}
            for cand in candidates:
                matched_key = forms_lower.get(cand.lower())
                if matched_key:
                    stem = _index_data["pokemon_forms"].get(matched_key)
                    # Re-resolve against the canonical key so _find_form_index
                    # picks the right form entry.
                    name = matched_key
                    break

    # Japanese input (phase3 first batch): species-level name_ja -> stem.
    # Ambiguous ja names (list values) are treated as a miss so the caller
    # gets the error+suggestions path instead of a silent pick.
    if not stem:
        ja_stem = _ja_lookup("pokemon", name)
        if ja_stem:
            stem = ja_stem

    # NOTE: bare fullwidth suffix without the species prefix ("喷火龙Ｙ") is
    # deliberately NOT resolved — the canonical form name is "超级喷火龙Ｙ",
    # and silently guessing a Mega form from a name the caller never wrote
    # breaks explicitness. The not-found + suggestions path lets the caller
    # self-correct.

    if not stem:
        return None

    data = _pokemon_data.get(stem)
    if not data:
        return None

    data = _apply_champions_pokemon_patch(stem, data)
    form_index = _find_form_index(name, data)
    return stem, data, form_index


def resolve_move(name: str) -> tuple[str, Any] | None:
    """Return (stem, data) for a move by zh, en, or ja name."""
    load_data()
    name = normalize_name(name, "moves")
    stem = _index_data["moves"].get(name)
    if not stem:
        for k, v in _index_data["moves"].items():
            if k.lower() == name.lower():
                stem = v
                break
    if not stem:
        ja_zh = _ja_lookup("moves", name)
        if ja_zh:
            stem = _index_data["moves"].get(ja_zh) or ja_zh
    if not stem:
        return None
    data = _moves_data.get(stem)
    if data is None:
        return None
    # moves.json (and the champions moves patch) are keyed by the Chinese
    # name, which IS the stem, so a second patch lookup by name_zh could
    # never hit — removed (round 2 audit D8).
    return stem, _apply_champions_move_patch(stem, data)


def resolve_ability(name: str) -> tuple[str, Any] | None:
    """Return (stem, data) for an ability by zh, en, or ja name."""
    load_data()
    name = normalize_name(name, "abilities")
    stem = _index_data["abilities"].get(name)
    if not stem:
        for k, v in _index_data["abilities"].items():
            if k.lower() == name.lower():
                stem = v
                break
    if not stem:
        ja_zh = _ja_lookup("abilities", name)
        if ja_zh:
            stem = _index_data["abilities"].get(ja_zh) or ja_zh
    if not stem:
        return None
    return stem, _abilities_data.get(stem)


# ---------------------------------------------------------------------------
# Item effects lookup
# ---------------------------------------------------------------------------

# Item effect descriptions live in data/items.json (generated by
# cache/build_item_index.py). cmd_item() reads them from the data layer.


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
    if not en:
        # ja retry: normalize both sides (halfwidth digits/middle dot/prolonged
        # mark) and rescan — items index ja keys come from upstream as-is.
        ja_name = normalize_ja(name)
        if ja_name != name:
            for k, v in items.items():
                if normalize_ja(k) == ja_name:
                    en = v
                    break
    return en


# Item-name inputs the items index cannot resolve (moved out of the engine
# by the engine-English refactor so the engine stays English-only).
_ITEM_INPUT_FALLBACK: dict[str, str] = {
    "无": "",  # explicit "no item"
    "红玉": "Red Orb", "蓝玉": "Blue Orb",
    "银色粉": "Silver Powder",
    # berry aliases absent from the items index
    "烛龙果": "Haban Berry", "罗望果": "Colbur Berry",
    "投鲜果": "Chilan Berry", "穹犀果": "Babiri Berry",
    # figy-family zh names absent from the items index (pairing per the
    # legacy ko_chance recovery table)
    "岳母果": "Aguav Berry", "爸爸果": "Iapapa Berry", "芒果": "Mago Berry",
}


def _normalize_item_input(name: str) -> str:
    """Resolve an item input (zh/ja/en/alias) to its canonical English name.

    Unknown names pass through unchanged; returns "" for explicit no-item
    inputs (e.g. "无").
    """
    if not name:
        return ""
    name = str(name)
    en = resolve_item(name)
    if en:
        return en
    return _ITEM_INPUT_FALLBACK.get(name, name)


def _resolve_item_to_zh(en_name: str) -> str | None:
    """Resolve an English item name to its Chinese canonical name if available."""
    if not en_name:
        return None
    load_data()
    items = _index_data.get("items", {})
    for zh, en in items.items():
        if en == en_name:
            return zh
    return None


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
    # Effect text comes from the data layer (data/items.json), keyed by the
    # canonical English name resolve_item() returns. The former zh-key
    # fallback in the inline effect table is provably dead: every zh key had
    # an en twin with an identical tuple (asserted by cache/test_items_data.py).
    effect_info = _items_data.get(en) if _items_data else None
    if effect_info:
        result["effect"] = effect_info.get("effect", "")
        result["category"] = effect_info.get("category", "")
    else:
        result["effect"] = ""
        result["category"] = ""
    return result


def _get_champions_learnset(stem: str, form_name: str | None = None) -> list[str]:
    """Get the Champions learnset for a stem (optionally for one form).

    Schema v2 stores learnsets nested per form, because regional/Mega forms
    learn different moves. Schema v1 (flat list) is still accepted: it has no
    form dimension, so every form of the species shares the one list.

    Form-key miss falls back to the species base-form key (the display name,
    e.g. '花叶蒂' under stem '0670-花叶蒂') before giving up.
    """
    patches = _load_champions_patches()
    entry = patches.get("learnset", {}).get(stem) if patches else None
    if not entry:
        return []
    if isinstance(entry, list):
        return entry  # schema v1: form-blind
    if form_name and form_name in entry:
        return entry[form_name]
    if form_name is None:
        # No form requested: fall back to the species' base form (first key),
        # which is the entry the pokemon patch lists first.
        first = next(iter(entry.values()), [])
        return first
    # Form key miss: try the species base-form key before giving up.
    base_key = stem.split("-", 1)[-1]
    if base_key and base_key in entry:
        return entry[base_key]
    return []


def _champions_learnset_coverage(stem: str, form_name: str | None) -> dict[str, Any] | None:
    """Report Champions learnset patch coverage for one species/form.

    Returns None when the species has no patch at all (plain Gen9 species);
    otherwise {"form_covered": bool, "available_forms": [...]}.
    """
    patches = _load_champions_patches()
    entry = patches.get("learnset", {}).get(stem) if patches else None
    if not entry:
        return None
    if isinstance(entry, list):
        return {"form_covered": True, "available_forms": []}
    available = list(entry.keys())
    base_key = stem.split("-", 1)[-1]
    covered = form_name is None or form_name in available or base_key in available
    return {"form_covered": covered, "available_forms": available}


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
    stem, data, form_idx = resolved
    forms = data.get("forms", [])
    selected_form = forms[form_idx] if forms and form_idx < len(forms) else {}
    form_name = selected_form.get("name", "")
    is_mega = form_name.startswith("超级") or form_name.startswith("原始")
    data_source = data.get("_data_source", "gen9")
    is_unobtainable = is_mega and data_source == "gen9"
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
        "_data_source": data_source,
        "is_unobtainable": is_unobtainable,
    }
    if _champions_patch_load_error():
        result["_patch_load_error"] = True
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
    stem, data, form_idx = resolved
    forms = data.get("forms", [])
    form_name = forms[form_idx].get("name") if forms and form_idx < len(forms) else None
    champions_moves = _get_champions_learnset(stem, form_name)
    if champions_moves:
        # Champions patch provides the move list for the requested form.
        formatted = [{"name": m} for m in champions_moves]
        return {
            "name_zh": data.get("name_zh"),
            "name_en": data.get("name_en"),
            "learnable_moves": [{"form": form_name or "", "data": formatted}],
            "machine_moves": [],
            "egg_moves": [],
            "tutor_moves": [],
            "_data_source": "champions",
        }
    result: dict[str, Any] = {
        "name_zh": data.get("name_zh"),
        "name_en": data.get("name_en"),
        "learnable_moves": data.get("learnable_moves", []),
        "machine_moves": data.get("machine_moves", []),
        "egg_moves": data.get("egg_moves", []),
        "tutor_moves": data.get("tutor_moves", []),
    }
    # Species is covered by a Champions patch but the requested form is not:
    # say so explicitly instead of silently falling back to Gen9.
    coverage = _champions_learnset_coverage(stem, form_name)
    if coverage and not coverage["form_covered"]:
        result["_data_source"] = "gen9"
        result["_champions_patch_note"] = (
            f"Champions 补丁存在但未覆盖形态「{form_name}」"
            f"（可用形态: {', '.join(coverage['available_forms'])}），已回落 Gen9 学习面"
        )
    if _champions_patch_load_error():
        result["_patch_load_error"] = True
    return result


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
    """Yield (move_dict, source_category, form_name) for all moves.

    If a Champions learnset patch exists for stem, yield from it per form
    (schema v2 nested; schema v1 flat yields form_name=None). Otherwise fall
    back to the reference data, whose entries are already form-labelled.
    """
    patches = _load_champions_patches()
    entry = patches.get("learnset", {}).get(stem) if patches else None
    if entry:
        if isinstance(entry, list):
            for move_name in entry:
                yield {"name": move_name}, "learnable_moves", None
            return
        for form_name, moves in entry.items():
            for move_name in moves:
                yield {"name": move_name}, "learnable_moves", form_name
        return
    for category in ("learnable_moves", "machine_moves", "egg_moves", "tutor_moves"):
        for form_block in pdata.get(category, []):
            if isinstance(form_block, dict) and "data" in form_block:
                form_label = form_block.get("form") or None
                for move in form_block["data"]:
                    if isinstance(move, dict):
                        yield move, category, form_label


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

        for move, category, form_name in _iter_moves(pdata, stem=stem):
            if move.get("name") == move_zh:
                forms = merged_pdata.get("forms", [{}])
                # Report the types of the form that actually learns the move,
                # not always the base form's.
                matched_types = []
                for f in forms:
                    if form_name and f.get("name") == form_name:
                        matched_types = f.get("types", [])
                        break
                if not matched_types and forms:
                    matched_types = forms[0].get("types", [])
                result.append({
                    "name_zh": pdata.get("name_zh"),
                    "name_en": pdata.get("name_en"),
                    "pokedex_id": pdata.get("pokedex_id"),
                    "form_name": form_name or "",
                    # Champions learnsets carry no level info (round 2 audit D11)
                    "method": "Champions" if data_source == "champions" else _get_method_name(move, category),
                    "types": matched_types,
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


def cmd_filter_pokemon(
    type_filters: list[str] | None = None,
    min_stats: dict[str, int] | None = None,
    max_stats: dict[str, int] | None = None,
    ability_filters: list[str] | None = None,
) -> dict[str, Any]:
    """Filter pokemon by type, base stats, and/or ability.

    Multiple filters within the same dimension use OR logic;
    different dimensions use AND logic.

    Args:
        type_filters: List of type names (zh or en). Pokemon matching ANY
                      listed type across any of their forms are included.
        min_stats: Dict of stat -> minimum base stat value (inclusive).
                   e.g. {"hp": 80, "attack": 100}
        max_stats: Dict of stat -> maximum base stat value (inclusive).
        ability_filters: List of ability names (zh or en). Pokemon matching ANY
                         listed ability across any of their forms are included.
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

    # Normalize ability names to Chinese canonical form
    normalized_abilities: set[str] = set()
    if ability_filters:
        for ability in ability_filters:
            zh = _resolve_ability_to_zh(ability)
            if not zh:
                zh = _resolve_ability_to_en(ability)
            if zh:
                normalized_abilities.add(zh)
            else:
                return {"error": f"Ability '{ability}' not found."}

    if min_stats is None:
        min_stats = {}
    if max_stats is None:
        max_stats = {}

    valid_stats = {"hp", "attack", "defense", "sp_attack", "sp_defense", "speed"}
    for stat in {**min_stats, **max_stats}.keys():
        if stat not in valid_stats:
            return {"error": f"Invalid stat '{stat}'. Valid stats: {sorted(valid_stats)}"}

    results: list[dict[str, Any]] = []

    for stem, data in _pokemon_data.items():
        # Apply Champions patch if available
        pdata = _apply_champions_pokemon_patch(stem, data)
        if not pdata:
            continue

        forms = pdata.get("forms", [{}])
        # Base stats are taken from the first matching stats entry (usually the default form)
        stats_list = pdata.get("stats", [])
        base_stats = stats_list[0].get("data", {}) if stats_list else {}

        # Collect all types and abilities across all forms
        all_types: set[str] = set()
        all_abilities: set[str] = set()
        for form in forms:
            form_types = form.get("types", [])
            all_types.update(form_types)
            for ability in form.get("abilities", []):
                if isinstance(ability, str):
                    all_abilities.add(ability)
                elif isinstance(ability, dict):
                    all_abilities.add(ability.get("name", ""))

        # Type filter (OR within dimension): any form must contain all filter types
        if normalized_types:
            if not all(ft in all_types for ft in normalized_types):
                continue

        # Ability filter (OR within dimension): any form must contain at least one filter ability
        if normalized_abilities:
            if not all_abilities & normalized_abilities:
                continue

        # Base stat filters (AND across dimensions, each stat range inclusive)
        stat_ok = True
        for stat, val in (min_stats or {}).items():
            if int(base_stats.get(stat, 0)) < val:
                stat_ok = False
                break
        if not stat_ok:
            continue
        for stat, val in (max_stats or {}).items():
            if int(base_stats.get(stat, 0)) > val:
                stat_ok = False
                break
        if not stat_ok:
            continue

        # De-duplicate abilities and strip empties
        abilities = sorted({a for a in all_abilities if a})

        results.append({
            "name_zh": pdata.get("name_zh", ""),
            "name_en": pdata.get("name_en", ""),
            "pokedex_id": pdata.get("pokedex_id"),
            "types": sorted(all_types),
            "base_stats": {k: int(v) for k, v in base_stats.items()},
            "abilities": abilities,
        })

    # Sort by pokedex_id, then by Chinese name
    results.sort(key=lambda x: (x.get("pokedex_id") or 0, x.get("name_zh", "")))

    return {
        "count": len(results),
        "filters": {
            "types": sorted(normalized_types),
            "min_stats": min_stats or {},
            "max_stats": max_stats or {},
            "abilities": sorted(normalized_abilities),
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


def _apply_setup_moves(attacker, defender, field, setup_moves: list[str]) -> list[str]:
    """Apply modeled setup effects and return warnings for unknown moves.

    Recognized moves without structured ``stat_changes`` remain intentional
    no-ops. Boosts accumulate across repeated setup moves but always obey the
    battle-stage range of -6..+6. Effective stats are re-derived afterwards.
    """
    from damage import get_modified_stat

    warnings: list[str] = []

    def _sync_stats(pk) -> None:
        if pk.raw_stats:
            pk.stats = {k: get_modified_stat(v, pk.boosts.get(k, 0))
                        for k, v in pk.raw_stats.items()}

    for move_name in setup_moves:
        move_data = _moves_data.get(move_name)
        if not move_data:
            resolved = resolve_move(move_name)
            move_data = resolved[1] if resolved else None
        if not move_data:
            warnings.append(f"未知 setup move，已忽略：{move_name}")
            continue
        stat_changes = move_data.get("stat_changes")
        if not stat_changes:
            continue

        # Apply self boosts
        if "self" in stat_changes:
            for stat, change in stat_changes["self"].items():
                attacker.boosts[stat] = max(-6, min(6, attacker.boosts.get(stat, 0) + change))
            _sync_stats(attacker)

        # Apply weather
        if "weather" in stat_changes:
            field.weather = stat_changes["weather"]

        # Apply terrain
        if "terrain" in stat_changes:
            field.terrain = stat_changes["terrain"]

        # Apply opponent debuffs
        if "opponent" in stat_changes:
            for stat, change in stat_changes["opponent"].items():
                defender.boosts[stat] = max(-6, min(6, defender.boosts.get(stat, 0) + change))
            _sync_stats(defender)

        # Apply heal
        if "heal" in stat_changes:
            heal_target = stat_changes["heal"].get("target", "self")
            ratio = stat_changes["heal"].get("ratio", 0)
            if heal_target == "self" and attacker.max_hp > 0:
                heal_amount = int(attacker.max_hp * ratio)
                attacker.current_hp = min(attacker.max_hp, attacker.current_hp + heal_amount)

    return warnings


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


def _parse_weight(raw: Any) -> float:
    """Parse a weight value from pokemon.json into a float kg value.

    The data layer stores weight as strings like "460.0kg"; G-Max forms use
    "???.?kg". Strip the "kg" suffix and convert to float, returning 0.0 for
    any non-numeric or missing value so the engine always sees a number.
    """
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        num = raw.removesuffix("kg").strip()
        try:
            return float(num)
        except ValueError:
            return 0.0
    return 0.0


def _sp_to_ev(sp: int) -> int:
    """Convert Champions Stat Points to Gen9 EVs (Lv.50, IV=31).

    The first stat point costs only 4 EVs; each further point costs 8 EVs,
    so EV = 8*SP - 4. SP=0 maps to 0 EV. SP=32 maps to 252 EV (the Gen9 cap).
    """
    sp = int(sp)
    if sp <= 0:
        return 0
    return 8 * sp - 4


def _ev_to_sp(ev: int) -> int:
    """Convert Gen9 EVs to Champions Stat Points for display (Lv.50, IV=31).

    Inverse of _sp_to_ev: SP = (EV + 4) // 8. 252 EV -> 32 SP, 248 EV -> 31 SP,
    4 EV -> 1 SP. Exact at IV=31; IV parity edge cases may differ by one.
    """
    ev = int(ev)
    if ev <= 0:
        return 0
    return (ev + 4) // 8


def _evs_to_sps(evs: dict[str, int]) -> dict[str, int]:
    """Convert an EV dict to an SP dict for display (does not mutate input)."""
    return {k: _ev_to_sp(v) for k, v in evs.items()}


def _sp_approx_keys(evs: dict[str, int]) -> list[str]:
    """Stats whose EV value is not exactly representable in SP (8-EV grid).

    SP display rounds EVs up to the next point (EV = 8*SP - 4), so values
    off-grid (e.g. 249-251 EV) lose up to 7 EV when a reader converts the
    displayed SP back. Callers surface these keys as an "sp_approx" marker.
    """
    return [k for k, v in evs.items() if isinstance(v, int) and v > 0 and (v + 4) % 8 != 0]


_ENGINE_FORM_NAMES = {
    ("Zacian", "剑之王"): "Zacian-Crowned",
    ("Zamazenta", "盾之王"): "Zamazenta-Crowned",
    ("Dialga", "起源形态"): "Dialga-Origin",
    ("Palkia", "起源形态"): "Palkia-Origin",
    ("Giratina", "起源形态"): "Giratina-Origin",
}
_ENGINE_FORM_PREFIXES = {
    "Alolan": "Alola",
    "Galarian": "Galar",
    "Hisuian": "Hisui",
    "Paldean": "Paldea",
    "Mega": "Mega",
    "Primal": "Primal",
    "Gigantamax": "Gmax",
}


def _engine_pokemon_name(species_en: str, form: dict[str, Any]) -> str:
    """Translate data-layer display forms to the engine's canonical form IDs.

    The data uses names such as ``Alolan Marowak`` while the engine compares
    stable IDs such as ``Marowak-Alola``. Keep species-scoped effects scoped to
    the species by falling back to ``species_en`` for cosmetic/unknown forms.
    """
    special = _ENGINE_FORM_NAMES.get((species_en, form.get("name", "")))
    if special:
        return special
    form_en = form.get("name_en") or species_en
    if not species_en or form_en == species_en:
        return species_en
    for prefix, suffix in _ENGINE_FORM_PREFIXES.items():
        marker = f"{prefix} "
        if not form_en.startswith(marker):
            continue
        remainder = form_en[len(marker):]
        if remainder == species_en:
            return f"{species_en}-{suffix}"
        if prefix == "Mega" and remainder in (f"{species_en} X", f"{species_en} Y", f"{species_en} Z"):
            return f"{species_en}-Mega-{remainder[-1]}"
        return species_en
    match = re.fullmatch(re.escape(species_en) + r" \(([^()]+)\)", form_en)
    if match:
        return f"{species_en}-{match.group(1)}"
    return species_en


def _species_can_evolve(data: dict[str, Any], form: dict[str, Any] | None = None) -> bool:
    """Infer whether the selected form has an outgoing evolution edge."""
    species_zh = data.get("name_zh", "")
    species_en = data.get("name_en", "")
    form = form or {}
    forms = data.get("forms")
    has_distinct_form_records = isinstance(forms, list) and len(forms) > 1
    form_zh = form.get("name", "")
    form_en = form.get("name_en", "")

    def matches_source_form(source_form_name: str | None) -> bool:
        if not source_form_name:
            # The source data does not constrain an omitted form_name. Preserve
            # its species-wide evolution edge instead of guessing special-form
            # exceptions that are not represented in the evolution chain.
            return True
        if source_form_name == form_zh:
            return True
        # Evolution data uses regional labels such as "洗翠的样子", while the
        # Pokémon records use full labels such as "洗翠狃拉" or "洗翠卡蒂狗".
        if source_form_name.endswith("的样子"):
            region_prefix = source_form_name[:-3]
            if region_prefix and form_zh.startswith(region_prefix):
                return True
        # Some datasets expose authenticity forms only in the evolution chain,
        # while the Pokémon record still has one undifferentiated form entry.
        if not has_distinct_form_records and (form_zh == species_zh or form_en == species_en):
            return True
        return False

    for chain in data.get("evolution_chains", []):
        if not isinstance(chain, list):
            continue
        for index, node in enumerate(chain):
            if not isinstance(node, dict) or node.get("from") != species_zh or index == 0:
                continue
            source = chain[index - 1]
            if (isinstance(source, dict) and source.get("name") == species_zh
                    and matches_source_form(source.get("form_name"))):
                return True
    return False


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
    default_item_zh = ""
    if is_mega:
        default_item_zh = _derive_mega_stone(form_name)
        default_item = resolve_item(default_item_zh) or default_item_zh

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
        "name_en": _engine_pokemon_name(data.get("name_en", ""), form),
        "can_evolve": _species_can_evolve(data, form),
        "level": 50,
        "base_stats": base_stats,
        "types": types,
        "ability": ability,          # English (engine layer)
        "ability_zh": ability_zh,    # Chinese (display layer)
        "item": default_item,        # English canonical (engine layer)
        "item_zh": default_item_zh,  # Chinese/display name (display layer)
        "nature": "勤奋",
        "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
        "boosts": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
        "status": None,
        "is_terastalize": False,
        "tera_type": None,
        "is_dynamax": False,
        # Populate weight from data so weight-based moves (Low Kick, Grass Knot,
        # Heavy Slam, Heat Crash) work out of the box. Data layer stores weight
        # as strings like "460.0kg"; G-Max forms use "???.?kg". Strip the unit
        # and fall back to 0.0 for non-numeric values.
        "weight": _parse_weight(form.get("weight")),
        "gender": _resolve_gender(form),
        "_data_source": data.get("_data_source", "gen9"),
        "is_unobtainable": is_mega and data.get("_data_source", "gen9") == "gen9",
        "is_mega": is_mega,
    }
    if overrides:
        # Structural validation for dict-typed fields: fail loudly (main()
        # converts to {"error": ...}) instead of AttributeError deep inside.
        for _k in ("evs", "ivs", "raw_stats", "stats", "boosts", "sps"):
            if _k in overrides and not isinstance(overrides[_k], dict):
                raise ValueError(
                    f"override 字段 {_k} 必须是 JSON 对象，收到 {type(overrides[_k]).__name__}"
                )
        pk.update(overrides)
    sp_warnings: list[str] = []
    # Merge SP (Stat Points) override into EVs. The engine stores EVs (keeping
    # full 4-EV granularity); `sps` is only an input/view layer. sps takes
    # precedence over evs for the same stat key when both are supplied.
    if overrides and isinstance(overrides.get("sps"), dict):
        base_evs = dict(pk.get("evs", {}))
        for stat, sp_val in overrides["sps"].items():
            try:
                sp_int = int(sp_val)
            except (TypeError, ValueError):
                sp_int = 0
                sp_warnings.append(f"{stat} SP={sp_val!r} 非整数，已按 0 处理")
            if sp_int > 32:
                sp_warnings.append(f"{stat} SP={sp_int} 超出 Champions 上限 32")
            elif sp_int < 0:
                sp_warnings.append(f"{stat} SP={sp_int} 为负数")
            base_evs[stat] = _sp_to_ev(sp_int)
        pk["evs"] = base_evs
    # Post-override: ensure ability is in English for the damage engine
    overridden_ability = pk.get("ability", "")
    pk["ability"] = _resolve_ability_to_en(overridden_ability)
    # Sync ability_zh with the final ability
    if overrides and "ability" in overrides:
        pk["ability_zh"] = _resolve_ability_to_zh(overridden_ability) or pk.get("ability_zh", "")
    # Post-override: ensure item is canonical English for the damage engine
    # while preserving the original display name (usually Chinese) for UI output
    overridden_item = pk.get("item", "")
    overridden_item_zh = pk.get("item_zh", "")
    if overridden_item:
        resolved_item = _normalize_item_input(overridden_item)
        if resolved_item:
            pk["item"] = resolved_item
            # If the user explicitly passed an item override, keep that original
            # text as the display name. Otherwise (Mega default item), prefer the
            # stored Chinese display name.
            if overrides and "item" in overrides:
                pk["item_zh"] = overridden_item
            else:
                pk["item_zh"] = overridden_item_zh or _resolve_item_to_zh(resolved_item) or overridden_item
        elif overridden_item in _ITEM_INPUT_FALLBACK:
            # Explicit no-item inputs (e.g. "无") normalize to the empty item.
            pk["item"] = ""
            if overrides and "item" in overrides:
                pk["item_zh"] = overridden_item
    # Filter out fields not supported by the Pokemon dataclass.
    # _data_source and is_unobtainable are kept so callers (cmd_calc etc.) can
    # report provenance and availability; they are popped before Pokemon construction.
    _VALID_PK_FIELDS = {
        "name", "name_en", "level", "base_stats", "evs", "ivs",
        "nature", "ability", "ability_zh", "item", "item_zh", "types", "tera_type",
        "is_terastalize", "boosts", "current_hp", "max_hp",
        "status", "weight", "is_dynamax", "can_evolve",
        "ability_on", "fainted_allies",
        "gender", "is_mega",
        "raw_stats", "stats",
        "_data_source", "is_unobtainable",
    }
    pk = {k: v for k, v in pk.items() if k in _VALID_PK_FIELDS}
    # Stash the SP display view under a single meta key so callers can pop it
    # before Pokemon(**pk); evs themselves stay as raw EVs (no flooring).
    # Keys whose EV value cannot round-trip through SP carry an "approx" list.
    sp_meta: dict[str, Any] = {
        "sps": _evs_to_sps(pk.get("evs", {})),
        "approx": _sp_approx_keys(pk.get("evs", {})),
    }
    if sp_warnings:
        sp_meta["warnings"] = sp_warnings
    pk["_sp_meta"] = sp_meta
    return pk


def _finalize_calc_pokemon(pk, overrides: dict[str, Any] | None) -> None:
    """Normalize a Pokemon built by _make_pokemon_from_data before a calc.

    Round 2 audit fixes (E3/E8):
    - raw_stats-only inputs left ``stats`` empty, so the engine's boosted-stat
      path read 0 (damage 1-1); always derive stats from raw_stats + boosts.
    - compute_raw_stats unconditionally overwrites max_hp, silently discarding
      an explicit override; re-apply user max_hp/current_hp AFTER derivation.
    """
    from damage import compute_raw_stats, get_modified_stat

    overrides = overrides or {}
    # stats-only input: treat as raw (same semantics as calc-raw)
    if pk.stats and not pk.raw_stats:
        pk.raw_stats = dict(pk.stats)
    if not pk.raw_stats:
        compute_raw_stats(pk)
    pk.stats = {k: get_modified_stat(v, pk.boosts.get(k, 0))
                for k, v in pk.raw_stats.items()}
    if "max_hp" in overrides:
        pk.max_hp = overrides["max_hp"]
    elif pk.max_hp == 0:
        pk.max_hp = pk.raw_stats.get("hp", pk.stats.get("hp", 0))
    if "current_hp" in overrides:
        pk.current_hp = overrides["current_hp"]
    elif pk.current_hp == 0:
        pk.current_hp = pk.max_hp


# Move field normalization constants (module-level for reuse).
_MOVE_CATEGORY_ZH_TO_EN: dict[str, str] = {
    "物理": "Physical",
    "特殊": "Special",
    "变化": "Status",
}
# English → Chinese type mapping (display layer; the engine canonicalizes
# zh/en type inputs at its entry). Single source: engine_enums.TYPE_EN_TO_ZH.
_MOVE_TYPE_EN_TO_ZH: dict[str, str] = {**TYPE_EN_TO_ZH, "Stellar": "星晶"}


def _normalize_move_fields(move: dict[str, Any]) -> None:
    """Normalize move category and English punctuation for the damage engine.

    Mutates the dict in place: Chinese category names are converted to
    English. Move type is NOT converted here — the engine normalizes both
    zh and en type inputs at its entry (engine-English refactor).
    """
    if "category" in move:
        move["category"] = _MOVE_CATEGORY_ZH_TO_EN.get(move["category"], move["category"])
    if isinstance(move.get("name"), str):
        move["name"] = move["name"].replace("’", "'")


# Behavior-only fields that cmd_calc accepts in move_override (AGENTS.md
# invariant: move_override must never modify base_power/type/category —
# use the calc-raw command for raw parameter input instead).
_MOVE_OVERRIDE_WHITELIST = frozenset({"is_crit", "hits", "fainted_allies", "times_affected"})
_MOVE_OVERRIDE_HITS_MAX = 10


def _make_move_from_data(data: dict[str, Any], overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a Move dict suitable for damage.py from move data."""
    power_str = str(data.get("power", "0"))
    try:
        power = int(power_str)
    except ValueError:
        power = 0
    # Parse hits: can be int or string like "multi"
    hits_raw = data.get("hits", 1)
    if hits_raw == "multi":
        # 2-5 hit variable moves: approximate with the expected count (3).
        # cmd_calc surfaces a warning when the data layer says "multi".
        hits = 3
    else:
        try:
            hits = int(hits_raw)
        except (ValueError, TypeError):
            hits = 1
    # Accuracy comes from the data layer ("100", "90", or "—" for
    # unmissable/NA) — fall back to the raw string rather than a fake 100.
    acc_raw = data.get("accuracy", 100)
    try:
        accuracy: Any = int(acc_raw)
    except (TypeError, ValueError):
        accuracy = acc_raw
    move = {
        "name": data.get("name_en", ""),
        "name_zh": data.get("name_zh", ""),
        "base_power": power,
        "type": data.get("type", "一般"),
        "category": data.get("category", ""),
        "accuracy": accuracy,
        "hits": hits,
        "is_crit": data.get("always_crit", False),
        "makes_contact": data.get("makes_contact", False),
        "has_recoil": data.get("has_recoil", False),
        "has_secondary_effect": data.get("has_secondary_effect", False),
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
        "ignores_defense_boosts": data.get(
            "ignores_defense_boosts",
            data.get("name_en") in ("Sacred Sword", "Chip Away", "Darkest Lariat"),
        ),
        "deals_physical_damage": data.get("deals_physical_damage", False),
        "fainted_allies": 0,
    }
    _normalize_move_fields(move)
    if overrides:
        move.update(overrides)
        _normalize_move_fields(move)
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

    overrides: list[dict[str, Any]] = []
    for index, label in enumerate(("att_override", "def_override", "field_override")):
        raw = extra_args[index] if len(extra_args) > index else None
        parsed, parse_error = _parse_json_object(raw, label)
        if parse_error is not None:
            return parse_error
        overrides.append(parsed or {})
    att_override, def_override, field_override = overrides

    for _side, _ov in (("attacker", att_override), ("defender", def_override)):
        _enum_err = _validate_override_enums(_side, _ov)
        if _enum_err is not None:
            return _enum_err

    att_dict = _make_pokemon_from_data(att_data, att_override, form_index=att_form_idx)
    def_dict = _make_pokemon_from_data(def_data, def_override, form_index=def_form_idx)
    move_dict = _make_move_from_data(move_data)

    # Remove extra metadata before passing to model constructors
    att_dict.pop("_data_source", None)
    att_dict.pop("is_unobtainable", None)
    att_dict.pop("is_mega", None)
    att_dict.pop("_sp_meta", None)
    def_dict.pop("_data_source", None)
    def_dict.pop("is_unobtainable", None)
    def_dict.pop("is_mega", None)
    def_dict.pop("_sp_meta", None)

    from models import Pokemon, Move, Field
    attacker = Pokemon(**att_dict)
    defender = Pokemon(**def_dict)
    move = Move(**move_dict)
    field = Field()
    _apply_field_overrides(field, field_override)
    # Same normalization as cmd_calc: derive stats/HP so optimizer judgements
    # read the computed HP pool instead of zeros (round 2 audit E3/E8).
    _finalize_calc_pokemon(attacker, att_override)
    _finalize_calc_pokemon(defender, def_override)

    return optimize_evs(attacker, defender, move, field, goal=goal, target=target, threshold=threshold, mode=mode)  # type: ignore[arg-type]


def _parse_json_object(raw: str | None, label: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Parse a CLI JSON object without silently substituting defaults."""
    if raw is None or raw == "":
        return {}, None
    try:
        parsed = json.loads(raw.strip().strip("'\""))
    except (json.JSONDecodeError, TypeError) as exc:
        return None, {"error": f"{label} 必须是合法 JSON：{exc}"}
    if not isinstance(parsed, dict):
        return None, {"error": f"{label} 必须是 JSON 对象"}
    return parsed, None


def _validate_override_enums(label: str, ov: dict[str, Any]) -> dict[str, Any] | None:
    """Whitelist-validate enum-ish override fields before they reach the engine.

    Returns an {"error": ..., "suggestions": [...]} payload on the first
    invalid field, or None when everything resolves.
    """
    types = ov.get("types")
    if types is not None:
        if (not isinstance(types, list)
                or not all(isinstance(t, str) and resolve_type_en(t) for t in types)):
            cands = list(TYPE_ZH_TO_EN) + sorted(VALID_TYPES_EN)
            bad = types if isinstance(types, str) else ", ".join(map(repr, types))
            return {"error": f"{label} types invalid: {bad}",
                    "suggestions": get_suggestions(bad, cands, n=3)}
    nature = ov.get("nature")
    if isinstance(nature, str) and nature and resolve_nature_en(nature) is None:
        cands = list(NATURE_ZH_TO_EN) + sorted(VALID_NATURES_EN)
        return {"error": f"{label} nature invalid: {nature!r}",
                "suggestions": get_suggestions(nature, cands, n=3)}
    status = ov.get("status")
    if isinstance(status, str) and status and status not in VALID_STATUS_EN:
        return {"error": f"{label} status invalid: {status!r}",
                "suggestions": get_suggestions(status, sorted(VALID_STATUS_EN), n=3)}
    if "is_terastalize" in ov and not isinstance(ov["is_terastalize"], bool):
        return {"error": f"{label} is_terastalize must be a JSON boolean"}
    if "tera_type" in ov and ov["tera_type"] is not None:
        tera_type = resolve_tera_type_en(ov["tera_type"])
        if tera_type is None:
            candidates = list(TYPE_ZH_TO_EN) + sorted(VALID_TYPES_EN) + ["星晶", "星愿", "Stellar"]
            bad = ov["tera_type"]
            return {"error": f"{label} tera_type invalid: {bad!r}",
                    "suggestions": get_suggestions(str(bad), candidates, n=3)}
    if ov.get("is_terastalize") is True and not ov.get("tera_type"):
        return {"error": f"{label} is_terastalize requires a valid tera_type"}
    return None


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

    # Collected input warnings surfaced in the response "warning" field
    calc_warnings: list[str] = []

    overrides: list[dict[str, Any]] = []
    for index, label in enumerate(("att_override", "move_override", "def_override", "field_override")):
        raw = extra_args[index] if len(extra_args) > index else None
        parsed, parse_error = _parse_json_object(raw, label)
        if parse_error is not None:
            return parse_error
        overrides.append(parsed or {})
    att_override, move_override, def_override, field_override = overrides

    # Whitelist behavior-only fields; never let move_override touch
    # base_power/type/category. Surface dropped keys instead of swallowing.
    dropped = sorted(set(move_override) - _MOVE_OVERRIDE_WHITELIST)
    if dropped:
        calc_warnings.append("move_override 忽略非法字段: " + ", ".join(dropped))
        move_override = {k: v for k, v in move_override.items() if k in _MOVE_OVERRIDE_WHITELIST}
    if "hits" in move_override:
        try:
            hits_val = int(move_override["hits"])
        except (TypeError, ValueError):
            hits_val = 1
            calc_warnings.append(f"move_override hits={move_override['hits']!r} 非整数，已按 1 处理")
        clamped = max(1, min(_MOVE_OVERRIDE_HITS_MAX, hits_val))
        if clamped != hits_val:
            calc_warnings.append(f"move_override hits={hits_val} 超出 1-{_MOVE_OVERRIDE_HITS_MAX}，已夹紧为 {clamped}")
        move_override["hits"] = clamped

    # Boundary enum validation: invalid type/nature/status inputs are rejected
    # here with suggestions instead of passing through (or exploding) in the engine.
    for _side, _ov in (("attacker", att_override), ("defender", def_override)):
        _enum_err = _validate_override_enums(_side, _ov)
        if _enum_err is not None:
            return _enum_err

    # Remember if user explicitly specified a preset before _apply_preset_to_override pops it
    att_has_explicit_preset = "preset" in att_override
    def_has_explicit_preset = "preset" in def_override

    # Apply presets if specified in overrides
    att_override = _apply_preset_to_override(att_override, att_data.get("name_en", ""))
    def_override = _apply_preset_to_override(def_override, def_data.get("name_en", ""))

    # Auto-match preset for partially specified configs (evs/nature/ivs only)
    if not att_has_explicit_preset:
        att_override, att_auto_preset, att_auto_item = _apply_auto_preset_to_override(
            att_override, att_data.get("name_en", "")
        )
    else:
        att_auto_preset = None
        att_auto_item = None
    if not def_has_explicit_preset:
        def_override, def_auto_preset, def_auto_item = _apply_auto_preset_to_override(
            def_override, def_data.get("name_en", "")
        )
    else:
        def_auto_preset = None
        def_auto_item = None

    att_dict = _make_pokemon_from_data(att_data, att_override, form_index=att_form_idx)
    def_dict = _make_pokemon_from_data(def_data, def_override, form_index=def_form_idx)
    move_dict = _make_move_from_data(move_data, move_override)

    # Extract extra metadata before passing to model constructors
    # (setup_moves never survives _make_pokemon_from_data's field whitelist;
    # the live read below comes from att_override directly)
    att_extra = {
        "_data_source": att_dict.pop("_data_source", "gen9"),
        "is_unobtainable": att_dict.pop("is_unobtainable", False),
        "is_mega": att_dict.pop("is_mega", False),
        "_sp_meta": att_dict.pop("_sp_meta", {}),
    }
    def_extra = {
        "_data_source": def_dict.pop("_data_source", "gen9"),
        "is_unobtainable": def_dict.pop("is_unobtainable", False),
        "is_mega": def_dict.pop("is_mega", False),
        "_sp_meta": def_dict.pop("_sp_meta", {}),
    }

    attacker = Pokemon(**att_dict)
    defender = Pokemon(**def_dict)
    move = Move(**move_dict)
    field = Field()
    _apply_field_overrides(field, field_override)

    # Derive stats from raw_stats+boosts and honour explicit HP overrides
    # (round 2 audit E3/E8; compute_raw_stats inside the engine would
    # otherwise clobber an explicit max_hp and leave stats empty).
    _finalize_calc_pokemon(attacker, att_override)
    _finalize_calc_pokemon(defender, def_override)

    # Surface SP input warnings (e.g. sp > 32) collected during override merge
    for _extra in (att_extra, def_extra):
        _sp_meta = _extra.get("_sp_meta") or {}
        for _w in _sp_meta.pop("warnings", []):
            calc_warnings.append(_w)

    # 2-5 hit variable moves (data layer hits == "multi") are approximated
    # with the expected hit count of 3 — say so instead of staying silent.
    if move_data.get("hits") == "multi":
        calc_warnings.append(
            f"{move_data.get('name_zh', move.name)} 为 2-5 段变段招式，"
            "total_damage 按 3 段（期望段数）估算")

    # Apply setup moves (e.g., Nasty Plot, Swords Dance) if specified in att_override
    setup_moves = att_override.get("setup_moves", [])
    if setup_moves is None:
        setup_moves = []
    if not isinstance(setup_moves, list) or not all(isinstance(name, str) for name in setup_moves):
        return {"error": "setup_moves 必须是招式名称数组"}
    if setup_moves:
        calc_warnings.extend(_apply_setup_moves(attacker, defender, field, setup_moves))

    result = calculate_damage(attacker, defender, move, field, gen=9)

    # KO chance
    from ko_chance import get_ko_chance_text, squash_multihit
    ko_text = get_ko_chance_text(result.damage, result.move or move, defender, field)

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
        # Raw input types (pre-engine copy): the engine normalizes its copy to
        # English internally; display keeps the caller-facing language.
        "types": att_dict["types"],
        "base_stats": attacker.base_stats,
        "stats": attacker.raw_stats,
        "ability": attacker.ability_zh,
        "all_abilities": att_all_abilities,
        "nature": attacker.nature,
        "item": attacker.item_zh or attacker.item,
        "evs": attacker.evs,
        "sps": att_extra.get("_sp_meta", {}).get("sps", _evs_to_sps(attacker.evs)),
        "sp_approx": att_extra.get("_sp_meta", {}).get("approx", []),
        "ivs": attacker.ivs,
        "level": attacker.level,
        "current_hp": attacker.current_hp,
        "max_hp": attacker.max_hp,
        "_data_source": att_extra.get("_data_source", "gen9"),
        "is_unobtainable": att_extra.get("is_unobtainable", False),
        "is_mega": att_extra.get("is_mega", False),
    }
    defender_info = {
        "name_zh": defender.name,
        "name_en": def_data.get("name_en", ""),
        "types": def_dict["types"],
        "base_stats": defender.base_stats,
        "stats": defender.raw_stats,
        "ability": defender.ability_zh,
        "all_abilities": def_all_abilities,
        "nature": defender.nature,
        "item": defender.item_zh or defender.item,
        "evs": defender.evs,
        "sps": def_extra.get("_sp_meta", {}).get("sps", _evs_to_sps(defender.evs)),
        "sp_approx": def_extra.get("_sp_meta", {}).get("approx", []),
        "ivs": defender.ivs,
        "level": defender.level,
        "current_hp": defender.current_hp,
        "max_hp": defender.max_hp,
        "_data_source": def_extra.get("_data_source", "gen9"),
        "is_unobtainable": def_extra.get("is_unobtainable", False),
        "is_mega": def_extra.get("is_mega", False),
    }

    # Read the engine's final private Move, not the caller's original object.
    final_move = result.move or move
    move_info: dict[str, Any] = {
        "name": move_data.get("name_zh") or final_move.name,
        "name_en": final_move.name,
        "type": _MOVE_TYPE_EN_TO_ZH.get(final_move.type, final_move.type),
        "category": "物理" if final_move.category == "Physical" else ("特殊" if final_move.category == "Special" else "变化"),
        "base_power": move_dict.get("base_power"),
        "effective_power": result.effective_power,
        "accuracy": move_dict.get("accuracy"),
        "hits": final_move.hits,
        "is_spread": bool(final_move.is_spread),
    }
    field_info: dict[str, Any] = {
        "weather": field.weather,
        "terrain": field.terrain,
        "format": field.format,
        "is_gravity": field.is_gravity,
        "is_reflect": field.is_reflect,
        "is_light_screen": field.is_light_screen,
        "is_aurora_veil": field.is_aurora_veil,
        "is_stealth_rock": field.is_stealth_rock,
        "spikes": field.spikes,
        "is_helping_hand": field.is_helping_hand,
        "is_friend_guard": field.is_friend_guard,
        "is_battery": field.is_battery,
        "is_power_spot": field.is_power_spot,
    }
    modifiers: dict[str, Any] = {
        "attacker_boosts": attacker.boosts,
        "attacker_status": attacker.status,
        "attacker_is_tera": attacker.is_terastalize,
        "attacker_tera_type": att_dict.get("tera_type"),
        "defender_boosts": defender.boosts,
        "defender_status": defender.status,
        "defender_is_tera": defender.is_terastalize,
        "defender_tera_type": def_dict.get("tera_type"),
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
        "move_info": move_info,
        "field_info": field_info,
        "modifiers": modifiers,
        "_data_source": attacker_info.get("_data_source", "gen9"),
    }
    if att_auto_preset:
        response["attacker_auto_preset"] = att_auto_preset
    if att_auto_item:
        response["attacker_auto_item"] = _resolve_item_to_zh(att_auto_item) or att_auto_item
    if def_auto_preset:
        response["defender_auto_preset"] = def_auto_preset
    if def_auto_item:
        response["defender_auto_item"] = _resolve_item_to_zh(def_auto_item) or def_auto_item
    if attacker_info.get("is_unobtainable") or defender_info.get("is_unobtainable"):
        calc_warnings.append("该形态在当前对战环境中不可用，以下结果为理论计算")
    if calc_warnings:
        response["warning"] = "；".join(calc_warnings)
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

    # EVs are kept as raw values (full 4-EV granularity); SP is only a view.
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
        "sps": _evs_to_sps(evs),
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

    parsed_inputs: list[dict[str, Any]] = []
    for raw, label in (
        (attacker_json, "attacker_json"),
        (move_json, "move_json"),
        (defender_json, "defender_json"),
        (field_json, "field_json"),
    ):
        parsed, parse_error = _parse_json_object(raw, label)
        if parse_error is not None:
            return parse_error
        parsed_inputs.append(parsed or {})
    att_dict, move_dict, def_dict, field_dict = parsed_inputs

    for _side, _ov in (("attacker", att_dict), ("defender", def_dict)):
        _enum_err = _validate_override_enums(_side, _ov)
        if _enum_err is not None:
            return _enum_err

    # Validate required fields
    if "stats" not in att_dict:
        return {"error": "attacker_json missing required field: stats"}
    if "stats" not in def_dict:
        return {"error": "defender_json missing required field: stats"}

    # Normalize move fields for the damage engine (Chinese category/type -> English category / Chinese type)
    _normalize_move_fields(move_dict)

    # hits may arrive as the data layer's "multi" string or other junk;
    # coerce like _make_move_from_data instead of crashing on str>int later.
    if "hits" in move_dict:
        if move_dict["hits"] == "multi":
            move_dict["hits"] = 3
        else:
            try:
                move_dict["hits"] = int(move_dict["hits"])
            except (TypeError, ValueError):
                move_dict["hits"] = 1

    # Pokemon types pass through as provided: the engine normalizes zh/en
    # type inputs at its entry (engine-English refactor), and the response
    # displays the final type in the data-layer language below.
    for _side in (att_dict, def_dict):
        if _side.get("item"):
            _side["item"] = _normalize_item_input(_side["item"])

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

    # Merge optional `sps` override into EVs (SP is an input/view layer; the
    # engine stores raw EVs). sps takes precedence over evs for the same key.
    for side_dict in (att_dict, def_dict):
        if isinstance(side_dict.get("sps"), dict):
            base_evs = dict(side_dict.get("evs", {}))
            for stat, sp_val in side_dict["sps"].items():
                base_evs[stat] = _sp_to_ev(sp_val)
            side_dict["evs"] = base_evs
        side_dict.pop("sps", None)

    # Ensure HP fields are set
    if att_dict.get("max_hp", 0) == 0:
        att_dict["max_hp"] = att_dict["raw_stats"].get("hp", 0)
    if att_dict.get("current_hp", 0) == 0:
        att_dict["current_hp"] = att_dict["max_hp"]

    if def_dict.get("max_hp", 0) == 0:
        def_dict["max_hp"] = def_dict["raw_stats"].get("hp", 0)
    if def_dict.get("current_hp", 0) == 0:
        def_dict["current_hp"] = def_dict["max_hp"]

    # Normalize item names to English canonical for the damage engine
    for side_dict in (att_dict, def_dict):
        item = side_dict.get("item", "")
        if item:
            resolved = resolve_item(item)
            if resolved:
                side_dict["item"] = resolved

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
    ko_text = get_ko_chance_text(result.damage, result.move or move, defender, field)

    # Multi-hit total damage
    total_damage_rolls: list[int] = []
    if move.hits > 1:
        total_damage_rolls = squash_multihit(result.damage, move.hits)

    # Build response
    attacker_info = {
        "name_zh": attacker.name,
        "name_en": attacker.name_en,
        "types": [_MOVE_TYPE_EN_TO_ZH.get(t, t) for t in attacker.types],
        "ability": attacker.ability_zh,
        "nature": attacker.nature,
        "item": attacker.item,
        "stats": attacker.raw_stats,
        "evs": attacker.evs,
        "sps": _evs_to_sps(attacker.evs),
        "ivs": attacker.ivs,
        "level": attacker.level,
        "current_hp": attacker.current_hp,
        "max_hp": attacker.max_hp,
    }
    defender_info = {
        "name_zh": defender.name,
        "name_en": defender.name_en,
        "types": [_MOVE_TYPE_EN_TO_ZH.get(t, t) for t in defender.types],
        "ability": defender.ability_zh,
        "nature": defender.nature,
        "item": defender.item,
        "stats": defender.raw_stats,
        "evs": defender.evs,
        "sps": _evs_to_sps(defender.evs),
        "ivs": defender.ivs,
        "level": defender.level,
        "current_hp": defender.current_hp,
        "max_hp": defender.max_hp,
    }

    # Match cmd_calc: source all final move fields from the structured result.
    final_move = result.move or move
    move_info: dict[str, Any] = {
        "name": final_move.name_zh or final_move.name,
        "name_en": final_move.name,
        "type": _MOVE_TYPE_EN_TO_ZH.get(final_move.type, final_move.type),
        "category": "物理" if final_move.category == "Physical" else ("特殊" if final_move.category == "Special" else "变化"),
        "base_power": move_dict.get("base_power"),
        "effective_power": result.effective_power,
        "accuracy": move_dict.get("accuracy"),
        "hits": final_move.hits,
        "is_spread": bool(final_move.is_spread),
    }
    field_info: dict[str, Any] = {
        "weather": field.weather,
        "terrain": field.terrain,
        "format": field.format,
        "is_gravity": field.is_gravity,
        "is_reflect": field.is_reflect,
        "is_light_screen": field.is_light_screen,
        "is_aurora_veil": field.is_aurora_veil,
        "is_stealth_rock": field.is_stealth_rock,
        "spikes": field.spikes,
        "is_helping_hand": field.is_helping_hand,
        "is_friend_guard": field.is_friend_guard,
        "is_battery": field.is_battery,
        "is_power_spot": field.is_power_spot,
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
        "move_info": move_info,
        "field_info": field_info,
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
        result = calculate_damage(attacker, defender, move, field, gen=9,
                                  _neutral_damage=True)
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
    safe_ko = None
    if safe_bp > 0:
        safe_damage, safe_ko = _test(safe_bp)
        safe_dr = [min(safe_damage), max(safe_damage)]

    abs_dr = [0, 0]
    abs_ko = None
    if abs_safe_bp > 0:
        abs_damage, abs_ko = _test(abs_safe_bp)
        abs_dr = [min(abs_damage), max(abs_damage)]

    return {
        "safe_bp": safe_bp,
        "absolute_safe_bp": abs_safe_bp,
        "safe_damage_range": safe_dr,
        "absolute_safe_damage_range": abs_dr,
        "search_max_bp": max_bp,
        "safe_bp_capped": safe_ko_hi < safe_threshold,
        "absolute_safe_bp_capped": abs_ko_hi == 0.0,
        "safe_ko_probability": safe_ko,
        "absolute_safe_ko_probability": abs_ko,
    }


def cmd_survivability(
    defender_name: str,
    attacker_stat: int | None = 200,
    category: str | None = None,
    def_ov: str = "{}",
    field_ov: str = "{}",
    setup_moves: list[str] | None = None,
) -> dict[str, Any]:
    """Find neutral, non-STAB, non-critical survivability at level 50.

    Missing attacker stats default to 200. Explicit defender investments are
    honored without auto-presets; unsupported inputs fail rather than vanish.
    """
    category = {"physical": "Physical", "special": "Special"}.get(
        category.lower() if isinstance(category, str) else ""
    )
    if category is None:
        return {"error": "category 必须是 Physical 或 Special（不区分大小写）"}
    if attacker_stat is None:
        attacker_stat = 200
    if type(attacker_stat) is not int or attacker_stat <= 0:
        return {"error": "attacker_stat 必须是正整数，未指定时默认 200"}

    try:
        def_override = json.loads(def_ov) if def_ov else {}
        field_override = json.loads(field_ov) if field_ov else {}
    except (json.JSONDecodeError, TypeError) as exc:
        return {"error": f"def_ov / field_ov 必须是合法 JSON：{exc}"}
    if not isinstance(def_override, dict) or not isinstance(field_override, dict):
        return {"error": "def_ov 和 field_ov 必须是 JSON 对象"}

    # Direct stat JSON remains available for synthetic comparisons and callers
    # without a species name. Explicit overrides take precedence over it.
    supplied: dict[str, Any] = {}
    try:
        maybe_json = json.loads(defender_name)
        if isinstance(maybe_json, dict):
            supplied = maybe_json
        elif not isinstance(maybe_json, str):
            return {"error": "防御方 JSON 必须是含 raw_stats 或 stats 的对象"}
    except (json.JSONDecodeError, TypeError):
        pass
    allowed_def = {
        "evs", "sps", "ivs", "nature", "raw_stats", "stats", "boosts",
        "setup_moves", "level", "current_hp", "max_hp",
    }
    unknown = set(def_override) - allowed_def
    unknown |= set(supplied) - allowed_def - {"name", "name_en", "types"}
    if unknown:
        return {"error": f"survivability 不支持防御方字段：{', '.join(sorted(unknown))}"}
    config = {**supplied, **def_override}
    if "level" in config and (type(config["level"]) is not int or config["level"] != 50):
        return {"error": "survivability 固定按 50 级计算，level 只能为 50"}
    if "nature" in config and (not isinstance(config["nature"], str)
                               or resolve_nature_en(config["nature"]) is None):
        return {"error": "nature 必须是有效的性格名称"}
    if "types" in supplied:
        types = supplied["types"]
        if (not isinstance(types, list) or not 1 <= len(types) <= 2
                or not all(isinstance(t, str) and resolve_type_en(t) for t in types)):
            return {"error": "防御方 types 必须是包含一至两个有效属性的数组"}
    for key in ("name", "name_en"):
        if key in supplied and not isinstance(supplied[key], str):
            return {"error": f"防御方 {key} 必须是字符串"}

    stat_keys = {"hp", "attack", "defense", "sp_attack", "sp_defense", "speed"}
    limits = {"evs": (0, 252), "sps": (0, 32), "ivs": (0, 31),
              "boosts": (-6, 6), "raw_stats": (1, None), "stats": (1, None)}
    for key, (low, high) in limits.items():
        if key not in config:
            continue
        values = config[key]
        if not isinstance(values, dict) or set(values) - stat_keys:
            return {"error": f"{key} 必须是仅含六项能力键的 JSON 对象"}
        if key == "boosts" and "hp" in values:
            return {"error": "boosts 不支持 hp"}
        for stat, value in values.items():
            if type(value) is not int or value < low or (high is not None and value > high):
                return {"error": f"{key}.{stat} 数值无效"}
        if key == "evs" and sum(values.values()) > 510:
            return {"error": "努力值总和不能超过 510"}
        if key == "sps" and sum(values.values()) > 66:
            return {"error": "能力点数总和不能超过 66"}
    if "raw_stats" in config and "stats" in config:
        return {"error": "raw_stats 与 stats 请只提供一项"}

    # Only conditions used by this single-hit search are accepted. Hazards and
    # end-of-turn damage belong to full calc, not this direct-hit KO threshold.
    allowed_field = {
        "format", "weather", "terrain", "is_gravity", "is_reflect",
        "is_light_screen", "is_aurora_veil", "is_friend_guard", "is_helping_hand",
        "is_battery", "is_power_spot", "is_flower_gift_atk", "is_flower_gift_spd",
        "is_sword_of_ruin", "is_beads_of_ruin", "is_tablets_of_ruin", "is_vessel_of_ruin",
    }
    unknown = set(field_override) - allowed_field
    if unknown:
        return {"error": f"survivability 不支持环境字段：{', '.join(sorted(unknown))}"}
    field_enums = {
        "format": ("Singles", "Doubles"),
        "weather": ("Sun", "Rain", "Sand", "Hail", "Snow", "Strong Winds", "Harsh Sun", "Heavy Rain"),
        "terrain": ("Electric", "Grassy", "Misty", "Psychic"),
    }
    for key, value in field_override.items():
        if key in field_enums:
            if value is None and key != "format":
                continue
            canonical = {v.lower(): v for v in field_enums[key]}
            if not isinstance(value, str) or value.lower() not in canonical:
                return {"error": f"{key} 取值无效"}
            field_override[key] = canonical[value.lower()]
        elif type(value) is not bool:
            return {"error": f"{key} 必须是布尔值"}

    setup_moves = config.pop("setup_moves", setup_moves)
    if setup_moves is None:
        setup_moves = []
    if not isinstance(setup_moves, list) or not all(isinstance(m, str) for m in setup_moves):
        return {"error": "setup_moves 必须是招式名称数组"}
    if setup_moves and (config.get("boosts") or field_override.get("weather")
                        or field_override.get("terrain")):
        return {"error": "setup_moves 与手动 boosts / weather / terrain 请二选一"}
    canonical_setup = []
    for name in setup_moves:
        resolved_move = resolve_move(name)
        if not resolved_move or not resolved_move[1].get("stat_changes"):
            return {"error": f"不支持的强化招式：{name}"}
        canonical_setup.append(resolved_move[0])

    # Reuse the data adapter and stat calculator; do not invoke auto-presets.
    if supplied:
        if not (config.get("raw_stats") or config.get("stats")):
            return {"error": "防御方 JSON 必须提供 raw_stats 或 stats"}
        if any(k in config for k in ("evs", "sps", "ivs", "nature")):
            return {"error": "防御方 JSON 已是最终能力值，不支持再指定 EV / SP / IV / nature"}
        pk_info = {"name": "Defender", "types": ["Normal"], **config}
    else:
        resolved = resolve_pokemon(defender_name)
        if not resolved:
            return {"error": f"Defender '{defender_name}' not found."}
        _, data, form_idx = resolved
        build_config = {k: v for k, v in config.items() if k not in ("raw_stats", "stats")}
        pk_info = _make_pokemon_from_data(data, build_config, form_index=form_idx)
    for key in ("_data_source", "is_unobtainable", "_sp_meta"):
        pk_info.pop(key, None)
    pk_info.update(ability="", ability_zh="", item="", item_zh="")
    defender = Pokemon(**pk_info)
    _finalize_calc_pokemon(defender, config)
    if "max_hp" in config and "current_hp" not in config:
        defender.current_hp = defender.max_hp
    # Champions' 66-SP budget is distinct from the main-series EV budget;
    # a valid 32/32/2 SP split stores as 252/252/12 EV internally.
    if "sps" in config:
        if sum(_evs_to_sps(defender.evs).values()) > 66:
            return {"error": "EV / SP 合并后的能力点数总和不能超过 66"}
    elif sum(defender.evs.values()) > 510:
        return {"error": "努力值总和不能超过 510"}
    # Merge partial final-stat overrides onto computed defaults.
    if not supplied:
        for key in ("raw_stats", "stats"):
            if key in config:
                defender.raw_stats.update(config[key])
        defender.stats = dict(defender.raw_stats)
        if "hp" in (config.get("raw_stats") or config.get("stats") or {}):
            if "max_hp" not in config:
                defender.max_hp = defender.raw_stats["hp"]
            if "current_hp" not in config:
                defender.current_hp = defender.max_hp
    defense_key = "defense" if category == "Physical" else "sp_defense"
    for key in ("hp", defense_key):
        if type(defender.raw_stats.get(key)) is not int or defender.raw_stats[key] <= 0:
            return {"error": f"防御方必须提供正整数能力值 {key}"}
    if (type(defender.max_hp) is not int or type(defender.current_hp) is not int
            or not 0 < defender.current_hp <= defender.max_hp):
        return {"error": "HP 必须满足 0 < current_hp <= max_hp，且均为整数"}

    raw_stats = {k: 0 for k in stat_keys}
    raw_stats["attack" if category == "Physical" else "sp_attack"] = attacker_stat
    attacker = Pokemon(
        name="VirtualAttacker", name_en="VirtualAttacker", level=50,
        types=["Fire"], stats=dict(raw_stats), raw_stats=dict(raw_stats),
    )
    field = Field(**field_override)
    if canonical_setup:
        _apply_setup_moves(defender, attacker, field, canonical_setup)
    result = _find_survivability_bp(attacker, defender, field, category)

    return {
        "defender": {
            "name_zh": defender.name,
            "name_en": defender.name_en,
            "hp": defender.current_hp,
            "max_hp": defender.max_hp,
            "defense": defender.raw_stats.get("defense", 0),
            "sp_defense": defender.raw_stats.get("sp_defense", 0),
            "level": 50,
            "effective_defense": defender.stats.get("defense", 0),
            "effective_sp_defense": defender.stats.get("sp_defense", 0),
            "evs": defender.evs,
            "sps": _evs_to_sps(defender.evs),
            "ivs": defender.ivs,
            "nature": defender.nature,
        },
        "attacker_stat": attacker_stat,
        "category": category,
        "format": field.format,
        "defender_boosts": dict(defender.boosts),
        "attacker_boosts": dict(attacker.boosts),
        "setup_moves": canonical_setup,
        "field_info": {k: getattr(field, k) for k in sorted(allowed_field)},
        "baseline": {
            "level": 50, "type_effectiveness": 1.0, "stab_applied": False,
            "is_critical": False, "hits": 1, "is_spread": False,
            "safe_ko_threshold": 0.15, "absolute_ko_threshold": 0.0,
            "pokemon_abilities_applied": False, "items_applied": False,
        },
        **result,
    }



# ---------------------------------------------------------------------------
# Meta environment commands (pokecamp.cc / Limitless tournament data)
# ---------------------------------------------------------------------------


def _find_usage_entry(pokemon_list: list[dict[str, Any]], name: str) -> dict[str, Any] | None:
    """Find a usage entry by zh/en/identifier, with alias normalization."""
    if not name:
        return None
    norm = normalize_name(name, "pokemon")
    lowered = {c.strip().lower() for c in (name, norm) if c and c.strip()}
    for e in pokemon_list:
        names = {str(e.get("name_zh", "")).lower(),
                 str(e.get("name_en", "")).lower(),
                 str(e.get("identifier", "")).lower()}
        if names & lowered:
            return e
    # Fall back to the local index: resolve to stem / name_en, then match
    resolved = resolve_pokemon(name)
    if resolved:
        stem, pdata, _ = resolved
        en = (pdata.get("name_en") or "").lower()
        for e in pokemon_list:
            if (str(e.get("identifier", "")).lower() == stem.lower()
                    or str(e.get("name_en", "")).lower() == en):
                return e
    return None


def cmd_usage(name: str = "", top: int = 20, online: bool = False) -> dict[str, Any]:
    """Deprecated alias for `meta --usage`; kept for existing tests/callers."""
    return cmd_meta(target=name, top=top, online=online, usage=True)


_LADDER_SOURCE_ALIASES = {"ladder": "ingame", "ingame": "ingame", "showdown": "showdown"}


def cmd_meta(target: str = "", top: int | None = None, online: bool = False,
             source: str = "tournament", battle_format: str = "doubles",
             usage: bool = False, teams: bool = False,
             pokemon: str = "", player: str = "", stats: bool = False,
             teammates: str = "", placing_max: int | None = None,
             tournament: str = "") -> dict[str, Any]:
    """Unified meta-environment query: usage stats + tournament teams + ladder.

    Routes to usage / teams / ladder handlers based on --source, explicit
    flags, or target inference. Sources: "tournament" (default, pokecamp.cc /
    Limitless public tournament data), "ladder"/"ingame" (official in-game
    ranked rankings, rank-only), "showdown" (Showdown ladder monthly report).
    ``battle_format`` ("singles"/"doubles", default "doubles") only applies to
    ladder sources. ``top`` is resolved per mode when omitted: 20 for
    usage/ladder queries, 12 for team lists.
    """
    # ---- source validation & ladder routing --------------------------------
    if source != "tournament":
        kind = _LADDER_SOURCE_ALIASES.get(source)
        if kind is None:
            return {
                "error": f"Unknown meta source '{source}'. Available: "
                         "'tournament' (pokecamp.cc / Limitless public tournament "
                         "data), 'ladder'/'ingame' (official in-game ranked data), "
                         "'showdown' (Showdown ladder monthly report).",
                "meta": {"source_requested": source,
                         "source_available": ["tournament", "ladder", "ingame", "showdown"]},
            }
        if teams or stats or teammates or player or tournament:
            return {
                "error": "Ladder data has no tournament teams concept; team queries "
                         "(--teams/--stats/--teammates/--player/--tournament) only "
                         "work with --source tournament. "
                         "天梯数据没有赛事队伍概念，队伍查询请用 --source tournament。",
                "meta": {"source_requested": source, "source_available": "tournament"},
            }
        if top is None:
            top = 20
        return _cmd_meta_ladder(name=pokemon or target, top=top, online=online,
                                source_kind=kind, battle_format=battle_format)

    # ---- mode resolution: explicit flags first, then inference ------------
    if teams or stats or teammates or player or tournament:
        mode = "teams"
    elif usage:
        # Explicit --usage wins over a bare --pokemon filter; the value
        # doubles as the usage-detail subject (meta --usage --pokemon X
        # is the same query as `meta X`).
        mode = "usage"
    elif pokemon or target.isdigit():
        # Pure number -> team number (e.g. "meta 3" -> team #3)
        mode = "teams"
    elif target:
        # Non-numeric target -> pokemon name for usage detail
        mode = "usage"
    else:
        # No target -> usage ranking (most common query)
        mode = "usage"

    if top is None:
        top = 12 if mode == "teams" else 20

    # ---- dispatch ---------------------------------------------------------
    if mode == "usage":
        return _cmd_meta_usage(name=pokemon or target, top=top, online=online)
    return _cmd_meta_teams(query=target, top=top, online=online,
                           pokemon=pokemon, player=player,
                           stats=stats, teammates=teammates,
                           placing_max=placing_max,
                           tournament=tournament)


def _cmd_meta_usage(name: str = "", top: int = 20, online: bool = False) -> dict[str, Any]:
    """Usage stats handler for cmd_meta."""
    try:
        data = pcs.get_usage_data(DATA_DIR, online=online)
    except Exception as e:
        # Missing/corrupt snapshot or failed online fetch must not leak a
        # traceback; align with the friendly error shapes used elsewhere.
        return {"error": f"使用率数据不可用: {type(e).__name__}: {e}", "meta": {}}
    meta = data.get("meta", {})
    plist = data.get("pokemon", [])

    if not name:
        ranking = [{
            "rank": e.get("rank"),
            "name_zh": e.get("name_zh"),
            "name_en": e.get("name_en"),
            "usage_percent": e.get("usage_percent"),
            "win_rate": e.get("win_rate"),
            "team_count": e.get("team_count"),
        } for e in plist[:top]]
        return {"meta": meta, "usage_top": ranking}

    entry = _find_usage_entry(plist, name)
    if not entry:
        candidates = [e.get("name_zh", "") for e in plist] + [e.get("name_en", "") for e in plist]
        suggestions = get_suggestions(name, candidates, n=3)
        err: dict[str, Any] = {
            "error": f"Pokemon '{name}' not found in meta usage data (format {meta.get('format')}).",
            "meta": meta,
        }
        if suggestions:
            err["suggestions"] = suggestions
        return err

    # Online light mode returns ranking-only entries; enrich with one detail fetch.
    if "abilities" not in entry and online:
        detailed = pcs.get_usage_entry_detail(DATA_DIR, entry.get("id"), online=True)
        if detailed:
            entry = detailed

    result: dict[str, Any] = {"meta": meta}
    result.update(entry)
    return result


def _cmd_meta_ladder(name: str = "", top: int = 20, online: bool = False,
                     source_kind: str = "ingame",
                     battle_format: str = "doubles") -> dict[str, Any]:
    """Ladder handler for cmd_meta (ingame official ranked / showdown monthly).

    ingame list data is rank-only (no usage % or win rate is published), so
    the ranking output is a pure rank table. Single-pokemon queries are
    enriched online with real-percentage build detail (moves/items/abilities/
    natures/spreads) from the next-data detail route.
    """
    if battle_format not in ("singles", "doubles"):
        battle_format = "doubles"
    try:
        data = pcs.get_ladder_data(DATA_DIR, source_kind, online=online)
    except Exception as e:
        return {"error": f"天梯数据不可用: {type(e).__name__}: {e}", "meta": {}}
    meta = dict(data.get("meta") or {})
    meta["battle_format"] = battle_format
    meta["format_note"] = (
        "当前显示双打排行，加 --format singles 查看单打"
        if battle_format == "doubles" else
        "当前显示单打排行，加 --format doubles 查看双打")
    plist = data.get("pokemon", [])
    rank_key = f"{battle_format}_rank"
    pct_key = f"{battle_format}_usage_percent"

    def _rank(e: dict[str, Any]) -> int:
        return e.get(rank_key) or 99999

    if not name:
        ordered = sorted(plist, key=_rank)[:top]
        ranking = []
        for e in ordered:
            row: dict[str, Any] = {
                "rank": e.get(rank_key),
                "name_zh": e.get("name_zh"),
                "name_en": e.get("name_en"),
            }
            if source_kind == "ingame":
                if e.get("includes_mega"):
                    row["includes_mega"] = True
            else:
                row["usage_percent"] = e.get(pct_key)
                if e.get("is_mega"):
                    row["is_mega"] = True
            ranking.append(row)
        return {"meta": meta, "ladder_top": ranking}

    entry = None
    if name.isdigit():
        # Bare number under a ladder source = "who is rank N" (reverse lookup).
        n = int(name)
        entry = next((e for e in plist if e.get(rank_key) == n), None)
        if entry is None:
            return {
                "error": f"No pokemon at {battle_format} rank {n} in ladder data "
                         f"(source {source_kind}).",
                "meta": meta,
            }
    else:
        entry = _find_usage_entry(plist, name)
    if not entry:
        candidates = [e.get("name_zh", "") for e in plist] + [e.get("name_en", "") for e in plist]
        suggestions = get_suggestions(name, candidates, n=3)
        err: dict[str, Any] = {
            "error": f"Pokemon '{name}' not found in ladder data "
                     f"(source {source_kind}, regulation {meta.get('regulation')}).",
            "meta": meta,
        }
        if suggestions:
            err["suggestions"] = suggestions
        return err

    result: dict[str, Any] = {"meta": meta}
    if name.isdigit():
        result["rank_query"] = int(name)
    out_entry: dict[str, Any] = {
        "id": entry.get("id"),
        "identifier": entry.get("identifier"),
        "name_zh": entry.get("name_zh"),
        "name_en": entry.get("name_en"),
        "singles_rank": entry.get("singles_rank"),
        "doubles_rank": entry.get("doubles_rank"),
    }
    if source_kind == "ingame":
        out_entry["includes_mega"] = bool(entry.get("includes_mega"))
        out_entry["rank_only"] = True
    else:
        out_entry["singles_usage_percent"] = entry.get("singles_usage_percent")
        out_entry["doubles_usage_percent"] = entry.get("doubles_usage_percent")
        if entry.get("is_mega"):
            out_entry["is_mega"] = True
    result.update(out_entry)

    if online:
        detail = pcs.get_ladder_entry_detail(DATA_DIR, entry.get("id"),
                                             battle_format=battle_format,
                                             source_kind=source_kind,
                                             online=True)
        if detail:
            result.update(detail)
    else:
        result["detail_note"] = ("单只配招/道具/性格/努力详情需加 --online 获取 "
                                 "(build detail requires --online)")
    return result


def _cmd_meta_teams(query: str = "", top: int = 12, online: bool = False,
                    pokemon: str = "", player: str = "", stats: bool = False,
                    teammates: str = "", placing_max: int | None = None,
                    tournament: str = "") -> dict[str, Any]:
    """Tournament teams handler for cmd_meta.

    Plain list / detail-by-number queries are served from the full SQLite
    index so the list and `meta --teams <N>` always share one source and
    ordering; the light meta_teams.json snapshot is only a fallback when
    the index is unavailable. Filter / aggregation queries always require
    the index. All outputs are hard-capped at 50 rows.
    """
    advanced = bool(stats or teammates or player or tournament or pokemon
                    or (query and not query.isdigit()))

    def _legacy_snapshot() -> dict[str, Any]:
        data = pcs.get_teams_data(DATA_DIR, online=online, top=max(top, 12))
        meta = data.get("meta", {})
        teams = data.get("teams", [])[:top]

        def _summary(i: int, t: dict[str, Any]) -> dict[str, Any]:
            tinfo = t.get("tournament") or {}
            return {
                "no": i + 1,
                "tournament": tinfo.get("name"),
                "date": tinfo.get("date"),
                "player": t.get("player"),
                "country": t.get("country"),
                "placing": t.get("placing"),
                "record": t.get("record"),
                "pokemon": [p.get("name_zh") for p in t.get("pokemon", [])],
            }

        if not query:
            return {"meta": meta, "teams": [_summary(i, t) for i, t in enumerate(teams)]}
        idx = int(query) - 1
        if 0 <= idx < len(teams):
            return {"meta": meta, "no": idx + 1, **teams[idx]}
        return {"error": f"Team number out of range: {query} (1-{len(teams)})", "meta": meta}

    if not advanced:
        # Plain list / detail-by-number: served from the full index so the
        # list and `meta --teams <N>` always share one source and ordering.
        # The light snapshot is only used when the index is unavailable
        # (bundled teams_full pack missing on a broken install).
        try:
            idx = pcs.get_teams_index(DATA_DIR, online=online)
        except Exception as e:
            return {"error": f"Teams data unavailable: {type(e).__name__}: {e}", "meta": {}}
        if idx.get("db_path") is not None:
            import teams_index as tix
            if query.isdigit():
                n = int(query)
                rows = tix.find_teams(idx["db_path"], limit=min(n, 50))["teams"]
                if 1 <= n <= len(rows):
                    detail = tix.get_team_detail(idx["db_path"], rows[n - 1]["id"])
                    if detail:
                        return {"meta": idx["meta"], "no": n, **detail}
                return {"error": f"Team number out of range: {query} (1-{len(rows)})",
                        "meta": idx["meta"]}
            result = tix.find_teams(idx["db_path"], limit=top)
            return {"meta": idx["meta"], **result}
        try:
            return _legacy_snapshot()
        except Exception as e:  # neither index nor snapshot available
            return {"error": f"Teams data unavailable: {type(e).__name__}: {e}"}

    # ---- full-index backed queries -------------------------------------
    try:
        idx = pcs.get_teams_index(DATA_DIR, online=online)
    except Exception as e:
        return {"error": f"Teams data unavailable: {type(e).__name__}: {e}", "meta": {}}
    meta = idx.get("meta", {})
    db_path = idx.get("db_path")
    if db_path is None:
        return {
            "error": "Full teams index unavailable (bundled teams_full pack missing); "
                     "only `meta --teams` / `meta --teams <number>` snapshot queries work.",
            "meta": meta,
        }
    import teams_index as tix

    def _resolve_pokemon(name: str) -> tuple[str | None, str | None]:
        """-> (identifier, name_zh) for index filtering; (None, norm) fallback."""
        try:
            usage = pcs.get_usage_data(DATA_DIR, online=False)
            entry = _find_usage_entry(usage.get("pokemon", []), name)
        except Exception:
            entry = None
        if entry:
            return entry.get("identifier"), entry.get("name_zh")
        return None, normalize_name(name, "pokemon")

    if stats:
        if pokemon:
            ident, name_zh = _resolve_pokemon(pokemon)
            if not ident:
                return {"error": f"Pokemon '{pokemon}' not found in meta data; "
                                 "cannot aggregate builds.", "meta": meta}
            result = tix.aggregate_pokemon_builds(db_path, ident)
            if not result.get("team_count"):
                return {"error": f"No indexed team uses '{pokemon}' in the current "
                                 f"{meta.get('date_range')} window.", "meta": meta}
            result["name_zh"] = result.get("name_zh") or name_zh or pokemon
            return {"meta": meta, **result}
        limit = top if top != 12 else 20
        return {"meta": meta, **tix.aggregate_pokemon_usage(
            db_path, placing_max=placing_max, tournament=tournament or None, limit=limit)}

    if teammates:
        ident, name_zh = _resolve_pokemon(teammates)
        if not ident:
            return {"error": f"Pokemon '{teammates}' not found in meta data; "
                             "cannot aggregate teammates.", "meta": meta}
        result = tix.aggregate_teammates(db_path, ident, limit=top)
        if not result.get("team_count"):
            return {"error": f"No indexed team uses '{teammates}' in the current "
                             f"{meta.get('date_range')} window.", "meta": meta}
        result["name_zh"] = name_zh or teammates
        return {"meta": meta, **result}

    poke_filter = pokemon or (query if query and not query.isdigit() else "")
    ident = name_zh = None
    if poke_filter:
        ident, name_zh = _resolve_pokemon(poke_filter)
    result = tix.find_teams(db_path, pokemon_identifier=ident, pokemon_name_zh=name_zh,
                            player=player or None, tournament=tournament or None,
                            limit=top)
    if not result["teams"]:
        return {"error": "No team matches the given filter in the indexed "
                         f"{meta.get('team_count', '?')} teams "
                         f"({meta.get('date_range')}).", "meta": meta}
    out: dict[str, Any] = {"meta": meta}
    if poke_filter:
        out["filter"] = poke_filter
    out.update(result)
    return out


def cmd_teams(query: str = "", top: int = 12, online: bool = False,
              pokemon: str = "", player: str = "", stats: bool = False,
              teammates: str = "", placing_max: int | None = None,
              tournament: str = "") -> dict[str, Any]:
    """Deprecated alias for `meta --teams`; kept for existing tests/callers."""
    return cmd_meta(target=query, top=top, online=online, teams=True,
                    pokemon=pokemon, player=player, stats=stats,
                    teammates=teammates, placing_max=placing_max,
                    tournament=tournament)


def cmd_lookup(name: str) -> dict[str, Any]:
    """Resolve a multi-language name to its canonical English identifier.

    Lightweight intent disambiguation (pokemon -> move -> ability -> item);
    the first match wins. Not a new query surface.
    """
    if not name:
        return {"error": "usage: lookup <name>"}
    p = resolve_pokemon(name)
    if p:
        return {"input": name, "canonical_en": p[1].get("name_en", ""), "entity_type": "pokemon"}
    mv = resolve_move(name)
    if mv:
        return {"input": name, "canonical_en": mv[1].get("name_en", ""), "entity_type": "move"}
    ab = resolve_ability(name)
    if ab:
        return {"input": name, "canonical_en": ab[1].get("name_en", ""), "entity_type": "ability"}
    it = resolve_item(name)
    if it:
        return {"input": name, "canonical_en": it, "entity_type": "item"}
    load_data()
    cands = (list(_index_data.get("pokemon", {}).keys())
             + list(_index_data.get("pokemon_forms", {}).keys())
             + list(_index_data.get("moves", {}).keys()))
    return {"error": f"'{name}' not found.", "suggestions": get_suggestions(name, cands, n=3)}


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
    "filter-pokemon": cmd_filter_pokemon,
    "preset": cmd_preset,
    "calc": cmd_calc,
    "calc-raw": cmd_calc_raw,
    "compute-stats": cmd_compute_stats,
    "optimize": cmd_optimize,
    "survivability": cmd_survivability,
    "meta": cmd_meta,
    "lookup": cmd_lookup,
}


def _extract_regulation_flag(argv: list[str]) -> tuple[list[str], str | None]:
    """Pull the internal (undocumented) --regulation cap out of argv.

    Accepts ``--regulation ID`` and ``--regulation=ID``. It is handled here
    rather than per-subcommand so every command gets the same behavior, and it
    is deliberately absent from help text and all user-facing docs.
    """
    out: list[str] = []
    value: str | None = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--regulation" and i + 1 < len(argv):
            value = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--regulation="):
            value = arg.split("=", 1)[1]
            i += 1
            continue
        out.append(arg)
        i += 1
    return out, value


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    sys.argv, _reg_arg = _extract_regulation_flag(sys.argv)
    if _reg_arg is not None:
        set_regulation_cap(_reg_arg)

    cmd = sys.argv[1]

    # Named-argument commands: use argparse
    if cmd in ("calc", "optimize", "calc-raw", "compute-stats", "find-move", "pokemon", "filter-moves", "filter-pokemon", "survivability", "usage", "teams", "meta", "lookup"):
        import argparse

        parser = argparse.ArgumentParser(description="Pokemon Calc CLI")
        subparsers = parser.add_subparsers(dest="command")

        # pokemon
        pokemon_parser = subparsers.add_parser("pokemon", help="Pokemon info or type-filtered search")
        pokemon_parser.add_argument("name", nargs="?", default="", help="Pokemon name (optional if --type is used)")
        pokemon_parser.add_argument("--type", dest="type_filters", action="append", default=[], help="Filter by type (can specify multiple, e.g. --type 超能 --type 恶)")

        # lookup
        lookup_parser = subparsers.add_parser("lookup", help="Resolve a multi-language name to canonical English")
        lookup_parser.add_argument("name", help="Pokemon / move / ability / item name")

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
        opt_parser.add_argument("--mode", default="ev", help="Optimization mode: ev (Gen9 Effort Values, default) or sp (Champions Stat Points)")
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

        # filter-pokemon
        filter_pokemon_parser = subparsers.add_parser("filter-pokemon", help="Filter pokemon by type, base stats, and/or ability")
        filter_pokemon_parser.add_argument("--type", dest="type_filters", action="append", default=[], help="Filter by type (can specify multiple, e.g. --type 火 --type 龙)")
        filter_pokemon_parser.add_argument("--min-stat", dest="min_stat_pairs", action="append", default=[], nargs=2, metavar=("STAT", "VALUE"), help="Minimum base stat, e.g. --min-stat hp 80")
        filter_pokemon_parser.add_argument("--max-stat", dest="max_stat_pairs", action="append", default=[], nargs=2, metavar=("STAT", "VALUE"), help="Maximum base stat, e.g. --max-stat speed 100")
        filter_pokemon_parser.add_argument("--ability", dest="ability_filters", action="append", default=[], help="Filter by ability (can specify multiple)")

        # survivability
        surv_parser = subparsers.add_parser("survivability", help="Reverse survivability: max unboosted BP defender can survive")
        surv_parser.add_argument("defender", help="Defender Pokemon name or JSON with raw_stats")
        surv_parser.add_argument("attacker_stat", type=int, nargs="?", default=200,
                                 help="Attacker's attack/sp_attack stat value (default: 200)")
        surv_parser.add_argument("category", help="Physical or Special")
        surv_parser.add_argument("--def_ov", default="{}", help="Defender override JSON (supports boosts, setup_moves, raw_stats)")
        surv_parser.add_argument("--def_ov_file", default=None, help="Path to defender override JSON file (takes precedence over --def_ov)")
        surv_parser.add_argument("--field_ov", default="{}", help="Field override JSON")
        surv_parser.add_argument("--field_ov_file", default=None, help="Path to field override JSON file (takes precedence over --field_ov)")

        # usage (deprecated alias for meta --usage)
        usage_parser = subparsers.add_parser("usage", help="DEPRECATED: use 'meta --usage' instead")
        usage_parser.add_argument("name", nargs="?", default="", help="Pokemon name (optional; empty = top ranking)")
        usage_parser.add_argument("--top", type=int, default=20, help="Number of entries in the ranking (default 20)")
        usage_parser.add_argument("--online", action="store_true", help="Fetch fresh data from pokecamp.cc (cached; falls back to bundled snapshot)")

        # teams (deprecated alias for meta --teams)
        teams_parser = subparsers.add_parser("teams", help="DEPRECATED: use 'meta --teams' instead")
        teams_parser.add_argument("query", nargs="?", default="", help="Team number for full detail, or pokemon name to filter (empty = list)")
        teams_parser.add_argument("--top", type=int, default=12, help="Max rows to return (default 12, hard cap 50)")
        teams_parser.add_argument("--pokemon", default="", help="Filter teams using this pokemon (full index)")
        teams_parser.add_argument("--player", default="", help="Filter teams by player name (substring)")
        teams_parser.add_argument("--tournament", default="", help="Filter by tournament name (substring)")
        teams_parser.add_argument("--stats", action="store_true", help="Pokemon appearance share across all indexed teams; with --pokemon shows that pokemon's item/ability/move/nature shares")
        teams_parser.add_argument("--teammates", default="", metavar="NAME", help="Most common teammates of this pokemon across all indexed teams")
        teams_parser.add_argument("--placing-max", type=int, default=None, help="With --stats: only count teams placing <= N (e.g. 8 = top-cut)")
        teams_parser.add_argument("--online", action="store_true", help="Fetch fresh data from pokecamp.cc (incremental; falls back to cache/snapshot)")

        # meta (unified environment data query)
        meta_parser = subparsers.add_parser("meta", help="Unified meta-environment query (usage stats + tournament teams)")
        meta_parser.add_argument("target", nargs="?", default="", help="Pokemon name for usage detail, or team number with --teams")
        meta_parser.add_argument("--top", type=int, default=None, help="Max rows / ranking entries (default: 20 for usage, 12 for teams; hard cap 50)")
        meta_parser.add_argument("--online", action="store_true", help="Fetch fresh data from pokecamp.cc (cached; falls back to snapshot)")
        meta_parser.add_argument("--source", default="tournament", help="Data source: tournament (default, Limitless public events) | ladder/ingame (official in-game ranked, rank-only) | showdown (Showdown ladder monthly)")
        meta_parser.add_argument("--format", dest="battle_format", default="doubles", choices=["singles", "doubles"], help="Battle format for ladder sources (default: doubles; ignored for tournament)")
        meta_parser.add_argument("--usage", action="store_true", help="Query usage stats (default when no target or target is a pokemon name)")
        meta_parser.add_argument("--teams", action="store_true", help="Query tournament teams")
        meta_parser.add_argument("--pokemon", default="", help="Filter teams using this pokemon (with --teams)")
        meta_parser.add_argument("--player", default="", help="Filter teams by player name (with --teams)")
        meta_parser.add_argument("--tournament", default="", help="Filter by tournament name (with --teams)")
        meta_parser.add_argument("--stats", action="store_true", help="Aggregate stats mode (with --teams)")
        meta_parser.add_argument("--teammates", default="", metavar="NAME", help="Most common teammates of this pokemon (with --teams)")
        meta_parser.add_argument("--placing-max", type=int, default=None, help="With --stats: only count teams placing <= N")

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
                if cmd == "survivability":
                    parser.error(f"无法读取覆盖文件 '{path}': {e}")
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
            elif cmd == "usage":
                print("DEPRECATION WARNING: 'usage' is deprecated, use 'meta --usage' instead.", file=sys.stderr)
                result = cmd_meta(target=args.name, top=args.top, online=args.online,
                                  usage=True)
            elif cmd == "teams":
                print("DEPRECATION WARNING: 'teams' is deprecated, use 'meta --teams' instead.", file=sys.stderr)
                result = cmd_meta(target=args.query, top=args.top, online=args.online,
                                  teams=True, pokemon=args.pokemon, player=args.player,
                                  stats=args.stats, teammates=args.teammates,
                                  placing_max=args.placing_max,
                                  tournament=args.tournament)
            elif cmd == "meta":
                result = cmd_meta(
                    target=args.target,
                    top=args.top,
                    online=args.online,
                    source=args.source,
                    battle_format=args.battle_format,
                    usage=args.usage,
                    teams=args.teams,
                    pokemon=args.pokemon,
                    player=args.player,
                    stats=args.stats,
                    teammates=args.teammates,
                    placing_max=args.placing_max,
                    tournament=args.tournament,
                )
            elif cmd == "filter-pokemon":
                min_stats = {}
                max_stats = {}
                for pair in args.min_stat_pairs:
                    stat, val = pair
                    try:
                        min_stats[stat] = int(val)
                    except ValueError:
                        print(json.dumps({"error": f"filter-pokemon --min-stat {stat} 需要整数，收到 '{val}'"},
                                         ensure_ascii=False))
                        return 1
                for pair in args.max_stat_pairs:
                    stat, val = pair
                    try:
                        max_stats[stat] = int(val)
                    except ValueError:
                        print(json.dumps({"error": f"filter-pokemon --max-stat {stat} 需要整数，收到 '{val}'"},
                                         ensure_ascii=False))
                        return 1
                result = cmd_filter_pokemon(
                    type_filters=args.type_filters or None,
                    min_stats=min_stats or None,
                    max_stats=max_stats or None,
                    ability_filters=args.ability_filters or None,
                )
            elif cmd == "lookup":
                result = cmd_lookup(args.name)
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
        except Exception as e:
            # Last-resort guard: never leak a raw traceback to the LLM caller.
            print(json.dumps({"error": f"{cmd} failed: {type(e).__name__}: {e}"},
                             ensure_ascii=False))
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
    except Exception as e:
        # Last-resort guard: never leak a raw traceback to the LLM caller.
        print(json.dumps({"error": f"{cmd} failed: {type(e).__name__}: {e}"},
                         ensure_ascii=False))
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
