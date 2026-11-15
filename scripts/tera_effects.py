#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Terastallization-triggered abilities and form-dependent move typing."""
from __future__ import annotations

from typing import Optional

from battle_effects import effective_ability
from models import Field, Move, Pokemon


_OGERPON_ASPECT_STATS = {
    "Ogerpon": "speed",
    "Ogerpon-Wellspring": "sp_defense",
    "Ogerpon-Hearthflame": "attack",
    "Ogerpon-Cornerstone": "defense",
}

_OGERPON_IVY_TYPES = {
    "Ogerpon-Wellspring": "Water",
    "Ogerpon-Hearthflame": "Fire",
    "Ogerpon-Cornerstone": "Rock",
    "Ogerpon-Wellspring-Tera": "Water",
    "Ogerpon-Hearthflame-Tera": "Fire",
    "Ogerpon-Cornerstone-Tera": "Rock",
}

_MASK_IVY_TYPES = {
    "Wellspring Mask": "Water",
    "Hearthflame Mask": "Fire",
    "Cornerstone Mask": "Rock",
}


def _canonical_form_name(name: str) -> str:
    """Normalize raw form labels that include the Tera suffix."""
    return name.removesuffix("-Tera")


def apply_tera_effects(attacker: Pokemon, defender: Pokemon, field: Field) -> None:
    """Apply one-time effects triggered by the attacker's Terastallization.

    Call this on private calculation objects after their raw and modified stats
    have been materialized. Mark the event handled even when Neutralizing Gas
    suppresses the ability, so removing Gas later does not replay the event.
    """
    if not attacker.is_terastalize or attacker.tera_effects_applied:
        return

    ability = effective_ability(attacker, field)
    if (_canonical_form_name(attacker.name_en) == "Terapagos-Stellar"
            and ability == "Teraform Zero"):
        field.weather = None
        field.terrain = None
    elif ability == "Embody Aspect":
        stat = _OGERPON_ASPECT_STATS.get(_canonical_form_name(attacker.name_en))
        if stat:
            current_stage = attacker.boosts.get(stat, 0)
            attacker.boosts[stat] = min(6, current_stage + 1)
            if stat in attacker.raw_stats:
                # Delayed import avoids a module cycle with the damage engine.
                from damage import get_modified_stat

                attacker.stats[stat] = get_modified_stat(attacker.raw_stats[stat], attacker.boosts[stat])

    attacker.tera_effects_applied = True


def resolve_dynamic_tera_move_type(move: Move, attacker: Pokemon) -> Optional[str]:
    """Return a move's form- or Terastallization-dependent type when applicable.

    Tera Starstorm also becomes a spread move for Stellar Terapagos; that move
    property is updated on the caller's private Move copy alongside its type.
    """
    if move.name == "Ivy Cudgel":
        form_name = _canonical_form_name(attacker.name_en)
        form_type = _OGERPON_IVY_TYPES.get(form_name)
        if form_type:
            return form_type
        return _MASK_IVY_TYPES.get(attacker.item, "Grass") if form_name == "Ogerpon" else None

    if move.name == "Revelation Dance":
        if attacker.is_terastalize and attacker.tera_type and attacker.tera_type != "Stellar":
            return attacker.tera_type
        return attacker.types[0] if attacker.types else None

    if move.name == "Tera Starstorm" and _canonical_form_name(attacker.name_en) == "Terapagos-Stellar":
        move.is_spread = True
        return "Stellar"

    return None
