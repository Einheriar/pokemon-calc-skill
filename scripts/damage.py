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
from copy import copy
from pathlib import Path
from typing import Any, Optional

from models import DamageResult, Field, Move, Pokemon

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"

_TYPE_CHART: dict[str, dict[str, float]] | None = None

# Chinese <-> English type mapping (aligned with data files and JS engine)
_TYPE_ZH_TO_EN: dict[str, str] = {
    "一般": "Normal", "格斗": "Fighting", "飞行": "Flying", "毒": "Poison",
    "地面": "Ground", "岩石": "Rock", "虫": "Bug", "幽灵": "Ghost",
    "钢": "Steel", "火": "Fire", "水": "Water", "草": "Grass",
    "电": "Electric", "超能力": "Psychic", "冰": "Ice", "龙": "Dragon",
    "恶": "Dark", "妖精": "Fairy",
}
_TYPE_EN_TO_ZH = {v: k for k, v in _TYPE_ZH_TO_EN.items()}

# Nature modifiers (zh name -> (boosted stat, lowered stat))
# Stats use English keys to match JS internals
NATURES: dict[str, tuple[str, str]] = {
    "勤奋": ("", ""), "固执": ("attack", "sp_attack"), "顽皮": ("attack", "defense"),
    "勇敢": ("attack", "speed"), " lonely": ("attack", "defense"),
    "大胆": ("defense", "attack"), "淘气": ("defense", "sp_attack"),
    "乐天": ("defense", "speed"), "悠闲": ("defense", "speed"),
    "内敛": ("sp_attack", "attack"), "慢吞吞": ("sp_attack", "defense"),
    "马虎": ("sp_attack", "sp_defense"), "冷静": ("sp_attack", "speed"),
    "温和": ("sp_defense", "attack"), "温顺": ("sp_defense", "defense"),
    "慎重": ("sp_defense", "sp_attack"), "自大": ("sp_defense", "speed"),
    "胆小": ("speed", "attack"), "急躁": ("speed", "defense"),
    "爽朗": ("speed", "sp_attack"), "天真": ("speed", "sp_defense"),
}

# Common Chinese nature aliases (English -> Chinese)
# Note: setdex presets use capitalized English names (e.g. "Adamant", "Jolly"),
# so these keys must match the lowercase form exactly.
_NATURE_ALIASES: dict[str, str] = {
    "adamant": "固执", "modest": "内敛", "jolly": "爽朗", "timid": "胆小",
    "brave": "勇敢", "bold": "大胆", "impish": "淘气", "careful": "慎重",
    "calm": "温和", "quiet": "冷静", "sassy": "自大", "relaxed": "悠闲",
    "lonely": "孤独", "mild": "慢吞吞", "gentle": "温顺", "hasty": "急躁",
    "naive": "天真", "rash": "马虎", "naughty": "顽皮", "lax": "乐天",
    "hardy": "勤奋",
}

