#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pokemon damage calculation engine (Phase 2).
Ported from script_res/damage_SV.js and damage_MASTER.js.

Usage:
    from damage import calculate_damage
    result = calculate_damage(attacker, defender, move, field, gen=9)
"""
from __future__ import annotations

import json
import math
import sys
from copy import copy, deepcopy
from pathlib import Path
from typing import Any, Optional

from models import DamageResult, Field, Move, Pokemon
from battle_effects import berries_blocked, effective_ability, effective_weather, ignorable_defender_ability
from tera_effects import apply_tera_effects, resolve_dynamic_tera_move_type
from speed_effects import get_effective_speed
import display_zh
from engine_enums import (
    NATURES_EN,
    T,
    TYPE_ZH_TO_EN,
    resolve_nature_en,
    resolve_tera_type_en,
    resolve_type_en,
    STELLAR_TERA_INPUTS,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

_TYPE_CHART: dict[str, dict[str, float]] | None = None

ATE_IZE_ABILITIES = [
    "Aerilate", "Pixilate", "Refrigerate", "Galvanize", "Normalize", "Dragonize"
]

# Moves that are NOT affected by Ate/Ize type changes
_ATE_IZE_IGNORED_MOVES = {
    "Hidden Power", "Weather Ball", "Natural Gift", "Judgment",
    "Techno Blast", "Revelation Dance", "Multi-Attack", "Terrain Pulse"
}

# Hardcoded move name sets for ability checks (mirrors JS move_data.js flags)
# Moves that are ignored by Parental Bond (Gen 6+)
_PARENTAL_BOND_IGNORED_MOVES = {
    "Counter", "Mirror Coat", "Metal Burst", "Final Gambit",
    "Seismic Toss", "Night Shade", "Dragon Rage", "Sonic Boom",
    "Endeavor", "Sheer Cold", "Fissure", "Horn Drill", "Guillotine",
}

_FIXED_DAMAGE_MOVES = frozenset({
    "Seismic Toss", "Night Shade", "Dragon Rage", "Sonic Boom",
    "Super Fang", "Nature's Madness", "Ruination", "Endeavor", "Final Gambit",
    "Sheer Cold", "Fissure", "Horn Drill", "Guillotine",
})

_PULSE_MOVES = {
    "Water Pulse", "Aura Sphere", "Dark Pulse", "Dragon Pulse",
    "Heal Pulse", "Origin Pulse", "Terrain Pulse",
}

_BITE_MOVES = {
    "Bite", "Hyper Fang", "Crunch", "Poison Fang", "Fire Fang",
    "Ice Fang", "Thunder Fang", "Psychic Fangs", "Jaw Lock", "Fishious Rend",
}

_SECONDARY_EFFECT_MOVES = {
    # Raw-parameter fallback. Named calc also consumes the data-layer
    # has_secondary_effect flag, so this list need not be the sole source.
    "Bite", "Crunch", "Dark Pulse", "Fire Fang", "Ice Fang", "Poison Fang",
    "Thunder Fang", "Thunder Punch", "Water Pulse",
    "Acid", "Blizzard", "Body Slam", "BubbleBeam", "Fire Blast", "Fire Punch",
    "Flamethrower", "Ice Beam", "Ice Punch", "Psychic", "Rock Slide", "Sky Attack",
    "Sludge", "Thunder", "Thunderbolt", "Twineedle", "Stomp",
    "Rolling Kick", "Poison Sting", "Ember", "Psybeam", "Aurora Beam", "Thunder Shock",
    "Lick", "Smog", "Bone Club", "Constrict", "Bubble", "Dizzy Punch", "Tri Attack",
    "Waterfall", "Ancient Power", "Dynamic Punch", "Flame Wheel", "Headbutt", "Icy Wind",
    "Iron Tail", "Sacred Fire", "Shadow Ball", "Sludge Bomb", "Steel Wing", "Zap Cannon",
    "Snore", "Powder Snow", "Mud-Slap", "Octazooka", "Spark", "Dragon Breath", "Metal Claw",
    "Twister", "Rock Smash", "Blaze Kick", "Bounce", "Extrasensory", "Fake Out", "Heat Wave",
    "Luster Purge", "Meteor Mash", "Muddy Water", "Mud Shot", "Rock Tomb", "Signal Beam",
    "Volt Tackle", "Secret Power", "Mist Ball", "Needle Arm", "Astonish", "Silver Wind",
    "Poison Tail", "Air Slash", "Bug Buzz", "Charge Beam", "Chatter", "Cross Poison",
    "Discharge", "Dragon Rush", "Earth Power", "Energy Ball", "Flare Blitz", "Flash Cannon",
    "Focus Blast", "Force Palm", "Gunk Shot", "Iron Head", "Lava Plume", "Mud Bomb",
    "Nature Power", "Poison Jab", "Rock Climb", "Seed Flare", "Zen Headbutt", "Mirror Shot",
    "Ominous Wind", "Electroweb", "Acid Spray", "Blue Flare", "Bolt Strike", "Bulldoze",
    "Fiery Dance", "Flame Charge", "Freeze Shock", "Glaciate", "Hurricane", "Ice Burn",
    "Icicle Crash", "Inferno", "Low Sweep", "Night Daze", "Razor Shell", "Relic Song",
    "Scald", "Searing Shot", "Sludge Wave", "Snarl", "Struggle Bug", "Heart Stamp",
    "Leaf Tornado", "Steamroller", "Diamond Storm", "Freeze-Dry", "Moonblast", "Play Rough",
    "Power-Up Punch", "Mystical Fire", "Steam Eruption", "Nuzzle", "Zing Zap", "Liquidation",
    "Shadow Bone", "Genesis Supernova", "Stoked Sparksurfer", "Trop Kick", "Fire Lash",
    "Lunge", "Anchor Shot", "Throat Chop", "Sparkling Aria", "Spirit Shackle",
    "Clangorous Soulblaze", "Drum Beating", "Pyro Ball", "Aura Wheel", "Breaking Swipe",
    "Apple Acid", "Grav Apple", "Spirit Break", "Strange Steam", "Rapid Spin",
    "Burning Jealousy", "Scorching Sands", "Shell Side Arm", "Skitter Smack", "Eerie Spell",
    "Fiery Wrath", "Freezing Glare", "Thunderous Kick", "Double Iron Bash", "Dire Claw",
    "Psyshield Bash", "Stone Axe", "Springtide Storm", "Mystical Power", "Mountain Gale",
    "Barb Barrage", "Esper Wing", "Bitter Malice", "Triple Arrows", "Infernal Parade",
    "Ceaseless Edge", "Bleakwind Storm", "Wildbolt Storm", "Sandsear Storm", "Axe Kick",
    "Lumina Crash", "Order Up", "Jet Punch", "Salt Cure", "Mortal Spin", "Torch Song",
    "Aqua Step", "Pounce", "Trailblaze", "Chilling Water", "Blazing Torque", "Wicked Torque",
    "Noxious Torque", "Combat Torque", "Magical Torque", "Matcha Gotcha", "Syrup Bomb",
    "Electro Shot", "Alluring Voice", "Psychic Noise", "Upper Hand", "Malignant Chain",
}

# Elemental boost items: item name -> boosted type (Chinese)
# Maps both English and Chinese item names to Chinese type names
# for comparison with move.type in the engine layer.
_ITEM_BOOST_MAP: dict[str, str] = {
    # Water
    "Mystic Water": T.WATER,
    "Sea Incense": T.WATER, "Wave Incense": T.WATER, "Splash Plate": T.WATER,
    # Fire
    "Charcoal": T.FIRE,
    "Flame Plate": T.FIRE,
    # Grass
    "Miracle Seed": T.GRASS,
    "Rose Incense": T.GRASS, "Meadow Plate": T.GRASS,
    # Electric
    "Magnet": T.ELECTRIC,
    "Zap Plate": T.ELECTRIC,
    # Ice
    "Never-Melt Ice": T.ICE, "NeverMeltIce": T.ICE,
    "Icicle Plate": T.ICE,
    # Fighting
    "Black Belt": T.FIGHTING,
    "Fist Plate": T.FIGHTING,
    # Poison
    "Poison Barb": T.POISON,
    "Toxic Plate": T.POISON,
    # Ground
    "Soft Sand": T.GROUND,
    "Earth Plate": T.GROUND,
    # Flying
    "Sharp Beak": T.FLYING,
    "Sky Plate": T.FLYING,
    # Psychic
    "Twisted Spoon": T.PSYCHIC, "TwistedSpoon": T.PSYCHIC,
    "Odd Incense": T.PSYCHIC, "Mind Plate": T.PSYCHIC,
    # Bug
    "Silver Powder": T.BUG, "SilverPowder": T.BUG,
    "Insect Plate": T.BUG,
    # Rock
    "Hard Stone": T.ROCK,
    "Rock Incense": T.ROCK, "Stone Plate": T.ROCK,
    # Ghost
    "Spell Tag": T.GHOST,
    "Spooky Plate": T.GHOST,
    # Dragon
    "Dragon Fang": T.DRAGON,
    "Draco Plate": T.DRAGON,
    # Dark
    "Black Glasses": T.DARK, "BlackGlasses": T.DARK,
    "Dread Plate": T.DARK,
    # Steel
    "Metal Coat": T.STEEL,
    "Iron Plate": T.STEEL,
    # Fairy
    "Fairy Feather": T.FAIRY, "Pixie Plate": T.FAIRY,
    # Normal
    "Silk Scarf": T.NORMAL,
    "Pink Bow": T.NORMAL, "Polkadot Bow": T.NORMAL,
}


# Aura abilities: move type (zh) -> the matching aura ability name.
_AURA_MAP: dict[str, str] = {T.FAIRY: "Fairy Aura", T.DARK: "Dark Aura"}

# Ogerpon's held masks boost all damaging moves by 1.2x on their matching form.
# Teal Ogerpon has no held Teal Mask item.
_OGERPON_MASKS: dict[str, str] = {
    "Wellspring Mask": "Ogerpon-Wellspring",
    "Hearthflame Mask": "Ogerpon-Hearthflame",
    "Cornerstone Mask": "Ogerpon-Cornerstone",
}

# Weather Ball / Terrain Pulse type changes (module-level: rebuilt per call
# was pure overhead).
_WEATHER_BALL_TYPE: dict[str, str] = {
    "Sun": T.FIRE, "Harsh Sun": T.FIRE,
    "Rain": T.WATER, "Heavy Rain": T.WATER,
    "Sand": T.ROCK,
    "Hail": T.ICE, "Snow": T.ICE,
}
_TERRAIN_PULSE_TYPE: dict[str, str] = {
    "Electric": T.ELECTRIC,
    "Grassy": T.GRASS,
    "Misty": T.FAIRY,
    "Psychic": T.PSYCHIC,
}

# Resist berries (halve super-effective moves of the corresponding type).
_RESIST_BERRIES: dict[str, list[str]] = {
    "Normal": ["Chilan Berry"],
    "Fire": ["Occa Berry"],
    "Water": ["Passho Berry"],
    "Electric": ["Wacan Berry"],
    "Grass": ["Rindo Berry"],
    "Ice": ["Yache Berry"],
    "Fighting": ["Chople Berry"],
    "Poison": ["Kebia Berry"],
    "Ground": ["Shuca Berry"],
    "Flying": ["Coba Berry"],
    "Psychic": ["Payapa Berry"],
    "Bug": ["Tanga Berry"],
    "Rock": ["Charti Berry"],
    "Ghost": ["Kasib Berry"],
    "Dragon": ["Haban Berry"],
    "Dark": ["Colbur Berry"],
    "Steel": ["Babiri Berry"],
    "Fairy": ["Roseli Berry"],
}

def _canonical_berry(item_name: str) -> str:
    """Canonicalize the defender item for resist-berry matching.

    Item inputs are normalized to canonical English at the adapter boundary
    (_normalize_item_input), so the legacy zh/slang alias table no longer
    lives in the engine.
    """
    return item_name or ""


def _ate_ize_type_change(move: Move, attacker: Pokemon) -> tuple[Move, bool]:
    """
    Apply Ate/Ize ability type changes (Aerilate, Pixilate, Refrigerate,
    Galvanize, Normalize) and Liquid Voice. Returns (modified_move, is_boosted).
    """
    if (move.is_z or move.name in _ATE_IZE_IGNORED_MOVES
            or (move.name == "Tera Blast" and attacker.is_terastalize)):
        return move, False

    is_boosted = False
    if attacker.ability == "Liquid Voice" and getattr(move, "is_sound", False):
        move.type = T.WATER
    elif attacker.ability in ATE_IZE_ABILITIES:
        if attacker.ability != "Normalize" and move.type == T.NORMAL:
            type_map = {
                "Aerilate": T.FLYING,
                "Pixilate": T.FAIRY,
                "Refrigerate": T.ICE,
                "Galvanize": T.ELECTRIC,
                "Dragonize": T.DRAGON,
            }
            move.type = type_map.get(attacker.ability, move.type)
            is_boosted = True
        elif attacker.ability == "Normalize":
            move.type = T.NORMAL
            is_boosted = True
    return move, is_boosted


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_type_chart() -> dict[str, dict[str, float]]:
    global _TYPE_CHART
    if _TYPE_CHART is None:
        path = DATA_DIR / "type_chart.json"
        # type_chart.json uses Chinese type names as keys
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        # Convert to English keys for internal consistency with JS logic
        chart: dict[str, dict[str, float]] = {}
        for atk_zh, row in raw.items():
            atk_en = TYPE_ZH_TO_EN.get(atk_zh) or atk_zh
            chart[atk_en] = {}
            for def_zh, val in row.items():
                def_en = TYPE_ZH_TO_EN.get(def_zh) or def_zh
                chart[atk_en][def_en] = val
        _TYPE_CHART = chart
    return _TYPE_CHART


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def poke_round(num: float) -> int:
    """GameFreak rounds DOWN on .5 (opposite of normal round)."""
    return math.ceil(num) if (num % 1) > 0.5 else math.floor(num)


def chain_mods(mods: list[int]) -> int:
    """Chain hexadecimal mods together (0x1000 = 1.0x)."""
    M = 0x1000
    for mod in mods:
        M = (M * mod + 0x800) >> 12
    return M


def get_current_types(pokemon: Pokemon) -> list[str]:
    """Return battle types while retaining original types for Tera STAB."""
    tera_type = resolve_tera_type_en(pokemon.tera_type) if pokemon.tera_type else None
    if pokemon.is_terastalize and tera_type and tera_type != "Stellar":
        return [tera_type]
    return [resolve_type_en(t) or t for t in pokemon.types]


def is_grounded(pokemon: Pokemon, field: Field) -> bool:
    """Check if a Pokemon is grounded (affected by terrain effects)."""
    if pokemon.item == "Iron Ball" or field.is_gravity:
        return True
    if T.FLYING in get_current_types(pokemon):
        return False
    if pokemon.item == "Air Balloon":
        return False
    if effective_ability(pokemon, field) in ("Levitate", "Eelevate"):
        return False
    return True

def check_conditional_spread(move, field, attacker, att_is_grounded):
    """Dynamically set is_spread for moves that become spread under certain conditions.

    Mirrors JS checkConditionalSpread() in damage_MASTER.js:
    - Expanding Force becomes spread in Psychic Terrain when attacker is grounded
    - Tera Starstorm becomes spread when used by Terapagos-Stellar
    """
    if (move.name == "Expanding Force" and field.terrain == "Psychic" and att_is_grounded) or        (move.name == "Tera Starstorm" and attacker.name_en == "Terapagos-Stellar"):
        move.is_spread = True


def get_modified_stat(stat: int, mod: int) -> int:
    """Apply stat stage modifiers."""
    if mod > 0:
        return math.floor(stat * (2 + mod) / 2)
    elif mod < 0:
        return math.floor(stat * 2 / (2 - mod))
    return stat


def get_nature_modifier(nature: str, stat: str) -> float:
    """Return nature multiplier for a given stat key.

    Accepts zh / English / alias / any-case nature input via
    engine_enums.resolve_nature_en; unknown values are neutral.
    """
    nature_en = resolve_nature_en(nature)
    boosted, lowered = NATURES_EN.get(nature_en, ("", "")) if nature_en else ("", "")
    if boosted == stat:
        return 1.1
    if lowered == stat:
        return 0.9
    return 1.0


def calc_raw_stat(base: int, iv: int, ev: int, level: int) -> int:
    """Calculate raw stat from base / iv / ev / level."""
    return math.floor((math.floor((2 * base + iv + math.floor(ev / 4)) * level) / 100) + 5)


def calc_hp_stat(base: int, iv: int, ev: int, level: int) -> int:
    """Calculate HP stat (different formula)."""
    return math.floor((math.floor((2 * base + iv + math.floor(ev / 4)) * level) / 100) + level + 10)


def compute_raw_stats(pokemon: Pokemon) -> None:
    """Compute rawStats and stats for a Pokemon, caching on the object."""
    stats = {}
    raw_stats = {}
    for stat_key, base in pokemon.base_stats.items():
        ev = pokemon.evs.get(stat_key, 0)
        iv = pokemon.ivs.get(stat_key, 31)
        if stat_key == "hp":
            raw = calc_hp_stat(base, iv, ev, pokemon.level)
        else:
            raw = calc_raw_stat(base, iv, ev, pokemon.level)
            nature_mod = get_nature_modifier(pokemon.nature, stat_key)
            raw = math.floor(raw * nature_mod)
        raw_stats[stat_key] = raw
        stats[stat_key] = get_modified_stat(raw, pokemon.boosts.get(stat_key, 0))
    pokemon.raw_stats = raw_stats
    pokemon.stats = stats
    if "hp" in raw_stats:
        pokemon.max_hp = raw_stats["hp"]
        if pokemon.current_hp == 0:
            pokemon.current_hp = pokemon.max_hp


# ---------------------------------------------------------------------------
# Type effectiveness
# ---------------------------------------------------------------------------

def _type_effectiveness_for(
    move_en: str,
    def_type_en: str,
    other_type_en: Optional[str],
    is_ghost_revealed: bool,
    is_gravity: bool,
    def_item: str,
    is_strong_winds: bool,
    move_name: str,
) -> float:
    """Effectiveness against a single defending type.

    Mirrors one getMoveEffectiveness() call in damage_SV.js: the special-case
    chain is evaluated per defending type (JS calls it once for type1 and once
    for type2, damage_SV.js:122-123). `other_type_en` corresponds to the JS
    `otherType` parameter used by the Thousand Arrows / Iron Ball rule.
    """
    chart = _load_type_chart()
    if is_ghost_revealed and def_type_en == "Ghost" and move_en in ("Normal", "Fighting"):
        return 1.0
    if ((is_gravity or def_item == "Iron Ball" or move_name == "Thousand Arrows")
            and def_type_en == "Flying" and move_en == "Ground"):
        return 1.0
    if (other_type_en == "Flying" and move_en == "Ground"
            and (move_name == "Thousand Arrows" or def_item == "Iron Ball") and not is_gravity):
        return 1.0
    if move_name == "Freeze-Dry" and def_type_en == "Water":
        return 2.0
    if move_name == "Flying Press":
        return chart["Fighting"].get(def_type_en, 1) * chart["Flying"].get(def_type_en, 1)
    if is_strong_winds and def_type_en == "Flying" and chart[move_en].get(def_type_en, 1) > 1:
        return 1.0
    if def_item == "Ring Target" and chart[move_en].get(def_type_en, 1) == 0:
        return 1.0
    return chart[move_en].get(def_type_en, 1)


def get_move_effectiveness(
    move_type: str,
    def_type1: str,
    def_type2: Optional[str],
    is_ghost_revealed: bool = False,
    is_gravity: bool = False,
    def_item: str = "",
    is_strong_winds: bool = False,
    is_tera_shell: bool = False,
    def_is_tera: bool = False,
    move_name: str = "",
) -> float:
    """Calculate type effectiveness multiplier.

    Dual-type defenders evaluate the special-case chain once per defending
    type (matching damage_SV.js), so e.g. Scrappy hits Ghost/X even when Ghost
    is the secondary type.
    """
    chart = _load_type_chart()
    move_en = TYPE_ZH_TO_EN.get(move_type, move_type)
    type1_en = TYPE_ZH_TO_EN.get(def_type1, def_type1)
    type2_en = TYPE_ZH_TO_EN.get(def_type2, def_type2) if def_type2 else None

    if move_en == "Stellar":
        effectiveness = 2.0 if def_is_tera else 1.0
    else:
        eff1 = _type_effectiveness_for(
            move_en, type1_en, type2_en,
            is_ghost_revealed, is_gravity, def_item, is_strong_winds, move_name,
        )
        if type2_en and type2_en != type1_en:
            eff2 = _type_effectiveness_for(
                move_en, type2_en, type1_en,
                is_ghost_revealed, is_gravity, def_item, is_strong_winds, move_name,
            )
        else:
            eff2 = 1
        effectiveness = eff1 * eff2

    if is_tera_shell and effectiveness >= 1:
        return 0.5
    return effectiveness


# ---------------------------------------------------------------------------
# Immunity checks (port of damage_MASTER.js immunityChecks)
# ---------------------------------------------------------------------------

# Data layer carries no priority field, so priority moves are enumerated here
# (same precedent as _SECONDARY_EFFECT_MOVES). Used by Dazzling / Queenly
# Majesty / Armor Tail and Psychic Terrain immunity checks.
_PRIORITY_MOVES = frozenset({
    "Fake Out", "First Impression", "Extreme Speed", "Sucker Punch",
    "Quick Attack", "Aqua Jet", "Bullet Punch", "Mach Punch", "Ice Shard",
    "Shadow Sneak", "Vacuum Wave", "Water Shuriken",
    "Jet Punch", "Thunderclap", "Accelerock", "Pursuit",
})

def _immunity_check(
    move: Move,
    attacker: Pokemon,
    defender: Pokemon,
    field: Field,
    type_effectiveness: float,
    def_ability: str,
    is_ghost_revealed: bool = False,
) -> Optional[str]:
    """Return an immunity reason suffix when the move cannot deal damage.

    Port of damage_MASTER.js immunityChecks():905. Returns ``None`` when the
    move should proceed, ``""`` for a generic type immunity, or a non-empty
    Chinese reason string for ability / item / weather immunities.
    """
    _reason = display_zh.immunity_reason

    move_type = move.type
    name = move.name
    is_priority = (
        getattr(move, "is_priority", False)
        or name in _PRIORITY_MOVES
        or (name == "Grassy Glide" and field.terrain == "Grassy" and is_grounded(attacker, field))
    )

    if (def_ability == "Wonder Guard" and type_effectiveness <= 1 and name != "Struggle"):
        return _reason(def_ability)
    if move_type == T.GRASS and def_ability == "Sap Sipper":
        return _reason(def_ability)
    if move_type == T.FIRE and def_ability in ("Flash Fire", "Well-Baked Body"):
        return _reason(def_ability)
    if move_type == T.WATER and def_ability in ("Dry Skin", "Storm Drain", "Water Absorb"):
        return _reason(def_ability)
    if move_type == T.ELECTRIC and def_ability in ("Lightning Rod", "Motor Drive", "Volt Absorb"):
        return _reason(def_ability)
    if move_type == T.GROUND and not field.is_gravity and (
            (def_ability == "Levitate" and defender.item != "Iron Ball")
            or def_ability in ("Earth Eater", "Eelevate")):
        # Iron Ball grounds its holder, negating Levitate (game truth; the JS
        # source misses this — round 2 audit 2k).
        return _reason(def_ability)
    if getattr(move, "is_bullet", False) and def_ability == "Bulletproof":
        return _reason(def_ability)
    if getattr(move, "is_sound", False) and def_ability == "Soundproof":
        return _reason(def_ability)
    if getattr(move, "is_wind", False) and def_ability == "Wind Rider":
        return _reason(def_ability)
    if (move_type == T.GROUND and not field.is_gravity
            and defender.item in ("Air Balloon",) and name != "Thousand Arrows"):
        return display_zh.REASON_AIR_BALLOON
    if (field.weather == "Harsh Sun" and move_type == T.WATER) or (field.weather == "Heavy Rain" and move_type == T.FIRE):
        return display_zh.REASON_WEATHER_LOCK
    if name == "Sky Drop" and (T.FLYING in get_current_types(defender) or defender.weight >= 200.0 or field.is_gravity):
        return display_zh.REASON_SKY_DROP
    if name == "Synchronoise" and not (set(get_current_types(attacker)) & set(get_current_types(defender))):
        return display_zh.REASON_SYNCHRONOISE
    if defender.is_dynamax and name in ("Grass Knot", "Low Kick", "Heat Crash", "Heavy Slam"):
        return display_zh.REASON_DYNAMAX_WEIGHT
    if ((def_ability == "Damp" or attacker.ability == "Damp")
            and name in ("Self-Destruct", "Explosion", "Mind Blown", "Misty Explosion")):
        return _reason("Damp")
    if name == "Fling" and _cant_fling_item(attacker.item, attacker):
        return display_zh.REASON_UNFLINGABLE
    if name == "Natural Gift" and "Berry" not in attacker.item:
        return display_zh.REASON_NATURAL_GIFT
    if def_ability in ("Queenly Majesty", "Dazzling", "Armor Tail") and is_priority:
        return _reason(def_ability)
    if field.terrain == "Psychic" and is_priority and is_grounded(defender, field):
        return display_zh.REASON_PSYCHIC_TERRAIN
    if name == "Dream Eater" and defender.status != "Asleep":
        return display_zh.REASON_DREAM_EATER

    if type_effectiveness == 0:
        return ""
    return None


# ---------------------------------------------------------------------------
# Physical / Special determination
# ---------------------------------------------------------------------------

def uses_physical_attack(attacker: Pokemon, defender: Pokemon, move: Move) -> bool:
    """Determine the attack category, independently of the defending stat.

    Psyshock-family moves remain Special: ``deals_physical_damage`` only
    selects the defender's Physical Defense and must not enable burn, Reflect,
    or other physical-category modifiers.
    """
    if move.name in ("Photon Geyser", "Light That Burns the Sky"):
        return attacker.stats.get("attack", 0) > attacker.stats.get("sp_attack", 0)
    if move.name == "Tera Blast" and attacker.is_terastalize:
        return attacker.stats.get("attack", 0) > attacker.stats.get("sp_attack", 0)
    if move.name == "Tera Starstorm":
        if attacker.name_en.removesuffix("-Tera") == "Terapagos-Stellar" and attacker.is_terastalize:
            return attacker.stats.get("attack", 0) > attacker.stats.get("sp_attack", 0)
        return False
    return move.category == "Physical"


def uses_physical_defense(attacker: Pokemon, defender: Pokemon, move: Move) -> bool:
    """Determine whether damage is calculated against the target's Defense."""
    return uses_physical_attack(attacker, defender, move) or move.deals_physical_damage


