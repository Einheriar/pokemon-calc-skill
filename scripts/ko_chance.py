#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KO chance calculator ported from script_res/ko_chance.js.
"""
from __future__ import annotations

import math
from copy import copy
from typing import Optional

from models import Field, Move, Pokemon
import display_zh
from engine_enums import T


def get_ko_chance_text(
    damage: list[int],
    move: Move,
    defender: Pokemon,
    field: Field,
    is_bad_dreams: bool = False,
) -> str:
    """
    Return a human-readable string describing the KO chance.

    damage: sorted list of possible damage values (from calculate_damage)
    """
    # Do not rely on calculate_damage normalizing caller-owned objects. KO
    # logic also runs independently in tests and direct library calls.
    move = copy(move)
    defender = copy(defender)
    move.type = _type_zh_to_en(move.type)
    defender.types = [_type_zh_to_en(t) for t in defender.types]

    if not damage or math.isnan(damage[0]):
        return display_zh.KO_ERROR

    if move.name == "Pain Split" and not getattr(move, "pain_max", False):
        return display_zh.KO_PAIN_SPLIT

    if move.category == "Status" and move.name not in ("Me First", "(No Move)"):
        return display_zh.KO_STATUS_MOVE

    if damage[-1] == 0:
        if field.weather == "Harsh Sun" and move.type == T.WATER:
            return display_zh.KO_SUN_EVAPORATED
        elif field.weather == "Heavy Rain" and move.type == T.FIRE:
            return display_zh.KO_RAIN_EXTINGUISHED
        return display_zh.KO_NO_DAMAGE

    has_sitrus = defender.item in ("Sitrus Berry",)
    has_figy = defender.item in ("Figy Berry", "Aguav Berry", "Iapapa Berry", "Mago Berry", "Wiki Berry")
    gluttony = defender.ability == "Gluttony"
    ripen = 2 if defender.ability == "Ripen" else 1

    # Guaranteed OHKO checks
    if (damage[0] >= defender.current_hp
            or (len(damage) == 256 and has_sitrus and damage[0] >= defender.current_hp + math.floor(ripen * defender.max_hp / 4))
            or (len(damage) == 256 and has_figy and damage[0] >= defender.current_hp + math.floor(ripen * defender.max_hp / 3))):
        return display_zh.KO_OHKO

    # Hazards
    hazards = 0
    hazard_texts: list[str] = []
    # Magic Guard prevents indirect damage in battle, not entry hazards.
    if field.is_stealth_rock and defender.item != "Heavy-Duty Boots":
        eff = _get_rock_effectiveness(defender)
        hazards += math.floor(eff * defender.max_hp / 8)
        hazard_texts.append(display_zh.HAZARD_STEALTH_ROCK)

    from damage import is_grounded
    grounded = is_grounded(defender, field)
    if grounded and defender.item != "Heavy-Duty Boots":
        if field.spikes == 1:
            hazards += math.floor(defender.max_hp / 8)
            hazard_texts.append(display_zh.HAZARD_SPIKES_1)
        elif field.spikes == 2:
            hazards += math.floor(defender.max_hp / 6)
            hazard_texts.append(display_zh.HAZARD_SPIKES_2)
        elif field.spikes == 3:
            hazards += math.floor(defender.max_hp / 4)
            hazard_texts.append(display_zh.HAZARD_SPIKES_3)

    # End-of-turn effects
    eot = 0
    eot_texts: list[str] = []
    max_chip = 0.5 if defender.is_dynamax else 1.0

    if field.weather == "Sun":
        if defender.ability in ("Dry Skin", "Solar Power"):
            eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append(display_zh.ability_damage(defender.ability))
    elif field.weather == "Rain":
        if defender.ability == "Dry Skin":
            eot += math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append(display_zh.EOT_DRY_SKIN_HEAL)
        elif defender.ability == "Rain Dish":
            eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append(display_zh.EOT_RAIN_DISH_HEAL)
    elif field.weather == "Sand":
        if "Rock" not in defender.types and "Ground" not in defender.types and "Steel" not in defender.types:
            if defender.ability not in ("Magic Guard", "Overcoat", "Sand Force", "Sand Rush", "Sand Veil") and defender.item != "Safety Goggles":
                eot -= math.floor(math.floor(defender.max_hp / 16) * max_chip)
                eot_texts.append(display_zh.EOT_SAND_DAMAGE)
    elif field.weather == "Hail":
        if defender.ability == "Ice Body":
            eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append(display_zh.EOT_ICE_BODY_HEAL)
        elif T.ICE not in defender.types and defender.ability not in ("Magic Guard", "Overcoat", "Snow Cloak") and defender.item != "Safety Goggles":
            eot -= math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append(display_zh.EOT_HAIL_DAMAGE)
    elif field.weather == "Snow" and defender.ability == "Ice Body":
        eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
        eot_texts.append(display_zh.EOT_ICE_BODY_HEAL)

    if defender.item == "Leftovers":
        eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
        eot_texts.append(display_zh.EOT_LEFTOVERS_HEAL)
    elif defender.item == "Black Sludge":
        if T.POISON in defender.types:
            eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append(display_zh.EOT_BLACK_SLUDGE_HEAL)
        elif defender.ability not in ("Magic Guard", "Klutz"):
            eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append(display_zh.EOT_BLACK_SLUDGE_DAMAGE)

    if field.terrain == "Grassy" and grounded:
        eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
        eot_texts.append(display_zh.EOT_GRASSY_HEAL)

    toxic_counter = 0
    if defender.status == "Poisoned":
        if defender.ability == "Poison Heal":
            eot += math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append(display_zh.EOT_POISON_HEAL_HEAL)
        elif defender.ability != "Magic Guard":
            eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append(display_zh.EOT_POISON_DAMAGE)
    elif defender.status == "Badly Poisoned":
        if defender.ability == "Poison Heal":
            eot += math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append(display_zh.EOT_POISON_HEAL_HEAL)
        elif defender.ability != "Magic Guard":
            eot_texts.append(display_zh.EOT_TOXIC_DAMAGE)
            toxic_counter = getattr(defender, "toxic_counter", 0)
    elif defender.status == "Burned":
        burn_div = 16  # gen >= 7
        if defender.ability == "Heatproof":
            eot -= math.floor(math.floor(defender.max_hp / burn_div / 2) * max_chip)
            eot_texts.append(display_zh.EOT_HALVED_BURN_DAMAGE)
        elif defender.ability != "Magic Guard":
            eot -= math.floor(math.floor(defender.max_hp / burn_div) * max_chip)
            eot_texts.append(display_zh.EOT_BURN_DAMAGE)
    elif defender.status == "Asleep" and is_bad_dreams and defender.ability != "Magic Guard":
        eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
        eot_texts.append(display_zh.EOT_BAD_DREAMS)

    if field.is_salt_cure and defender.ability != "Magic Guard":
        if T.WATER not in defender.types and T.STEEL not in defender.types:
            eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append(display_zh.EOT_SALT_CURE_DAMAGE)
        else:
            eot -= math.floor(math.floor(defender.max_hp / 4) * max_chip)
            eot_texts.append(display_zh.EOT_SALT_CURE_EXTRA)

    # Multi-hit squash
    qualifier = ""
    multihit = len(damage) == 256 or move.hits > 1
    if move.hits > 1 and not getattr(move, "is_triple_hit", False):
        qualifier = display_zh.MULTI_HIT_QUALIFIER
        damage = squash_multihit(damage, move.hits)
        multihit = True

    # Calculate KO chance
    c = _get_ko_chance(damage, multihit, defender.current_hp - hazards, 0, 1, defender.max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen)
    after_text = display_zh.condition_suffix(hazard_texts)

    if c == 1:
        return display_zh.ko_ohko_with(after_text)
    elif c > 0:
        pct = round(c * 1000) / 10
        return display_zh.ko_prob_with(qualifier, pct, after_text)

    # Berry recovery text
    if has_sitrus and move.name != "Knock Off":
        eot_texts.append(display_zh.EOT_SITRUS_HEAL)
    if has_figy and move.name != "Knock Off":
        eot_texts.append(display_zh.EOT_BERRY_HEAL)

    c = _get_ko_chance(damage, multihit, defender.current_hp - hazards + eot, eot, 1, defender.max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen)
    after_text2 = display_zh.condition_suffix(hazard_texts + eot_texts)

    if c == 1:
        return display_zh.ko_ohko_with(after_text2)
    elif c > 0:
        pct = round(c * 1000) / 10
        return display_zh.ko_prob_with(qualifier, pct, after_text2)

    # Recovery and residual damage apply between subsequent hits too.
    for i in range(2, 5):
        c = _get_ko_chance(damage, multihit, defender.current_hp - hazards, eot, i, defender.max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen)
        if c == 1:
            return display_zh.ko_n_guaranteed(i, after_text2)
        elif c > 0:
            pct = round(c * 1000) / 10
            return display_zh.ko_n_prob(qualifier, pct, i, after_text2)

    # Only the min/max rolls are needed for 5-9HKO boundary prediction. Using
    # one-roll state trees avoids exponential enumeration without changing rules.
    for i in range(5, 10):
        min_c = _get_ko_chance([damage[0]], multihit, defender.current_hp - hazards, eot, i, defender.max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen)
        if min_c == 1:
            return display_zh.ko_n_guaranteed(i, after_text2)
        max_c = _get_ko_chance([damage[-1]], multihit, defender.current_hp - hazards, eot, i, defender.max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen)
        if max_c > 0:
            return display_zh.ko_n_possible(i, after_text2)

    return display_zh.KO_MORE_ROUNDS


def _get_rock_effectiveness(defender: Pokemon) -> float:
    """Rock-type effectiveness against defender (for Stealth Rock damage)."""
    from damage import _load_type_chart
    chart = _load_type_chart()
    eff = chart.get("Rock", {}).get(_type_zh_to_en(defender.types[0]), 1.0)
    if len(defender.types) > 1:
        eff *= chart.get("Rock", {}).get(_type_zh_to_en(defender.types[1]), 1.0)
    return eff


def _type_zh_to_en(t: str) -> str:
    from engine_enums import resolve_type_en
    return resolve_type_en(t) or t


def _get_ko_chance(
    damage: list[int],
    multihit: bool,
    hp: int,
    eot: int,
    hits: int,
    max_hp: int,
    toxic_counter: int,
    has_sitrus: bool,
    has_figy: bool,
    gluttony: bool,
    ripen: int,
) -> float:
    """Recursive KO probability with branch-local HP and berry state."""
    n = len(damage)
    if hits <= 0:
        return 0.0
    if hits == 1:
        # Keep the existing aggregate multi-hit berry approximation. Ordinary
        # hits always check lethality directly; recovery never revives a KO.
        if (not multihit or (not has_sitrus and not has_figy)) and damage[-1] < hp:
            return 0.0
        if multihit and has_sitrus and damage[-1] < hp + math.floor(ripen * max_hp / 4):
            return 0.0
        if multihit and has_figy and damage[-1] < hp + math.floor(ripen * max_hp / 3):
            return 0.0
        for i in range(n):
            if (not multihit or (not has_sitrus and not has_figy)) and damage[i] >= hp:
                return (n - i) / n
            if multihit and has_sitrus and damage[i] >= hp + math.floor(ripen * max_hp / 4):
                return (n - i) / n
            if multihit and has_figy and damage[i] >= hp + math.floor(ripen * max_hp / 3):
                return (n - i) / n
        return 0.0

    toxic_damage = math.floor(toxic_counter * max_hp / 16) if toxic_counter > 0 else 0
    next_toxic_counter = toxic_counter + 1 if toxic_counter > 0 else toxic_counter

    total = 0.0
    last_c = 0.0
    for i, dealt in enumerate(damage):
        if i == 0 or dealt != damage[i - 1]:
            if dealt >= hp:
                c = 1.0
            else:
                branch_hp = hp - dealt
                branch_sitrus = has_sitrus
                branch_figy = has_figy
                if branch_sitrus and branch_hp <= max_hp // 2:
                    branch_hp = min(max_hp, branch_hp + math.floor(ripen * max_hp / 4))
                    branch_sitrus = False
                elif branch_figy and (
                    (branch_hp <= max_hp // 4 and not gluttony)
                    or (branch_hp <= max_hp // 2 and gluttony)
                ):
                    branch_hp = min(max_hp, branch_hp + math.floor(ripen * max_hp / 3))
                    branch_figy = False

                branch_hp = min(max_hp, branch_hp + eot) - toxic_damage
                if branch_hp <= 0:
                    c = 1.0
                else:
                    c = _get_ko_chance(
                        damage, multihit, branch_hp, eot, hits - 1, max_hp,
                        next_toxic_counter, branch_sitrus, branch_figy, gluttony, ripen,
                    )
        else:
            c = last_c
        total += c
        last_c = c

    return total / n


def _predict_total(
    damage: int,
    eot: int,
    hits: int,
    toxic_counter: int,
    hp: int,
    max_hp: int,
    has_sitrus: bool,
    has_figy: bool,
    gluttony: bool,
    ripen: int,
) -> int:
    total = 0
    for i in range(hits):
        total += damage
        if (hp - total <= max_hp // 2) and has_sitrus:
            total -= math.floor(ripen * max_hp / 4)
            has_sitrus = False
        elif ((hp - total <= max_hp // 4 and has_figy and not gluttony)
              or (hp - total <= max_hp // 2 and has_figy and gluttony)):
            total -= math.floor(ripen * max_hp / 3)
            has_figy = False
        if i < hits - 1:
            total -= eot
            if toxic_counter > 0:
                total += math.floor((toxic_counter + i) * max_hp / 16)
    return total


def squash_multihit(d: list[int], hits: int) -> list[int]:
    """Approximate multi-hit damage distribution.

    The JS original also has 39-length tables for Triple Kick/Axel-style
    escalating hits; Python's damage pipeline only ever produces 1/16/256
    length arrays, so those tables were unreachable and have been removed
    (round 2 audit S1).
    """
    if len(d) == 1:
        return [d[0] * hits]
    if len(d) == 16:
        # Simplified approximations for common hit counts
        if hits == 2:
            return [
                2*d[0], d[2]+d[3], d[4]+d[4], d[4]+d[5],
                d[5]+d[6], d[6]+d[6], d[6]+d[7], d[7]+d[7],
                d[8]+d[8], d[8]+d[9], d[9]+d[9], d[9]+d[10],
                d[10]+d[11], d[11]+d[11], d[12]+d[13], 2*d[15]
            ]
        elif hits == 3:
            return [
                3*d[0], d[3]+d[3]+d[4], d[4]+d[4]+d[5], d[5]+d[5]+d[6],
                d[5]+d[6]+d[6], d[6]+d[6]+d[7], d[6]+d[7]+d[7], d[7]+d[7]+d[8],
                d[7]+d[8]+d[8], d[8]+d[8]+d[9], d[8]+d[9]+d[9], d[9]+d[9]+d[10],
                d[9]+d[10]+d[10], d[10]+d[11]+d[11], d[11]+d[12]+d[12], 3*d[15]
            ]
        elif hits == 5:
            return [
                5*d[0], d[4]+d[4]+d[4]+d[5]+d[5], d[5]+d[5]+d[5]+d[5]+d[6], d[5]+d[6]+d[6]+d[6]+d[6],
                d[6]+d[6]+d[6]+d[6]+d[7], d[6]+d[6]+d[7]+d[7]+d[7], 5*d[7], d[7]+d[7]+d[7]+d[8]+d[8],
                d[7]+d[7]+d[8]+d[8]+d[8], 5*d[8], d[8]+d[8]+d[8]+d[9]+d[9], d[8]+d[9]+d[9]+d[9]+d[9],
                d[9]+d[9]+d[9]+d[9]+d[10], d[9]+d[10]+d[10]+d[10]+d[10], d[10]+d[10]+d[11]+d[11]+d[11], 5*d[15]
            ]
        elif hits == 4:
            return [
                4*d[0], 4*d[4], d[4]+d[5]+d[5]+d[5], d[5]+d[5]+d[6]+d[6],
                4*d[6], d[6]+d[6]+d[7]+d[7], 4*d[7], d[7]+d[7]+d[7]+d[8],
                d[7]+d[8]+d[8]+d[8], 4*d[8], d[8]+d[8]+d[9]+d[9], 4*d[9],
                d[9]+d[9]+d[10]+d[10], d[10]+d[10]+d[10]+d[11], 4*d[11], 4*d[15]
            ]
        elif hits == 6:
            return [
                6*d[0], 2*d[4]+4*d[5], 3*d[5]+3*d[6], 6*d[6],
                3*d[6]+3*d[7], 6*d[7], 5*d[7]+d[8], 4*d[7]+2*d[8],
                2*d[7]+4*d[8], d[7]+5*d[8], 6*d[8], 3*d[8]+3*d[9],
                6*d[9], 3*d[9]+3*d[10], 4*d[10]+2*d[11], 6*d[15]
            ]
        elif hits == 7:
            return [
                7*d[0], 5*d[5]+2*d[6], 2*d[5]+5*d[6], 5*d[6]+2*d[7],
                3*d[6]+4*d[7], 7*d[7], 5*d[7]+2*d[8], 4*d[7]+3*d[8],
                3*d[7]+4*d[8], 2*d[7]+5*d[8], 7*d[8], 4*d[8]+3*d[9],
                5*d[9]+2*d[10], 5*d[10]+2*d[11], 2*d[10]+5*d[11], 7*d[15]
            ]
        elif hits == 8:
            return [
                8*d[0], 4*d[5]+4*d[6], 8*d[6], 4*d[6]+4*d[7],
                8*d[7], 7*d[7]+d[8], 6*d[7]+2*d[8], 5*d[7]+3*d[8],
                3*d[7]+5*d[8], 2*d[7]+6*d[8], d[7]+7*d[8], 8*d[8],
                4*d[8]+4*d[9], 8*d[9], 4*d[9]+4*d[10], 8*d[15]
            ]
        elif hits == 9:
            return [
                9*d[0], 2*d[5]+7*d[6], 7*d[6]+2*d[7], 4*d[6]+5*d[7],
                9*d[7], 7*d[7]+2*d[8], 6*d[7]+3*d[8], 5*d[7]+4*d[8],
                4*d[7]+5*d[8], 3*d[7]+6*d[8], 2*d[7]+7*d[8], 9*d[8],
                5*d[8]+4*d[9], 7*d[9]+2*d[10], 7*d[10]+2*d[11], 9*d[15]
            ]
        elif hits == 10:
            return [
                10*d[0], 10*d[6], 5*d[6]+5*d[7], 10*d[7],
                9*d[7]+d[8], 8*d[7]+2*d[8], 7*d[7]+3*d[8], 6*d[7]+4*d[8],
                4*d[7]+6*d[8], 3*d[7]+7*d[8], 2*d[7]+8*d[8], d[7]+9*d[8],
                10*d[8], 5*d[8]+5*d[9], 10*d[9], 10*d[15]
            ]
    # Default fallback
    return [d[0] * hits, d[len(d)//2] * hits, d[-1] * hits]
