---
name: pokemon-calc
description: >
  宝可梦百科查询与伤害计算 Skill。
  当用户询问以下任何内容时触发此 Skill：
  (1) 宝可梦属性、种族值、弱点抗性、特性、技能池、进化链、图鉴描述、profile、prototype 等百科信息；
  (2) 招式威力、命中、PP、效果、属性相克；
  (3) 宝可梦伤害计算、KO 概率、努力值优化（Phase 2+）；
  (4) 黑话翻译、对战术语解释；
  (5) 任何与 Pokemon VGC、单打、双打对战相关的数据查询。
  仅支持中文和英文名称查询。数据来源为 pokemon-dataset-zh 与 VGC 伤害计算器。
---

# 宝可梦伤害计算器 Skill

## 设计原则

- **LLM 只做理解，不做计算**：LLM 仅负责将用户的自然语言请求转化为结构化参数或选择合适的查询命令，所有伤害数值计算由固定程序完成。
- **零外部依赖**：核心数据已静态化为 JSON，查询脚本仅使用 Python 标准库。
- **中文优先**：数据以中文名为主索引，同时支持英文名称。
- **能力值优先，淡化努力值**：在"宝可梦冠军"等新对战环境中，回答应始终使用**能力值**而非努力值来描述配置和结果。用户在提问时可能使用努力值（如"252 攻击"），但 LLM 在回答时必须转换为对应的能力值数值（如"攻击能力值 172"）。 optimize 命令的返回值也应在总结时转换为能力值描述。
- **跨世代数据范围**：数据中覆盖全国图鉴（1~1025 号），**包含所有形态**（含 Mega、原始回归等），不区分世代过签状态。`query.py` 不做过签过滤。若用户询问 Gen9 未过签的宝可梦（如 Mega 喷火龙Y），计算器仍返回理论伤害值。LLM **必须主动识别此类情况**，在回答中明确告知"该形态在当前对战环境中不可用，以下结果为理论计算"。

## 可用工具

所有查询通过执行 bundled script [`scripts/query.py`](scripts/query.py) 完成。

| 命令 | 参数 | 用途 | 返回值类型 |
|------|------|------|-----------|
| `pokemon <name>` | 宝可梦中文/英文名 | 基础信息、形态、特性、种族值、进化链 | JSON 对象 |
| `move <name>` | 招式中文/英文名 | 威力、命中、PP、属性、分类、效果描述 | JSON 对象 |
| `ability <name>` | 特性中文/英文名 | 效果描述、元信息 | JSON 对象 |
| `item <name>` | 道具中文/英文名 | 效果描述、分类、持有效果 | JSON 对象 |
| `type <atk> <def>` | 攻击属性 防御属性 | 属性相克倍率与描述 | JSON 对象 |
| `stats <name>` | 宝可梦名 | 各形态种族值与总和 | JSON 对象 |
| `weak <name>` | 宝可梦名 | 弱点、抗性、免疫列表 | JSON 对象 |
| `learnset <name>` | 宝可梦名 | 升级/TM/遗传/教学招式 | JSON 数组 |
| `evo <name>` | 宝可梦名 | 进化链与超级进化 | JSON 对象 |
| `pokedex <name>` | 宝可梦名 | 各版本图鉴描述 | JSON 数组 |
| `profile <name>` | 宝可梦名 | 外形描述、原型考据、多语言词源 | JSON 对象 |
| `find-move <move>` | 招式名 | 反向查询：能学会该招式的所有宝可梦 | JSON 数组 |
| `preset <pokemon> [preset_name]` | 宝可梦名 [预设名] | 列出该宝可梦的所有预设配置，或获取指定预设的完整配置 | JSON 对象 |
| `calc <attacker> <move> <defender> [att_override] [move_override] [def_override] [field_override]` | 攻击方 招式 防御方 | 快速伤害计算（默认 Lv.50） | JSON 对象（见下方 I/O 规范） |
| `compute-stats <base_stats> [evs] [ivs] [nature] [level]` | 种族值 JSON | 从种族值+配置计算能力值 | JSON 对象 |
| `calc-raw <attacker_json> <move_json> <defender_json> [field_json]` | 完整宝可梦/招式/场地 JSON | 纯参数伤害计算 | JSON 对象（见下方 I/O 规范） |
| `optimize <attacker> <move> <defender> [goal] [target] [threshold] [att_override] [def_override] [field_override]` | 攻击方 招式 防御方 目标 阈值 确信度 | 努力值优化搜索 | JSON 对象（见下方 I/O 规范） |

### 命令体系说明

本 Skill 的命令分为两类：

**Phase 1 — 百科查询**（`pokemon` / `move` / `ability` / `stats` / `weak` / ...）：
通过名字查询 JSON 数据文件，返回基础百科信息。这些命令是**纯数据查询**，不涉及计算。

**Phase 2 — 伤害计算**（`calc` / `calc-raw` / `compute-stats` / `optimize`）：
负责伤害数值计算。其中：
- `calc` 是**快捷命令**（名字直接进，内部自动查数据+算能力值+算伤害）
- `compute-stats` 是**能力值计算工具**（种族值+配置 → 能力值）
- `calc-raw` 是**纯参数计算器**（只接收能力值和修正参数，不查名字，不查数据）

当处理 Gen9 未过签的宝可梦（如 Mega 形态）时，使用三层流程：
```
pokemon 查询种族值 → compute-stats 计算能力值 → calc-raw 纯参数计算伤害
```
LLM 在回答时需明确告知用户该形态在 Gen9 不可用，计算结果为理论值。

### 使用方式

调用 `query.py` 时，命令与参数以空格分隔；若参数本身包含空格，用引号包裹。

