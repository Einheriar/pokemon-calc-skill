"""Engine-layer enum constants: single source of truth for type / nature / status.

Canonical values are English, isomorphic to damage_SV.js. Chinese names belong
to the data layer (zh primary keys) and are translated at the adapter boundary
(query.py / normalize.py) — never inside the engine.

This module contains data and pure lookup helpers only; no business logic.
Values must stay verbatim-aligned with the historical tables in damage.py
(_TYPE_ZH_TO_EN / NATURES / _NATURE_ALIASES) that this module replaces.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Types (18, Gen 1-8 chart; "Stellar" is handled specially by damage.py)
# ---------------------------------------------------------------------------

class T:
    """English type-name constants for engine-internal comparisons."""
    NORMAL = "Normal"
    FIGHTING = "Fighting"
    FLYING = "Flying"
    POISON = "Poison"
    GROUND = "Ground"
    ROCK = "Rock"
    BUG = "Bug"
    GHOST = "Ghost"
    STEEL = "Steel"
    FIRE = "Fire"
    WATER = "Water"
    GRASS = "Grass"
    ELECTRIC = "Electric"
    PSYCHIC = "Psychic"
    ICE = "Ice"
    DRAGON = "Dragon"
    DARK = "Dark"
    FAIRY = "Fairy"


# zh (data layer) <-> en (engine layer), verbatim from damage.py's legacy table
TYPE_ZH_TO_EN: dict[str, str] = {
    "一般": "Normal", "格斗": "Fighting", "飞行": "Flying", "毒": "Poison",
    "地面": "Ground", "岩石": "Rock", "虫": "Bug", "幽灵": "Ghost",
    "钢": "Steel", "火": "Fire", "水": "Water", "草": "Grass",
    "电": "Electric", "超能力": "Psychic", "冰": "Ice", "龙": "Dragon",
    "恶": "Dark", "妖精": "Fairy",
}
TYPE_EN_TO_ZH: dict[str, str] = {v: k for k, v in TYPE_ZH_TO_EN.items()}

# zh-Hant type inputs (zh_hant_support Step 3, 2026-09-13). Sources:
# PokeAPI /type/{1..18} names[] zh-Hant field, cross-checked against 52poke
# type pages (格斗/幽灵/龙/电 4 页, 0 mismatch) — see cache/audit/zh_hant_tier2_enums.md.
# Only the 8 differing types are listed; the other 10 are script-identical.
TYPE_ZH_HANT_TO_EN: dict[str, str] = {
    "格鬥": "Fighting", "飛行": "Flying", "蟲": "Bug", "幽靈": "Ghost",
    "鋼": "Steel", "電": "Electric", "龍": "Dragon", "惡": "Dark",
}

VALID_TYPES_EN: frozenset[str] = frozenset(TYPE_EN_TO_ZH)

_TYPE_EN_LOWER: dict[str, str] = {t.lower(): t for t in VALID_TYPES_EN}


def resolve_type_en(name: str) -> str | None:
    """Resolve zh / zh-Hant / en / any-case type input to the canonical English name."""
    if not name:
        return None
    n = str(name).strip()
    if n in TYPE_ZH_TO_EN:
        return TYPE_ZH_TO_EN[n]
    if n in TYPE_ZH_HANT_TO_EN:
        return TYPE_ZH_HANT_TO_EN[n]
    if n in VALID_TYPES_EN:
        return n
    return _TYPE_EN_LOWER.get(n.lower())


# Tera Type: the 19th "type" (Gen 9 Terastallization Stellar type).
# Official zh name is 星晶; 星愿 is a legacy in-repo alias (V4.9.1 audit fix)
# kept as input tolerance. Membership is an EXACT match.
STELLAR_TERA_INPUTS: frozenset[str] = frozenset({"Stellar", "星晶", "星愿"})


def resolve_type_en(name: str) -> str | None:
    """Resolve zh / zh-Hant / en / any-case type input to the canonical English name."""
    if not name:
        return None
    n = str(name).strip()
    if n in TYPE_ZH_TO_EN:
        return TYPE_ZH_TO_EN[n]
    if n in TYPE_ZH_HANT_TO_EN:
        return TYPE_ZH_HANT_TO_EN[n]
    if n in VALID_TYPES_EN:
        return n
    return _TYPE_EN_LOWER.get(n.lower())


def resolve_tera_type_en(name: str) -> str | None:
    """Canonicalize tera-type input for the engine.

    星晶/星愿 → "Stellar"; the 18 zh type names → English; zh-Hant type
    names → English (zh_hant_support Step 3). English names are case-insensitive
    and surrounding whitespace is ignored. Unknown names and non-string values
    resolve to None so callers can reject them at the CLI boundary.
    """
    if not isinstance(name, str):
        return None
    n = name.strip()
    if not n:
        return None
    if n in STELLAR_TERA_ZH:
        return TERA_STELLAR_EN
    hit = TYPE_ZH_TO_EN.get(n) or TYPE_ZH_HANT_TO_EN.get(n)
    return hit or _TYPE_EN_LOWER.get(n.lower()) or (TERA_STELLAR_EN if n.lower() == "stellar" else None)


TERA_STELLAR_EN = "Stellar"
STELLAR_TERA_ZH: frozenset[str] = frozenset({"星晶", "星愿", "星願"})


# ---------------------------------------------------------------------------
# Natures (25): English canonical name -> (boosted stat, lowered stat)
# Stat keys are the English engine keys ("sp_attack" etc.), "" = neutral.
# ---------------------------------------------------------------------------

NATURES_EN: dict[str, tuple[str, str]] = {
    # Neutral natures (no stat change)
    "Hardy": ("", ""), "Docile": ("", ""), "Bashful": ("", ""),
    "Quirky": ("", ""), "Serious": ("", ""),
    # +Attack
    "Lonely": ("attack", "defense"), "Adamant": ("attack", "sp_attack"),
    "Naughty": ("attack", "sp_defense"), "Brave": ("attack", "speed"),
    # +Defense
    "Bold": ("defense", "attack"), "Impish": ("defense", "sp_attack"),
    "Lax": ("defense", "sp_defense"), "Relaxed": ("defense", "speed"),
    # +Sp. Attack
    "Modest": ("sp_attack", "attack"), "Mild": ("sp_attack", "defense"),
    "Rash": ("sp_attack", "sp_defense"), "Quiet": ("sp_attack", "speed"),
    # +Sp. Defense
    "Calm": ("sp_defense", "attack"), "Gentle": ("sp_defense", "defense"),
    "Careful": ("sp_defense", "sp_attack"), "Sassy": ("sp_defense", "speed"),
    # +Speed
    "Timid": ("speed", "attack"), "Hasty": ("speed", "defense"),
    "Jolly": ("speed", "sp_attack"), "Naive": ("speed", "sp_defense"),
}

# Canonical zh (data layer) <-> en (engine layer)
NATURE_ZH_TO_EN: dict[str, str] = {
    "勤奋": "Hardy", "坦率": "Docile", "害羞": "Bashful", "浮躁": "Quirky", "认真": "Serious",
    "怕寂寞": "Lonely", "固执": "Adamant", "顽皮": "Naughty", "勇敢": "Brave",
    "大胆": "Bold", "淘气": "Impish", "乐天": "Lax", "悠闲": "Relaxed",
    "内敛": "Modest", "慢吞吞": "Mild", "马虎": "Rash", "冷静": "Quiet",
    "温和": "Calm", "温顺": "Gentle", "慎重": "Careful", "自大": "Sassy",
    "胆小": "Timid", "急躁": "Hasty", "爽朗": "Jolly", "天真": "Naive",
}
NATURE_EN_TO_ZH: dict[str, str] = {v: k for k, v in NATURE_ZH_TO_EN.items()}

# zh-Hant nature inputs (zh_hant_support Step 3, 2026-09-13). Sources:
# PokeAPI /nature/{1..25} names[] zh-Hant field, cross-checked against the
# 52poke 性格 page 任天堂译名 table (25/25, 0 mismatch) — see
# cache/audit/zh_hant_tier2_enums.md. Only the 14 differing natures are listed.
NATURE_ZH_HANT_TO_EN: dict[str, str] = {
    "勤奮": "Hardy", "大膽": "Bold", "內斂": "Modest", "溫和": "Calm",
    "膽小": "Timid", "溫順": "Gentle", "固執": "Adamant", "淘氣": "Impish",
    "馬虎": "Rash", "頑皮": "Naughty", "樂天": "Lax", "悠閒": "Relaxed",
    "冷靜": "Quiet", "認真": "Serious",
}

VALID_NATURES_EN: frozenset[str] = frozenset(NATURES_EN)

# Case/alias tolerance, verbatim from damage.py's legacy _NATURE_ALIASES:
# lowercase English (incl. neutral natures) and alternate zh names -> canonical zh.
NATURE_ALIASES_TO_ZH: dict[str, str] = {
    "adamant": "固执", "modest": "内敛", "jolly": "爽朗", "timid": "胆小",
    "brave": "勇敢", "bold": "大胆", "impish": "淘气", "careful": "慎重",
    "calm": "温和", "quiet": "冷静", "sassy": "自大", "relaxed": "悠闲",
    "lonely": "怕寂寞", "mild": "慢吞吞", "gentle": "温顺", "hasty": "急躁",
    "naive": "天真", "rash": "马虎", "naughty": "顽皮", "lax": "乐天",
    "hardy": "勤奋",
    # Chinese-name aliases (fault tolerance): alternate zh name -> canonical zh name
    "孤独": "怕寂寞",
    # Neutral-nature English names -> canonical zh names
    "docile": "坦率", "bashful": "害羞", "quirky": "浮躁", "serious": "认真",
}


def resolve_nature_en(name: str) -> str | None:
    """Resolve zh / zh-Hant / en / alias / any-case nature input to the canonical English name."""
    if not name:
        return None
    n = str(name).strip()
    if not n:
        return None
    if n in NATURE_ZH_TO_EN:
        return NATURE_ZH_TO_EN[n]
    if n in NATURE_ZH_HANT_TO_EN:
        return NATURE_ZH_HANT_TO_EN[n]
    if n in NATURES_EN:
        return n
    alias_zh = NATURE_ALIASES_TO_ZH.get(n.lower()) or NATURE_ALIASES_TO_ZH.get(n)
    if alias_zh is not None:
        return NATURE_ZH_TO_EN.get(alias_zh)
    # aliases.json natures 段（alias_layer Step 3a 入库的旧译/代理商译名）。
    # 懒加载避免 normalize <-> engine_enums 循环导入；无命中时返回 None。
    from normalize import normalize_name
    alias_hit = normalize_name(n, "natures")
    if alias_hit != n:
        return NATURE_ZH_TO_EN.get(alias_hit) or NATURE_ZH_HANT_TO_EN.get(alias_hit)
    return None


# ---------------------------------------------------------------------------
# Major statuses — the exact strings the engine compares against
# ---------------------------------------------------------------------------

STATUS_BURNED = "Burned"
STATUS_POISONED = "Poisoned"
STATUS_BADLY_POISONED = "Badly Poisoned"
STATUS_PARALYZED = "Paralyzed"
STATUS_ASLEEP = "Asleep"

VALID_STATUS_EN: frozenset[str] = frozenset({
    STATUS_BURNED, STATUS_POISONED, STATUS_BADLY_POISONED,
    STATUS_PARALYZED, STATUS_ASLEEP,
})
