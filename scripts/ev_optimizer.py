#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EV optimizer (Phase 3).
Searches for minimal EV investment to meet damage thresholds.

Usage:
    from ev_optimizer import optimize_attack_ev, optimize_defense_ev
    result = optimize_attack_ev(attacker, defender, move, field, target="ohko")
"""
from __future__ import annotations

import copy
from typing import Literal, Optional

from damage import calculate_damage
from models import DamageResult, Field, Move, Pokemon

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_TOTAL_EVS = 508
MAX_SINGLE_EVS = 252
EV_STEP = 4

# Champions Stat Points (SP) constants
MAX_TOTAL_SP = 66
MAX_SINGLE_SP = 32
SP_STEP = 1

_STAT_KEYS = ["hp", "attack", "defense", "sp_attack", "sp_defense", "speed"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _set_ev(pokemon: Pokemon, stat: str, ev: int) -> Pokemon:
    """Return a copy of pokemon with the given stat's EV set."""
    pk = copy.copy(pokemon)
    pk.evs = dict(pokemon.evs)
    pk.evs[stat] = ev
    # Invalidate cached stats
    pk.raw_stats = {}
    pk.stats = {}
    return pk


def _set_sp(pokemon: Pokemon, stat: str, sp: int) -> Pokemon:
    """Return a copy of pokemon with the given stat's SP converted to equivalent EV.

    Champions SP mode: 1 SP = +1 stat at Lv.50 with IV=31.
    Conversion: ev = sp * 8, because in Gen9 formula at Lv.50/IV=31,
    each 8 EV increases raw stat by 1 (for non-HP) or 1 (for HP, since floor(8/4)/2=1).

    After setting ev, we invalidate cached stats so compute_raw_stats()
    in the damage engine will recalculate them correctly.
    """
    pk = copy.copy(pokemon)
    if not pk.evs:
        pk.evs = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    pk.evs = dict(pk.evs)
    pk.evs[stat] = sp * 8
    # Invalidate cached stats so compute_raw_stats recalculates
    pk.raw_stats = {}
    pk.stats = {}
    return pk


def _evaluate_attack(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    stat: str,
    value: int,
    mode: Literal["ev", "sp"] = "ev",
) -> DamageResult:
    """Evaluate damage with a specific EV/SP investment on the attacking stat."""
    if mode == "sp":
        att = _set_sp(attacker, stat, value)
    else:
        att = _set_ev(attacker, stat, value)
    return calculate_damage(att, defender, move, field, gen=9)


def _evaluate_defense(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    stat: str,
    value: int,
    mode: Literal["ev", "sp"] = "ev",
) -> DamageResult:
    """Evaluate damage with a specific EV/SP investment on the defending stat."""
    if mode == "sp":
        dfn = _set_sp(defender, stat, value)
    else:
        dfn = _set_ev(defender, stat, value)
    return calculate_damage(attacker, dfn, move, field, gen=9)


# ---------------------------------------------------------------------------
# Single-stat optimization
# ---------------------------------------------------------------------------


def optimize_attack_ev(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    target: Literal["ohko", "2hko", "3hko"] = "ohko",
    threshold: Literal["guaranteed", "likely"] = "guaranteed",
    mode: Literal["ev", "sp"] = "ev",
) -> dict:
    """
    Find the minimal attacking EV investment to reach a KO threshold.

    target:
        "ohko"  -> min damage >= defender.current_hp
        "2hko"  -> min damage * 2 >= defender.current_hp
        "3hko"  -> min damage * 3 >= defender.current_hp

    threshold:
        "guaranteed" -> use min_damage (worst roll)
        "likely"     -> use average damage

    Returns a dict with the optimal EV, resulting damage, and description.
    """
    hits_needed = {"ohko": 1, "2hko": 2, "3hko": 3}[target]
    use_min = threshold == "guaranteed"

    # Determine which stat to optimize
    result = calculate_damage(attacker, defender, move, field, gen=9)
    if result.min_damage == 0:
        return {
            "success": False,
            "reason": "该招式不造成伤害或免疫",
            "optimal_ev": 0,
            "damage_at_optimal": result.min_damage,
        }

    # Physical vs Special determination (same logic as damage.py)
    from damage import uses_physical_attack
    hits_physical = uses_physical_attack(attacker, defender, move)
    stat = "attack" if hits_physical else "sp_attack"

    best_val: Optional[int] = None
    best_damage: Optional[DamageResult] = None

    if mode == "sp":
        max_single = MAX_SINGLE_SP
        step = SP_STEP
        max_total = MAX_TOTAL_SP
        val_label = "能力点数"
    else:
        max_single = MAX_SINGLE_EVS
        step = EV_STEP
        max_total = MAX_TOTAL_EVS
        val_label = "努力值"

    for val in range(0, max_single + 1, step):
        result = _evaluate_attack(attacker, defender, move, field, stat, val, mode=mode)
        dmg = result.min_damage if use_min else sum(result.damage) // len(result.damage)
        total = dmg * hits_needed

        if total >= defender.current_hp:
            best_val = val
            best_damage = result
            break

    if best_val is None:
        result_max = _evaluate_attack(attacker, defender, move, field, stat, max_single, mode=mode)
        return {
            "success": False,
            "reason": f"即使满 {max_single} {stat} {val_label}也无法达成 {target}",
            "optimal_ev": max_single if mode == "ev" else 0,
            "optimal_sp": max_single if mode == "sp" else 0,
            "damage_at_optimal": result_max.min_damage,
            "damage_range": [result_max.min_damage, result_max.max_damage],
        }

    return {
        "success": True,
        "target": target,
        "threshold": threshold,
        "stat": stat,
        "optimal_ev": best_val if mode == "ev" else 0,
        "optimal_sp": best_val if mode == "sp" else 0,
        "remaining_evs": max_total - best_val if mode == "ev" else 0,
        "remaining_sp": max_total - best_val if mode == "sp" else 0,
        "damage_range": [best_damage.min_damage, best_damage.max_damage],
        "description": best_damage.description,
    }