示例（执行脚本）：
```bash
python scripts/query.py stats 喷火龙
python scripts/query.py type 水 火
python scripts/query.py weak Charizard
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟 "{\"evs\":{\"sp_attack\":252},\"item\":\"木炭\"}" "{}" "{\"evs\":{\"sp_defense\":252}}"
# 多段攻击招式（如双翼）：calc 会自动返回单次 + 合计总伤害
python scripts/query.py calc 化石翼龙 双翼 胡地 "{\"evs\":{\"attack\":252,\"speed\":252}}" "{}" "{\"evs\":{\"hp\":0,\"defense\":0}}"
# 场地条件覆盖（天气、场地、墙壁等）
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟 "{\"evs\":{\"sp_attack\":252}}" "{}" "{}" "{\"weather\":\"Sun\"}"
# 使用预设配置（setdex）进行伤害计算
python scripts/query.py preset 烈箭鹰
python scripts/query.py calc 烈箭鹰 Brave\ Bird 喷火龙 '{"preset":"Sharp Beak Set"}'
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 ko ohko guaranteed
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 survive survive guaranteed
```

---

## preset 命令完整 I/O 规范

### 输入参数

| 位置 | 参数名 | 类型 | 必填 | 说明 |
|------|--------|------|------|------|
| 1 | `pokemon` | string | 是 | 宝可梦中文/英文名 |
| 2 | `preset_name` | string | 否 | 预设配置名。不传则列出该宝可梦的所有预设名 |

### 输出格式

**列出预设名（未指定 preset_name）**：
```json
{
  "pokemon_en": "Talonflame",
  "presets": ["Bulky Tera Ghost Goggles", "Sharp Beak Set"]
}
```

**获取具体预设配置**：
```json
{
  "pokemon_en": "Talonflame",
  "preset_name": "Sharp Beak Set",
  "config": {
    "level": 50,
    "evs": {"hp": 4, "attack": 252, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 252},
    "nature": "Jolly",
    "ability": "Gale Wings",
    "item": "Sharp Beak",
    "moves": ["Brave Bird", "Tailwind", "Taunt", "Protect"],
    "tera_type": "Flying"
  }
}
```

**注意**：`config` 中的 `moves` 字段仅用于参考，在 `calc` 命令中使用 `preset` 时会被自动过滤，不影响伤害计算。

---

## calc 命令完整 I/O 规范

### 输入参数

| 位置 | 参数名 | 类型 | 必填 | 说明 |
|------|--------|------|------|------|
| 1 | `attacker` | string | 是 | 攻击方宝可梦中文/英文名 |
| 2 | `move` | string | 是 | 招式中文/英文名 |
| 3 | `defender` | string | 是 | 防御方宝可梦中文/英文名 |
| 4 | `att_override` | JSON string | 否 | 覆盖攻击方默认配置 |
| 5 | `move_override` | JSON string | 否 | 覆盖招式默认配置 |
| 6 | `def_override` | JSON string | 否 | 覆盖防御方默认配置 |
| 7 | `field_override` | JSON string | 否 | 覆盖场地条件（天气、场地、墙壁等） |

### att_override / def_override 可覆盖字段

```json
{
  "level": 50,
  "evs": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
  "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
  "nature": "爽朗",
  "ability": "坚硬脑袋",
  "item": "讲究头带",
  "types": ["飞行", "岩石"],
  "boosts": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
  "status": null,
  "is_terastalize": false,
  "tera_type": null,
  "is_dynamax": false,
  "preset": "Sharp Beak Set"
}
```

**`preset` 字段说明**：在 `att_override` 或 `def_override` 中传入 `"preset": "预设名"`，系统会自动从 setdex 数据库中加载该宝可梦的预设配置（包括性格、道具、努力值、特性等），作为基础配置后再应用用户的其他覆盖字段。预设名可通过 `preset <宝可梦名>` 命令查询。

### move_override 可覆盖字段

```json
{
  "base_power": 80,
  "type": "飞行",
  "category": "Physical",
  "is_crit": false,
  "hits": 1
}
```

### field_override 可覆盖字段

```json
{
  "weather": "Sun",
  "terrain": "Electric",
  "format": "Doubles",
  "is_gravity": false,
  "is_reflect": false,
  "is_light_screen": false,
  "is_aurora_veil": false,
  "is_friend_guard": false,
  "is_battery": false,
  "is_power_spot": false,
  "is_steely_spirit": false,
  "is_tailwind_atk": false,
  "is_tailwind_def": false,
  "is_neutralizing_gas": false,
  "is_sword_of_ruin": false,
  "is_beads_of_ruin": false,
  "is_tablets_of_ruin": false,
  "is_vessel_of_ruin": false,
  "is_stealth_rock": false,
  "spikes": 0,
  "is_salt_cure": false,
  "is_helping_hand": false
}
```

| 字段 | 类型 | 取值 | 说明 |
|------|------|------|------|
| `weather` | string | Sun / Rain / Sand / Hail / Snow / Strong Winds / Harsh Sun / Heavy Rain | 天气 |
| `terrain` | string | Electric / Grassy / Misty / Psychic | 场地 |
| `format` | string | Singles / Doubles | 对战模式 |
| `is_gravity` | bool | true / false | 重力 |
| `is_reflect` | bool | true / false | 反射壁 |
| `is_light_screen` | bool | true / false | 光墙 |
| `is_aurora_veil` | bool | true / false | 极光幕 |
| `is_friend_guard` | bool | true / false | 友情防守 |
| `is_battery` | bool | true / false | 蓄电池 |
| `is_power_spot` | bool | true / false | 能量点 |
| `is_steely_spirit` | bool | true / false | 钢之意志 |
| `is_tailwind_atk` | bool | true / false | 顺风（攻击方速度×2） |
| `is_tailwind_def` | bool | true / false | 顺风（防御方速度×2） |
| `is_neutralizing_gas` | bool | true / false | 化学变化气体 |
| `is_sword_of_ruin` | bool | true / false | 灾祸之简（降低敌方防御） |
| `is_beads_of_ruin` | bool | true / false | 灾祸之鼎（降低敌方特防） |
| `is_tablets_of_ruin` | bool | true / false | 灾祸之剑（降低敌方攻击） |
| `is_vessel_of_ruin` | bool | true / false | 灾祸之玉（降低敌方特攻） |
| `is_stealth_rock` | bool | true / false | 隐形岩 |
| `spikes` | int | 0~3 | 撒菱层数 |
| `is_salt_cure` | bool | true / false | 盐腌 |
| `is_helping_hand` | bool | true / false | 帮助 |

