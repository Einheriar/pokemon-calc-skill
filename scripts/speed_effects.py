#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Pure-parameter calculation of the in-battle Speed stat."""
from __future__ import annotations

from battle_effects import effective_ability, effective_weather
from models import Field, Pokemon


_WEATHER_SPEED_ABILITIES = {
    "Chlorophyll": {"Sun", "Harsh Sun"},
    "Swift Swim": {"Rain", "Heavy Rain"},
    "Sand Rush": {"Sand"},
    "Slush Rush": {"Hail", "Snow"},
}

_HALF_SPEED_ITEMS = {
    "Iron Ball", "Macho Brace", "Power Anklet", "Power Band", "Power Belt",
    "Power Bracer", "Power Lens", "Power Weight",
}

# These items ignore Klutz in Showdown; the other listed speed items do not.
_KLUTZ_IGNORING_SPEED_ITEMS = {
    "Macho Brace", "Power Anklet", "Power Band", "Power Belt", "Power Bracer",
    "Power Lens", "Power Weight",
}


def _chain_modifier(modifier: int, numerator: int, denominator: int = 1) -> int:
    """Chain one Showdown fixed-point modifier at 1/4096 precision."""
    next_modifier = numerator * 4096 // denominator
    return (modifier * next_modifier + 2048) >> 12


def _apply_modifier(value: int, modifier: int) -> int:
    """Apply Showdown's Gen 9 fixed-point rounding to a stat value."""
    return (value * modifier + 2048 - 1) // 4096


def _has_status(pokemon: Pokemon) -> bool:
    return bool(pokemon.status and pokemon.status != "Healthy")


def get_effective_speed(
    pokemon: Pokemon,
    field: Field,
    attacker: Pokemon | None = None,
    defender: Pokemon | None = None,
    *,
    tailwind: bool = False,
) -> int:
    """Return actual Speed from precomputed stages plus active battle modifiers.

    ``pokemon.stats['speed']`` already includes the stat-stage adjustment. The
    optional attack context is used only to resolve shared weather suppression;
    it does not mutate either Pokemon or the field. ``tailwind`` applies only
    to this Pokemon's side and joins the modifier chain before final rounding.
    """
    speed = int(pokemon.stats.get("speed", 1))
    modifier = 4096
    ability = effective_ability(pokemon, field)
    weather_attacker = attacker or pokemon
    weather_defender = defender or pokemon
    weather = effective_weather(
        weather_attacker, weather_defender, field, move_user=False,
    )

    weather_speed_blocked = (
        pokemon.item == "Utility Umbrella"
        and weather in ("Sun", "Harsh Sun", "Rain", "Heavy Rain")
    )
    if (ability in _WEATHER_SPEED_ABILITIES
            and weather in _WEATHER_SPEED_ABILITIES[ability]
            and not weather_speed_blocked):
        modifier = _chain_modifier(modifier, 2)
    elif ability == "Surge Surfer" and field.terrain == "Electric":
        modifier = _chain_modifier(modifier, 2)
    elif ability in ("Protosynthesis", "Quark Drive"):
        booster_active = pokemon.item == "Booster Energy"
        if ability == "Protosynthesis":
            ability_active = booster_active or weather in ("Sun", "Harsh Sun")
        else:
            ability_active = booster_active or field.terrain == "Electric"
        if ability_active:
            # Keep the stat selection identical to the damage engine's shared rule.
            from damage import _highest_stat

            if _highest_stat(pokemon) == "speed":
                modifier = _chain_modifier(modifier, 3, 2)

    if ability == "Unburden" and pokemon.ability_on and not pokemon.item:
        modifier = _chain_modifier(modifier, 2)
    if ability == "Quick Feet" and _has_status(pokemon):
        modifier = _chain_modifier(modifier, 3, 2)
    if ability == "Slow Start" and pokemon.ability_on:
        modifier = _chain_modifier(modifier, 1, 2)

    item = pokemon.item
    if ability == "Klutz" and item not in _KLUTZ_IGNORING_SPEED_ITEMS:
        item = ""
    if item == "Choice Scarf":
        modifier = _chain_modifier(modifier, 3, 2)
    elif item in _HALF_SPEED_ITEMS:
        modifier = _chain_modifier(modifier, 1, 2)

    if tailwind:
        modifier = _chain_modifier(modifier, 2)

    speed = _apply_modifier(speed, modifier)
    if pokemon.status == "Paralyzed" and ability != "Quick Feet":
        speed = speed * 50 // 100

    # Showdown clamps only the upper bound here; all lower-stage/final modifiers
    # are allowed to reduce Speed to zero.
    return min(10000, max(0, speed))