def optimize_defense_ev(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    target: Literal["survive", "survive_2hko"] = "survive",
    threshold: Literal["guaranteed", "likely"] = "guaranteed",
    mode: Literal["ev", "sp"] = "ev",
) -> dict:
    """
    Find the minimal defensive EV investment to survive a hit.

    target:
        "survive"     -> max_damage < defender.current_hp (guaranteed survive 1 hit)
        "survive_2hko"-> max_damage * 2 < defender.current_hp (guaranteed survive 2 hits)

    threshold:
        "guaranteed" -> use max_damage (worst roll)
        "likely"     -> use average damage

    Returns a dict with the optimal EV allocation.
    """
    hits_to_survive = {"survive": 1, "survive_2hko": 2}[target]
    use_max = threshold == "guaranteed"

    # Determine which defensive stat to optimize
    from damage import uses_physical_attack
    hits_physical = uses_physical_attack(attacker, defender, move)
    stat = "defense" if hits_physical else "sp_defense"

    result = calculate_damage(attacker, defender, move, field, gen=9)
    if result.max_damage == 0:
        return {
            "success": True,
            "reason": "该招式不造成伤害或免疫，无需防御努力值",
            "optimal_ev": 0,
            "damage_range": [0, 0],
        }

    best_val: Optional[int] = None
    best_damage: Optional[DamageResult] = None

    if mode == "sp":
        max_single = MAX_SINGLE_SP
        step = SP_STEP
        max_total = MAX_TOTAL_SP
        val_label = "能力点数"
    else:
        max_single = MAX_SINGLE_EVS
        step = EV_STEP
        max_total = MAX_TOTAL_EVS
        val_label = "努力值"

    for val in range(0, max_single + 1, step):
        result = _evaluate_defense(attacker, defender, move, field, stat, val, mode=mode)
        dmg = result.max_damage if use_max else sum(result.damage) // len(result.damage)
        total = dmg * hits_to_survive

        if total < defender.current_hp:
            best_val = val
            best_damage = result
            break

    if best_val is None:
        result_max = _evaluate_defense(attacker, defender, move, field, stat, max_single, mode=mode)
        return {
            "success": False,
            "reason": f"即使满 {max_single} {stat} {val_label}也无法{target}",
            "optimal_ev": max_single if mode == "ev" else 0,
            "optimal_sp": max_single if mode == "sp" else 0,
            "damage_range": [result_max.min_damage, result_max.max_damage],
            "suggestion": "尝试同时投资 HP 和防御",
        }

    return {
        "success": True,
        "target": target,
        "threshold": threshold,
        "stat": stat,
        "optimal_ev": best_val if mode == "ev" else 0,
        "optimal_sp": best_val if mode == "sp" else 0,
        "remaining_evs": max_total - best_val if mode == "ev" else 0,
        "remaining_sp": max_total - best_val if mode == "sp" else 0,
        "damage_range": [best_damage.min_damage, best_damage.max_damage],
        "description": best_damage.description,
    }


# ---------------------------------------------------------------------------
# Dual-stat optimization (HP + Defense / HP + Sp. Defense)
# ---------------------------------------------------------------------------