### 返回值 JSON Schema

```json
{
  "attacker": "化石翼龙",
  "move": "双翼",
  "defender": "胡地",
  "damage_range": [55, 66],
  "damage_rolls": [55, 55, 57, 57, 58, 58, 60, 60, 60, 61, 61, 63, 63, 64, 64, 66],
  "description": "Lv.50 化石翼龙 的 Dual Wingbeat vs Lv.50 胡地 | 威力 40 | 攻击 157 | 防御 65 | 伤害范围 55 ~ 66",
  "is_critical": false,
  "type_effectiveness": 1.0,
  "stab_applied": true,
  "burn_applied": false,
  "ko_chance": "约 6.2% 概率一击必杀",
  "attacker_info": {
    "name_zh": "化石翼龙",
    "types": ["岩石", "飞行"],
    "base_stats": {"hp": 80, "attack": 105, "defense": 65, "sp_attack": 60, "sp_defense": 75, "speed": 130},
    "stats": {"hp": 155, "attack": 157, "defense": 85, "sp_attack": 80, "sp_defense": 95, "speed": 182},
    "ability": "坚硬脑袋",
    "all_abilities": ["坚硬脑袋", "压迫感", "紧张感"],
    "nature": "勤奋",
    "item": "",
    "evs": {"attack": 252, "speed": 252},
    "level": 50
  },
  "defender_info": {
    "name_zh": "胡地",
    "types": ["超能力"],
    "base_stats": {"hp": 55, "attack": 50, "defense": 45, "sp_attack": 135, "sp_defense": 95, "speed": 120},
    "stats": {"hp": 130, "attack": 70, "defense": 65, "sp_attack": 155, "sp_defense": 115, "speed": 140},
    "ability": "同步",
    "all_abilities": ["同步", "精神力", "魔法防守"],
    "nature": "勤奋",
    "item": "",
    "evs": {"hp": 0, "defense": 0},
    "level": 50,
    "current_hp": 130,
    "max_hp": 130
  },
  "total_damage_range": [110, 132],
  "total_damage_rolls": [110, 114, 116, 116, 118, 120, 120, 120, 120, 121, 122, 122, 124, 126, 127, 132],
  "move_hits": 2
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `damage_range` | [int, int] | [最小伤害, 最大伤害]（**单次打击**） |
| `damage_rolls` | int[] | 全部 16 个乱数 roll 的伤害值（已排序，**单次打击**） |
| `type_effectiveness` | float | 属性相克倍率（0, 0.25, 0.5, 1, 2, 4） |
| `stab_applied` | bool | 是否触发了 STAB |
| `burn_applied` | bool | 是否因烧伤而伤害减半 |
| `description` | string | 伤害描述文本 |
| `ko_chance` | string | 一击必杀概率的文本描述 |
| `attacker_info` | object | 攻击方基础信息（属性、种族值、能力值、**全部特性**、道具、努力值、等级、HP） |
| `defender_info` | object | 防御方基础信息（同上） |
| `total_damage_range` | [int, int] | **[多段招式特有]** [最小总伤害, 最大总伤害] |
| `total_damage_rolls` | int[] | **[多段招式特有]** 16 个乱数 roll 的总伤害值 |
| `move_hits` | int | **[多段招式特有]** 连续攻击次数 |

**多段攻击招式说明**：当招式为多段攻击（如双翼、种子机关枪）时，`damage_range` / `damage_rolls` 仍表示**单次打击**的伤害，`total_damage_range` / `total_damage_rolls` 表示**全部段数合计**的伤害。LLM 在总结时应优先引用 `total_damage_range` 判断能否秒杀。

---

## compute-stats 命令完整 I/O 规范

### 输入参数

| 位置 | 参数名 | 类型 | 必填 | 说明 |
|------|--------|------|------|------|
| 1 | `base_stats_json` | JSON string | 是 | 种族值字典，如 `{"hp":78,"attack":84,...}` |
| 2 | `evs_json` | JSON string | 否 | 努力值字典，默认全 0 |
| 3 | `ivs_json` | JSON string | 否 | 个体值字典，默认全 31 |
| 4 | `nature` | string | 否 | 性格中文名，默认"勤奋" |
| 5 | `level` | int | 否 | 等级，默认 50 |

**调用示例**：

```bash
python scripts/query.py compute-stats '{"hp":78,"attack":84,"defense":78,"sp_attack":109,"sp_defense":85,"speed":100}' '{"sp_attack":252}' '{}' '内敛' 50
```

**输出**：

```json
{
  "level": 50,
  "nature": "内敛",
  "base_stats": {"hp": 78, "attack": 84, "defense": 78, "sp_attack": 109, "sp_defense": 85, "speed": 100},
  "evs": {"sp_attack": 252},
  "ivs": {},
  "stats": {"hp": 153, "attack": 93, "defense": 98, "sp_attack": 177, "sp_defense": 105, "speed": 120}
}
```

---

## calc-raw 命令完整 I/O 规范

### 输入参数

| 位置 | 参数名 | 类型 | 必填 | 说明 |
|------|--------|------|------|------|
| 1 | `attacker_json` | JSON string | 是 | 攻击方完整参数（见下方 schema） |
| 2 | `move_json` | JSON string | 是 | 招式完整参数 |
| 3 | `defender_json` | JSON string | 是 | 防御方完整参数 |
| 4 | `field_json` | JSON string | 否 | 场地条件，默认空对象 |

**attacker_json / defender_json 必填字段**：

```json
{
  "name": "超级喷火龙Y",
  "name_en": "Mega Charizard Y",
  "level": 50,
  "stats": {"hp": 153, "attack": 90, "defense": 80, "sp_attack": 177, "sp_defense": 100, "speed": 115},
  "types": ["火", "飞行"],
  "ability": "日照",
  "item": "",
  "nature": "内敛",
  "evs": {"hp": 4, "sp_attack": 252, "speed": 252},
  "ivs": {"hp": 31, "attack": 31, "defense": 31, "sp_attack": 31, "sp_defense": 31, "speed": 31},
  "boosts": {"hp": 0, "attack": 0, "defense": 0, "sp_attack": 0, "sp_defense": 0, "speed": 0},
  "current_hp": 153,
  "max_hp": 153,
  "status": null,
  "is_terastalize": false,
  "tera_type": null,
  "is_dynamax": false,
  "weight": 90.5
}
```

**move_json 必填字段**：

```json
{
  "name": "热风",
  "base_power": 95,
  "type": "火",
  "category": "Special",
  "is_crit": false,
  "hits": 1
}
```

**field_json 字段**：与 `calc` 命令的 `field_override` 完全相同。

**关键约束**：
- `stats` 字段**必填** — 纯参数计算器的核心输入，直接作为能力值使用
- `current_hp` 和 `max_hp` **必填** — 用于 KO 概率计算
- 计算器**不执行名字查询**，也**不从 base_stats 自动计算能力值**
- **`is_spread` 自动补全** — 若 `move_json` 省略了 `is_spread` 字段但提供了 `name` 或 `name_zh`，系统会自动从招式数据补全该值；若用户显式传入 `is_spread`，则**优先使用用户值**

**调用示例**：

```bash
python scripts/query.py calc-raw \
  '{"name":"超级喷火龙Y","level":50,"stats":{"hp":153,"sp_attack":177},"types":["火","飞行"],"ability":"日照","nature":"内敛","current_hp":153,"max_hp":153,...}' \
  '{"name":"热风","base_power":95,"type":"火","category":"Special"}' \
  '{"name":"超级胡地","level":50,"stats":{"hp":120,"sp_defense":105},"types":["超能力"],"ability":"复制","nature":"勤奋","current_hp":120,"max_hp":120,...}' \
  '{"weather":"Sun"}'
