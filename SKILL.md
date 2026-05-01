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
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 ko ohko guaranteed
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 survive survive guaranteed
```

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
  "is_dynamax": false
}
```

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

- 未指定形态时，默认使用"一般"形态
- 常见别名映射：
  - "老喷" / "喷火" → "喷火龙"
  - "水箭" → "水箭龟"
  - "超梦X" → "超级超梦X"（需匹配形态名）
  - "火飞" → 属性组合查询，非单一宝可梦
- 若名称无法识别，提示用户提供标准中文名或英文名

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