def optimize_bulk_evs(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    target: Literal["survive", "survive_2hko"] = "survive",
    mode: Literal["ev", "sp"] = "ev",
) -> dict:
    """
    Search for the minimal combined HP + Defense (or HP + Sp. Defense)
    EV investment to survive a hit. Uses a simple grid search.

    Constraints:
        hp_ev + def_ev <= MAX_TOTAL_EVS
        hp_ev <= MAX_SINGLE_EVS, def_ev <= MAX_SINGLE_EVS

    Returns the best allocation found.
    """
    from damage import uses_physical_attack
    hits_physical = uses_physical_attack(attacker, defender, move)
    def_stat = "defense" if hits_physical else "sp_defense"
    hits_to_survive = {"survive": 1, "survive_2hko": 2}[target]

    if mode == "sp":
        max_single = MAX_SINGLE_SP
        step = SP_STEP
        max_total = MAX_TOTAL_SP
        val_label = "能力点数"
    else:
        max_single = MAX_SINGLE_EVS
        step = EV_STEP
        max_total = MAX_TOTAL_EVS
        val_label = "努力值"

    best_total = max_total + 1
    best_combo = (0, 0)
    best_result = None

    # Grid search — at most (33 * 33) = 1089 iterations in SP mode
    for hp_val in range(0, max_single + 1, step):
        for def_val in range(0, max_single + 1, step):
            if hp_val + def_val > max_total:
                break
            if hp_val + def_val >= best_total:
                continue

            dfn = copy.copy(defender)
            if mode == "sp":
                dfn = _set_sp(dfn, "hp", hp_val)
                dfn = _set_sp(dfn, def_stat, def_val)
            else:
                dfn.evs = dict(defender.evs)
                dfn.evs["hp"] = hp_val
                dfn.evs[def_stat] = def_val
                dfn.raw_stats = {}
                dfn.stats = {}

            result = calculate_damage(attacker, dfn, move, field, gen=9)
            if result.max_damage * hits_to_survive < dfn.current_hp:
                best_total = hp_val + def_val
                best_combo = (hp_val, def_val)
                best_result = result
                # Early exit: can't do better than this total
                break

    if best_result is None:
        return {
            "success": False,
            "reason": f"即使满{val_label}分配也无法{target}",
            "optimal_hp_ev": 0,
            "optimal_def_ev": 0,
            "optimal_hp_sp": 0,
            "optimal_def_sp": 0,
        }

    hp_val, def_val = best_combo
    return {
        "success": True,
        "target": target,
        "hp_stat": "hp",
        "def_stat": def_stat,
        "optimal_hp_ev": hp_val if mode == "ev" else 0,
        "optimal_def_ev": def_val if mode == "ev" else 0,
        "optimal_hp_sp": hp_val if mode == "sp" else 0,
        "optimal_def_sp": def_val if mode == "sp" else 0,
        "total_evs": best_total if mode == "ev" else 0,
        "total_sp": best_total if mode == "sp" else 0,
        "remaining_evs": max_total - best_total if mode == "ev" else 0,
        "remaining_sp": max_total - best_total if mode == "sp" else 0,
        "damage_range": [best_result.min_damage, best_result.max_damage],
        "description": best_result.description,
    }


# ---------------------------------------------------------------------------
# High-level wrapper
# ---------------------------------------------------------------------------


def optimize_evs(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    goal: Literal["ko", "survive", "survive_bulk"] = "ko",
    target: Literal["ohko", "2hko", "3hko", "survive", "survive_2hko"] = "ohko",
    threshold: Literal["guaranteed", "likely"] = "guaranteed",
    mode: Literal["ev", "sp"] = "ev",
) -> dict:
    """
    Unified EV/SP optimizer entry point.

    mode:
        "ev" -> Gen9 effort values (508/252/4 system)
        "sp" -> Champions stat points (66/32/1 system)

    goal:
        "ko"           -> optimize attacking EVs/SPs (use target="ohko"/"2hko"/"3hko")
        "survive"      -> optimize single defensive EV/SP (use target="survive"/"survive_2hko")
        "survive_bulk" -> optimize HP + Defense combined

    Examples:
        # How many Attack EVs to OHKO?
        optimize_evs(att, dfn, move, field, goal="ko", target="ohko")

        # How many Defense SPs to survive? (Champions)
        optimize_evs(att, dfn, move, field, goal="survive", target="survive", mode="sp")

        # Optimal HP + Defense split to survive?
        optimize_evs(att, dfn, move, field, goal="survive_bulk", target="survive")
    """
    if goal == "ko":
        return optimize_attack_ev(attacker, defender, move, field, target=target, threshold=threshold, mode=mode)  # type: ignore[arg-type]
    elif goal == "survive":
        return optimize_defense_ev(attacker, defender, move, field, target=target, threshold=threshold, mode=mode)  # type: ignore[arg-type]
    else:
        return optimize_bulk_evs(attacker, defender, move, field, target=target, mode=mode)  # type: ignore[arg-type]