ATE_IZE_ABILITIES = [
    "Aerilate", "Pixilate", "Refrigerate", "Galvanize", "Normalize"
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

_PULSE_MOVES = {
    "Water Pulse", "Aura Sphere", "Dark Pulse", "Dragon Pulse",
    "Heal Pulse", "Origin Pulse", "Terrain Pulse",
}

_BITE_MOVES = {
    "Bite", "Hyper Fang", "Crunch", "Poison Fang", "Fire Fang",
    "Ice Fang", "Thunder Fang", "Psychic Fangs", "Jaw Lock", "Fishious Rend",
}

_SECONDARY_EFFECT_MOVES = {
    "Acid", "Blizzard", "Body Slam", "BubbleBeam", "Fire Blast", "Fire Punch",
    "Flamethrower", "Ice Beam", "Ice Punch", "Psychic", "Rock Slide", "Sky Attack",
    "Sludge", "Thunder", "ThunderPunch", "Thunderbolt", "Twineedle", "Stomp",
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
    "Mystic Water": "水", "神秘水滴": "水",
    "Sea Incense": "水", "Wave Incense": "水", "Splash Plate": "水",
    # Fire
    "Charcoal": "火", "木炭": "火",
    "Flame Plate": "火",
    # Grass
    "Miracle Seed": "草", "奇迹种子": "草",
    "Rose Incense": "草", "Meadow Plate": "草",
    # Electric
    "Magnet": "电", "磁铁": "电",
    "Zap Plate": "电",
    # Ice
    "Never-Melt Ice": "冰", "NeverMeltIce": "冰", "不融冰": "冰",
    "Icicle Plate": "冰",
    # Fighting
    "Black Belt": "格斗", "黑带": "格斗",
    "Fist Plate": "格斗",
    # Poison
    "Poison Barb": "毒", "毒针": "毒",
    "Toxic Plate": "毒",
    # Ground
    "Soft Sand": "地面", "柔软沙子": "地面",
    "Earth Plate": "地面",
    # Flying
    "Sharp Beak": "飞行", "锐利鸟嘴": "飞行",
    "Sky Plate": "飞行",
    # Psychic
    "Twisted Spoon": "超能力", "TwistedSpoon": "超能力", "弯曲的汤匙": "超能力",
    "Odd Incense": "超能力", "Mind Plate": "超能力",
    # Bug
    "Silver Powder": "虫", "SilverPowder": "虫", "银色粉": "虫",
    "Insect Plate": "虫",
    # Rock
    "Hard Stone": "岩石", "硬石头": "岩石",
    "Rock Incense": "岩石", "Stone Plate": "岩石",
    # Ghost
    "Spell Tag": "幽灵", "诅咒之符": "幽灵",
    "Spooky Plate": "幽灵",
    # Dragon
    "Dragon Fang": "龙", "龙之牙": "龙",
    "Draco Plate": "龙",
    # Dark
    "Black Glasses": "恶", "BlackGlasses": "恶", "黑色眼镜": "恶",
    "Dread Plate": "恶",
    # Steel
    "Metal Coat": "钢", "金属膜": "钢",
    "Iron Plate": "钢",
    # Fairy
    "Fairy Feather": "妖精", "Pixie Plate": "妖精",
    # Normal
    "Silk Scarf": "一般", "丝绸围巾": "一般",
    "Pink Bow": "一般", "Polkadot Bow": "一般",
}


def _ate_ize_type_change(move: Move, attacker: Pokemon) -> tuple[Move, bool]:
    """
    Apply Ate/Ize ability type changes (Aerilate, Pixilate, Refrigerate,
    Galvanize, Normalize) and Liquid Voice. Returns (modified_move, is_boosted).
    """
    if move.is_z or move.name in _ATE_IZE_IGNORED_MOVES:
        return move, False

    is_boosted = False
    if attacker.ability == "Liquid Voice" and getattr(move, "is_sound", False):
        move.type = "水"
    elif attacker.ability in ATE_IZE_ABILITIES:
        if attacker.ability != "Normalize" and move.type == "一般":
            type_map = {
                "Aerilate": "飞行",
                "Pixilate": "妖精",
                "Refrigerate": "冰",
                "Galvanize": "电",
            }
            move.type = type_map.get(attacker.ability, move.type)
            is_boosted = True
        elif attacker.ability == "Normalize":
            move.type = "一般"
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
            atk_en = _TYPE_ZH_TO_EN.get(atk_zh) or atk_zh
            chart[atk_en] = {}
            for def_zh, val in row.items():
                def_en = _TYPE_ZH_TO_EN.get(def_zh) or def_zh
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


def is_grounded(pokemon: Pokemon, field: Field) -> bool:
    """Check if a Pokemon is grounded (affected by terrain effects)."""
    if pokemon.item == "Iron Ball" or field.is_gravity:
        return True
    if "飞行" in pokemon.types:
        return False
    if pokemon.item == "Air Balloon":
        return False
    if pokemon.ability == "Levitate":
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
    """Return nature multiplier for a given stat key."""
    nature_zh = _NATURE_ALIASES.get(nature.lower(), nature)
    boosted, lowered = NATURES.get(nature_zh, ("", ""))
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
    """Calculate type effectiveness multiplier."""
    chart = _load_type_chart()
    move_en = _TYPE_ZH_TO_EN.get(move_type, move_type)
    type1_en = _TYPE_ZH_TO_EN.get(def_type1, def_type1)
    type2_en = _TYPE_ZH_TO_EN.get(def_type2, def_type2) if def_type2 else None

    if is_tera_shell and chart[move_en].get(type1_en, 1) >= 0.5:
        return 0.5
    if move_en == "Stellar" and def_is_tera:
        return 2.0
    if is_ghost_revealed and type1_en == "Ghost" and move_en in ("Normal", "Fighting"):
        return 1.0
    if ((is_gravity or def_item == "Iron Ball" or move_name == "Thousand Arrows")
            and type1_en == "Flying" and move_en == "Ground"):
        return 1.0
    if (type2_en == "Flying" and move_en == "Ground"
            and (move_name == "Thousand Arrows" or def_item == "Iron Ball") and not is_gravity):
        return 1.0
    if move_name == "Freeze-Dry" and type1_en == "Water":
        return 2.0
    if move_name == "Flying Press":
        return chart["Fighting"].get(type1_en, 1) * chart["Flying"].get(type1_en, 1)
    if is_strong_winds and type1_en == "Flying" and chart[move_en].get(type1_en, 1) > 1:
        return 1.0
    if def_item == "Ring Target" and chart[move_en].get(type1_en, 1) == 0:
        return 1.0

    eff1 = chart[move_en].get(type1_en, 1)
    if type2_en and type2_en != type1_en and move_en != "Stellar":
        eff2 = chart[move_en].get(type2_en, 1)
    else:
        eff2 = 1
    return eff1 * eff2


# ---------------------------------------------------------------------------
# Physical / Special determination
# ---------------------------------------------------------------------------

def uses_physical_attack(attacker: Pokemon, defender: Pokemon, move: Move) -> bool:
    """Determine if a move uses the Physical category."""
    if move.name == "Photon Geyser" or move.name == "Light That Burns the Sky":
        return attacker.stats.get("attack", 0) > attacker.stats.get("sp_attack", 0)
    if move.name == "Tera Blast" and attacker.is_terastalize:
        return attacker.stats.get("attack", 0) > attacker.stats.get("sp_attack", 0)
    if move.category == "Physical":
        return True
    if move.deals_physical_damage:  # type: ignore[attr-defined]
        return True
    return False


# ---------------------------------------------------------------------------
# Base Power
# ---------------------------------------------------------------------------

def base_power_func(
    move: Move,
    attacker: Pokemon,
    defender: Pokemon,
    field: Field,
    turn_order: str,
) -> int:
    """Calculate custom base power for variable-power moves."""
    bp = move.base_power
    name = move.name

    if name == "Gyro Ball":
        bp = min(150, math.floor(25 * defender.stats.get("speed", 1) / max(1, attacker.stats.get("speed", 1))))
    elif name == "Electro Ball":
        r = math.floor(attacker.stats.get("speed", 1) / max(1, defender.stats.get("speed", 1)))
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
        ratio = attacker.current_hp / max(1, attacker.max_hp)
        bp = 200 if ratio <= 0.0417 else 150 if ratio <= 0.104 else 100 if ratio <= 0.208 else 80 if ratio <= 0.354 else 40 if ratio <= 0.688 else 20
    elif name == "Water Shuriken" and attacker.name_en == "Greninja-Ash":
        bp = 20
    elif name == "Facade" and attacker.status not in (None, "Healthy"):
        bp = 70
    elif name in ("Brine", "Venoshock") and attacker.current_hp <= attacker.max_hp // 2:
        bp *= 2
    elif name == "Retaliate" and getattr(attacker, "ability_on", False):
        bp *= 2
    elif name == "Earthquake" and defender.item == "Float Stone":
        pass  # No BP change, handled elsewhere
    elif name == "Bulldoze" and defender.item == "Float Stone":
        pass
    elif name in ("Knock Off",) and defender.item != "":
        bp = math.floor(bp * 1.5)
    elif name == "Grav Apple" and field.is_gravity:
        bp = 120
    elif name == "Expanding Force" and field.terrain == "Psychic":
        bp = 120
    elif name == "Misty Explosion" and field.terrain == "Misty":
        bp = 150
    elif name == "Rising Voltage" and field.terrain == "Electric":
        bp = 140
    elif name == "Weather Ball" and field.weather and field.weather not in ("", "Strong Winds"):
        bp *= 2
    elif name == "Terrain Pulse" and field.terrain:
        bp *= 2
    elif name == "Last Respects":
        bp += 50 * move.fainted_allies

    return bp


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
) -> list[int]:
    """Calculate base power modifiers (hex values)."""
    bp_mods: list[int] = []

    # a. Rivalry (omitted for simplicity; add if needed)
    # b. Ate/Ize abilities (Pixilate, etc.)
    if ate_ize_boosted and not move.is_z and not attacker.is_dynamax:
        bp_mods.append(0x1333)  # Gen 7+

    # c. Reckless / Iron Fist
    if ((attacker.ability == "Reckless" and move.has_recoil)
            or (attacker.ability == "Iron Fist" and move.is_punch)):
        bp_mods.append(0x1333)

    # d. 1.3x BP abilities (Sheer Force, Sand Force, Analytic, Tough Claws)
    if attacker.ability == "Sheer Force" and move.name in _SECONDARY_EFFECT_MOVES:
        bp_mods.append(0x14CD)
    elif attacker.ability == "Sand Force" and field.weather == "Sand" and move.type in ("岩石", "钢", "地面"):
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
    elif attacker.ability == "Technician" and temp_bp <= 60:
        bp_mods.append(0x1800)

    # d. Field abilities
    if field.is_battery and move.category == "Special":
        bp_mods.append(0x14CD)
    if field.is_power_spot:
        bp_mods.append(0x14CD)
    if field.is_steely_spirit and move.type == "钢":
        bp_mods.append(0x1800)

    # e. Helping Hand
    if field.is_helping_hand:
        bp_mods.append(0x14CD)

    # f. Charge, Power Spot etc omitted for brevity
    # g. Terrain pulse
    if move.name == "Terrain Pulse" and field.terrain:
        bp_mods.append(0x1800)

    # h. Muscle Band / Wise Glasses (1.1x)
    if attacker.item in ("Muscle Band", "力量头带") and move.category == "Physical":
        bp_mods.append(0x1199)
    elif attacker.item in ("Wise Glasses", "博识眼镜") and move.category == "Special":
        bp_mods.append(0x1199)

    # i. Elemental boost items (1.2x) — Plates, Incenses, type gems, etc.
    boost_type = _ITEM_BOOST_MAP.get(attacker.item)
    if boost_type and boost_type == move.type:
        bp_mods.append(0x1333)

    # v. Offensive Terrain (Gen9: 0x14CD = ~1.3x)
    if att_is_grounded:
        terrain_multiplier = 0x14CD  # Gen9
        if field.terrain == "Electric" and move.type == "电":
            bp_mods.append(terrain_multiplier)
        elif field.terrain == "Grassy" and move.type == "草":
            bp_mods.append(terrain_multiplier)
        elif field.terrain == "Psychic" and move.type == "超能力":
            bp_mods.append(terrain_multiplier)

    # w. Defensive Terrain
    if def_is_grounded:
        if field.terrain == "Misty" and move.type == "龙":
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

    # Ruin abilities
    if field.is_tablets_of_ruin and move.category == "Physical" and attacker.ability != "Tablets of Ruin":
        at_mods.append(0x0C00)
    elif field.is_vessel_of_ruin and move.category == "Special" and attacker.ability != "Vessel of Ruin":
        at_mods.append(0x0C00)

    # Slow Start / Defeatist
    if ((attacker.ability == "Slow Start" and attacker.ability_on)
            or (attacker.ability == "Defeatist" and attacker.current_hp <= attacker.max_hp // 2)):
        at_mods.append(0x800)

    # Flower Gift
    if (attacker.ability == "Flower Gift" and attacker.name_en == "Cherrim"
            and field.weather and "Sun" in field.weather
            and move.category == "Physical" and attacker.item != "大晴天伞"):
        at_mods.append(0x1800)
    elif field.is_flower_gift_atk and field.weather and "Sun" in field.weather and move.category == "Physical":
        at_mods.append(0x1800)

    # 1.5x offensive abilities
    hp_third = attacker.max_hp // 3
    if ((attacker.ability == "Guts" and attacker.status not in (None, "Healthy") and move.category == "Physical")
            or (attacker.ability == "Overgrow" and attacker.current_hp <= hp_third and move.type == "草")
            or (attacker.ability == "Blaze" and attacker.current_hp <= hp_third and move.type == "火")
            or (attacker.ability == "Torrent" and attacker.current_hp <= hp_third and move.type == "水")
            or (attacker.ability == "Swarm" and attacker.current_hp <= hp_third and move.type == "虫")
            or (attacker.ability == "Dragon's Maw" and move.type == "龙")
            or (attacker.ability == "Flash Fire" and attacker.ability_on and move.type == "火")
            or (attacker.ability == "Steelworker" and move.type == "钢")
            or (attacker.ability == "Gorilla Tactics" and move.category == "Physical" and not attacker.is_dynamax)
            or (attacker.ability in ("Plus", "Minus") and attacker.ability_on)
            or (attacker.ability == "Sharpness" and move.is_slice)
            or (attacker.ability == "Rocky Payload" and move.type == "岩石")):
        at_mods.append(0x1800)
    elif (attacker.ability == "Solar Power" and field.weather and "Sun" in field.weather
          and move.category == "Special" and attacker.item != "大晴天伞"):
        at_mods.append(0x1800)

    # 1.3x abilities (Protosynthesis / Quark Drive / Transistor Gen9)
    if (((attacker.ability == "Protosynthesis" and (attacker.item in ("Booster Energy", "驱劲能量") or (field.weather and "Sun" in field.weather)))
         or (attacker.ability == "Quark Drive" and (attacker.item in ("Booster Energy", "驱劲能量") or field.terrain == "Electric")))
            and ((attacker.stats.get("attack", 0) >= attacker.stats.get("sp_attack", 0) and move.category == "Physical")
                 or (attacker.stats.get("sp_attack", 0) > attacker.stats.get("attack", 0) and move.category == "Special"))):
        at_mods.append(0x14CD)
    elif attacker.ability == "Transistor" and move.type == "电":
        at_mods.append(0x14CD)

    # Orichalcum Pulse / Hadron Engine
    if ((attacker.ability == "Orichalcum Pulse" and field.weather == "Sun" and move.category == "Physical")
            or (attacker.ability == "Hadron Engine" and field.terrain == "Electric" and move.category == "Special")):
        at_mods.append(0x1555)

    # 2.0x abilities
    if ((attacker.ability == "Water Bubble" and move.type == "水")
            or (attacker.ability in ("Huge Power", "Pure Power") and move.category == "Physical")
            or (attacker.ability == "Stakeout" and attacker.ability_on)):
        at_mods.append(0x2000)

    # Supreme Overlord (Gen9): +10% per fainted ally, up to 5 allies (+50%)
    if attacker.ability == "Supreme Overlord" and attacker.fainted_allies > 0:
        overlord_boost = [0x119A, 0x1333, 0x14CD, 0x1666, 0x1800]
        idx = min(attacker.fainted_allies, 5) - 1
        at_mods.append(overlord_boost[idx])

    # 0.5x defensive abilities
    if ((def_ability == "Thick Fat" and move.type in ("火", "冰"))
            or (def_ability == "Water Bubble" and move.type == "火")
            or (def_ability == "Purifying Salt" and move.type == "幽灵")
            or (def_ability == "Heatproof" and move.type == "火")):
        at_mods.append(0x800)

    # 2.0x items
    if ((attacker.item == "Thick Club" and attacker.name_en in ("Cubone", "Marowak", "Marowak-Alola") and move.category == "Physical")
            or (attacker.item == "Deep Sea Tooth" and attacker.name_en == "Clamperl" and move.category == "Special")
            or (attacker.item == "Light Ball" and attacker.name_en.startswith("Pikachu"))):
        at_mods.append(0x2000)
    # 1.5x items
    elif ((attacker.item in ("讲究头带", "Choice Band") and move.category == "Physical" and not attacker.is_dynamax)
          or (attacker.item in ("讲究眼镜", "Choice Specs") and move.category == "Special" and not attacker.is_dynamax)):
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

    if move.name == "Spectral Thief" and defender.boosts.get(defense_stat, 0) > 0:
        defense = defender.raw_stats.get(defense_stat, 0)
    elif attacker.ability == "Unaware" and defender.boosts.get(defense_stat, 0) != 0:
        defense = defender.raw_stats.get(defense_stat, 0)
    elif move.ignores_screens and defender.boosts.get(defense_stat, 0) != 0:  # Chip Away / Sacred Sword
        defense = defender.raw_stats.get(defense_stat, 0)
    elif defender.boosts.get(defense_stat, 0) == 0 or (is_critical and defender.boosts.get(defense_stat, 0) > 0):
        defense = defender.raw_stats.get(defense_stat, 0)
    elif move.ignores_screens or attacker.ability == "Unaware":
        defense = defender.raw_stats.get(defense_stat, 0)
    else:
        defense = defender.stats.get(defense_stat, 0)

    # Weather defense mods (applied directly)
    if (field.weather == "Sand" and ("岩石" in defender.types or defender.types[1] == "岩石" if len(defender.types) > 1 else False)
            and not hits_physical):
        defense = poke_round(defense * 3 / 2)
    elif (field.weather == "Snow" and ("冰" in defender.types)
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

    # Ruin abilities
    if field.is_sword_of_ruin and hits_physical and def_ability != "Sword of Ruin":
        df_mods.append(0x0C00)
    elif field.is_beads_of_ruin and not hits_physical and def_ability != "Beads of Ruin":
        df_mods.append(0x0C00)

    # Flower Gift
    if (def_ability == "Flower Gift" and defender.name_en == "Cherrim"
            and field.weather and "Sun" in field.weather
            and not hits_physical and defender.item != "大晴天伞"):
        df_mods.append(0x1800)
    elif field.is_flower_gift_spd and field.weather and "Sun" in field.weather and not hits_physical:
        df_mods.append(0x1800)

    # 1.5x abilities
    if ((def_ability == "Marvel Scale" and defender.status not in (None, "Healthy") and hits_physical)
            or (def_ability == "Grass Pelt" and field.terrain == "Grassy" and hits_physical)):
        df_mods.append(0x1800)

    # 1.3x abilities (Protosynthesis / Quark Drive on defense)
    if (((def_ability == "Protosynthesis" and (defender.item in ("Booster Energy", "驱劲能量") or (field.weather and "Sun" in field.weather)))
         or (def_ability == "Quark Drive" and (defender.item in ("Booster Energy", "驱劲能量") or field.terrain == "Electric")))
            and ((defender.stats.get("defense", 0) >= defender.stats.get("sp_defense", 0) and hits_physical)
                 or (defender.stats.get("sp_defense", 0) > defender.stats.get("defense", 0) and not hits_physical))):
        df_mods.append(0x14CD)

    # 2.0x abilities
    if def_ability == "Fur Coat" and hits_physical:
        df_mods.append(0x2000)

    # 1.5x items
    if ((defender.item in ("突击背心", "Assault Vest") and not hits_physical)
            or (defender.item in ("进化奇石", "Eviolite") and defender.can_evolve)
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

    # Fluffy (contact) - Long Reach ignores contact effects
    is_contact = move.makes_contact and attacker.ability != "Long Reach"
    if def_ability == "Fluffy" and is_contact:
        final_mods.append(0x800)

    # Punk Rock
    if def_ability == "Punk Rock" and move.is_sound:
        final_mods.append(0x800)

    # Ice Scales
    if def_ability == "Ice Scales" and not hits_physical:
        final_mods.append(0x800)

    # Friend Guard
    if field.is_friend_guard and def_ability != "[ignored]":
        final_mods.append(0xC00)

    # Solid Rock / Filter / Prism Armor
    if def_ability in ("Solid Rock", "Filter", "Prism Armor") and type_effectiveness > 1:
        final_mods.append(0xC00)

    # Fluffy (fire moves)
    if def_ability == "Fluffy" and move.type == "火":
        final_mods.append(0x2000)

    # Expert Belt
    if attacker.item in ("达人带", "Expert Belt") and type_effectiveness > 1:
        final_mods.append(0x1333)
    # Life Orb
    elif attacker.item in ("生命宝珠", "Life Orb"):
        final_mods.append(0x14CC)

    # Resist berries (halve super-effective moves of the corresponding type)
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

    # Berry aliases: zh official names + slang -> en canonical name
    _BERRY_ALIASES: dict[str, str] = {
        # Slang (most commonly used by players)
        "抗火果": "Occa Berry",
        "抗水果": "Passho Berry",
        "抗电果": "Wacan Berry",
        "抗草果": "Rindo Berry",
        "抗冰果": "Yache Berry",
        "抗斗果": "Chople Berry",
        "抗毒果": "Kebia Berry",
        "抗地果": "Shuca Berry",
        "抗飞果": "Coba Berry",
        "抗超果": "Payapa Berry",
        "抗虫果": "Tanga Berry",
        "抗岩果": "Charti Berry",
        "抗鬼果": "Kasib Berry",
        "抗龙果": "Haban Berry",
        "抗恶果": "Colbur Berry",
        "抗钢果": "Babiri Berry",
        "抗仙果": "Roseli Berry",
        "抗一般果": "Chilan Berry",
        # Chinese official names (Gen 7+)
        "千香果": "Occa Berry",
        "烛木果": "Passho Berry",
        "罗子果": "Wacan Berry",
        "番荔果": "Rindo Berry",
        "腰木果": "Yache Berry",
        "巧可果": "Chople Berry",
        "棱瓜果": "Kebia Berry",
        "葫苏果": "Shuca Berry",
        "乐芭果": "Coba Berry",
        "芭亚果": "Payapa Berry",
        "莲蒲果": "Tanga Berry",
        "霹霹果": "Charti Berry",
        "烛龙果": "Haban Berry",
        "佛柑果": "Kasib Berry",
        "罗望果": "Colbur Berry",
        "投鲜果": "Chilan Berry",
        "刺耳果": "Colbur Berry",
        "穹犀果": "Babiri Berry",
        "香罗果": "Roseli Berry",
    }

    def _canonical_berry(item_name: str) -> str:
        """Resolve zh/slang berry name to canonical English name."""
        if not item_name:
            return ""
        # Already English
        if item_name.endswith("Berry"):
            return item_name
        return _BERRY_ALIASES.get(item_name, item_name)

    move_type_en = _TYPE_ZH_TO_EN.get(move.type, move.type)
    resist_berries = _RESIST_BERRIES.get(move_type_en, [])
    canonical_item = _canonical_berry(defender.item)
    if canonical_item in resist_berries and type_effectiveness > 1:
        final_mods.append(0x800)

    return final_mods


# ---------------------------------------------------------------------------
# Main calculation entry point
# ---------------------------------------------------------------------------

def calculate_damage(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    gen: int = 9,
) -> DamageResult:
    """
    Calculate damage for a single move.

    Returns a DamageResult containing:
      - damage: list of all possible damage rolls (sorted)
      - min_damage / max_damage
      - description: human-readable summary
      - is_critical, type_effectiveness, stab_applied, burn_applied
    """
    # Ensure stats are computed
    if not attacker.raw_stats:
        compute_raw_stats(attacker)
    if not defender.raw_stats:
        compute_raw_stats(defender)

    # Default result for status moves
    if move.base_power == 0 or move.category == "Status":
        return DamageResult(
            damage=[0],
            min_damage=0,
            max_damage=0,
            description=f"{move.name} 是变化招式，不造成伤害",
        )

    # Determine physical vs special
    hits_physical = uses_physical_attack(attacker, defender, move)
    move.category = "Physical" if hits_physical else "Special"

    # Type effectiveness
    def_type1 = defender.types[0] if defender.types else "一般"
    def_type2 = defender.types[1] if len(defender.types) > 1 else None
    type_effectiveness = get_move_effectiveness(
        move.type, def_type1, def_type2,
        is_ghost_revealed=(attacker.ability in ("Scrappy", "Mind's Eye") or field.is_foresight),
        is_gravity=field.is_gravity,
        def_item=defender.item,
        is_strong_winds=(field.weather == "Strong Winds"),
        is_tera_shell=(defender.ability == "Tera Shell" and defender.current_hp == defender.max_hp),
        def_is_tera=defender.is_terastalize,
        move_name=move.name,
    )

    # Immunity check
    if type_effectiveness == 0:
        return DamageResult(
            damage=[0],
            min_damage=0,
            max_damage=0,
            description=f"{move.name} 对 {defender.name} 无效（属性免疫）",
            type_effectiveness=0.0,
        )

    # Ability ignore (Mold Breaker, Teravolt, Turboblaze)
    def_ability = defender.ability
    if attacker.ability in ("Mold Breaker", "Teravolt", "Turboblaze"):
        def_ability = "[ignored]"

    # Critical hit
    is_critical = move.is_crit and def_ability not in ("Battle Armor", "Shell Armor")
    # Merciless: always crit against poisoned/toxiced defender
    if attacker.ability == "Merciless" and defender.status in ("Poisoned", "Badly Poisoned"):
        is_critical = True

    # Move type changes based on weather / terrain (Weather Ball, Terrain Pulse, etc.)
    if move.name == "Weather Ball" and field.weather and attacker.item not in ("Utility Umbrella", "大晴天伞"):
        weather_type_map = {
            "Sun": "火", "Harsh Sun": "火",
            "Rain": "水", "Heavy Rain": "水",
            "Sand": "岩石",
            "Hail": "冰", "Snow": "冰",
        }
        move.type = weather_type_map.get(field.weather, move.type)
    elif move.name in ("Terrain Pulse", "Nature Power") and field.terrain:
        terrain_type_map = {
            "Electric": "电",
            "Grassy": "草",
            "Misty": "妖精",
            "Psychic": "超能力",
        }
        move.type = terrain_type_map.get(field.terrain, move.type)

    # Turn order (for speed-based moves)
    turn_order = "FIRST" if attacker.stats.get("speed", 0) > defender.stats.get("speed", 0) else "LAST"

    # Base power
    base_power = base_power_func(move, attacker, defender, field, turn_order)
    base_power = max(1, base_power)

    # Ate/Ize type change (Pixilate, Aerilate, etc.)
    move, ate_ize_boosted = _ate_ize_type_change(move, attacker)

    # Grounded checks for terrain effects
    att_is_grounded = is_grounded(attacker, field)
    def_is_grounded = is_grounded(defender, field)

    # Conditional spread (e.g. Expanding Force in Psychic Terrain)
    check_conditional_spread(move, field, attacker, att_is_grounded)

    # BP mods
    bp_mods = calc_bp_mods(attacker, defender, field, move, ate_ize_boosted, base_power, turn_order, def_ability, att_is_grounded, def_is_grounded)
    base_power = max(1, poke_round(base_power * chain_mods(bp_mods) / 0x1000))

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

    # b. Weather
    if field.weather:
        if (("Sun" in field.weather and move.type == "火") or ("Rain" in field.weather and move.type == "水")) and defender.item != "大晴天伞":
            base_dmg = poke_round(base_dmg * 0x1800 / 0x1000)
        elif ((field.weather == "Sun" and move.type == "水") or (field.weather == "Rain" and move.type == "火")) and defender.item != "大晴天伞":
            base_dmg = poke_round(base_dmg * 0x800 / 0x1000)

    # c. Critical hit
    if is_critical:
        base_dmg = math.floor(base_dmg * 1.5)

    # STAB
    stab_mod = 0x1000
    move_type_en = _TYPE_ZH_TO_EN.get(move.type, move.type)
    atk_type1_en = _TYPE_ZH_TO_EN.get(attacker.types[0], attacker.types[0]) if attacker.types else ""
    atk_type2_en = _TYPE_ZH_TO_EN.get(attacker.types[1], attacker.types[1]) if len(attacker.types) > 1 else ""
    tera_type_en = _TYPE_ZH_TO_EN.get(attacker.tera_type, attacker.tera_type) if attacker.tera_type else ""

    if attacker.is_terastalize and tera_type_en != "Stellar":
        if move_type_en == tera_type_en and (atk_type1_en == tera_type_en or atk_type2_en == tera_type_en):
            stab_mod = 0x2400 if attacker.ability == "Adaptability" else 0x2000
        elif (move_type_en != tera_type_en and (atk_type1_en == move_type_en or atk_type2_en == move_type_en)) or move_type_en == tera_type_en:
            stab_mod = 0x2000 if (attacker.ability == "Adaptability" and move_type_en == tera_type_en) else 0x1800
    elif attacker.is_terastalize and tera_type_en == "Stellar":
        if move_type_en in (atk_type1_en, atk_type2_en):
            stab_mod = 0x2000
        else:
            stab_mod = 0x1333
    else:
        if move_type_en in (atk_type1_en, atk_type2_en):
            stab_mod = 0x2000 if attacker.ability == "Adaptability" else 0x1800
        elif attacker.ability in ("Protean", "Libero"):
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

    # Parental Bond: second hit at 25% base power (Gen 6+)
    if (attacker.ability == "Parental Bond"
            and move.name not in _PARENTAL_BOND_IGNORED_MOVES
            and move.hits == 1):
        second_move = copy(move)
        second_move.base_power = max(1, math.floor(second_move.base_power * 0.25))
        second_move.fainted_allies = 0  # Prevent dynamic BP boosts from reapplying
        # Temporarily disable Parental Bond to prevent infinite recursion
        original_ability = attacker.ability
        attacker.ability = ""
        second_result = calculate_damage(attacker, defender, second_move, field, gen)
        attacker.ability = original_ability

        # Merge damage rolls: all combinations of first + second hit
        merged_rolls: list[int] = []
        for d1 in damage_rolls:
            for d2 in second_result.damage:
                merged_rolls.append(d1 + d2)
        merged_rolls.sort()
        damage_rolls = merged_rolls

    # Build description
    eff_desc = ""
    if type_effectiveness > 1:
        eff_desc = f" 效果拔群（{int(type_effectiveness)}倍）"
    elif type_effectiveness < 1:
        eff_desc = f" 效果不佳（{type_effectiveness}倍）"

    crit_desc = " 击中要害" if is_critical else ""
    burn_desc = "（烧伤减半）" if apply_burn else ""
    pb_desc = "（亲子爱：两段攻击）" if (attacker.ability == "Parental Bond"
                                         and move.name not in _PARENTAL_BOND_IGNORED_MOVES
                                         and move.hits == 1) else ""

    description = (
        f"Lv.{attacker.level} {attacker.name} 的 {move.name} "
        f"vs Lv.{defender.level} {defender.name}{eff_desc}{crit_desc}{burn_desc}{pb_desc} | "
        f"威力 {base_power} | 攻击 {attack} | 防御 {defense} | "
        f"伤害范围 {damage_rolls[0]} ~ {damage_rolls[-1]}"
    )

    return DamageResult(
        damage=damage_rolls,
        min_damage=damage_rolls[0],
        max_damage=damage_rolls[-1],
        description=description,
        is_critical=is_critical,
        type_effectiveness=type_effectiveness,
        stab_applied=stab_mod != 0x1000,
        burn_applied=apply_burn,
    )