# ---------------------------------------------------------------------------
# Base Power
# ---------------------------------------------------------------------------

def _count_positive_boosts(boosts: dict) -> int:
    """Sum of positive stat stages (JS countBoosts in damage_MASTER.js:575)."""
    return sum(v for v in boosts.values() if isinstance(v, (int, float)) and v > 0)


# Items that cannot be removed by Knock Off (item_data.js cantRemoveItem:867).
_SPECIES_LOCKED_ITEMS = {
    "Dialga-Origin": "Adamant Crystal",
    "Palkia-Origin": "Lustrous Globe",
    "Ogerpon-Wellspring": "Wellspring Mask",
    "Ogerpon-Hearthflame": "Hearthflame Mask",
    "Ogerpon-Cornerstone": "Cornerstone Mask",
    "Giratina-Origin": "Griseous Orb",
    "Zacian-Crowned": "Rusted Sword",
    "Zamazenta-Crowned": "Rusted Shield",
}

# English names that match the "ite"/"ite " Mega Stone heuristic but are NOT
# Mega Stones (full scan of the items index, round 2 audit E2). Eviolite and
# White Herb are battle-relevant; the rest are non-holdables kept for safety.
_ITE_HEURISTIC_EXCEPTIONS = {
    "Eviolite", "White Herb", "White Flute", "White Apricorn", "White Dish",
    "White Mane Hair", "Meteorite", "Meteorite Shard", "Suite Key",
    "Armorite Ore", "Dynite Ore", "Black Augurite",
}


