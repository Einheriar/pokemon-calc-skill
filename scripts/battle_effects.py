#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared, pure-parameter battle effect rules."""
from __future__ import annotations

from typing import Optional

from models import Field, Pokemon


# Flags transcribed from Pokemon Showdown's primary abilities.ts table.
# https://github.com/smogon/pokemon-showdown/blob/master/data/abilities.ts
# Showdown's cantsuppress flag: these abilities remain active under Neutralizing Gas.
_CANNOT_BE_SUPPRESSED = {
    # The engine uses the aggregate "As One" label for both Showdown variants.
    "As One", "As One (Glastrier)", "As One (Spectrier)", "Battle Bond",
    "Comatose", "Disguise", "Gulp Missile", "Ice Face", "Multitype",
    "Power Construct", "RKS System", "Schooling", "Shields Down",
    "Stance Change", "Tera Shift", "Zen Mode", "Zero to Hero",
}

# Showdown's breakable flag: Mold Breaker and its variants ignore these abilities.
_BREAKABLE_ABILITIES = {
    "Armor Tail", "Aroma Veil", "Aura Break", "Aura Guard", "Battle Armor",
    "Big Pecks", "Bulletproof", "Clear Body", "Contrary", "Damp", "Dazzling",
    "Disguise", "Dry Skin", "Earth Eater", "Eelevate", "Filter", "Flash Fire",
    "Flower Gift", "Flower Veil", "Fluffy", "Friend Guard", "Fur Coat",
    "Good as Gold", "Grass Pelt", "Guard Dog", "Heatproof", "Heavy Metal",
    "Hyper Cutter", "Ice Face", "Ice Scales", "Illuminate", "Immunity",
    "Inner Focus", "Insomnia", "Keen Eye", "Leaf Guard", "Levitate",
    "Light Metal", "Lightning Rod", "Limber", "Magic Bounce", "Magma Armor",
    "Marvel Scale", "Mind's Eye", "Mirror Armor", "Motor Drive", "Mountaineer",
    "Multiscale", "Oblivious", "Overcoat", "Own Tempo", "Pastel Veil",
    "Punk Rock", "Purifying Salt", "Queenly Majesty", "Rebound", "Sand Veil",
    "Sap Sipper", "Shell Armor", "Shield Dust", "Simple", "Snow Cloak",
    "Solid Rock", "Soundproof", "Sticky Hold", "Storm Drain", "Sturdy",
    "Suction Cups", "Sweet Veil", "Tangled Feet", "Telepathy", "Tera Shell",
    "Thermal Exchange", "Thick Fat", "Unaware", "Vital Spirit", "Volt Absorb",
    "Water Absorb", "Water Bubble", "Water Veil", "Well-Baked Body",
    "White Smoke", "Wind Rider", "Wonder Guard", "Wonder Skin",
}

_MOLD_BREAKER_ABILITIES = {"Mold Breaker", "Teravolt", "Turboblaze"}


def effective_ability(pokemon: Pokemon, field: Field) -> str:
    """Return the ability currently functioning, preserving the configured ability."""
    ability = pokemon.ability or ""
    if not ability or ability in _CANNOT_BE_SUPPRESSED:
        return ability
    if field.is_neutralizing_gas and ability != "Neutralizing Gas" and pokemon.item != "Ability Shield":
        return ""
    return ability


def ignorable_defender_ability(attacker: Pokemon, defender: Pokemon, field: Field) -> str:
    """Return the defender ability after Mold Breaker-style suppression, if any."""
    defender_ability = effective_ability(defender, field)
    attacker_ability = effective_ability(attacker, field)
    if (attacker_ability in _MOLD_BREAKER_ABILITIES
            and defender.item != "Ability Shield"
            and defender_ability in _BREAKABLE_ABILITIES):
        return ""
    return defender_ability


def berries_blocked(attacker: Pokemon, defender: Pokemon, field: Field) -> bool:
    """Whether the active attacking-side ability prevents the defender eating a berry."""
    ability = effective_ability(attacker, field)
    return ability in {"Unnerve", "As One", "As One (Glastrier)", "As One (Spectrier)"}


def field_ability_active(ability: str, attacker: Pokemon, field: Field) -> bool:
    """Resolve an unshielded external ability source represented by a field flag.

    The current field model has no source Pokemon/item for allied effects, so a
    shield held by the damage recipient cannot protect that external source.
    """
    if field.is_neutralizing_gas and ability not in _CANNOT_BE_SUPPRESSED:
        return False
    return not (effective_ability(attacker, field) in _MOLD_BREAKER_ABILITIES
                and ability in _BREAKABLE_ABILITIES)


def effective_weather(
    attacker: Pokemon,
    defender: Pokemon,
    field: Field,
    *,
    move_user: bool = True,
) -> Optional[str]:
    """Return weather affecting this move, without changing the actual field weather.

    Cloud Nine and Air Lock suppress weather effects while leaving the displayed
    weather in place. Showdown's Mega Sol user-side weather query overrides that
    suppression for the active attacker's move.
    """
    weather = field.weather
    weather_suppressed = any(
        effective_ability(pokemon, field) in {"Cloud Nine", "Air Lock"}
        for pokemon in (attacker, defender)
    )
    if weather_suppressed:
        weather = None

    if move_user and effective_ability(attacker, field) == "Mega Sol":
        return "Sun"
    return weather