```

**输出**：与 `calc` 命令返回格式完全相同（damage_range、ko_chance、attacker_info、defender_info 等）。

---

## optimize 命令完整 I/O 规范

### 输入参数

| 位置 | 参数名 | 类型 | 必填 | 说明 |
|------|--------|------|------|------|
| 1 | `attacker` | string | 是 | 攻击方宝可梦名 |
| 2 | `move` | string | 是 | 招式名 |
| 3 | `defender` | string | 是 | 防御方宝可梦名 |
| 4 | `goal` | string | 否 | `ko` / `survive` / `survive_bulk`（默认 `ko`） |
| 5 | `target` | string | 否 | `ohko` / `2hko` / `3hko` / `survive` / `survive_2hko`（默认 `ohko`） |
| 6 | `threshold` | string | 否 | `guaranteed`（最差乱数）/ `likely`（平均乱数）（默认 `guaranteed`） |
| 7 | `att_override` | JSON string | 否 | 覆盖攻击方配置（语法同 calc `att_override`） |
| 8 | `def_override` | JSON string | 否 | 覆盖防御方配置（语法同 calc `def_override`） |
| 9 | `field_override` | JSON string | 否 | 覆盖场地条件（语法同 calc `field_override`） |

**注意**：`att_override` 和 `def_override` 按 calc 命令格式传入，但作为 **query.py optimize** 的第 7、8 个参数，**不含 move_override**。参数顺序为：`optimize <att> <move> <def> [goal] [target] [threshold] [att_ov] [def_ov] [field_ov]`。

### 返回值 JSON Schema

#### goal="ko"（攻击优化）返回示例

```json
{
  "success": true,
  "target": "ohko",
  "threshold": "guaranteed",
  "stat": "sp_attack",
  "optimal_ev": 252,
  "remaining_evs": 256,
  "damage_range": [130, 156],
  "description": "Lv.50 喷火龙 的 喷射火焰 vs Lv.50 水箭龟 | 威力 90 | 特攻 177 | 特防 125 | 伤害范围 130 ~ 156"
}
```

#### goal="survive"（防御优化）返回示例

```json
{
  "success": true,
  "target": "survive",
  "threshold": "guaranteed",
  "stat": "sp_defense",
  "optimal_ev": 252,
  "remaining_evs": 256,
  "damage_range": [130, 156],
  "description": "..."
}
```

#### goal="survive_bulk"（HP+防御联合优化）返回示例

```json
{
  "success": true,
  "target": "survive",
  "hp_stat": "hp",
  "def_stat": "sp_defense",
  "optimal_hp_ev": 252,
  "optimal_def_ev": 0,
  "total_evs": 252,
  "remaining_evs": 256,
  "damage_range": [130, 156],
  "description": "..."
}
```

#### 失败返回示例

```json
{
  "success": false,
  "reason": "即使满 252 sp_attack 努力值也无法达成 ohko",
  "optimal_ev": 252,
  "damage_at_optimal": 120,
  "damage_range": [120, 144]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否找到满足条件的配置 |
| `target` / `threshold` | string | 回显输入参数 |
| `stat` | string | 优化的单项能力值键名（"ko"/"survive" 时） |
| `optimal_ev` | int | 最优单项努力值投入（"ko"/"survive" 时） |
| `remaining_evs` | int | 剩余可用努力值（MAX_TOTAL_EVS - optimal_ev） |
| `damage_range` | [int, int] | [最小伤害, 最大伤害]（优化后的结果） |
| `description` | string | 伤害描述文本 |
| `hp_stat` / `def_stat` | string | 联合优化的两个能力值键名（"survive_bulk" 时） |
| `optimal_hp_ev` / `optimal_def_ev` | int | 联合优化的两项努力值（"survive_bulk" 时） |
| `total_evs` | int | 联合优化总投入（"survive_bulk" 时） |
| `reason` | string | 失败原因（success=false 时） |
| `damage_at_optimal` | int | 满努力值时的最小伤害（success=false 时） |

**注意**：所有返回值中的努力值字段（`optimal_ev`、`optimal_hp_ev` 等）在 LLM 回答时必须转换为**能力值描述**（如"攻击能力值需要达到 172"），禁止直接说"252 攻击努力值"。

---

## LLM 职责边界

### LLM 负责

1. **从用户问题中识别意图**（百科查询 / 属性相克 / 伤害计算 / 努力值优化）
2. **提取并规范化名称**：
   - 将别名、简称映射到标准中文名（如 "老喷" → "喷火龙"）
   - 识别英文名称并保留原样
3. **选择正确的 `query.py` 子命令**
4. **构造覆盖 JSON**：将用户自然语言中的配置转化为标准 JSON 格式
5. **对脚本返回的 JSON 结果进行自然语言总结**，保留关键数字

### LLM 不负责

1. **任何数值计算**（倍率乘法、伤害公式、概率推导）
2. **属性相克判断**（必须使用 `query.py type` 或 `weak`）
3. **编造不存在的数据**

---

## 查询流程

```
1. 解析用户意图
   └─ 判断：百科查询 / 属性相克 / 伤害计算 / 努力值优化

2. 名称规范化
   └─ 将别名映射到标准名，确定形态（未指定则默认"一般"形态）

3. 【信息补全】检查用户是否遗漏关键配置
   └─ 伤害计算类问题，检查是否遗漏：性格、努力值、道具、特性、太晶化状态
   └─ 若遗漏，按"信息缺失处理策略"执行（见下方）

4. 构造 query.py 命令并执行
   └─ 一次性构造完整命令，包含所有覆盖参数

5. 结果解析与回答
   └─ 按"回答模板"组织输出（见下方）
```

---

## 信息缺失处理策略

当用户提出伤害计算问题但**未提供完整配置**时，按以下规则处理：

### 1. 性格未指定

**分析影响**：性格直接影响关键能力值（+10% / -10%），是伤害计算的重要变量。

**处理规则**：
- 若用户指定了"252 攻击"但未指定性格：
  - 物理攻击手：同时计算 **爽朗**（+速度 -特攻）和 **固执**（+攻击 -特攻）两种情况
  - 特攻攻击手：同时计算 **胆小**（+速度 -攻击）和 **内敛**（+特攻 -攻击）两种情况
- 输出格式：列出两种性格的能力值和伤害范围对比，**禁止只写努力值**

### 2. 努力值未指定

**处理规则**：
- 若用户未提及努力值：使用默认配置（所有努力值 = 0）
- 若用户说"252 攻击 252 速度"：按此配置计算，但回答时转换为对应的能力值数值
- 若用户说"不加某属性"：该属性努力值 = 0

### 3. 道具未指定

**处理规则**：
- 默认道具为空字符串（`""`）
- 若用户提到常见道具（如生命宝珠、讲究头带），纳入覆盖 JSON

### 4. 特性未指定

**处理规则**：
- 使用数据文件中的默认特性（第一特性）
- 若用户指定特性，覆盖默认特性

### 5. 多方案对比输出（能力值优先）

当存在多个合理配置时，输出格式如下。注意：**表格中只写能力值，不写努力值**。

```
## 方案对比

| 配置 | 攻击能力值 | 单次伤害 | 总伤害 | KO 概率 |
|------|-----------|---------|--------|---------|
| 爽朗 | 157 | 55～65 | 110～130 | 约 6.25% |
| 固执 | 172 | 60～71 | 120～142 | 约 75% |
```

### 6. 能力值与努力值转换规则

LLM 在回答时，必须将努力值描述转换为能力值描述：

- **错误**："252 攻击努力值的化石翼龙"
- **正确**："攻击能力值 157（对应 252 攻击努力值 + 爽朗性格）的化石翼龙"

- **错误**："要确定击杀，需要加多少攻击努力值"
- **正确**："要确定击杀，攻击能力值需要达到多少"

用户在提问时可能使用努力值术语，这是可以接受的。但 LLM 的回答必须始终使用能力值术语。

### 7. 全国图鉴百科 + Gen9 伤害计算

**数据范围说明**：
- 百科查询数据（`pokemon.json`）覆盖全国图鉴（1~1025 号），包含所有世代的宝可梦信息。
- 伤害计算引擎（`damage.py`）默认以 **Gen9（朱紫）** 规则执行，招式数据来自 `MOVES_SV`。
- 数据中**不过签过滤**：Mega 形态、原始回归等未过签数据依然存在并可查询。

**伤害计算有两种方式**：

1. **快捷模式**（`calc`）：用户输入名字 → 系统内部自动查数据、算能力值、算伤害。适用于 Gen9 中可用的标准宝可梦。

2. **纯参数模式**（`calc-raw`）：用户（或 LLM）直接传入能力值 → 系统只算伤害，不查数据。适用于：
   - Gen9 未过签的宝可梦（Mega、原始回归等）
   - 自定义假设场景（"如果有一只 HP150/特攻180 的宝可梦"）
   - 需要精确控制每一项参数的场合

**未过签宝可梦的处理流程**：

```
1. `pokemon` 命令查询种族值/属性/特性
2. `compute-stats` 命令计算能力值
3. `calc-raw` 命令传入能力值和 HP 计算伤害
4. LLM 在回答中注明"该形态在 Gen9 不可用，以下结果为理论计算"
```

**LLM 应对策略**：
1. 百科查询类问题：所有 1025 只宝可梦均可正常查询。
2. 伤害计算类问题：
   - 标准宝可梦（Gen9 可用）：使用 `calc` 快捷命令
   - 未过签宝可梦（Mega 等）：使用 `pokemon` → `compute-stats` → `calc-raw` 三层流程
3. 若收到 `not found` 错误，首先确认名称拼写/别名是否正确。
4. **禁止编造不存在的宝可梦或招式数据**。

### 8. 默认配置推断（当用户未指定完整配置时）

当用户未指定性格、努力值、道具等配置时，LLM 应根据宝可梦的常见战术角色推断默认配置，而非全部使用 0 努力值 + 勤奋性格。

**常见角色默认配置表**：

| 角色类型 | 默认努力值 | 默认性格 | 默认道具 | 默认特性 |
|---------|-----------|---------|---------|---------|
| 物理攻击手 | 252攻击/252速度/4HP | 爽朗（+速度 -特攻） | 气势披带 | 第一特性 |
| 特殊攻击手 | 252特攻/252速度/4HP | 胆小（+速度 -攻击） | 气势披带 | 第一特性 |
| 物攻坦克 | 252HP/252防御/4攻击 | 淘气（+防御 -特攻） | 剩饭 | 第一特性 |
| 特攻坦克 | 252HP/252特防/4特攻 | 慎重（+特防 -攻击） | 剩饭 | 第一特性 |
| 辅助/控速手 | 252HP/252速度/4任意 | 爽朗/胆小 | 气势披带 | 战术相关特性 |
| 空间打手（低速） | 252HP/252攻击/4防御 | 勇敢（+攻击 -速度） | 气势披带 | 第一特性 |
| 天气/场地手 | 252HP/252速度/4任意 | 爽朗/胆小 | 气势披带/功能道具 | 天气/场地特性 |

**推断优先级**：
1. 若用户明确提到"252 攻击"等具体努力值，按用户指定处理
2. 若用户提到"气势披带"等道具，按用户指定处理
3. 若用户提到性格名称，按用户指定处理
4. 若用户什么都没说，根据宝可梦种族值分配判断角色类型，套用默认配置
5. **无论使用何种默认配置，LLM 在回答中必须明确告知用户假设的配置**

**示例**：
- 用户："铁臂膀的闪电拳打超甲狂犀"
- 推断：铁臂膀种族值攻击140/速度50，为典型空间物攻手 → 默认配置为 252HP/252攻击/4防御，勇敢性格，气势披带
- 回答开头必须注明："以下计算假设铁臂膀为空间打手配置：攻击能力值 220（252 攻击努力值 + 勇敢性格）"

---

## 回答模板

### 伤害计算类问题的标准回答结构

**步骤 1：介绍参与对战的宝可梦基础信息**

先执行百科查询命令获取基础数据，然后总结：

```
## 宝可梦信息

**攻击方：{宝可梦名}**
- 属性：{属性1} / {属性2}
- 种族值：HP {hp} / 攻击 {atk} / 防御 {def} / 特攻 {spa} / 特防 {spd} / 速度 {spe}
- 特性：{特性}

**防御方：{宝可梦名}**
- 属性：{属性1} / {属性2}
- 种族值：HP {hp} / 攻击 {atk} / 防御 {def} / 特攻 {spa} / 特防 {spd} / 速度 {spe}
- 特性：{特性}

**招式：{招式名}**
- 属性：{属性} | 分类：{物理/特殊} | 威力：{威力}
- 效果：{效果描述}
```

**步骤 2：给出实际配置下的能力值**

```
## Lv 50 实际能力值

| 宝可梦 | 性格 | 关键能力值 |
|--------|------|-----------|
| {攻击方} | {性格} | 攻击 {值} / 速度 {值} |
| {防御方} | {性格} | HP {值} / 防御 {值} |
```

**步骤 3：给出计算结果**

```
## 伤害计算结果

- **伤害范围**：{min} ～ {max}
- **全部乱数 roll**：{damage_rolls}
- **属性相克**：{倍率}x
- **是否 STAB**：{是/否}
- **KO 概率**：{概率描述}

**结论**：{能否秒杀 / 大概剩多少血}
```

---

## 工具使用规则

### 禁止过度确认

- **首次读取代码后，禁止在同一对话中反复读取相同文件/相同段落来"再次确认"**
- 若对某个接口有疑问，应**直接执行命令**，根据报错信息修正，而非反复读代码
- 读代码的目的是"理解接口"，不是"背诵接口"。理解后即可执行

### 执行优先原则

```
正确流程：理解接口 → 构造命令 → 执行 → 根据报错修正
错误流程：理解接口 → 再读一遍确认 → 再读一遍 → ...（循环）
```

### 单次读取原则

- 每个文件的每个段落，**同一对话中最多读取一次**
- 若确实需要重新读取（如之前读错了），应在读取前说明原因

---

## 名称规范化规则

- 未指定形态时，默认使用"一般"形态。
- 别名映射由 `data/aliases.json` 维护（如 "老喷"→"喷火龙"、"土猫"→"土地云" 等），`scripts/normalize.py` 在查询时自动应用。
- 别名查找不区分大小写，Pokemon 形态后缀（如 X/Y）会自动进行全角规范化。
- 若名称无法识别，系统会自动返回最接近的建议列表（基于 `difflib.get_close_matches`）。

> **LLM 注意**：当遇到用户使用的别名不在 `aliases.json` 中时，可继续尝试直接传入 `query.py`；若返回 `not found`，再提示用户提供标准中文名或英文名。

---

## 当前阶段

- **Phase 1（百科查询）**：已可用。支持属性/弱点/种族值/招式/特性/进化链/图鉴/技能池/反向查询/道具查询。
- **Phase 2（伤害计算）**：已可用。支持两种模式：
  - `calc`：快捷伤害计算（名字直接进，内部自动查数据+算能力值+算伤害）
  - `compute-stats` + `calc-raw`：纯参数驱动模式（种族值 → 能力值 → 伤害计算），适用于未过签宝可梦和自定义场景
- **Phase 3（能力值优化）**：已可用。支持通过 `optimize` 命令自动搜索最优能力值配置（单攻/单防/HP+防御联合优化）。注意：命令内部搜索的是努力值，但 LLM 回答时必须转换为能力值描述。

---

## 数据说明

数据位于 `data/` 目录下：
- `pokemon.json` — 1025 只宝可梦完整百科数据（~17.6 MB）
- `moves.json` — **782** 个招式（含 SV 全世代招式，已合并计算标记）
- `abilities.json` — 307 个特性（~0.7 MB）
- `type_chart.json` — 18×18 属性相克表
- `name_index.json` — 中文名/英文名 → 数据键索引

---

## 支持的计算特性

### 已实现的修正
- **属性相克**：18 属性完整相克表，含 Stellar、Freeze-Dry、Flying Press 等特殊规则
- **STAB / 太晶化**：含 Adaptability、星晶属性加成
- **特性修正**：含 30+ 种攻击/防御特性（Overgrow/Blaze/Torrent、Huge Power、Guts、Protosynthesis 等）
- **道具修正**：生命宝珠、讲究头带/眼镜、突击背心、进化奇石、深海的牙齿/鳞片、厚骨棒、光粉等
- **场地/天气**：晴天/雨天/沙暴/下雪、青草/电气/薄雾/精神场地
- **Ate/Ize 特性**：Pixilate / Aerilate / Refrigerate / Galvanize / Normalize 类型转换 + 威力提升
- **抗性树果**：16 种树果在效果拔群时触发
- **其他**：烧伤减半、要害 1.5x、能力等级变化、重力、光墙/反射壁/极光幕

---

## 对战机制速览

### 单打 vs 双打核心差异

| 维度 | 单打（6选3） | 双打（6选4 / VGC） |
|------|-------------|-------------------|
| 核心逻辑 | 联防重于联攻，消耗战价值高 | 联攻优先于联防，强调即时配合 |
| 换人 | 核心战略，消耗换人次数 | 频率降低，保护招式更常用 |
| 辅助招式 | 回复/剧毒/羽栖等高价值 | 看我嘛/帮助/顺风/击掌奇袭等高价值 |
| 广域招式 | 地震等无衰减 | 双打中对每只目标威力×0.75 |
| 墙壁效果 | 光墙/反射壁 伤害×0.5 | 双打中伤害×0.67（约 2/3） |
| 控速 | 个体速度线为主 | 顺风/空间/冰冻之风/麻痹等系统控速 |

### 关键机制修正速查

| 机制 | 效果 | 常见触发方式 |
|------|------|-------------|
| 顺风 | 己方速度翻倍，持续4回合 | 风妖精（恶作剧之心）、化石翼龙等 |
| 戏法空间 | 速度顺序反转，持续5回合 | 奇麒麟、布莉姆温、青铜钟等 |
| 日照/晴天 | 火系×1.5，水系×0.5 | 煤炭龟、固拉多、故勒顿（终结之地不可覆盖） |
| 降雨/雨天 | 水系×1.5，火系×0.5 | 大嘴鸥、盖欧卡（始源之海不可覆盖） |
| 电气场地 | 电系×1.3，地面宝可梦免疫睡眠 | 密勒顿（强子引擎自动开启） |
| 精神场地 | 超能系×1.3，地面宝可梦免疫先制 | 爱管侍等 |
| 青草场地 | 草系×1.3，地面宝可梦每回合回复 1/16HP | 轰擂金刚猩、奥利瓦等 |
| 薄雾场地 | 龙系×0.5，地面宝可梦免疫异常 | 卡璞·鳍鳍等 |
| 太晶化 | 一次性属性改变，持续至战斗结束 | 每场战斗仅可使用一次 |
| 太晶本系 | 太晶属性与原有本系一致 → 招式威力×2 | — |
| 太晶非本系 | 太晶属性与原有本系不同 → 招式威力×1.5 | — |

### 常见战术术语

| 术语 | 含义 | 典型代表 |
|------|------|---------|
| 控速 | 改变行动顺序以获取回合优势 | 顺风/空间/冰冻之风/麻痹 |
| 轴 | 围绕核心机制构建的战术闭环 | 顺风轴/空间轴/天气轴 |
| 选出 | 从6只中选4只出战，决定首发 | 根据对手阵容动态调整 |
| 威吓轮转 | 威吓特性宝可梦反复换人降低对方物攻 | 炽焰咆哮虎→土地云→风速狗 |
| 并场联防 | 两只宝可梦同时站场，抗性叠加互补 | 水火草联防体系 |
| 崩溃线 | 多只宝可梦共享同一弱点，被单一招式贯穿 | 火+草+虫 → 岩系崩溃线 |
| 极速 | 252努力+加速性格 | 多龙巴鲁托极限速度 406 |
| 满速 | 252努力无性格修正 | 多龙巴鲁托满速 369 |
| 极限低速 | 0努力+减速性格 | 铁臂膀极限低速 94（空间用） |
| 速度线 | 特定配置下的速度实数值，用于判断先后手 | — |

---

## 交互式配置确认流程

当用户首次提出伤害计算请求且配置信息不完整时，按以下流程处理：

### Step 1: 执行默认计算
基于推断规则或预设配置给出首份结果。LLM 必须在回答开头明确标注假设的配置。

### Step 2: 主动提示缺失信息
若关键配置（如对方耐久努力值）可能影响结论，主动提示：
> "以上计算假设防御方为 0 努力值配置。若实际配置不同（如加了 HP/特防），结果可能有变化。需要我重新计算吗？"

### Step 3: 支持快速调整
用户可以通过自然语言快速调整配置，无需完整重写命令：
- 用户："胡地加了 252HP"
- LLM：直接修改 `evs` 重新执行 `calc` 或 `calc-raw`

### Step 4: 支持预设切换
当存在多种合理配置时，提供对比：
> "该宝可梦常见配置有两种：`Sash Set`（气势披带速攻）和 `Bulk Set`（剩饭耐久）。当前计算使用 `Sash Set`，需要切换吗？"

### 禁止行为
- **禁止在未标注假设的情况下直接给出结果**
- **禁止在用户未明确指定时默认使用满努力值配置（如 252 全属性）**
- **禁止忽略用户未指定的重要参数（如对方耐久）**

---

## 常见术语速查表

### 道具类

| 中文名 | 英文名 | 效果 | 常见称呼 |
|--------|--------|------|---------|
| 气势披带 | Focus Sash | 满HP时不会被一击秒杀 | 腰带、Sash |
| 讲究头带 | Choice Band | 攻击×1.5，锁定招式 | 头带、CB |
| 讲究眼镜 | Choice Specs | 特攻×1.5，锁定招式 | 眼镜、CS |
| 讲究围巾 | Choice Scarf | 速度×1.5，锁定招式 | 围巾、Scarf |
| 生命宝珠 | Life Orb | 招式威力×1.3，每回合损10%HP | 命玉、LO |
| 剩饭 | Leftovers | 每回合回复 1/16 HP | 剩饭 |
| 突击背心 | Assault Vest | 特防×1.5，不能使用变化招式 | 背心、AV |
| 弱点保险 | Weakness Policy | 被弱点攻击时攻击/特攻+2 | 弱策、WP |
| 讲究护具 | Choice Item | 头带/眼镜/围巾的统称 | 锁招道具 |
| 气势头带 | Focus Band | 10% 概率一击不死 | 头带（易与气势披带混淆，注意区分） |

### 招式类

| 中文名 | 英文名 | 效果 | 常见称呼 |
|--------|--------|------|---------|
| 击掌奇袭 | Fake Out | +3优先度，30%畏缩，首回合限用 | 击掌、Fake Out |
| 急速折返 | U-turn | 造成伤害后换人 | UT、U-turn |
| 伏特替换 | Volt Switch | 电系急速折返 | VS、Volt Switch |
| 看我嘛 | Follow Me | 吸引对方单体攻击 | 看我嘛、Follow Me |
| 愤怒粉 | Rage Powder | 虫系看我嘛，草系免疫 | 愤怒粉 |
| 顺风 | Tailwind | 己方速度翻倍，持续4回合 | 顺风 |
| 戏法空间 | Trick Room | 速度顺序反转，持续5回合 | 空间、TR |
| 再来一次 | Encore | 强制目标连续使用上回合招式 | 再来一次、Encore |
| 挑衅 | Taunt | 3回合内目标不能使用变化招式 | 挑衅 |
| 帮助 | Helping Hand | 队友招式威力×1.5 | 帮助、HH |
| 广域防守 | Wide Guard | 保护己方免受广域招式伤害 | 广防 |
| 快速防守 | Quick Guard | 保护己方免受先制招式伤害 | 快防 |
| 守住 | Protect | 本回合不受大部分招式伤害 | 保护、Protect |
| 替身 | Substitute | 消耗25%HP制造替身 | 替身 |

### 特性类

| 中文名 | 英文名 | 效果 | 常见称呼 |
|--------|--------|------|---------|
| 威吓 | Intimidate | 出场降低对方全体物攻1级 | 威吓 |
| 恶作剧之心 | Prankster | 变化招式优先度+1 | 恶作剧、Prankster |
| 疾风之翼 | Gale Wings | 满HP时飞行系招式优先度+1 | 疾风 |
| 女王威严 | Queenly Majesty | 阻止对方使用先制招式 | 女王 |
| 再生力 | Regenerator | 下场回复 1/3 HP | 再生力 |
| 自然回复 | Natural Cure | 下场治愈异常状态 | 自然回复 |
| 叶绿素 | Chlorophyll | 晴天下速度翻倍 | 叶绿素 |
| 悠游自如 | Swift Swim | 雨天下速度翻倍 | 轻快 |
| 夸克充能 | Quark Drive | 电气场地下最高能力值提升 | 夸克充能 |
| 古代活性 | Protosynthesis | 日光/晴天下最高能力值提升 | 古代活性 |
| 强子引擎 | Hadron Engine | 出场开启电气场地并提升特攻 | 强子引擎 |
| 终结之地 | Desolate Land | 出场开启不可覆盖的日照 | 终结之地 |
| 始源之海 | Primordial Sea | 出场开启不可覆盖的降雨 | 始源之海 |
| 不服输 | Defiant | 被降低能力时物攻+2 | 不服输 |
| 好胜 | Competitive | 被降低能力时特攻+2 | 好胜 |

### 其他术语

| 术语 | 含义 |
|------|------|
| STAB | Same Type Attack Bonus，同属性招式威力×1.5 |
| 本系 | 与宝可梦属性一致的招式，享受 STAB |
| 补盲 | 弥补打击面盲点的非本系招式 |
| 确一 / OHKO | 一击击杀（One Hit Knock Out） |
| 确二 / 2HKO | 两击击杀 |
| 乱数 | 伤害公式中 85~100 的随机整数，共16个取值 |
| 耐久三维 | HP、防御、特防的统称 |
| 抗性与弱点 | 受到某属性攻击时的伤害倍率（0.5x/2x/4x/0x） |
| 换人惩罚 | 换人消耗一回合，新上场宝可梦可能承受攻击 |
| 漂浮 | 免疫地面系招式（飞行属性或飘浮特性） |
| 踩影 | 特性，阻止对方换人 |
| 魔法防守 | 特性，不受非直接攻击伤害 |