def _cant_remove_item(item: str, defender: Pokemon) -> bool:
    """Whether the defender's item is immune to Knock Off.

    Port of item_data.js cantRemoveItem():867, extended with Mega Stones and
    the weather orbs (removable in no game; Champions M-C carries Mega forms).
    """
    if not item:
        return True
    if "ium Z" in item or item.endswith("Ｚ"):
        return True
    if item.endswith(" Seed"):
        return True
    # Mega Stones: "Charizardite X", "Gyaradosite", ...
    if ("ite " in item or item.endswith("ite")) and item not in _ITE_HEURISTIC_EXCEPTIONS:
        return True
    if item in ("Red Orb", "Blue Orb", "Griseous Orb"):
        return True
    if (name_en := (defender.name_en or "")).startswith("Ogerpon") and item in _OGERPON_MASKS:
        return True
    if _SPECIES_LOCKED_ITEMS.get(defender.name_en) == item:
        return True
    if name_en == "Arceus" and " Plate" in item:
        return True
    if name_en == "Genesect" and " Drive" in item:
        return True
    if name_en == "Silvally" and " Memory" in item:
        return True
    return False


def _cant_fling_item(item: str, attacker: Pokemon) -> bool:
    """Whether the attacker's item cannot be thrown with Fling.

    Port of item_data.js cantFlingItem():876. Terrain seeds ARE flingable, so
    this deliberately does not reuse _cant_remove_item's seed rule.
    """
    if not item:
        return True
    if " Gem" in item:
        return True
    if "ium Z" in item or item.endswith("Ｚ"):
        return True
    if item in ("Red Orb", "Blue Orb",
                "Griseous Orb", "Rusted Sword", "Rusted Shield"):
        return True
    if _SPECIES_LOCKED_ITEMS.get(attacker.name_en) == item:
        return True
    if ("ite " in item or item.endswith("ite")) and item not in _ITE_HEURISTIC_EXCEPTIONS:
        return True
    name_en = attacker.name_en or ""
    if name_en == "Arceus" and " Plate" in item:
        return True
    if name_en == "Genesect" and " Drive" in item:
        return True
    if name_en == "Silvally" and " Memory" in item:
        return True
    return False


