#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KO chance calculator ported from script_res/ko_chance.js.
"""
from __future__ import annotations

import math
from copy import copy, deepcopy
from dataclasses import fields, is_dataclass
from typing import Optional

from models import Field, Move, Pokemon
import display_zh
from engine_enums import T

_HALF_CURRENT_HP_MOVES = frozenset({"Super Fang", "Nature's Madness", "Ruination"})
_SINGLE_USE_MOVES = frozenset({"Endeavor", "Final Gambit"})


def get_ko_chance_text(
    damage: list[int],
    move: Move,
    defender: Pokemon,
    field: Field,
    is_bad_dreams: bool = False,
    *,
    battle_context: tuple[Pokemon, Pokemon, Move, Field] | None = None,
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
    # Hazards model entry before this turn's Terastallization. Residuals and
    # terrain recovery use the current battle types instead.
    entry_defender = copy(defender)
    entry_defender.is_terastalize = False
    from damage import get_current_types
    defender.types = get_current_types(defender)

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

    # Aggregate multihit rolls cannot prove an OHKO when an intermediate hit
    # can consume a berry or change Tera state. Reject before the fast OHKO path.
    if (battle_context and _requires_stateful_tera(*battle_context)
            and (len(damage) == 256 or move.hits > 1 or move.is_multi_hit)):
        return display_zh.KO_TERA_STATE_UNSUPPORTED

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
    hazard_immune = defender.ability == "Magic Guard" or defender.item == "Heavy-Duty Boots"
    if field.is_stealth_rock and not hazard_immune:
        eff = _get_rock_effectiveness(entry_defender)
        hazards += math.floor(eff * defender.max_hp / 8)
        hazard_texts.append(display_zh.HAZARD_STEALTH_ROCK)

    from damage import is_grounded
    grounded = is_grounded(defender, field)
    if is_grounded(entry_defender, field) and not hazard_immune:
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
    eot_deltas: list[int] = []
    field_eot_deltas: list[int] = []
    max_chip = 0.5 if defender.is_dynamax else 1.0

    def add_eot(delta: int, label: str, field_dependent: bool = False) -> None:
        nonlocal eot
        eot += delta
        eot_deltas.append(delta)
        if field_dependent:
            field_eot_deltas.append(delta)
        eot_texts.append(label)

    if field.weather == "Sun" and defender.item != "Utility Umbrella":
        if defender.ability in ("Dry Skin", "Solar Power"):
            add_eot(-math.floor(math.floor(defender.max_hp / 8) * max_chip), display_zh.ability_damage(defender.ability), True)
    elif field.weather == "Rain" and defender.item != "Utility Umbrella":
        if defender.ability == "Dry Skin":
            add_eot(math.floor(math.floor(defender.max_hp / 8) * max_chip), display_zh.EOT_DRY_SKIN_HEAL, True)
        elif defender.ability == "Rain Dish":
            add_eot(math.floor(math.floor(defender.max_hp / 16) * max_chip), display_zh.EOT_RAIN_DISH_HEAL, True)
    elif field.weather == "Sand":
        if "Rock" not in defender.types and "Ground" not in defender.types and "Steel" not in defender.types:
            if defender.ability not in ("Magic Guard", "Overcoat", "Sand Force", "Sand Rush", "Sand Veil") and defender.item != "Safety Goggles":
                add_eot(-math.floor(math.floor(defender.max_hp / 16) * max_chip), display_zh.EOT_SAND_DAMAGE, True)
    elif field.weather == "Hail":
        if defender.ability == "Ice Body":
            add_eot(math.floor(math.floor(defender.max_hp / 16) * max_chip), display_zh.EOT_ICE_BODY_HEAL, True)
        elif T.ICE not in defender.types and defender.ability not in ("Magic Guard", "Overcoat", "Snow Cloak") and defender.item != "Safety Goggles":
            add_eot(-math.floor(math.floor(defender.max_hp / 16) * max_chip), display_zh.EOT_HAIL_DAMAGE, True)
    elif field.weather == "Snow" and defender.ability == "Ice Body":
        add_eot(math.floor(math.floor(defender.max_hp / 16) * max_chip), display_zh.EOT_ICE_BODY_HEAL, True)

    if defender.item == "Leftovers":
        add_eot(math.floor(math.floor(defender.max_hp / 16) * max_chip), display_zh.EOT_LEFTOVERS_HEAL)
    elif defender.item == "Black Sludge":
        if T.POISON in defender.types:
            add_eot(math.floor(math.floor(defender.max_hp / 16) * max_chip), display_zh.EOT_BLACK_SLUDGE_HEAL)
        elif defender.ability not in ("Magic Guard", "Klutz"):
            add_eot(-math.floor(math.floor(defender.max_hp / 8) * max_chip), display_zh.EOT_BLACK_SLUDGE_DAMAGE)

    if field.terrain == "Grassy" and grounded:
        add_eot(math.floor(math.floor(defender.max_hp / 16) * max_chip), display_zh.EOT_GRASSY_HEAL, True)

    toxic_counter = 0
    if defender.status == "Poisoned":
        if defender.ability == "Poison Heal":
            add_eot(math.floor(math.floor(defender.max_hp / 8) * max_chip), display_zh.EOT_POISON_HEAL_HEAL)
        elif defender.ability != "Magic Guard":
            add_eot(-math.floor(math.floor(defender.max_hp / 8) * max_chip), display_zh.EOT_POISON_DAMAGE)
    elif defender.status == "Badly Poisoned":
        if defender.ability == "Poison Heal":
            add_eot(math.floor(math.floor(defender.max_hp / 8) * max_chip), display_zh.EOT_POISON_HEAL_HEAL)
        elif defender.ability != "Magic Guard":
            eot_texts.append(display_zh.EOT_TOXIC_DAMAGE)
            toxic_counter = getattr(defender, "toxic_counter", 0)
    elif defender.status == "Burned":
        burn_div = 16  # gen >= 7
        if defender.ability == "Heatproof":
            add_eot(-math.floor(math.floor(defender.max_hp / burn_div / 2) * max_chip), display_zh.EOT_HALVED_BURN_DAMAGE)
        elif defender.ability != "Magic Guard":
            add_eot(-math.floor(math.floor(defender.max_hp / burn_div) * max_chip), display_zh.EOT_BURN_DAMAGE)
    elif defender.status == "Asleep" and is_bad_dreams and defender.ability != "Magic Guard":
        add_eot(-math.floor(math.floor(defender.max_hp / 8) * max_chip), display_zh.EOT_BAD_DREAMS)

    if field.is_salt_cure and defender.ability != "Magic Guard":
        if T.WATER not in defender.types and T.STEEL not in defender.types:
            add_eot(-math.floor(math.floor(defender.max_hp / 8) * max_chip), display_zh.EOT_SALT_CURE_DAMAGE)
        else:
            add_eot(-math.floor(math.floor(defender.max_hp / 4) * max_chip), display_zh.EOT_SALT_CURE_EXTRA)

    # Multi-hit squash
    qualifier = ""
    multihit = len(damage) == 256 or move.hits > 1
    if move.hits > 1 and not getattr(move, "is_triple_hit", False):
        qualifier = display_zh.MULTI_HIT_QUALIFIER
        damage = squash_multihit(damage, move.hits)
        multihit = True

    if move.name in _HALF_CURRENT_HP_MOVES:
        return _half_current_hp_ko_text(
            defender.current_hp - hazards, defender.max_hp, eot, toxic_counter,
            has_sitrus, has_figy, gluttony, ripen, hazard_texts, eot_texts,
            any(delta > 0 for delta in eot_deltas),
            any(delta < 0 for delta in eot_deltas) or toxic_counter > 0,
        )

    if battle_context and _requires_stateful_tera(*battle_context):
        return _stateful_ko_text(
            battle_context, move, defender, field, hazards, eot,
            toxic_counter, has_sitrus, has_figy, gluttony, ripen,
            hazard_texts, eot_texts, eot_deltas, field_eot_deltas,
        )

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

    if move.name in _SINGLE_USE_MOVES:
        return display_zh.KO_SINGLE_USE_NO_KO

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


def _half_current_hp_ko_text(
    hp: int,
    max_hp: int,
    eot: int,
    toxic_counter: int,
    has_sitrus: bool,
    has_figy: bool,
    gluttony: bool,
    ripen: int,
    hazard_texts: list[str],
    eot_texts: list[str],
    has_healing_eot: bool,
    has_damaging_eot: bool,
) -> str:
    """Resolve repeated current-HP halving moves with deterministic HP state."""
    suffix_texts = list(hazard_texts + eot_texts)
    if has_sitrus:
        suffix_texts.append(display_zh.EOT_SITRUS_HEAL)
    if has_figy:
        suffix_texts.append(display_zh.EOT_BERRY_HEAL)
    suffix = display_zh.condition_suffix(suffix_texts)

    # Netting recovery with residual damage can miss a faint before the later
    # event runs. Do not promise a KO when the current model cannot order them.
    if has_damaging_eot and (has_healing_eot or has_sitrus or has_figy):
        return display_zh.KO_HALF_UNSUPPORTED + suffix

    hp = max(0, hp)
    if hp == 0:
        return display_zh.ko_ohko_with(suffix)

    for hits in range(1, 10):
        dealt = max(1, hp // 2)
        if dealt >= hp:
            return display_zh.ko_ohko_with(suffix) if hits == 1 else display_zh.ko_n_guaranteed(hits, suffix)
        hp -= dealt

        if has_sitrus and hp <= max_hp // 2:
            hp = min(max_hp, hp + math.floor(ripen * max_hp / 4))
            has_sitrus = False
        elif has_figy and (
            (hp <= max_hp // 4 and not gluttony)
            or (hp <= max_hp // 2 and gluttony)
        ):
            hp = min(max_hp, hp + math.floor(ripen * max_hp / 3))
            has_figy = False

        hp = min(max_hp, hp + eot)
        if toxic_counter > 0:
            hp -= math.floor(toxic_counter * max_hp / 16)
            toxic_counter += 1
        if hp <= 0:
            return display_zh.ko_ohko_with(suffix) if hits == 1 else display_zh.ko_n_guaranteed(hits, suffix)

    return display_zh.KO_MORE_ROUNDS


def _requires_stateful_tera(attacker: Pokemon, defender: Pokemon, move: Move, field: Field) -> bool:
    from engine_enums import resolve_tera_type_en

    stellar_user = (
        attacker.is_terastalize
        and resolve_tera_type_en(attacker.tera_type or "") == "Stellar"
    )
    teraform_zero_pending = (
        not attacker.tera_effects_applied
        and attacker.is_terastalize
        and attacker.name_en == "Terapagos-Stellar"
        and attacker.ability == "Teraform Zero"
        or not defender.tera_effects_applied
        and defender.is_terastalize
        and defender.name_en == "Terapagos-Stellar"
        and defender.ability == "Teraform Zero"
    )
    shell_can_change = defender.ability == "Tera Shell" and defender.max_hp > 0
    tera_blast_drop = stellar_user and move.name == "Tera Blast"
    return stellar_user or teraform_zero_pending or shell_can_change or tera_blast_drop


def _freeze_state(value):
    """Build a hashable key from model state for KO memoization."""
    if is_dataclass(value):
        return tuple((item.name, _freeze_state(getattr(value, item.name))) for item in fields(value))
    if isinstance(value, dict):
        return tuple(sorted((key, _freeze_state(val)) for key, val in value.items()))
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_state(item) for item in value)
    if isinstance(value, set):
        return tuple(sorted(_freeze_state(item) for item in value))
    return value


def _stateful_ko_probability(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    hits: int,
    starting_hp: int,
    eot: int,
    toxic_counter: int,
    has_sitrus: bool,
    has_figy: bool,
    gluttony: bool,
    ripen: int,
    field_eot_deltas: list[int],
    memo: dict[tuple, float | None] | None = None,
    result_cache: dict[tuple, object] | None = None,
) -> float | None:
    """Recalculate each attack using branch-local HP and attacker state."""
    if hits <= 0:
        return 0.0
    if move.hits > 1 or getattr(move, "is_multi_hit", False):
        return None

    from damage import calculate_damage

    memo = memo if memo is not None else {}
    result_cache = result_cache if result_cache is not None else {}

    def walk(
        att: Pokemon,
        dfn: Pokemon,
        current_field: Field,
        hp: int,
        remaining: int,
        counter: int,
        sitrus_available: bool,
        figy_available: bool,
        turn_eot: int,
    ) -> float | None:
        key = (
            remaining, hp, counter, sitrus_available, figy_available, turn_eot,
            _freeze_state(att), _freeze_state(dfn), _freeze_state(current_field),
        )
        if key in memo:
            return memo[key]
        if hp <= 0:
            return 1.0
        if remaining <= 0:
            return 0.0

        attack_defender = deepcopy(dfn)
        attack_defender.current_hp = hp
        damage_key = (hp, _freeze_state(att), _freeze_state(attack_defender), _freeze_state(current_field))
        result = result_cache.get(damage_key)
        if result is None:
            result = calculate_damage(att, attack_defender, move, current_field, gen=9)
            result_cache[damage_key] = result
        rolls = result.damage
        if not rolls or len(rolls) == 256:
            memo[key] = None
            return None
        after_attacker = deepcopy(result.attacker_after or att)
        after_defender = deepcopy(result.defender_after or attack_defender)
        after_field = deepcopy(result.field_state or current_field)

        total = 0.0
        n = len(rolls)
        cached_damage: dict[int, float | None] = {}
        for dealt in rolls:
            if dealt >= hp:
                chance = 1.0
            else:
                branch_hp = hp - dealt
                branch_sitrus = sitrus_available
                branch_figy = figy_available
                branch_defender = deepcopy(after_defender)
                if branch_sitrus and branch_hp <= dfn.max_hp // 2:
                    branch_hp = min(dfn.max_hp, branch_hp + math.floor(ripen * dfn.max_hp / 4))
                    branch_sitrus = False
                    branch_defender.item = ""
                elif branch_figy and (
                    (branch_hp <= dfn.max_hp // 4 and not gluttony)
                    or (branch_hp <= dfn.max_hp // 2 and gluttony)
                ):
                    branch_hp = min(dfn.max_hp, branch_hp + math.floor(ripen * dfn.max_hp / 3))
                    branch_figy = False
                    branch_defender.item = ""

                branch_eot = turn_eot
                if after_field.weather != current_field.weather or after_field.terrain != current_field.terrain:
                    branch_eot -= sum(field_eot_deltas)
                branch_hp = min(dfn.max_hp, branch_hp + branch_eot)
                next_counter = counter
                if counter > 0:
                    branch_hp -= math.floor(counter * dfn.max_hp / 16)
                    next_counter += 1

                if branch_hp <= 0:
                    chance = 1.0
                elif remaining == 1:
                    chance = 0.0
                else:
                    branch_defender.current_hp = branch_hp
                    if dealt in cached_damage:
                        chance = cached_damage[dealt]
                    else:
                        chance = walk(
                            after_attacker, branch_defender, after_field, branch_hp,
                            remaining - 1, next_counter, branch_sitrus, branch_figy,
                            branch_eot,
                        )
                        cached_damage[dealt] = chance
            if chance is None:
                memo[key] = None
                return None
            total += chance

        probability = total / n
        memo[key] = probability
        return probability

    return walk(
        deepcopy(attacker), deepcopy(defender), deepcopy(field), starting_hp,
        hits, toxic_counter, has_sitrus, has_figy, eot,
    )


def get_stateful_ko_probability(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    hits: int,
    *,
    starting_hp: int | None = None,
    eot: int = 0,
) -> float | None:
    """Return exact sequential KO probability for a stateful Tera move sequence.

    ``None`` means the requested sequence needs an unsupported multihit model.
    Callers may pass ``starting_hp`` after entry hazards and ``eot`` for the
    single net end-of-turn effect they want modeled.
    """
    hp = defender.current_hp if starting_hp is None else starting_hp
    has_sitrus = defender.item == "Sitrus Berry"
    has_figy = defender.item in ("Figy Berry", "Aguav Berry", "Iapapa Berry", "Mago Berry", "Wiki Berry")
    gluttony = defender.ability == "Gluttony"
    ripen = 2 if defender.ability == "Ripen" else 1
    return _stateful_ko_probability(
        attacker, defender, move, field, hits, hp, eot, 0,
        has_sitrus, has_figy, gluttony, ripen, [],
    )


def _stateful_ko_text(
    battle_context: tuple[Pokemon, Pokemon, Move, Field],
    move: Move,
    defender: Pokemon,
    field: Field,
    hazards: int,
    eot: int,
    toxic_counter: int,
    has_sitrus: bool,
    has_figy: bool,
    gluttony: bool,
    ripen: int,
    hazard_texts: list[str],
    eot_texts: list[str],
    eot_deltas: list[int],
    field_eot_deltas: list[int],
) -> str:
    suffix_texts = list(hazard_texts + eot_texts)
    if has_sitrus and move.name != "Knock Off":
        suffix_texts.append(display_zh.EOT_SITRUS_HEAL)
    if has_figy and move.name != "Knock Off":
        suffix_texts.append(display_zh.EOT_BERRY_HEAL)
    suffix = display_zh.condition_suffix(suffix_texts)

    has_healing_eot = any(delta > 0 for delta in eot_deltas)
    has_damaging_eot = any(delta < 0 for delta in eot_deltas) or toxic_counter > 0
    if has_damaging_eot and (has_healing_eot or has_sitrus or has_figy):
        return display_zh.KO_TERA_STATE_UNSUPPORTED + suffix

    attacker, _, context_move, context_field = battle_context
    if move.name in _SINGLE_USE_MOVES:
        hits_to_check = 1
    else:
        hits_to_check = 9
    starting_hp = max(0, defender.current_hp - hazards)
    if starting_hp <= 0:
        return display_zh.ko_ohko_with(suffix)

    memo: dict[tuple, float | None] = {}
    result_cache: dict[tuple, object] = {}
    for count in range(1, hits_to_check + 1):
        chance = _stateful_ko_probability(
            attacker, defender, context_move, context_field, count, starting_hp,
            eot, toxic_counter, has_sitrus and move.name != "Knock Off",
            has_figy and move.name != "Knock Off", gluttony, ripen,
            field_eot_deltas, memo, result_cache,
        )
        if chance is None:
            return display_zh.KO_TERA_STATE_UNSUPPORTED + suffix
        if chance >= 1.0:
            return display_zh.ko_ohko_with(suffix) if count == 1 else display_zh.ko_n_guaranteed(count, suffix)
        if chance > 0.0:
            pct = round(chance * 1000) / 10
            if count == 1:
                return display_zh.ko_prob_with("", pct, suffix)
            return display_zh.ko_n_prob("", pct, count, suffix)

    if move.name in _SINGLE_USE_MOVES:
        return display_zh.KO_SINGLE_USE_NO_KO
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
