"""中文渲染层（display layer）：所有面向用户的中文文案在此拼接。

重构（PLAN_2026-09-12_engine_english_multilang_EXECUTION[已实施].md Step 2）将引擎中的
文案集中到本模块：damage.py / ko_chance.py / ev_optimizer.py 通过引用这里的
常量与纯函数组装文案，引擎内不再直接书写中文字面量文案。

硬约束：
- 所有拼接格式与抽离前逐字节一致（含空格、半/全角标点、语序）。
- description 仅用于展示；最终属性、分类与有效威力由 DamageResult 结构化返回，
  query.py 不再从描述文本解析计算字段。
- 主描述中 {效果}{要害}{烧伤}{亲子爱} 四段必须保持既有拼接顺序（原子迁移）。
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# damage.py — 免疫原因 / 描述模板
# ---------------------------------------------------------------------------

# English ability name -> Chinese display name（原 damage.py._IMMUNITY_ABILITY_ZH）
IMMUNITY_ABILITY_ZH: dict[str, str] = {
    "Sap Sipper": "食草", "Flash Fire": "引火", "Well-Baked Body": "焦香之躯",
    "Dry Skin": "干燥皮肤", "Storm Drain": "引水", "Water Absorb": "储水",
    "Lightning Rod": "避雷针", "Motor Drive": "电气引擎", "Volt Absorb": "蓄电",
    "Levitate": "飘浮", "Earth Eater": "食土", "Eelevate": "鳗鳗高升",
    "Bulletproof": "防弹", "Soundproof": "隔音", "Wind Rider": "乘风",
    "Wonder Guard": "神奇守护", "Damp": "湿气", "Dazzling": "鲜艳之躯",
    "Queenly Majesty": "女王的威严", "Armor Tail": "尾甲",
}


def immunity_reason(ability_en: str) -> str:
    """`（{zh 特性名}特性免疫）`；未知特性名原样展示。"""
    zh = IMMUNITY_ABILITY_ZH.get(ability_en, ability_en)
    return f"（{zh}特性免疫）"


REASON_AIR_BALLOON = "（气球道具免疫地面招式）"
REASON_WEATHER_LOCK = "（大日照/下大雨天气下无法使用该属性招式）"
REASON_SKY_DROP = "（该目标无法被 Sky Drop 抓起）"
REASON_SYNCHRONOISE = "（同步喧闹仅对与自身属性相同的宝可梦生效）"
REASON_DYNAMAX_WEIGHT = "（极巨化宝可梦免疫体重类招式）"
REASON_UNFLINGABLE = "（该道具无法投掷或未持有道具）"
REASON_NATURAL_GIFT = "（天然礼物需要携带树果）"
REASON_PSYCHIC_TERRAIN = "（精神场地使先制招式无效）"
REASON_DREAM_EATER = "（食梦仅对睡眠状态的宝可梦生效）"


def status_move_description(move_name: str) -> str:
    return f"{move_name} 是变化招式，不造成伤害"


def immune_description(move_name: str, defender_name: str, reason: str) -> str:
    """`{招式} 对 {防御方} 无效{原因}`；reason 为空串时即通用属性免疫。"""
    return f"{move_name} 对 {defender_name} 无效{reason}"


def fixed_damage_description(
    attacker_level: int,
    attacker_name: str,
    move_name: str,
    defender_level: int,
    defender_name: str,
    damage: int,
) -> str:
    """Fixed-damage result without misleading power/attack/defense fields."""
    return (
        f"Lv.{attacker_level} {attacker_name} 的 {move_name} "
        f"vs Lv.{defender_level} {defender_name} | 固定伤害 | "
        f"伤害范围 {damage} ~ {damage}"
    )


def main_description(
    attacker_level: int,
    attacker_name: str,
    move_name: str,
    defender_level: int,
    defender_name: str,
    type_effectiveness: float,
    is_critical: bool,
    apply_burn: bool,
    parental_bond: bool,
    base_power: int,
    attack: int,
    defense: int,
    min_damage: int,
    max_damage: int,
) -> str:
    """主伤害描述。{效果}{要害}{烧伤}{亲子爱} 四段按原顺序原子拼接，不得拆改。"""
    eff_desc = ""
    if type_effectiveness > 1:
        eff_desc = f" 效果拔群（{int(type_effectiveness)}倍）"
    elif type_effectiveness < 1:
        eff_desc = f" 效果不佳（{type_effectiveness}倍）"

    crit_desc = " 击中要害" if is_critical else ""
    burn_desc = "（烧伤减半）" if apply_burn else ""
    pb_desc = "（亲子爱：两段攻击）" if parental_bond else ""

    return (
        f"Lv.{attacker_level} {attacker_name} 的 {move_name} "
        f"vs Lv.{defender_level} {defender_name}{eff_desc}{crit_desc}{burn_desc}{pb_desc} | "
        f"威力 {base_power} | 攻击 {attack} | 防御 {defense} | "
        f"伤害范围 {min_damage} ~ {max_damage}"
    )


# ---------------------------------------------------------------------------
# ko_chance.py — KO 过程文案
# ---------------------------------------------------------------------------

KO_ERROR = "计算出错"
KO_PAIN_SPLIT = "双方平分了体力！"
KO_STATUS_MOVE = "这是变化招式，不造成伤害。"
KO_SUN_EVAPORATED = "水属性招式在大日照下蒸发了！"
KO_RAIN_EXTINGUISHED = "火属性招式在大雨中熄灭了！"
KO_NO_DAMAGE = "没有造成伤害"
KO_OHKO = "确定一击必杀"
KO_MORE_ROUNDS = "可能需要更多回合"
KO_SINGLE_USE_NO_KO = "当前伤害不足以击倒目标；未模拟该招式重复使用的状态变化"
KO_HALF_UNSUPPORTED = "无法可靠计算：半血招式与回复／持续伤害的触发时序尚未建模"
KO_TERA_STATE_UNSUPPORTED = "无法可靠计算：该太晶状态的多段或回复／持续伤害组合尚未建模"
OPT_STATEFUL_REPEAT_UNSUPPORTED = "不支持该招式的多次使用优化：伤害随剩余 HP 或攻击方状态变化"

# 多击招式的回合数前缀
MULTI_HIT_QUALIFIER = "约 "

HAZARD_STEALTH_ROCK = "隐形岩"
HAZARD_SPIKES_1 = "1层撒菱"
HAZARD_SPIKES_2 = "2层撒菱"
HAZARD_SPIKES_3 = "3层撒菱"


def ability_damage(ability_en: str) -> str:
    """`{特性英文名} 伤害`（阳光之力等天气伤害文案）。"""
    return ability_en + " 伤害"


EOT_DRY_SKIN_HEAL = "干燥皮肤 回复"
EOT_RAIN_DISH_HEAL = "雨盘 回复"
EOT_SAND_DAMAGE = "沙暴伤害"
EOT_ICE_BODY_HEAL = "冰冻之躯 回复"
EOT_HAIL_DAMAGE = "冰雹伤害"
EOT_LEFTOVERS_HEAL = "剩饭 回复"
EOT_BLACK_SLUDGE_HEAL = "黑色污泥 回复"
EOT_BLACK_SLUDGE_DAMAGE = "黑色污泥 伤害"
EOT_GRASSY_HEAL = "青草场地 回复"
EOT_POISON_HEAL_HEAL = "毒疗 回复"
EOT_POISON_DAMAGE = "中毒伤害"
EOT_TOXIC_DAMAGE = "剧毒伤害"
EOT_HALVED_BURN_DAMAGE = "减半烧伤伤害"
EOT_BURN_DAMAGE = "烧伤伤害"
EOT_BAD_DREAMS = "梦魇"
EOT_SALT_CURE_DAMAGE = "盐腌伤害"
EOT_SALT_CURE_EXTRA = "盐腌额外伤害"
EOT_SITRUS_HEAL = "文柚果 回复"
EOT_BERRY_HEAL = "树果 回复"


def condition_suffix(texts: list[str]) -> str:
    """`（计入{a, b}后）`；列表为空时返回空串。"""
    return f"（计入{', '.join(texts)}后）" if texts else ""


def ko_ohko_with(suffix: str) -> str:
    return f"确定一击必杀{suffix}"


def ko_prob_with(qualifier: str, pct: float, suffix: str) -> str:
    return f"{qualifier}{pct}% 概率一击必杀{suffix}"


def ko_n_guaranteed(n: int, suffix: str) -> str:
    return f"确定{n}击必杀{suffix}"


def ko_n_prob(qualifier: str, pct: float, n: int, suffix: str) -> str:
    return f"{qualifier}{pct}% 概率{n}击必杀{suffix}"


def ko_n_possible(n: int, suffix: str) -> str:
    return f"可能{n}击必杀{suffix}"


# ---------------------------------------------------------------------------
# ev_optimizer.py — reason / suggestion / val_label 文案
# ---------------------------------------------------------------------------

OPT_NO_DAMAGE = "该招式不造成伤害或免疫"
OPT_NO_DAMAGE_DEFENSE = "该招式不造成伤害或免疫，无需防御努力值"
VAL_LABEL_SP = "能力点数"
VAL_LABEL_EV = "努力值"
SUGGEST_HP_DEFENSE = "尝试同时投资 HP 和防御"


def opt_fail_attack(max_single: int, stat: str, val_label: str, target: str) -> str:
    return f"即使满 {max_single} {stat} {val_label}也无法达成 {target}"


def opt_fail_defense(max_single: int, stat: str, val_label: str, target: str) -> str:
    return f"即使满 {max_single} {stat} {val_label}也无法{target}"


def opt_fail_dual(val_label: str, target: str) -> str:
    return f"即使满{val_label}分配也无法{target}"