# Stat keys in JS allStats order (AT, DF, SA, SD, SP): ties resolve to the
# earliest stat, matching damage_MASTER.js:334 allStats.indexOf(Math.max(...)).
_HIGHEST_STAT_ORDER = ("attack", "defense", "sp_attack", "sp_defense", "speed")


def _highest_stat(pokemon: Pokemon) -> str:
    """The pokemon's highest non-HP stat from unboosted stats.

    Protosynthesis / Quark Drive boost exactly this stat (JS
    damage_MASTER.js:332-341). Comparing only attack vs sp_attack wrongly
    boosts offense for mons whose top stat is defense/speed (round 2 audit E1).
    """
    raw = pokemon.raw_stats or pokemon.stats
    best, best_val = _HIGHEST_STAT_ORDER[0], None
    for key in _HIGHEST_STAT_ORDER:
        val = raw.get(key, 0)
        if best_val is None or val > best_val:
            best, best_val = key, val
    return best


def _weather_ball_weather(attacker: Pokemon, field: Field) -> Optional[str]:
    """Weather Ball's user-side weather, without suppressing sand or snow."""
    weather = field.weather
    if attacker.ability == "Mega Sol":
        weather = "Sun"
    if attacker.item == "Utility Umbrella" and weather in ("Sun", "Rain", "Harsh Sun", "Heavy Rain"):
        return None
    return weather


