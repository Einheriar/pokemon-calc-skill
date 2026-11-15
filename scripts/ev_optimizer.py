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

from damage import calculate_damage, compute_raw_stats, get_modified_stat
from models import DamageResult, Field, Move, Pokemon
import display_zh

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
_STATEFUL_REPEAT_MOVES = frozenset({
    "Super Fang", "Nature's Madness", "Ruination", "Endeavor", "Final Gambit",
})


def _unsupported_stateful_repeat(move: Move, repeated: bool) -> dict | None:
    """Reject multi-turn thresholds the optimizer cannot model as repeated hits."""
    canonical_name = move.name.replace("’", "'")
    if repeated and canonical_name in _STATEFUL_REPEAT_MOVES:
        return {
            "success": False,
            "unsupported": True,
            "reason": display_zh.OPT_STATEFUL_REPEAT_UNSUPPORTED,
        }
    return None


def _has_stateful_tera_sequence(attacker: Pokemon, defender: Pokemon, move: Move, repeated: bool) -> bool:
    if not repeated:
        return False
    from engine_enums import resolve_tera_type_en

    stellar_user = attacker.is_terastalize and resolve_tera_type_en(attacker.tera_type or "") == "Stellar"
    teraform_zero = (
        attacker.is_terastalize and not attacker.tera_effects_applied
        and attacker.name_en == "Terapagos-Stellar" and attacker.ability == "Teraform Zero"
    )
    shell_defender = defender.ability == "Tera Shell"
    return stellar_user or teraform_zero or shell_defender


def _stateful_sequence_unsupported(move: Move) -> dict:
    return {
        "success": False,
        "unsupported": True,
        "reason": display_zh.OPT_STATEFUL_REPEAT_UNSUPPORTED,
    }


def _probability_meets_threshold(probability: float, threshold: str, goal: str) -> bool:
    """Use exact all-roll success for guaranteed and a 50% chance for likely."""
    if goal == "ko":
        return probability >= (1.0 if threshold == "guaranteed" else 0.5)
    survival_probability = 1.0 - probability
    return survival_probability >= (1.0 if threshold == "guaranteed" else 0.5)


def _stateful_worst_case_survives(
    attacker: Pokemon, defender: Pokemon, move: Move, field: Field, hits: int,
) -> tuple[bool, DamageResult | None]:
    """Check sequential maximum rolls, recalculating HP- and state-dependent damage."""
    if move.hits > 1 or getattr(move, "is_multi_hit", False):
        return False, None
    att = copy.deepcopy(attacker)
    dfn = copy.deepcopy(defender)
    base_move = copy.deepcopy(move)
    current_field = copy.deepcopy(field)
    first_result = None
    for _ in range(hits):
        # Re-evaluate move type/category from its original definition each use.
        result = calculate_damage(att, dfn, base_move, current_field, gen=9)
        if first_result is None:
            first_result = result
        if not result.damage or result.max_damage >= dfn.current_hp:
            return False, first_result
        next_hp = dfn.current_hp - result.max_damage
        att = copy.deepcopy(result.attacker_after or att)
        dfn = copy.deepcopy(result.defender_after or dfn)
        dfn.current_hp = next_hp
        current_field = copy.deepcopy(result.field_state or current_field)
    return True, first_result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_stats(pokemon: Pokemon) -> None:
    """Materialize optimizer-owned inputs before reading their HP pool."""
    if not pokemon.raw_stats:
        compute_raw_stats(pokemon)
    elif not pokemon.stats:
        pokemon.stats = {stat: get_modified_stat(value, pokemon.boosts.get(stat, 0))
                         for stat, value in pokemon.raw_stats.items()}


def _set_ev(pokemon: Pokemon, stat: str, ev: int) -> Pokemon:
    """Return a copy of pokemon with the given stat's EV set."""
    pk = copy.copy(pokemon)
    pk.evs = dict(pokemon.evs)
    pk.evs[stat] = ev
    # Invalidate cached stats and HP pool: optimizers evaluate from a fresh
    # full-HP state, so current_hp must be recomputed from the new max_hp.
    pk.raw_stats = {}
    pk.stats = {}
    pk.current_hp = 0
    return pk


def _set_sp(pokemon: Pokemon, stat: str, sp: int) -> Pokemon:
    """Return a copy of pokemon with the given stat's SP converted to equivalent EV.

    Champions SP mode: SP is an input/view layer; the engine stores EVs
    (AGENTS.md invariant: EV = 8*SP - 4, SP=0 maps to 0 EV, SP=32 -> 252 EV).
    At Lv.50/IV=31 this yields exactly +1 stat point per SP.

    After setting ev, we invalidate cached stats so compute_raw_stats()
    in the damage engine will recalculate them correctly.
    """
    pk = copy.copy(pokemon)
    if not pk.evs:
        pk.evs = {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0}
    pk.evs = dict(pk.evs)
    pk.evs[stat] = 0 if sp <= 0 else 8 * sp - 4
    # Invalidate cached stats and HP pool so compute_raw_stats recalculates
    pk.raw_stats = {}
    pk.stats = {}
    pk.current_hp = 0
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


