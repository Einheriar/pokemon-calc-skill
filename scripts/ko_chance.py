#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
KO chance calculator ported from script_res/ko_chance.js.
"""
from __future__ import annotations

import math
from typing import Optional

from models import Field, Move, Pokemon


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
    if not damage or math.isnan(damage[0]):
        return "计算出错"

    if move.name == "Pain Split" and not getattr(move, "pain_max", False):
        return "双方平分了体力！"

    if move.category == "Status" and move.name not in ("Me First", "(No Move)"):
        return "这是变化招式，不造成伤害。"

    if damage[-1] == 0:
        if field.weather == "Harsh Sun" and move.type == "水":
            return "水属性招式在大日照下蒸发了！"
        elif field.weather == "Heavy Rain" and move.type == "火":
            return "火属性招式在大雨中熄灭了！"
        return "没有造成伤害"

    has_sitrus = defender.item in ("Sitrus Berry", "文柚果")
    has_figy = defender.item in (
        "Figy Berry", "亚开果", "Aguav Berry", "岳母果", "Iapapa Berry", "爸爸果",
        "Mago Berry", "芒果", "Wiki Berry", "木子果"
    )
    gluttony = defender.ability == "Gluttony"
    ripen = 2 if defender.ability == "Ripen" else 1

    # Guaranteed OHKO checks
    if (damage[0] >= defender.current_hp
            or (len(damage) == 256 and has_sitrus and damage[0] >= defender.current_hp + math.floor(ripen * defender.max_hp / 4))
            or (len(damage) == 256 and has_figy and damage[0] >= defender.current_hp + math.floor(ripen * defender.max_hp / 3))):
        return "确定一击必杀"

    # Hazards
    hazards = 0
    hazard_texts: list[str] = []
    if field.is_stealth_rock and defender.ability != "Magic Guard" and defender.item != "Heavy-Duty Boots":
        # Simplified: type effectiveness for Rock
        eff = _get_rock_effectiveness(defender)
        hazards += math.floor(eff * defender.max_hp / 8)
        hazard_texts.append("隐形岩")

    if "飞行" not in defender.types and defender.ability not in ("Magic Guard", "Levitate") and defender.item not in ("Air Balloon", "Heavy-Duty Boots"):
        if field.spikes == 1:
            hazards += math.floor(defender.max_hp / 8)
            hazard_texts.append("1层撒菱")
        elif field.spikes == 2:
            hazards += math.floor(defender.max_hp / 6)
            hazard_texts.append("2层撒菱")
        elif field.spikes == 3:
            hazards += math.floor(defender.max_hp / 4)
            hazard_texts.append("3层撒菱")

    # End-of-turn effects
    eot = 0
    eot_texts: list[str] = []
    max_chip = 0.5 if defender.is_dynamax else 1.0

    if field.weather == "Sun":
        if defender.ability in ("Dry Skin", "Solar Power"):
            eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append(defender.ability + " 伤害")
    elif field.weather == "Rain":
        if defender.ability == "Dry Skin":
            eot += math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append("干燥皮肤 回复")
        elif defender.ability == "Rain Dish":
            eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append("雨盘 回复")
    elif field.weather == "Sand":
        if "Rock" not in defender.types and "Ground" not in defender.types and "Steel" not in defender.types:
            if defender.ability not in ("Magic Guard", "Overcoat", "Sand Force", "Sand Rush", "Sand Veil") and defender.item != "Safety Goggles":
                eot -= math.floor(math.floor(defender.max_hp / 16) * max_chip)
                eot_texts.append("沙暴伤害")
    elif field.weather == "Hail":
        if defender.ability == "Ice Body":
            eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append("寒冰之躯 回复")
        elif "冰" not in defender.types and defender.ability not in ("Magic Guard", "Overcoat", "Snow Cloak") and defender.item != "Safety Goggles":
            eot -= math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append("冰雹伤害")
    elif field.weather == "Snow" and defender.ability == "Ice Body":
        eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
        eot_texts.append("寒冰之躯 回复")

    if defender.item == "Leftovers":
        eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
        eot_texts.append("剩饭 回复")
    elif defender.item == "Black Sludge":
        if "毒" in defender.types:
            eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append("黑色污泥 回复")
        elif defender.ability not in ("Magic Guard", "Klutz"):
            eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append("黑色污泥 伤害")

    if field.terrain == "Grassy":
        if field.is_gravity or ("飞行" not in defender.types and defender.item != "Air Balloon" and defender.ability != "Levitate"):
            eot += math.floor(math.floor(defender.max_hp / 16) * max_chip)
            eot_texts.append("青草场地 回复")

    toxic_counter = 0
    if defender.status == "Poisoned":
        if defender.ability == "Poison Heal":
            eot += math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append("毒疗 回复")
        elif defender.ability != "Magic Guard":
            eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append("中毒伤害")
    elif defender.status == "Badly Poisoned":
        if defender.ability == "Poison Heal":
            eot += math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append("毒疗 回复")
        elif defender.ability != "Magic Guard":
            eot_texts.append("剧毒伤害")
            toxic_counter = getattr(defender, "toxic_counter", 0)
    elif defender.status == "Burned":
        burn_div = 16  # gen >= 7
        if defender.ability == "Heatproof":
            eot -= math.floor(math.floor(defender.max_hp / burn_div / 2) * max_chip)
            eot_texts.append("减半烧伤伤害")
        elif defender.ability != "Magic Guard":
            eot -= math.floor(math.floor(defender.max_hp / burn_div) * max_chip)
            eot_texts.append("烧伤伤害")
    elif defender.status == "Asleep" and is_bad_dreams and defender.ability != "Magic Guard":
        eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
        eot_texts.append("噩梦")

    if field.is_salt_cure and defender.ability != "Magic Guard":
        if "水" not in defender.types and "钢" not in defender.types:
            eot -= math.floor(math.floor(defender.max_hp / 8) * max_chip)
            eot_texts.append("盐腌伤害")
        else:
            eot -= math.floor(math.floor(defender.max_hp / 4) * max_chip)
            eot_texts.append("盐腌额外伤害")

    # Multi-hit squash
    qualifier = ""
    multihit = len(damage) == 256 or move.hits > 1
    if move.hits > 1 and not getattr(move, "is_triple_hit", False):
        qualifier = "约 "
        damage = squash_multihit(damage, move.hits)
        multihit = True

    # Calculate KO chance
    c = _get_ko_chance(damage, multihit, defender.current_hp - hazards, 0, 1, defender.max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen)
    after_text = f"（计入{', '.join(hazard_texts)}后）" if hazard_texts else ""

    if c == 1:
        return f"确定一击必杀{after_text}"
    elif c > 0:
        pct = round(c * 1000) / 10
        return f"{qualifier}{pct}% 概率一击必杀{after_text}"

    # Berry recovery text
    if has_sitrus and move.name != "Knock Off":
        eot_texts.append("文柚果 回复")
    if has_figy and move.name != "Knock Off":
        eot_texts.append("树果 回复")

    c = _get_ko_chance(damage, multihit, defender.current_hp - hazards + eot, eot, 1, defender.max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen)
    after_text2 = f"（计入{', '.join(hazard_texts + eot_texts)}后）" if (hazard_texts or eot_texts) else ""

    if c == 1:
        return f"确定一击必杀{after_text2}"
    elif c > 0:
        pct = round(c * 1000) / 10
        return f"{qualifier}{pct}% 概率一击必杀{after_text2}"

    # 2HKO to 4HKO
    for i in range(2, 5):
        c = _get_ko_chance(damage, multihit, defender.current_hp - hazards, 0, i, defender.max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen)
        if c == 1:
            return f"确定{i}击必杀{after_text}"
        elif c > 0:
            pct = round(c * 1000) / 10
            return f"{qualifier}{pct}% 概率{i}击必杀{after_text}"

    # 5HKO to 9HKO prediction
    for i in range(5, 10):
        if _predict_total(damage[0], 0, i, toxic_counter, defender.current_hp - hazards, defender.max_hp, has_sitrus, has_figy, gluttony, ripen) >= defender.current_hp - hazards:
            return f"确定{i}击必杀{after_text}"
        elif _predict_total(damage[-1], 0, i, toxic_counter, defender.current_hp - hazards, defender.max_hp, has_sitrus, has_figy, gluttony, ripen) >= defender.current_hp - hazards:
            return f"可能{i}击必杀{after_text}"

    return "可能需要更多回合"


def _get_rock_effectiveness(defender: Pokemon) -> float:
    """Rock-type effectiveness against defender (for Stealth Rock damage)."""
    from damage import _load_type_chart
    chart = _load_type_chart()
    eff = chart.get("Rock", {}).get(_type_zh_to_en(defender.types[0]), 1.0)
    if len(defender.types) > 1:
        eff *= chart.get("Rock", {}).get(_type_zh_to_en(defender.types[1]), 1.0)
    return eff


def _type_zh_to_en(t: str) -> str:
    from damage import _TYPE_ZH_TO_EN
    return _TYPE_ZH_TO_EN.get(t, t)


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
    """Recursive KO probability calculation."""
    n = len(damage)
    if hits == 1:
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

    toxic_damage = 0
    if toxic_counter > 0:
        toxic_damage = math.floor(toxic_counter * max_hp / 16)
        toxic_counter += 1

    total = 0.0
    last_c = 0.0
    for i in range(n):
        if (hp - damage[i] <= max_hp // 2) and has_sitrus:
            hp += math.floor(ripen * max_hp / 4)
            has_sitrus = False
        elif ((hp - damage[i] <= max_hp // 4 and has_figy and not gluttony)
              or (hp - damage[i] <= max_hp // 2 and has_figy and gluttony)):
            hp += math.floor(ripen * max_hp / 3)
            has_figy = False

        if i == 0 or damage[i] != damage[i - 1]:
            c = _get_ko_chance(
                damage, multihit, hp - damage[i] + eot - toxic_damage,
                eot, hits - 1, max_hp, toxic_counter, has_sitrus, has_figy, gluttony, ripen
            )
        else:
            c = last_c

        if c == 1:
            total += (n - i)
            break
        else:
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
    """Approximate multi-hit damage distribution."""
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
    # Default fallback
    return [d[0] * hits, d[len(d)//2] * hits, d[-1] * hits]