def base_power_func(
    move: Move,
    attacker: Pokemon,
    defender: Pokemon,
    field: Field,
) -> int:
    """Calculate custom base power for variable-power moves.

    Port of the basePowerFunc switch in damage_MASTER.js:1130-1355.
    """
    bp = move.base_power
    name = move.name

    if name == "Gyro Ball":
        own_speed = get_effective_speed(attacker, field, attacker, defender)
        target_speed = get_effective_speed(defender, field, attacker, defender)
        bp = min(150, 25 * target_speed // own_speed + 1) if own_speed else 1
    elif name == "Electro Ball":
        own_speed = get_effective_speed(attacker, field, attacker, defender)
        target_speed = get_effective_speed(defender, field, attacker, defender)
        r = own_speed // target_speed if target_speed else 0
        bp = 150 if r >= 4 else 120 if r >= 3 else 80 if r >= 2 else 60 if r >= 1 else 40
    elif name in ("Low Kick", "Grass Knot"):
        w = defender.weight
        bp = 120 if w >= 200 else 100 if w >= 100 else 80 if w >= 50 else 60 if w >= 25 else 40 if w >= 10 else 20
    elif name in ("Heavy Slam", "Heat Crash"):
        wr = attacker.weight / max(0.1, defender.weight)
        bp = 120 if wr >= 5 else 100 if wr >= 4 else 80 if wr >= 3 else 60 if wr >= 2 else 40
    elif name in ("Eruption", "Water Spout", "Dragon Energy"):
        bp = max(1, math.floor(150 * attacker.current_hp / max(1, attacker.max_hp)))
    elif name in ("Flail", "Reversal"):
        # Exact JS form (damage_MASTER.js:1188): p = floor(48 * curHP / maxHP).
        p = math.floor(48 * attacker.current_hp / max(1, attacker.max_hp))
        bp = 200 if p <= 1 else 150 if p <= 4 else 100 if p <= 9 else 80 if p <= 16 else 40 if p <= 32 else 20
    elif name in ("Crush Grip", "Wring Out"):
        # Game mechanic scales with the TARGET's remaining HP. The local JS
        # copy (damage_MASTER.js:1192) reads attacker.curHP, which is a port
        # bug; see PLAN_2026-09-11 A7 for the recorded divergence.
        bp = max(1, math.floor(120 * defender.current_hp / max(1, defender.max_hp)))
    elif name == "Hard Press":
        bp = max(1, math.floor(100 * defender.current_hp / max(1, defender.max_hp)))
    elif name in ("Stored Power", "Power Trip"):
        bp = 20 + 20 * _count_positive_boosts(attacker.boosts)
    elif name == "Punishment":
        bp = min(200, 60 + 20 * _count_positive_boosts(defender.boosts))
    elif name in ("Hex", "Infernal Parade"):
        if defender.status not in (None, "Healthy"):
            bp *= 2
    elif name == "Smelling Salts" and defender.status == "Paralyzed":
        bp *= 2
    elif name == "Wake-Up Slap" and defender.status == "Asleep":
        bp *= 2
    elif name == "Acrobatics":
        item = attacker.item or ""
        boosted = (
            item == ""
            or item in ("Flying Gem",)
            or item.endswith(" Seed")
            or (item in ("Booster Energy",)
                and attacker.ability in ("Protosynthesis", "Quark Drive"))
        )
        bp = 110 if boosted else 55
    elif name == "Water Shuriken":
        bp = 20 if attacker.ability == "Battle Bond" else 15
    elif name == "Facade":
        if attacker.status in ("Burned", "Paralyzed", "Poisoned", "Badly Poisoned"):
            bp *= 2
    elif name == "Brine" and defender.current_hp <= defender.max_hp // 2:
        bp *= 2
    elif name in ("Venoshock", "Barb Barrage") and defender.status in ("Poisoned", "Badly Poisoned"):
        bp *= 2
    elif name == "Retaliate" and getattr(attacker, "ability_on", False):
        bp *= 2
    elif name == "Knock Off" and defender.item and not _cant_remove_item(defender.item, defender):
        bp = math.floor(bp * 1.5)
    elif name == "Grav Apple" and field.is_gravity:
        bp = 120
    elif name == "Expanding Force" and field.terrain == "Psychic" and is_grounded(attacker, field):
        # Terrain boosts only reach grounded users (JS:1521-1525, audit E6)
        bp = 120
    elif name == "Misty Explosion" and field.terrain == "Misty" and is_grounded(attacker, field):
        bp = 150
    elif name == "Rising Voltage" and field.terrain == "Electric" and is_grounded(defender, field):
        # Surges through the terrain into the grounded *target* (JS:1273-1275)
        bp = 140
    elif name == "Weather Ball" and _weather_ball_weather(attacker, field) in _WEATHER_BALL_TYPE:
        bp *= 2
    elif name == "Terrain Pulse" and field.terrain and is_grounded(attacker, field):
        bp *= 2
    elif name in ("Triple Kick", "Triple Axel") and move.hits > 1:
        # Per-hit powers escalate (e.g. 20/40/60). The engine rolls one damage
        # value per hit, so scale each roll to the per-hit average.
        bp = math.floor(bp * (move.hits + 1) / 2)
    elif name == "Tera Blast" and attacker.is_terastalize and attacker.tera_type in STELLAR_TERA_INPUTS:
        bp = 100
    elif name == "Last Respects":
        bp += 50 * move.fainted_allies
    elif name == "Rage Fist":
        bp += 50 * getattr(move, "times_affected", 0)

    return bp


_TERA_FLOOR_POSITIVE_PRIORITY_MOVES = frozenset({
    "Accelerock", "Aqua Jet", "Bullet Punch", "Extreme Speed", "Fake Out",
    "Feint", "First Impression", "Ice Shard", "Jet Punch", "Mach Punch",
    "Quick Attack", "Shadow Sneak", "Sucker Punch", "Thunderclap",
    "Upper Hand", "Vacuum Wave", "Water Shuriken",
})


def _apply_tera_base_power_floor(base_power: int, move: Move, attacker: Pokemon) -> int:
    """Apply Gen 9's 60 BP floor after base-power modifiers."""
    if (not attacker.is_terastalize or move.category == "Status"
            or move.base_power <= 0 or base_power >= 60
            or getattr(move, "is_multi_hit", False)
            or move.priority > 0 or getattr(move, "is_priority", False)
            or move.name in _TERA_FLOOR_POSITIVE_PRIORITY_MOVES):
        return base_power

    # These 150 BP moves have a Base Power callback in the source rules and
    # keep their HP-scaled value instead of being raised back to 60.
    if move.base_power == 150 and move.name in ("Eruption", "Water Spout", "Dragon Energy"):
        return base_power

    if attacker.tera_type == "Stellar":
        already_boosted = (attacker.name_en != "Terapagos-Stellar"
                           and move.type in getattr(attacker, "stellar_boosted_types", ()))
        if already_boosted:
            return base_power
    elif move.type != attacker.tera_type:
        return base_power

    return 60


# ---------------------------------------------------------------------------
# BP Modifiers
# ---------------------------------------------------------------------------

def calc_bp_mods(
    attacker: Pokemon,
    defender: Pokemon,
    field: Field,
    move: Move,
    ate_ize_boosted: bool,
    base_power: int,
    turn_order: str,
    def_ability: str,
    att_is_grounded: bool,
    def_is_grounded: bool,
    gen: int,
) -> list[int]:
    """Calculate base power modifiers (hex values)."""
    bp_mods: list[int] = []

    # a. Rivalry (斗争心): same gender 1.25x, opposite 0.75x, no effect if unknown/genderless
    if attacker.ability == "Rivalry" and attacker.gender and defender.gender:
        if attacker.gender == defender.gender:
            bp_mods.append(0x1400)  # 1.25x
        else:
            bp_mods.append(0x0C00)  # 0.75x
    # b. Ate/Ize abilities (Pixilate, etc.)
    if ate_ize_boosted and not move.is_z and not attacker.is_dynamax:
        bp_mods.append(0x1333)  # Gen 7+

    # c. Aura abilities (Fairy Aura, Dark Aura, Aura Break)
    expected_aura = _AURA_MAP.get(move.type)
    if expected_aura and not field.is_neutralizing_gas:
        aura_active = (attacker.ability == expected_aura or def_ability == expected_aura)
        aura_break = (attacker.ability == "Aura Break" or def_ability == "Aura Break")
        if aura_active:
            if aura_break and def_ability != "[ignored]":
                bp_mods.append(0x0C00)  # 0.75x
            elif gen > 7 or def_ability != "[ignored]":
                bp_mods.append(0x1548)  # ~1.33x

    # d. Reckless / Iron Fist
    if ((attacker.ability == "Reckless" and move.has_recoil)
            or (attacker.ability == "Iron Fist" and move.is_punch)):
        bp_mods.append(0x1333)

    # d. 1.3x BP abilities (Sheer Force, Sand Force, Analytic, Tough Claws)
    if (attacker.ability == "Sheer Force"
            and (move.has_secondary_effect or move.name in _SECONDARY_EFFECT_MOVES)):
        bp_mods.append(0x14CD)
    elif attacker.ability == "Sand Force" and field.weather == "Sand" and move.type in (T.ROCK, T.STEEL, T.GROUND):
        bp_mods.append(0x14CD)
    elif attacker.ability == "Analytic" and turn_order == "LAST":
        bp_mods.append(0x14CD)
    elif attacker.ability == "Tough Claws" and move.makes_contact:
        bp_mods.append(0x14CD)

    # e. 1.5x BP abilities (Mega Launcher, Strong Jaw, Technician)
    # Technician checks BP AFTER prior mods are applied
    temp_bp = poke_round(base_power * chain_mods(bp_mods) / 0x1000)
    if attacker.ability == "Mega Launcher" and move.name in _PULSE_MOVES:
        bp_mods.append(0x1800)
    elif attacker.ability == "Strong Jaw" and move.name in _BITE_MOVES:
        bp_mods.append(0x1800)
    elif attacker.ability == "Fire Mane" and move.type == T.FIRE:
        bp_mods.append(0x1800)
    elif attacker.ability == "Technician" and temp_bp <= 60:
        bp_mods.append(0x1800)
    elif attacker.ability == "Punk Rock" and getattr(move, "is_sound", False):
        bp_mods.append(0x14CD)
    elif attacker.ability == "Steely Spirit" and move.type == T.STEEL:
        bp_mods.append(0x1800)

    # d. Field abilities
    if field.is_battery and move.category == "Special":
        bp_mods.append(0x14CD)
    if field.is_power_spot:
        bp_mods.append(0x14CD)
    if field.is_steely_spirit and move.type == T.STEEL:
        bp_mods.append(0x1800)

    # e. Helping Hand (1.5x)
    if field.is_helping_hand:
        bp_mods.append(0x1800)

    # Terrain Pulse's 1.5x is Mega Launcher, handled above. Applying another
    # unconditional 1.5x here would double-count the pulse modifier.

    # h. Muscle Band / Wise Glasses (1.1x)
    if attacker.item in ("Muscle Band",) and move.category == "Physical":
        bp_mods.append(0x1199)
    elif attacker.item in ("Wise Glasses",) and move.category == "Special":
        bp_mods.append(0x1199)

    # i. Elemental boost items (1.2x) — Plates, Incenses, type gems, etc.
    boost_type = _ITEM_BOOST_MAP.get(attacker.item)
    if boost_type and boost_type == move.type:
        bp_mods.append(0x1333)

    # i2. Ogerpon masks boost every damaging move for the matching form.
    # The mask is an item, not a move-type booster.
    if (attacker.item in _OGERPON_MASKS
            and (attacker.name_en == "Ogerpon"
                 or attacker.name_en.startswith(_OGERPON_MASKS[attacker.item]))):
        bp_mods.append(0x1333)

    # i3. Punching Glove: punch moves 1.1x (JS:1581-1584)
    if attacker.item in ("Punching Glove",) and move.is_punch:
        bp_mods.append(0x119A)

    # i4. Solar Beam / Solar Blade halve in non-sun weather (JS:1491-1495)
    if (move.name in ("Solar Beam", "SolarBeam", "Solar Blade")
            and effective_weather(attacker, defender, field) not in (None, "", "None", "Sun", "Harsh Sun", "Strong Winds")
            and not (field.weather in ("Rain", "Heavy Rain") and defender.item == "Utility Umbrella")):
        bp_mods.append(0x800)

    # v. Offensive Terrain (Gen9: 0x14CD = ~1.3x)
    if att_is_grounded:
        terrain_multiplier = 0x14CD  # Gen9
        if field.terrain == "Electric" and move.type == T.ELECTRIC:
            bp_mods.append(terrain_multiplier)
        elif field.terrain == "Grassy" and move.type == T.GRASS:
            bp_mods.append(terrain_multiplier)
        elif field.terrain == "Psychic" and move.type == T.PSYCHIC:
            bp_mods.append(terrain_multiplier)

    # w. Defensive Terrain
    if def_is_grounded:
        if field.terrain == "Misty" and move.type == T.DRAGON:
            bp_mods.append(0x800)
        elif field.terrain == "Grassy" and move.name in ("Earthquake", "Bulldoze"):
            bp_mods.append(0x800)

    return bp_mods


# ---------------------------------------------------------------------------
# Attack calculation
# ---------------------------------------------------------------------------

def calc_attack(
    move: Move,
    attacker: Pokemon,
    defender: Pokemon,
    is_critical: bool,
    def_ability: str,
) -> int:
    """Calculate the effective Attack (or Sp. Attack) stat."""
    attack_source = defender if move.name == "Foul Play" else attacker
    uses_def = move.name == "Body Press"
    attack_stat = "defense" if uses_def else ("attack" if move.category == "Physical" else "sp_attack")

    # Unaware
    if def_ability == "Unaware" and attack_source.boosts.get(attack_stat, 0) != 0:
        attack = attack_source.raw_stats.get(attack_stat, 0)
    elif move.name == "Spectral Thief" and defender.boosts.get(attack_stat, 0) > 0:
        combined = min(6, attacker.boosts.get(attack_stat, 0) + defender.boosts.get(attack_stat, 0))
        attack = get_modified_stat(attack_source.raw_stats.get(attack_stat, 0), combined)
    elif move.name in ("Meteor Beam", "Electro Shot"):
        combined = min(6, attack_source.boosts.get(attack_stat, 0) + 1)
        attack = get_modified_stat(attack_source.raw_stats.get(attack_stat, 0), combined)
    elif attack_source.boosts.get(attack_stat, 0) == 0 or (is_critical and attack_source.boosts.get(attack_stat, 0) < 0):
        attack = attack_source.raw_stats.get(attack_stat, 0)
    elif def_ability == "Unaware":
        attack = attack_source.raw_stats.get(attack_stat, 0)
    else:
        attack = attack_source.stats.get(attack_stat, 0)

    # Hustle (applied directly, not as a mod)
    if attacker.ability == "Hustle" and move.category == "Physical":
        attack = poke_round(attack * 3 / 2)

    return attack


# ---------------------------------------------------------------------------
# Attack modifiers
# ---------------------------------------------------------------------------

def calc_at_mods(
    move: Move,
    attacker: Pokemon,
    def_ability: str,
    field: Field,
) -> list[int]:
    """Calculate attack stat modifiers."""
    at_mods: list[int] = []

    # Ruin abilities (suppressed by Neutralizing Gas, JS:1813-1818)
    if (field.is_tablets_of_ruin and move.category == "Physical"
            and attacker.ability != "Tablets of Ruin" and not field.is_neutralizing_gas):
        at_mods.append(0x0C00)
    elif (field.is_vessel_of_ruin and move.category == "Special"
          and attacker.ability != "Vessel of Ruin" and not field.is_neutralizing_gas):
        at_mods.append(0x0C00)

    # Slow Start / Defeatist
    if ((attacker.ability == "Slow Start" and attacker.ability_on)
            or (attacker.ability == "Defeatist" and attacker.current_hp <= attacker.max_hp // 2)):
        at_mods.append(0x800)

    # Flower Gift
    if (attacker.ability == "Flower Gift" and attacker.name_en == "Cherrim"
            and field.weather and "Sun" in field.weather
            and move.category == "Physical"
            and attacker.item not in ("Utility Umbrella",)):
        at_mods.append(0x1800)
    elif field.is_flower_gift_atk and field.weather and "Sun" in field.weather and move.category == "Physical":
        at_mods.append(0x1800)

    # 1.5x offensive abilities
    hp_third = attacker.max_hp // 3
    if ((attacker.ability == "Guts" and attacker.status not in (None, "Healthy") and move.category == "Physical")
            or (attacker.ability == "Toxic Boost" and attacker.status in ("Poisoned", "Badly Poisoned") and move.category == "Physical")
            or (attacker.ability == "Flare Boost" and attacker.status == "Burned" and move.category == "Special")
            or (attacker.ability == "Overgrow" and attacker.current_hp <= hp_third and move.type == T.GRASS)
            or (attacker.ability == "Blaze" and attacker.current_hp <= hp_third and move.type == T.FIRE)
            or (attacker.ability == "Torrent" and attacker.current_hp <= hp_third and move.type == T.WATER)
            or (attacker.ability == "Swarm" and attacker.current_hp <= hp_third and move.type == T.BUG)
            or (attacker.ability == "Dragon's Maw" and move.type == T.DRAGON)
            or (attacker.ability == "Flash Fire" and attacker.ability_on and move.type == T.FIRE)
            or (attacker.ability == "Steelworker" and move.type == T.STEEL)
            or (attacker.ability == "Gorilla Tactics" and move.category == "Physical" and not attacker.is_dynamax)
            or (attacker.ability in ("Plus", "Minus") and attacker.ability_on and move.category == "Special")
            or (attacker.ability == "Sharpness" and move.is_slice)
            or (attacker.ability == "Rocky Payload" and move.type == T.ROCK)):
        at_mods.append(0x1800)
    elif (attacker.ability == "Solar Power" and field.weather and "Sun" in field.weather
          and move.category == "Special" and attacker.item not in ("Utility Umbrella",)):
        at_mods.append(0x1800)

    # 1.3x abilities (Protosynthesis / Quark Drive / Transistor Gen9).
    # Proto/Quark boosts the mon's HIGHEST stat (all five, from unboosted
    # values) — only that stat's offense gets the 1.3x (JS:1714-1716, audit E1).
    proto_quark_stat = _highest_stat(attacker)
    if (((attacker.ability == "Protosynthesis" and (attacker.item in ("Booster Energy",) or (field.weather and "Sun" in field.weather)))
         or (attacker.ability == "Quark Drive" and (attacker.item in ("Booster Energy",) or field.terrain == "Electric")))
            and ((proto_quark_stat == "attack" and move.category == "Physical")
                 or (proto_quark_stat == "sp_attack" and move.category == "Special"))):
        at_mods.append(0x14CD)
    elif attacker.ability == "Transistor" and move.type == T.ELECTRIC:
        at_mods.append(0x14CD)

    # Orichalcum Pulse / Hadron Engine
    if ((attacker.ability == "Orichalcum Pulse" and field.weather == "Sun" and move.category == "Physical"
         and attacker.item != "Utility Umbrella")
            or (attacker.ability == "Hadron Engine" and field.terrain == "Electric" and move.category == "Special")):
        at_mods.append(0x1555)

    # 2.0x abilities
    if ((attacker.ability == "Water Bubble" and move.type == T.WATER)
            or (attacker.ability in ("Huge Power", "Pure Power") and move.category == "Physical")
            or (attacker.ability == "Stakeout" and attacker.ability_on)):
        at_mods.append(0x2000)

    # Supreme Overlord (Gen9): +10% per fainted ally, up to 5 allies (+50%)
    if attacker.ability == "Supreme Overlord" and attacker.fainted_allies > 0:
        overlord_boost = [0x119A, 0x1333, 0x14CD, 0x1666, 0x1800]
        idx = min(attacker.fainted_allies, 5) - 1
        at_mods.append(overlord_boost[idx])

    # 0.5x defensive abilities
    if ((def_ability == "Thick Fat" and move.type in (T.FIRE, T.ICE))
            or (def_ability == "Water Bubble" and move.type == T.FIRE)
            or (def_ability == "Purifying Salt" and move.type == T.GHOST)
            or (def_ability == "Heatproof" and move.type == T.FIRE)):
        at_mods.append(0x800)

    # 2.0x items
    if ((attacker.item == "Thick Club" and attacker.name_en in ("Cubone", "Marowak", "Marowak-Alola") and move.category == "Physical")
            or (attacker.item == "Deep Sea Tooth" and attacker.name_en == "Clamperl" and move.category == "Special")
            or (attacker.item == "Light Ball" and attacker.name_en.startswith("Pikachu"))):
        at_mods.append(0x2000)
    # 1.5x items
    elif ((attacker.item in ("Choice Band",) and move.category == "Physical" and not attacker.is_dynamax)
          or (attacker.item in ("Choice Specs",) and move.category == "Special" and not attacker.is_dynamax)):
        at_mods.append(0x1800)

    return at_mods


# ---------------------------------------------------------------------------
# Defense calculation
# ---------------------------------------------------------------------------

def calc_defense(
    move: Move,
    attacker: Pokemon,
    defender: Pokemon,
    hits_physical: bool,
    is_critical: bool,
    field: Field,
) -> int:
    """Calculate the effective Defense (or Sp. Defense) stat."""
    defense_stat = "defense" if hits_physical else "sp_defense"
    ignores_defense_boosts = (
        move.ignores_defense_boosts
        or move.name in ("Sacred Sword", "Chip Away", "Darkest Lariat")
    )

    if move.name == "Spectral Thief" and defender.boosts.get(defense_stat, 0) > 0:
        defense = defender.raw_stats.get(defense_stat, 0)
    elif attacker.ability == "Unaware" and defender.boosts.get(defense_stat, 0) != 0:
        defense = defender.raw_stats.get(defense_stat, 0)
    elif ignores_defense_boosts and defender.boosts.get(defense_stat, 0) != 0:
        defense = defender.raw_stats.get(defense_stat, 0)
    elif defender.boosts.get(defense_stat, 0) == 0 or (is_critical and defender.boosts.get(defense_stat, 0) > 0):
        defense = defender.raw_stats.get(defense_stat, 0)
    elif ignores_defense_boosts or attacker.ability == "Unaware":
        defense = defender.raw_stats.get(defense_stat, 0)
    else:
        defense = defender.stats.get(defense_stat, 0)

    # Weather defense mods (applied directly)
    # Sand boosts Sp. Defense of Rock-types by 1.5x; Snow boosts Defense of Ice-types.
    current_types = get_current_types(defender)
    if (field.weather == "Sand" and T.ROCK in current_types
            and not hits_physical):
        defense = poke_round(defense * 3 / 2)
    elif (field.weather == "Snow" and T.ICE in current_types
            and hits_physical):
        defense = poke_round(defense * 3 / 2)

    return defense


# ---------------------------------------------------------------------------
# Defense modifiers
# ---------------------------------------------------------------------------

def calc_def_mods(
    move: Move,
    defender: Pokemon,
    field: Field,
    hits_physical: bool,
    def_ability: str,
) -> list[int]:
    """Calculate defense stat modifiers."""
    df_mods: list[int] = []

    # Ruin abilities (suppressed by Neutralizing Gas, JS:1813-1818)
    if (field.is_sword_of_ruin and hits_physical
            and def_ability != "Sword of Ruin" and not field.is_neutralizing_gas):
        df_mods.append(0x0C00)
    elif (field.is_beads_of_ruin and not hits_physical
          and def_ability != "Beads of Ruin" and not field.is_neutralizing_gas):
        df_mods.append(0x0C00)

    # Flower Gift
    if (def_ability == "Flower Gift" and defender.name_en == "Cherrim"
            and field.weather and "Sun" in field.weather
            and not hits_physical
            and defender.item not in ("Utility Umbrella",)):
        df_mods.append(0x1800)
    elif field.is_flower_gift_spd and field.weather and "Sun" in field.weather and not hits_physical:
        df_mods.append(0x1800)

    # 1.5x abilities
    if ((def_ability == "Marvel Scale" and defender.status not in (None, "Healthy") and hits_physical)
            or (def_ability == "Grass Pelt" and field.terrain == "Grassy" and hits_physical)):
        df_mods.append(0x1800)

    # 1.3x abilities (Protosynthesis / Quark Drive on defense): boosts the
    # mon's HIGHEST stat only (JS:1845-1847, audit E1 — defense/speed-highest
    # mons must not get the offense-side boost).
    proto_quark_stat = _highest_stat(defender)
    if (((def_ability == "Protosynthesis" and (defender.item in ("Booster Energy",) or (field.weather and "Sun" in field.weather)))
         or (def_ability == "Quark Drive" and (defender.item in ("Booster Energy",) or field.terrain == "Electric")))
            and ((proto_quark_stat == "defense" and hits_physical)
                 or (proto_quark_stat == "sp_defense" and not hits_physical))):
        df_mods.append(0x14CD)

    # 2.0x abilities
    if def_ability == "Fur Coat" and hits_physical:
        df_mods.append(0x2000)

    # 1.5x items
    if ((defender.item in ("Assault Vest",) and not hits_physical)
            or (defender.item in ("Eviolite",) and defender.can_evolve)
            ):
        df_mods.append(0x1800)
    # 2.0x items
    elif ((defender.item == "Deep Sea Scale" and defender.name_en == "Clamperl" and not hits_physical)
          or (defender.item == "Metal Powder" and defender.name_en == "Ditto" and hits_physical)):
        df_mods.append(0x2000)

    return df_mods


# ---------------------------------------------------------------------------
# Base damage
# ---------------------------------------------------------------------------

def calc_base_damage(level: int, base_power: int, attack: int, defense: int) -> int:
    """Calculate base damage before general modifiers."""
    return math.floor(math.floor((math.floor((2 * level) / 5 + 2) * base_power * attack) / max(1, defense)) / 50 + 2)


# ---------------------------------------------------------------------------
# Final mods
# ---------------------------------------------------------------------------

def calc_final_mods(
    move: Move,
    attacker: Pokemon,
    defender: Pokemon,
    field: Field,
    is_critical: bool,
    type_effectiveness: float,
    def_ability: str,
    hits_physical: bool,
) -> list[int]:
    """Calculate final damage modifiers."""
    final_mods: list[int] = []

    # Screens
    if field.is_aurora_veil and not is_critical and not move.ignores_screens:
        final_mods.append(0xAAC if field.format != "Singles" else 0x800)
    elif field.is_reflect and move.category == "Physical" and not is_critical and not move.ignores_screens:
        final_mods.append(0xAAC if field.format != "Singles" else 0x800)
    elif field.is_light_screen and move.category == "Special" and not is_critical:
        final_mods.append(0xAAC if field.format != "Singles" else 0x800)

    # Neuroforce
    if attacker.ability == "Neuroforce" and type_effectiveness > 1:
        final_mods.append(0x1400)

    # Collision Course / Electro Drift
    if move.name in ("Collision Course", "Electro Drift") and type_effectiveness > 1:
        final_mods.append(0x1555)

    # Sniper
    if attacker.ability == "Sniper" and is_critical:
        final_mods.append(0x1800)

    # Tinted Lens
    if attacker.ability == "Tinted Lens" and type_effectiveness < 1:
        final_mods.append(0x2000)

    # Dynamax Cannon / Behemoth moves
    if move.name in ("Dynamax Cannon", "Behemoth Blade", "Behemoth Bash") and defender.is_dynamax:
        final_mods.append(0x2000)

    # Multiscale / Shadow Shield
    if def_ability in ("Multiscale", "Shadow Shield") and defender.current_hp == defender.max_hp:
        final_mods.append(0x800)

    # Contact reduction - Long Reach ignores contact effects; Punching Glove
    # keeps punch moves contact-free (audit E13)
    is_contact = (move.makes_contact and attacker.ability != "Long Reach"
                  and not (move.is_punch and attacker.item in ("Punching Glove",)))
    if def_ability in ("Fluffy", "Aura Guard") and is_contact:
        final_mods.append(0x800)

    # Punk Rock
    if def_ability == "Punk Rock" and move.is_sound:
        final_mods.append(0x800)

    # Ice Scales
    if def_ability == "Ice Scales" and move.category == "Special":
        final_mods.append(0x800)

    # Friend Guard
    if field.is_friend_guard and def_ability != "[ignored]":
        final_mods.append(0xC00)

    # Solid Rock / Filter / Prism Armor
    if def_ability in ("Solid Rock", "Filter", "Prism Armor") and type_effectiveness > 1:
        final_mods.append(0xC00)

    # Fluffy (fire moves)
    if def_ability == "Fluffy" and move.type == T.FIRE:
        final_mods.append(0x2000)

    # Dry Skin: fire moves deal 1.25x damage
    if def_ability == "Dry Skin" and move.type == T.FIRE:
        final_mods.append(0x1400)

    # Expert Belt
    if attacker.item in ("Expert Belt",) and type_effectiveness > 1:
        final_mods.append(0x1333)
    # Life Orb
    elif attacker.item in ("Life Orb",):
        final_mods.append(0x14CC)

    # Chilan Berry halves Normal damage without a super-effective requirement.
    # Other resist berries still require their corresponding type to be SE.
    move_type_en = move.type
    resist_berries = _RESIST_BERRIES.get(move_type_en, [])
    canonical_item = _canonical_berry(defender.item)
    can_eat_berry = not berries_blocked(attacker, defender, field)
    if can_eat_berry and canonical_item == "Chilan Berry" and move_type_en == T.NORMAL:
        final_mods.append(0x800)
    elif can_eat_berry and canonical_item in resist_berries and type_effectiveness > 1:
        final_mods.append(0x800)

    return final_mods


# ---------------------------------------------------------------------------
# Main calculation entry point
# ---------------------------------------------------------------------------

def _check_seeds(defender: Pokemon, field: Field) -> None:
    """Apply terrain seed boosts to the defender's defensive stats.

    Mirrors the front-end checkSeeds behaviour: when the defender holds
    a seed and the corresponding terrain is active, raise the matching
    defensive stat by one stage.  Seeds are consumed in-game, but the
    calculator treats them as a one-time boost for the current calculation.
    """
    stat = ""
    if field.terrain == "Psychic" and defender.item == "Psychic Seed":
        stat = "sp_defense"
    elif field.terrain == "Misty" and defender.item == "Misty Seed":
        stat = "sp_defense"
    elif field.terrain == "Electric" and defender.item == "Electric Seed":
        stat = "defense"
    elif field.terrain == "Grassy" and defender.item == "Grassy Seed":
        stat = "defense"
    if stat:
        new_boost = min(6, defender.boosts.get(stat, 0) + 1)
        defender.boosts[stat] = new_boost
        defender.stats[stat] = get_modified_stat(defender.raw_stats.get(stat, 0), new_boost)
        defender.item = ""


def calculate_damage(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    gen: int = 9,
    _skip_seeds: bool = False,
    _neutral_damage: bool = False,
) -> DamageResult:
    """
    Calculate damage for a single move.

    Returns a DamageResult containing:
      - damage: list of all possible damage rolls (sorted)
      - min_damage / max_damage
      - description: human-readable summary
      - is_critical, type_effectiveness, stab_applied, burn_applied

    All engine-side normalization, derived-stat calculation and Terrain Seed
    boosts happen on private copies. Caller-owned Pokemon and Move objects,
    including their mutable stat/boost dictionaries, remain unchanged across
    repeated calculations. ``_skip_seeds`` is an internal flag used by the
    Parental Bond recursion: the seed boost persists across both hits in-game,
    so the second hit must not apply it a second time.

    ``_neutral_damage`` is reserved for survivability's synthetic, non-STAB
    probe. It bypasses type effectiveness without replacing defender types,
    preserving explicitly requested weather-based defensive modifiers.
    """

    attacker = copy(attacker)
    defender = copy(defender)
    move = copy(move)
    field = copy(field)
    for pokemon in (attacker, defender):
        pokemon.types = list(pokemon.types)
        pokemon.stellar_boosted_types = list(pokemon.stellar_boosted_types)
        for attr in ("base_stats", "evs", "ivs", "boosts", "raw_stats", "stats"):
            setattr(pokemon, attr, dict(getattr(pokemon, attr)))

    # Engine speaks English (engine-English refactor): normalize type and
    # tera inputs once at entry. zh data-layer values and en/any-case input
    # canonicalize here; unknown strings pass through unchanged.
    attacker.types = [resolve_type_en(t) or t for t in attacker.types]
    defender.types = [resolve_type_en(t) or t for t in defender.types]
    move.type = resolve_type_en(move.type) or move.type
    if attacker.tera_type:
        attacker.tera_type = resolve_tera_type_en(attacker.tera_type)
    if defender.tera_type:
        defender.tera_type = resolve_tera_type_en(defender.tera_type)
    attacker.stellar_boosted_types = [
        resolve_type_en(t) or resolve_tera_type_en(t) or t
        for t in attacker.stellar_boosted_types
    ]
    defender.stellar_boosted_types = [
        resolve_type_en(t) or resolve_tera_type_en(t) or t
        for t in defender.stellar_boosted_types
    ]
    return _calculate_damage_core(attacker, defender, move, field, gen, _skip_seeds, _neutral_damage)


def _calculate_damage_core(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    gen: int,
    _skip_seeds: bool,
    _neutral_damage: bool,
) -> DamageResult:
    # Keep the final private copy in the result. Callers must not reconstruct
    # dynamic type/category/power from the original Move or display text.
    final_move = copy(move)
    for pokemon in (attacker, defender):
        if not pokemon.raw_stats:
            compute_raw_stats(pokemon)
    # Trigger events against the configured abilities before using their
    # temporary effective forms for the current attack.
    apply_tera_effects(attacker, defender, field)
    apply_tera_effects(defender, attacker, field)
    attacker_before = deepcopy(attacker)
    defender_before = deepcopy(defender)
    original_abilities = (attacker.ability, defender.ability)
    attacker.ability = effective_ability(attacker, field)
    defender.ability = effective_ability(defender, field)
    calculation_field = copy(field)
    calculation_field.weather = effective_weather(attacker, defender, field, move_user=False)
    try:
        result = _calculate_damage_impl(
            attacker, defender, final_move, calculation_field, gen, _skip_seeds, _neutral_damage,
        )
    finally:
        attacker.ability, defender.ability = original_abilities
    result.move = final_move
    result.attacker_used = result.attacker_used or attacker_before
    result.defender_used = result.defender_used or defender_before
    result.attacker_used.ability = original_abilities[0]
    result.defender_used.ability = original_abilities[1]
    result.attacker_after = deepcopy(attacker)
    result.defender_after = deepcopy(defender)
    result.field_state = deepcopy(field)
    result.field_used = deepcopy(calculation_field)
    return result


def _with_used_state(
    result: DamageResult,
    attacker_used: Pokemon,
    defender_used: Pokemon,
) -> DamageResult:
    """Attach the post-activation, post-seed state used for this hit."""
    result.attacker_used = attacker_used
    result.defender_used = defender_used
    return result


def _calculate_damage_impl(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    gen: int,
    _skip_seeds: bool,
    _neutral_damage: bool,
) -> DamageResult:
    # Ensure stats are computed
    if not attacker.raw_stats:
        compute_raw_stats(attacker)
    if not defender.raw_stats:
        compute_raw_stats(defender)

    # Terastallization-triggered abilities activate before the move's damage
    # calculation. Apply both sides' pending events against the shared field.
    apply_tera_effects(attacker, defender, field)
    apply_tera_effects(defender, attacker, field)
    dynamic_type = resolve_dynamic_tera_move_type(move, attacker)
    if dynamic_type:
        move.type = dynamic_type
    attacker_used = deepcopy(attacker)
    defender_used = deepcopy(defender)

    # Zero-power fixed-damage moves still need the normal immunity pipeline.
    is_fixed_damage = move.name in _FIXED_DAMAGE_MOVES or move.is_ohko
    if (move.base_power == 0 or move.category == "Status") and not is_fixed_damage:
        return _with_used_state(DamageResult(
            damage=[0],
            min_damage=0,
            max_damage=0,
            description=display_zh.status_move_description(move.name),
        ), attacker_used, defender_used)

    # Attack category and defending stat are separate dimensions. Psyshock,
    # Psystrike and Secret Sword use Special Attack against Physical Defense.
    move.category = "Physical" if uses_physical_attack(attacker, defender, move) else "Special"
    hits_physical = uses_physical_defense(attacker, defender, move)

    # Ability ignore (Mold Breaker, Teravolt, Turboblaze)
    def_ability = ignorable_defender_ability(attacker, defender, field)

    # Terrain Seed one-time defensive boost (public wrapper already
    # copy-protected boosts/stats and rolls the mutation back on exit).
    if not _skip_seeds:
        _check_seeds(defender, field)
    attacker_used = deepcopy(attacker)
    defender_used = deepcopy(defender)

    # Battle Armor / Shell Armor suppress every critical-hit source,
    # including guaranteed-crit moves and Merciless.
    forced_critical = (
        attacker.ability == "Merciless"
        and defender.status in ("Poisoned", "Badly Poisoned")
    )
    is_critical = (move.is_crit or forced_critical) and def_ability not in ("Battle Armor", "Shell Armor")

    # Effective weather for the attacker (Mega Sol treats it as Sun)
    move_weather = effective_weather(attacker, defender, field)

    # Move type changes based on weather / terrain (Weather Ball, Terrain Pulse, etc.)
    if move.name == "Weather Ball":
        move.type = _WEATHER_BALL_TYPE.get(_weather_ball_weather(attacker, field), move.type)
    elif (move.name in ("Terrain Pulse", "Nature Power") and field.terrain
          and (move.name != "Terrain Pulse" or is_grounded(attacker, field))):
        move.type = _TERRAIN_PULSE_TYPE.get(field.terrain, move.type)
    elif move.name == "Tera Blast" and attacker.is_terastalize and attacker.tera_type:
        move.type = attacker.tera_type

    # Turn order (for speed-based moves)
    turn_order = "FIRST" if get_effective_speed(attacker, field, attacker, defender) > get_effective_speed(defender, field, attacker, defender) else "LAST"

    # Base power
    base_power = base_power_func(move, attacker, defender, field)
    base_power = max(1, base_power)

    # Ate/Ize type change (Pixilate, Aerilate, etc.)
    move, ate_ize_boosted = _ate_ize_type_change(move, attacker)
    # Non-Stellar Terastallization replaces the defender's original types.
    # Stellar is the exception: the defender keeps its original typing.
    current_types = get_current_types(defender)
    def_type1 = current_types[0] if current_types else T.NORMAL
    def_type2 = current_types[1] if len(current_types) > 1 else None
    type_effectiveness = get_move_effectiveness(
        move.type, def_type1, def_type2,
        is_ghost_revealed=(attacker.ability in ("Scrappy", "Mind's Eye") or field.is_foresight),
        is_gravity=field.is_gravity,
        def_item=defender.item,
        is_strong_winds=(field.weather == "Strong Winds"),
        is_tera_shell=(def_ability == "Tera Shell" and defender.current_hp == defender.max_hp),
        def_is_tera=defender.is_terastalize,
        move_name=move.name,
    )
    if _neutral_damage:
        type_effectiveness = 1.0

    # Ability / item / weather immunities — port of damage_MASTER.js
    # immunityChecks():905. Uses def_ability (Mold Breaker-aware) so abilities
    # ignored by Mold Breaker / Teravolt / Turboblaze no longer grant immunity.
    immunity_field = copy(field)
    immunity_field.weather = move_weather
    immunity_reason = _immunity_check(
        move, attacker, defender, immunity_field, type_effectiveness, def_ability,
        is_ghost_revealed=(attacker.ability in ("Scrappy", "Mind's Eye") or field.is_foresight),
    )
    if immunity_reason is not None:
        return _with_used_state(DamageResult(
            damage=[0],
            min_damage=0,
            max_damage=0,
            description=display_zh.immune_description(move.name, defender.name, immunity_reason),
            type_effectiveness=0.0,
        ), attacker_used, defender_used)

    if is_fixed_damage:
        if move.name in ("Seismic Toss", "Night Shade"):
            fixed_damage = attacker.level
        elif move.name == "Dragon Rage":
            fixed_damage = 40
        elif move.name == "Sonic Boom":
            fixed_damage = 20
        elif move.name in ("Super Fang", "Nature's Madness", "Ruination"):
            fixed_damage = max(1, math.floor(defender.current_hp / 2)) if defender.current_hp > 0 else 0
        elif move.name == "Endeavor":
            fixed_damage = max(0, defender.current_hp - attacker.current_hp)
        elif move.name == "Final Gambit":
            fixed_damage = attacker.current_hp
        else:  # Sheer Cold / Fissure / Horn Drill / Guillotine
            fixed_damage = defender.current_hp
        return _with_used_state(DamageResult(
            damage=[fixed_damage],
            min_damage=fixed_damage,
            max_damage=fixed_damage,
            description=display_zh.fixed_damage_description(
                attacker.level, attacker.name, move.name,
                defender.level, defender.name, fixed_damage,
            ),
            type_effectiveness=type_effectiveness,
        ), attacker_used, defender_used)

    # Grounded checks for terrain effects
    att_is_grounded = is_grounded(attacker, field)
    def_is_grounded = is_grounded(defender, field)

    # Conditional spread (e.g. Expanding Force in Psychic Terrain)
    check_conditional_spread(move, field, attacker, att_is_grounded)

    # BP mods
    bp_mods = calc_bp_mods(attacker, defender, field, move, ate_ize_boosted, base_power, turn_order, def_ability, att_is_grounded, def_is_grounded, gen)
    base_power = max(1, poke_round(base_power * chain_mods(bp_mods) / 0x1000))
    base_power = _apply_tera_base_power_floor(base_power, move, attacker)

    # Attack
    attack = calc_attack(move, attacker, defender, is_critical, def_ability)
    at_mods = calc_at_mods(move, attacker, def_ability, field)
    attack = max(1, poke_round(attack * chain_mods(at_mods) / 0x1000))

    # Defense
    defense = calc_defense(move, attacker, defender, hits_physical, is_critical, field)
    df_mods = calc_def_mods(move, defender, field, hits_physical, def_ability)
    defense = max(1, poke_round(defense * chain_mods(df_mods) / 0x1000))

    # Base damage
    base_dmg = calc_base_damage(attacker.level, base_power, attack, defense)

    # General mods
    # a. Spread move
    if field.format != "Singles" and move.is_spread:
        base_dmg = poke_round(base_dmg * 0xC00 / 0x1000)
    elif getattr(move, "_parental_bond_child", False):
        base_dmg = poke_round(base_dmg * 0x400 / 0x1000)

    # b. Weather. Hydro Steam's user-side effect is distinct from the
    # target-side Umbrella rule for ordinary Fire/Water weather damage.
    if move_weather:
        if "Sun" in move_weather and move.name == "Hydro Steam":
            if attacker.item != "Utility Umbrella":
                base_dmg = poke_round(base_dmg * 0x1800 / 0x1000)
            elif defender.item != "Utility Umbrella":
                base_dmg = poke_round(base_dmg * 0x800 / 0x1000)
        elif (("Sun" in move_weather and move.type == T.FIRE)
                or ("Rain" in move_weather and move.type == T.WATER)):
            if defender.item not in ("Utility Umbrella",):
                base_dmg = poke_round(base_dmg * 0x1800 / 0x1000)
        elif ((move_weather == "Sun" and move.type == T.WATER)
              or (move_weather == "Rain" and move.type == T.FIRE)) \
                and defender.item not in ("Utility Umbrella",):
            base_dmg = poke_round(base_dmg * 0x800 / 0x1000)

    # c. Critical hit
    if is_critical:
        base_dmg = math.floor(base_dmg * 1.5)

    # STAB
    stab_mod = 0x1000
    move_type_en = move.type
    atk_type1_en = attacker.types[0] if attacker.types else ""
    atk_type2_en = attacker.types[1] if len(attacker.types) > 1 else ""
    tera_type_en = attacker.tera_type or ""

    if attacker.is_terastalize and tera_type_en != "Stellar":
        if move_type_en == tera_type_en and (atk_type1_en == tera_type_en or atk_type2_en == tera_type_en):
            stab_mod = 0x2400 if attacker.ability == "Adaptability" else 0x2000
        elif (move_type_en != tera_type_en and (atk_type1_en == move_type_en or atk_type2_en == move_type_en)) or move_type_en == tera_type_en:
            stab_mod = 0x2000 if (attacker.ability == "Adaptability" and move_type_en == tera_type_en) else 0x1800
    elif attacker.is_terastalize and tera_type_en == "Stellar":
        is_base_stab = move_type_en in (atk_type1_en, atk_type2_en)
        if attacker.name_en == "Terapagos-Stellar" or move_type_en not in attacker.stellar_boosted_types:
            stab_mod = 0x2000 if is_base_stab else 0x1333
        else:
            stab_mod = 0x1800 if is_base_stab else 0x1000
    else:
        if move_type_en in (atk_type1_en, atk_type2_en):
            stab_mod = 0x2000 if attacker.ability == "Adaptability" else 0x1800
        elif attacker.ability in ("Protean", "Libero") and attacker.ability_on:
            stab_mod = 0x1800

    # Burn
    apply_burn = (attacker.status == "Burned" and move.category == "Physical"
                  and attacker.ability != "Guts" and not move.ignores_burn)

    # Final mods
    final_mods = calc_final_mods(move, attacker, defender, field, is_critical, type_effectiveness, def_ability, hits_physical)
    final_mod_val = chain_mods(final_mods)

    # Damage rolls (16 rolls: 85% to 100%)
    damage_rolls: list[int] = []
    for i in range(16):
        dmg = math.floor(base_dmg * (85 + i) / 100)
        dmg = poke_round(dmg * stab_mod / 0x1000)
        dmg = math.floor(dmg * type_effectiveness)
        if apply_burn:
            dmg = math.floor(dmg / 2)
        dmg = poke_round(dmg * final_mod_val / 0x1000)
        dmg = max(1, dmg)
        if dmg > 65535:
            dmg %= 65536
        damage_rolls.append(dmg)

    damage_rolls.sort()

    # A later attack cannot receive the same resist berry reduction again.
    if (_canonical_berry(defender.item) in _RESIST_BERRIES.get(move_type_en, [])
            and (type_effectiveness > 1 or move_type_en == T.NORMAL)
            and not berries_blocked(attacker, defender, field)):
        defender.item = ""

    # Parental Bond: second hit at 25% base damage (Gen 7+). In doubles the
    # second hit only applies to non-spread moves (JS:1980, audit E5).
    _pb_active = (attacker.ability == "Parental Bond"
                 and move.name not in _PARENTAL_BOND_IGNORED_MOVES
                 and move.hits == 1
                 and (field.format == "Singles" or not move.is_spread))
    hit_damage_rolls = None
    if _pb_active:
        second_move = copy(move)
        second_move._parental_bond_child = True
        # Temporarily disable Parental Bond to prevent infinite recursion
        original_ability = attacker.ability
        attacker.ability = ""
        try:
            # _skip_seeds: the seed boost persists across both hits, so the
            # second hit keeps the stage already applied above (audit E4).
            second_result = calculate_damage(attacker, defender, second_move, field, gen,
                                             _skip_seeds=True, _neutral_damage=_neutral_damage)
        finally:
            attacker.ability = original_ability

        # Merge damage rolls: all combinations of first + second hit
        hit_damage_rolls = [list(damage_rolls), list(second_result.damage)]
        merged_rolls: list[int] = []
        for d1 in damage_rolls:
            for d2 in second_result.damage:
                merged_rolls.append(d1 + d2)
        merged_rolls.sort()
        damage_rolls = merged_rolls

    # Both hits of one Parental Bond attack share the first-use bonus.
    if (attacker.is_terastalize and tera_type_en == "Stellar"
            and attacker.name_en != "Terapagos-Stellar"
            and move_type_en not in attacker.stellar_boosted_types
            and damage_rolls and damage_rolls[-1] > 0):
        attacker.stellar_boosted_types.append(move_type_en)

    if (attacker.is_terastalize and tera_type_en == "Stellar"
            and move.name == "Tera Blast" and damage_rolls and damage_rolls[-1] > 0):
        delta = 1 if attacker.ability == "Contrary" else -2 if attacker.ability == "Simple" else -1
        for stat in ("attack", "sp_attack"):
            attacker.boosts[stat] = max(-6, min(6, attacker.boosts.get(stat, 0) + delta))
            attacker.stats[stat] = get_modified_stat(
                attacker.raw_stats.get(stat, 0), attacker.boosts[stat],
            )

    # Build description — copy assembly lives in display_zh; the
    # {eff}{crit}{burn}{pb} segments stay an atomic ordered unit.
    description = display_zh.main_description(
        attacker.level, attacker.name, move.name,
        defender.level, defender.name,
        type_effectiveness, is_critical, apply_burn, _pb_active,
        base_power, attack, defense,
        damage_rolls[0], damage_rolls[-1],
    )

    return _with_used_state(DamageResult(
        damage=damage_rolls,
        min_damage=damage_rolls[0],
        max_damage=damage_rolls[-1],
        description=description,
        is_critical=is_critical,
        type_effectiveness=type_effectiveness,
        stab_applied=stab_mod != 0x1000,
        burn_applied=apply_burn,
        effective_power=base_power,
        hit_damage_rolls=hit_damage_rolls,
    ), attacker_used, defender_used)