def _remaining_allocation(
    pokemon: Pokemon,
    optimized: dict[str, int],
    mode: Literal["ev", "sp"],
) -> int:
    """Return the unused pool after replacing only the optimized stats.

    The original allocation on every other stat remains part of the set and
    must therefore be deducted from the reported remainder. SP is a display
    view over the stored EVs, so convert those other stats with the same
    EV -> SP rule used by the public query layer.
    """
    original_evs = getattr(pokemon, "evs", None) or {}
    if mode == "sp":
        max_total = MAX_TOTAL_SP

        def allocation(ev: object) -> int:
            ev_value = max(0, int(ev or 0))
            return 0 if ev_value == 0 else (ev_value + 4) // 8

    else:
        max_total = MAX_TOTAL_EVS

        def allocation(ev: object) -> int:
            return max(0, int(ev or 0))

    other_total = sum(
        allocation(original_evs.get(stat, 0))
        for stat in _STAT_KEYS
        if stat not in optimized
    )
    return max(0, max_total - sum(optimized.values()) - other_total)


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
        "likely"     -> use average damage, or a >=50% exact KO chance for
                        supported stateful Terastallization sequences

    Returns a dict with the optimal EV, resulting damage, and description.
    """
    unsupported = _unsupported_stateful_repeat(move, target in ("2hko", "3hko"))
    if unsupported is not None:
        return unsupported

    hits_needed = {"ohko": 1, "2hko": 2, "3hko": 3}[target]
    use_min = threshold == "guaranteed"
    _ensure_stats(attacker)
    _ensure_stats(defender)
    stateful_sequence = _has_stateful_tera_sequence(attacker, defender, move, hits_needed > 1)
    if stateful_sequence and (move.hits > 1 or getattr(move, "is_multi_hit", False)):
        return _stateful_sequence_unsupported(move)

    # Determine which stat to optimize
    result = calculate_damage(attacker, defender, move, field, gen=9)
    if (_has_stateful_tera_sequence(attacker, defender, move, True)
            and (move.hits > 1 or move.is_multi_hit or len(result.damage) == 256)):
        return _stateful_sequence_unsupported(move)
    if result.min_damage == 0:
        return {
            "success": False,
            "reason": display_zh.OPT_NO_DAMAGE,
            "optimal_ev": 0,
            "damage_at_optimal": result.min_damage,
        }

    # Physical vs Special determination (same logic as damage.py)
    hits_physical = (result.move or move).category == "Physical"
    stat = "attack" if hits_physical else "sp_attack"
    search_stats = [stat]
    if (move.name == "Tera Blast" and attacker.is_terastalize) or (
        move.name == "Tera Starstorm" and attacker.name_en == "Terapagos-Stellar"
        and attacker.is_terastalize
    ):
        search_stats.append("sp_attack" if hits_physical else "attack")

    best_val: Optional[int] = None
    best_damage: Optional[DamageResult] = None

    if mode == "sp":
        max_single = MAX_SINGLE_SP
        step = SP_STEP
        max_total = MAX_TOTAL_SP
        val_label = display_zh.VAL_LABEL_SP
    else:
        max_single = MAX_SINGLE_EVS
        step = EV_STEP
        max_total = MAX_TOTAL_EVS
        val_label = display_zh.VAL_LABEL_EV

    for val in range(0, max_single + 1, step):
        for candidate_stat in search_stats:
            result = _evaluate_attack(attacker, defender, move, field, candidate_stat, val, mode=mode)
            if stateful_sequence:
                from ko_chance import get_stateful_ko_probability

                candidate_attacker = _set_sp(attacker, candidate_stat, val) if mode == "sp" else _set_ev(attacker, candidate_stat, val)
                _ensure_stats(candidate_attacker)
                probability = get_stateful_ko_probability(
                    candidate_attacker, defender, move, field, hits_needed,
                )
                if probability is None:
                    return _stateful_sequence_unsupported(move)
                meets_target = _probability_meets_threshold(probability, threshold, "ko")
            else:
                probability = None
                dmg = result.min_damage if use_min else sum(result.damage) // len(result.damage)
                # Each candidate can change Tera Blast's category independently.
                move_hits = max(1, int(getattr(move, "hits", 1) or 1))
                total = dmg * hits_needed * move_hits
                meets_target = total >= defender.current_hp
            if meets_target:
                stat = candidate_stat
                best_val = val
                best_damage = result
                best_probability = probability
                break
        if best_val is not None:
            break

    if best_val is None:
        maximums = [_evaluate_attack(attacker, defender, move, field, candidate, max_single, mode=mode)
                    for candidate in search_stats]
        result_max = max(maximums, key=lambda candidate: candidate.min_damage if use_min
                         else sum(candidate.damage) / len(candidate.damage))
        return {
            "success": False,
            "reason": display_zh.opt_fail_attack(max_single, "/".join(search_stats), val_label, target),
            "optimal_ev": 0,
            "optimal_sp": 0,
            "max_invested_ev": max_single if mode == "ev" else 0,
            "max_invested_sp": max_single if mode == "sp" else 0,
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
        "remaining_evs": _remaining_allocation(attacker, {stat: best_val}, mode) if mode == "ev" else 0,
        "remaining_sp": _remaining_allocation(attacker, {stat: best_val}, mode) if mode == "sp" else 0,
        "damage_range": [best_damage.min_damage, best_damage.max_damage],
        "description": best_damage.description,
        **({"ko_probability": round(best_probability * 100, 1)} if stateful_sequence else {}),
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
        "likely"     -> use average damage, or a >=50% exact survival chance
                        for supported stateful Terastallization sequences

    Returns a dict with the optimal EV allocation.
    """
    unsupported = _unsupported_stateful_repeat(move, target == "survive_2hko")
    if unsupported is not None:
        return unsupported

    hits_to_survive = {"survive": 1, "survive_2hko": 2}[target]
    use_max = threshold == "guaranteed"
    _ensure_stats(attacker)
    _ensure_stats(defender)
    stateful_sequence = _has_stateful_tera_sequence(attacker, defender, move, hits_to_survive > 1)
    if stateful_sequence and (move.hits > 1 or getattr(move, "is_multi_hit", False)):
        return _stateful_sequence_unsupported(move)

    # Determine which defensive stat to optimize
    result = calculate_damage(attacker, defender, move, field, gen=9)
    if (_has_stateful_tera_sequence(attacker, defender, move, True)
            and (move.hits > 1 or move.is_multi_hit or len(result.damage) == 256)):
        return _stateful_sequence_unsupported(move)
    effective_move = result.move or move
    hits_physical = effective_move.category == "Physical" or effective_move.deals_physical_damage
    stat = "defense" if hits_physical else "sp_defense"
    if result.max_damage == 0:
        return {
            "success": True,
            "reason": display_zh.OPT_NO_DAMAGE_DEFENSE,
            "optimal_ev": 0,
            "damage_range": [0, 0],
        }

    best_val: Optional[int] = None
    best_damage: Optional[DamageResult] = None

    if mode == "sp":
        max_single = MAX_SINGLE_SP
        step = SP_STEP
        max_total = MAX_TOTAL_SP
        val_label = display_zh.VAL_LABEL_SP
    else:
        max_single = MAX_SINGLE_EVS
        step = EV_STEP
        max_total = MAX_TOTAL_EVS
        val_label = display_zh.VAL_LABEL_EV

    for val in range(0, max_single + 1, step):
        result = _evaluate_defense(attacker, defender, move, field, stat, val, mode=mode)
        if stateful_sequence:
            from ko_chance import get_stateful_ko_probability

            candidate_defender = _set_sp(defender, stat, val) if mode == "sp" else _set_ev(defender, stat, val)
            _ensure_stats(candidate_defender)
            probability = get_stateful_ko_probability(
                attacker, candidate_defender, move, field, hits_to_survive,
            )
            if probability is None:
                return _stateful_sequence_unsupported(move)
            meets_target = _probability_meets_threshold(probability, threshold, "survive")
        else:
            probability = None
            dmg = result.max_damage if use_max else sum(result.damage) // len(result.damage)
            # Damage rolls are per-hit; surviving a multi-hit move means
            # surviving hits × hits_to_survive total damage.
            move_hits = max(1, int(getattr(move, "hits", 1) or 1))
            total = dmg * hits_to_survive * move_hits
            meets_target = total < defender.current_hp

        if meets_target:
            best_val = val
            best_damage = result
            best_probability = probability
            break

    if best_val is None:
        result_max = _evaluate_defense(attacker, defender, move, field, stat, max_single, mode=mode)
        return {
            "success": False,
            "reason": display_zh.opt_fail_defense(max_single, stat, val_label, target),
            "optimal_ev": 0,
            "optimal_sp": 0,
            "max_invested_ev": max_single if mode == "ev" else 0,
            "max_invested_sp": max_single if mode == "sp" else 0,
            "damage_range": [result_max.min_damage, result_max.max_damage],
            "suggestion": display_zh.SUGGEST_HP_DEFENSE,
        }

    return {
        "success": True,
        "target": target,
        "threshold": threshold,
        "stat": stat,
        "optimal_ev": best_val if mode == "ev" else 0,
        "optimal_sp": best_val if mode == "sp" else 0,
        "remaining_evs": _remaining_allocation(defender, {stat: best_val}, mode) if mode == "ev" else 0,
        "remaining_sp": _remaining_allocation(defender, {stat: best_val}, mode) if mode == "sp" else 0,
        "damage_range": [best_damage.min_damage, best_damage.max_damage],
        "description": best_damage.description,
        **({"survival_probability": round((1 - best_probability) * 100, 1)} if stateful_sequence else {}),
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
    unsupported = _unsupported_stateful_repeat(move, target == "survive_2hko")
    if unsupported is not None:
        return unsupported

    _ensure_stats(attacker)
    _ensure_stats(defender)
    hits_to_survive = {"survive": 1, "survive_2hko": 2}[target]
    stateful_sequence = _has_stateful_tera_sequence(attacker, defender, move, hits_to_survive > 1)
    if stateful_sequence and (move.hits > 1 or getattr(move, "is_multi_hit", False)):
        return _stateful_sequence_unsupported(move)
    initial_result = calculate_damage(attacker, defender, move, field, gen=9)
    if (_has_stateful_tera_sequence(attacker, defender, move, True)
            and (move.hits > 1 or move.is_multi_hit or len(initial_result.damage) == 256)):
        return _stateful_sequence_unsupported(move)
    effective_move = initial_result.move or move
    hits_physical = effective_move.category == "Physical" or effective_move.deals_physical_damage
    def_stat = "defense" if hits_physical else "sp_defense"

    if mode == "sp":
        max_single = MAX_SINGLE_SP
        step = SP_STEP
        max_total = MAX_TOTAL_SP
        val_label = display_zh.VAL_LABEL_SP
    else:
        max_single = MAX_SINGLE_EVS
        step = EV_STEP
        max_total = MAX_TOTAL_EVS
        val_label = display_zh.VAL_LABEL_EV

    best_total = max_total + 1
    best_combo = (0, 0)
    best_result = None

    move_hits = max(1, int(getattr(move, "hits", 1) or 1))

    # Grid search — at most (33 * 33) = 1089 iterations in SP mode
    for hp_val in range(0, max_single + 1, step):
        for def_val in range(0, max_single + 1, step):
            if hp_val + def_val > max_total:
                break
            if hp_val + def_val >= best_total:
                continue

            # Route through _set_ev/_set_sp so cached stats AND the HP pool
            # (current_hp) are invalidated for both EV and SP modes.
            if mode == "sp":
                dfn = _set_sp(defender, "hp", hp_val)
                dfn = _set_sp(dfn, def_stat, def_val)
            else:
                dfn = _set_ev(defender, "hp", hp_val)
                dfn = _set_ev(dfn, def_stat, def_val)

            # The damage engine works on private copies; materialize this
            # optimizer-owned candidate before reading its recomputed HP.
            compute_raw_stats(dfn)
            result = calculate_damage(attacker, dfn, move, field, gen=9)
            if stateful_sequence:
                if dfn.item in (
                    "Sitrus Berry", "Figy Berry", "Aguav Berry", "Iapapa Berry",
                    "Mago Berry", "Wiki Berry",
                ):
                    from ko_chance import get_stateful_ko_probability

                    probability = get_stateful_ko_probability(
                        attacker, dfn, move, field, hits_to_survive,
                    )
                    if probability is None:
                        return _stateful_sequence_unsupported(move)
                    survives = probability == 0.0
                else:
                    survives, sequence_result = _stateful_worst_case_survives(
                        attacker, dfn, move, field, hits_to_survive,
                    )
                    if sequence_result is not None:
                        result = sequence_result
            else:
                survives = result.max_damage * hits_to_survive * move_hits < dfn.current_hp
            if survives:
                best_total = hp_val + def_val
                best_combo = (hp_val, def_val)
                best_result = result
                # Early exit: can't do better than this total
                break

    if best_result is None:
        return {
            "success": False,
            "reason": display_zh.opt_fail_dual(val_label, target),
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
        "remaining_evs": _remaining_allocation(
            defender, {"hp": hp_val, def_stat: def_val}, mode,
        ) if mode == "ev" else 0,
        "remaining_sp": _remaining_allocation(
            defender, {"hp": hp_val, def_stat: def_val}, mode,
        ) if mode == "sp" else 0,
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
        # Coerce ko-style targets (e.g. the CLI default "ohko") to survive goals
        if target not in ("survive", "survive_2hko"):
            target = "survive"
        return optimize_defense_ev(attacker, defender, move, field, target=target, threshold=threshold, mode=mode)  # type: ignore[arg-type]
    else:
        if target not in ("survive", "survive_2hko"):
            target = "survive"
        return optimize_bulk_evs(attacker, defender, move, field, target=target, mode=mode)  # type: ignore[arg-type]
