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


def _evaluate_attack(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    stat: str,
    ev: int,
) -> DamageResult:
    """Evaluate damage with a specific EV investment on the attacking stat."""
    att = _set_ev(attacker, stat, ev)
    return calculate_damage(att, defender, move, field, gen=9)


def _evaluate_defense(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    stat: str,
    ev: int,
) -> DamageResult:
    """Evaluate damage with a specific EV investment on the defending stat."""
    dfn = _set_ev(defender, stat, ev)
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

    best_ev: Optional[int] = None
    best_damage: Optional[DamageResult] = None

    # Linear search with step EV_STEP (4) — fast enough for 64 iterations max
    for ev in range(0, MAX_SINGLE_EVS + 1, EV_STEP):
        result = _evaluate_attack(attacker, defender, move, field, stat, ev)
        dmg = result.min_damage if use_min else sum(result.damage) // len(result.damage)
        total = dmg * hits_needed

        if total >= defender.current_hp:
            best_ev = ev
            best_damage = result
            break

    if best_ev is None:
        # Even 252 EVs not enough
        result_252 = _evaluate_attack(attacker, defender, move, field, stat, MAX_SINGLE_EVS)
        return {
            "success": False,
            "reason": f"即使满 {MAX_SINGLE_EVS} {stat} 努力值也无法达成 {target}",
            "optimal_ev": MAX_SINGLE_EVS,
            "damage_at_optimal": result_252.min_damage,
            "damage_range": [result_252.min_damage, result_252.max_damage],
        }

    return {
        "success": True,
        "target": target,
        "threshold": threshold,
        "stat": stat,
        "optimal_ev": best_ev,
        "remaining_evs": MAX_TOTAL_EVS - best_ev,
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

    best_ev: Optional[int] = None
    best_damage: Optional[DamageResult] = None

    for ev in range(0, MAX_SINGLE_EVS + 1, EV_STEP):
        result = _evaluate_defense(attacker, defender, move, field, stat, ev)
        dmg = result.max_damage if use_max else sum(result.damage) // len(result.damage)
        total = dmg * hits_to_survive

        if total < defender.current_hp:
            best_ev = ev
            best_damage = result
            break

    if best_ev is None:
        # Even 252 EVs not enough — try HP instead or report failure
        result_252 = _evaluate_defense(attacker, defender, move, field, stat, MAX_SINGLE_EVS)
        return {
            "success": False,
            "reason": f"即使满 {MAX_SINGLE_EVS} {stat} 努力值也无法{target}",
            "optimal_ev": MAX_SINGLE_EVS,
            "damage_range": [result_252.min_damage, result_252.max_damage],
            "suggestion": "尝试同时投资 HP 和防御",
        }

    return {
        "success": True,
        "target": target,
        "threshold": threshold,
        "stat": stat,
        "optimal_ev": best_ev,
        "remaining_evs": MAX_TOTAL_EVS - best_ev,
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

    best_total = MAX_TOTAL_EVS + 1
    best_combo = (0, 0)
    best_result = None

    # Grid search with step EV_STEP — at most (64 * 64) = 4096 iterations
    for hp_ev in range(0, MAX_SINGLE_EVS + 1, EV_STEP):
        for def_ev in range(0, MAX_SINGLE_EVS + 1, EV_STEP):
            if hp_ev + def_ev > MAX_TOTAL_EVS:
                break
            if hp_ev + def_ev >= best_total:
                continue

            dfn = copy.copy(defender)
            dfn.evs = dict(defender.evs)
            dfn.evs["hp"] = hp_ev
            dfn.evs[def_stat] = def_ev
            dfn.raw_stats = {}
            dfn.stats = {}

            result = calculate_damage(attacker, dfn, move, field, gen=9)
            if result.max_damage * hits_to_survive < dfn.current_hp:
                best_total = hp_ev + def_ev
                best_combo = (hp_ev, def_ev)
                best_result = result
                # Early exit: can't do better than this total
                break

    if best_result is None:
        return {
            "success": False,
            "reason": f"即使满努力值分配也无法{target}",
            "optimal_hp_ev": 0,
            "optimal_def_ev": 0,
        }

    hp_ev, def_ev = best_combo
    return {
        "success": True,
        "target": target,
        "hp_stat": "hp",
        "def_stat": def_stat,
        "optimal_hp_ev": hp_ev,
        "optimal_def_ev": def_ev,
        "total_evs": best_total,
        "remaining_evs": MAX_TOTAL_EVS - best_total,
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
) -> dict:
    """
    Unified EV optimizer entry point.

    goal:
        "ko"           -> optimize attacking EVs (use target="ohko"/"2hko"/"3hko")
        "survive"      -> optimize single defensive EV (use target="survive"/"survive_2hko")
        "survive_bulk" -> optimize HP + Defense combined

    Examples:
        # How many Attack EVs to OHKO?
        optimize_evs(att, dfn, move, field, goal="ko", target="ohko")

        # How many Defense EVs to survive?
        optimize_evs(att, dfn, move, field, goal="survive", target="survive")

        # Optimal HP + Defense split to survive?
        optimize_evs(att, dfn, move, field, goal="survive_bulk", target="survive")
    """
    if goal == "ko":
        return optimize_attack_ev(attacker, defender, move, field, target=target, threshold=threshold)  # type: ignore[arg-type]
    elif goal == "survive":
        return optimize_defense_ev(attacker, defender, move, field, target=target, threshold=threshold)  # type: ignore[arg-type]
    else:
        return optimize_bulk_evs(attacker, defender, move, field, target=target)  # type: ignore[arg-type]
