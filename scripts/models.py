#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Data models for the Pokemon damage calculator (Phase 2).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Pokemon:
    """Battle Pokemon with stats, abilities, items, and status."""
    name: str                          # Display name (zh)
    name_en: str = ""
    level: int = 50
    base_stats: dict[str, int] = field(default_factory=dict)
    evs: dict[str, int] = field(default_factory=lambda: {
        "hp": 0, "attack": 0, "defense": 0,
        "sp_attack": 0, "sp_defense": 0, "speed": 0
    })
    ivs: dict[str, int] = field(default_factory=lambda: {
        "hp": 31, "attack": 31, "defense": 31,
        "sp_attack": 31, "sp_defense": 31, "speed": 31
    })
    nature: str = "勤奋"               # Chinese nature name
    ability: str = ""                # English (engine layer)
    ability_zh: str = ""             # Chinese (display layer)
    item: str = ""
    types: list[str] = field(default_factory=list)
    tera_type: Optional[str] = None
    is_terastalize: bool = False
    boosts: dict[str, int] = field(default_factory=lambda: {
        "hp": 0, "attack": 0, "defense": 0,
        "sp_attack": 0, "sp_defense": 0, "speed": 0
    })
    current_hp: int = 0
    max_hp: int = 0
    status: Optional[str] = None       # e.g., "Burned", "Poisoned"
    weight: float = 0.0
    is_dynamax: bool = False
    can_evolve: bool = False           # For Eviolite item
    # Derived stats (calculated once then cached)
    raw_stats: dict[str, int] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)


@dataclass
class Move:
    """Battle move."""
    name: str
    name_zh: str = ""
    base_power: int = 0
    type: str = "一般"
    category: str = "Physical"         # Physical / Special / Status
    accuracy: int = 100
    hits: int = 1
    is_z: bool = False
    is_spread: bool = False
    makes_contact: bool = False
    is_crit: bool = False
    ignores_burn: bool = False
    ignores_screens: bool = False
    is_ohko: bool = False
    is_priority: bool = False
    deals_physical_damage: bool = False
    has_recoil: bool = False           # For Reckless ability
    is_punch: bool = False             # For Iron Fist ability
    is_sound: bool = False             # For Liquid Voice / Punk Rock
    is_slice: bool = False             # For Sharpness ability
    is_wind: bool = False              # For Wind Rider ability
    is_bullet: bool = False            # For Bulletproof ability
    fainted_allies: int = 0            # For Last Respects base power boost


@dataclass
class Field:
    """Battle field conditions."""
    weather: Optional[str] = None      # Sun, Rain, Sand, Hail, Snow, Strong Winds, Harsh Sun, Heavy Rain
    terrain: Optional[str] = None      # Electric, Grassy, Misty, Psychic
    format: str = "Doubles"            # Singles / Doubles
    is_gravity: bool = False
    is_reflect: bool = False
    is_light_screen: bool = False
    is_aurora_veil: bool = False
    is_foresight: bool = False
    is_friend_guard: bool = False
    is_battery: bool = False
    is_power_spot: bool = False
    is_steely_spirit: bool = False
    is_flower_gift_atk: bool = False
    is_flower_gift_spd: bool = False
    is_tailwind_atk: bool = False
    is_tailwind_def: bool = False
    is_neutralizing_gas: bool = False
    # Ruin abilities
    is_sword_of_ruin: bool = False
    is_beads_of_ruin: bool = False
    is_tablets_of_ruin: bool = False
    is_vessel_of_ruin: bool = False
    # Hazards and persistent field effects
    is_stealth_rock: bool = False
    spikes: int = 0
    is_salt_cure: bool = False
    is_gmax_field: bool = False
    is_helping_hand: bool = False


@dataclass
class DamageResult:
    """Result of a damage calculation."""
    damage: list[int] = field(default_factory=list)
    min_damage: int = 0
    max_damage: int = 0
    description: str = ""
    is_critical: bool = False
    type_effectiveness: float = 1.0
    stab_applied: bool = False
    burn_applied: bool = False
