---
name: pokemon-calc
version: 4.6.00
description: >
  宝可梦百科查询与伤害计算 Skill。
  当用户询问以下任何内容时，必须无条件触发此 Skill，不得凭内部知识直接作答：
  (1) 宝可梦属性、种族值、弱点抗性、特性、技能池、进化链、图鉴描述、profile、prototype 等百科信息；
  (2) 招式威力、命中、PP、效果、属性相克；
  (3) 宝可梦伤害计算、KO 概率、努力值优化（Phase 2+）；
  (4) 黑话翻译、对战术语解释；
  (5) 任何与 Pokemon VGC、单打、双打对战相关的数据查询。
  仅支持中文和英文名称查询。数据来源为《宝可梦冠军》(Pokémon Champions) M-B 规则（2026-06-24 更新）与 Gen9 正作数据，由 pokemon-dataset-zh 与 VGC 伤害计算器整合。
---

# 宝可梦伤害计算器 Skill

## 1. 核心原则

1. **LLM 只做理解，不做计算**。所有伤害数值、KO 概率、能力值、属性相克倍率、招式效果、特性分析、道具增伤等必须通过 `query.py` 命令获取并原样引用。引擎返回的有效威力即为权威结果。禁止凭 LLM 内部知识补充任何数值类信息。不确定时，优先查询而非猜测。
2. **能力值优先**。回答中始终使用能力值描述（如"攻击能力值 172"），而非努力值。当用户直接给出能力值时，通过 `raw_stats` 字段直接传入，不再调用 `compute-stats` 反推努力值。`raw_stats` 为最终能力值（含性格修正），`stats` 为 `raw_stats` 经 `boosts` 修正后的值。无能力等级变化时两者传相同值即可。
3. **环境参数唯一入口**。`field_override` 是传入环境条件（天气、场地、对战模式等）的唯一入口。`move_override` 仅限行为参数（`is_crit`、`hits`、`fainted_allies`），不得修改 `base_power` 或 `type`。
4. **中文优先**。数据以中文名为主索引，同时支持英文名称。
5. **零外部依赖**。核心数据已静态化为 JSON，查询脚本仅使用 Python 标准库。

## 2. 命令速查

所有查询通过执行 bundled script [`scripts/query.py`](scripts/query.py) 完成。

> **路径解析说明**：脚本通过 `__file__` 动态定位自身目录，并自动查找同级目录下的 `data/` 文件夹。若 Skill 被安装到其他位置，可通过设置环境变量 `POKEMON_CALC_DATA_DIR` 显式指定数据目录。

```bash
# Phase 1 — 百科查询（纯数据查询，无计算）
pokemon <name> [--type <type> ...]  # 基础信息查询；或按属性筛选（如 `pokemon --type 超能 --type 恶` 列出所有超能+恶属性宝可梦）
move <name>           # 威力、命中、PP、属性、分类、效果
                      # `description` 为游戏内官方中文描述（单行，换行符已替换为空格）。若为空，表示该招式暂无官方描述。
ability <name>        # 效果描述、元信息
item <name>           # 效果描述、分类、持有效果
type <atk> [def]      # 属性相克倍率。传入两个属性则返回点对点倍率（如 `type 冰 龙` → 2.0x）；仅传入一个属性则返回该属性的完整克制速查表（进攻端克制/被抵抗/无效 + 防御端弱点/抗性/免疫）
stats <name>          # 各形态种族值
weak <name>           # 弱点、抗性、免疫
learnset <name>       # 升级/TM/遗传/教学招式
evo <name>            # 进化链与超级进化
pokedex <name>        # 各版本图鉴描述
profile <name>        # 外形描述、原型考据、多语言词源
find-move <move> [--source champions|gen9]  # 反向查询：能学会该招式的所有宝可梦（返回含 types 字段）
filter-moves [--type <type> ...] [--category <cat> ...] [--min-power <n>] [--max-power <n>]
                        # 招式筛选：按属性、分类、威力范围过滤。同维度多选为 OR，不同维度为 AND。
                        # 例：`filter-moves --type 恶 --category 物理 --min-power 90`
preset <pokemon> [name] # 列出预设配置或获取具体配置

# Phase 2 — 伤害计算与优化
calc <att> <move> <def> [att_ov] [move_ov] [def_ov] [field_ov]       # 快捷伤害计算（Lv.50）
calc-raw <att_json> <move_json> <def_json> [field_json]              # 纯参数计算
compute-stats <base_stats> --evs <evs> --ivs <ivs> --nature <nature> --level <level>  # 种族值+配置 → 能力值
optimize <att> <move> <def> [goal] [target] [threshold] [att_ov] [def_ov] [field_ov]  # 努力值优化
survivability <defender> <attacker_stat> <category> [def_ov] [field_ov]                # 等效威力反查（无加成最大可承受招式威力）
```

### 参数覆盖 JSON 示例

```json
// att_override / def_override — 仅传需要覆盖的字段
{
  "level": 50,
  "evs": {"hp": 4, "attack": 252, "speed": 252},
  "nature": "爽朗",
  "ability": "坚硬脑袋",
  "item": "气势披带",
  "boosts": {"attack": 0},
  "is_terastalize": false,
  "tera_type": null,
  "preset": "Sharp Beak Set",    // 从 setdex 加载预设配置，覆盖字段在此基础上叠加
  "setup_moves": ["诡计", "求雨"]  // 由引擎自动解析招式效果并应用（替代手动构造 boosts/weather）
}

// 直接传入能力值（跳过 compute-stats，适用于用户已明确给出能力值时）
{
  "raw_stats": {"hp": 155, "attack": 80, "defense": 85, "sp_attack": 192, "sp_defense": 105, "speed": 90},
  "stats": {"hp": 155, "attack": 80, "defense": 85, "sp_attack": 192, "sp_defense": 105, "speed": 90},
  "item": "龙之牙"
}
// raw_stats = 最终能力值（已含性格修正），stats = raw_stats 经 boosts 修正后的值
// 无能力等级变化时，raw_stats 和 stats 传相同值即可

// move_override — 仅限行为参数，禁止改 base_power / type
{"is_crit": false, "hits": 1, "fainted_allies": 0}

// 需要激活 abilityOn 类特性时，在 att_override / def_override 中传入
{"ability": "Flash Fire", "ability_on": true}
{"ability": "Supreme Overlord", "fainted_allies": 3}

// field_override — 环境条件唯一入口
{
  "weather": "Sun",
  "terrain": "Electric",
  "format": "Doubles",
  "is_reflect": false,
  "is_light_screen": false,
  "is_aurora_veil": false,
  "is_stealth_rock": false,
  "spikes": 0,
  "is_helping_hand": false
}
```

**setup_moves 说明**：

- `setup_moves` 是 `att_override` 的字段，接收变化类招式名称数组（如 `["诡计", "求雨"]`）。引擎自动解析并应用招式效果（能力等级变化、天气/场地设置等）。
- **禁止同时传入 `setup_moves` 和对应的手动 `boosts`/`weather`/`terrain`**，避免冲突。

**field_override 取值**：
- `weather`: Sun / Rain / Sand / Hail / Snow / Strong Winds / Harsh Sun / Heavy Rain
- `terrain`: Electric / Grassy / Misty / Psychic
- `format`: Singles / Doubles
- 墙壁/辅助特性/灾祸系列等：布尔开关，见 `field_override` JSON 示例

### 命令执行环境兼容性

| 环境 | 推荐方式 | 说明 |
|------|---------|------|
| bash / zsh | 命令行直接执行 | 单引号包裹 JSON：`--att_ov '{"evs":...}'` |
| Windows cmd.exe / PowerShell | **写临时脚本调用** | cmd.exe 对 JSON 引号解析不友好，建议写临时 Python 脚本直接 import `cmd_calc` |

**Windows 临时脚本模板**：

```python
import json, sys; sys.path.insert(0, "pokemon-calc/scripts")
from query import cmd_calc
result = cmd_calc("ATT", "MOVE", "DEF", json.dumps({...}), json.dumps({}), json.dumps({}), json.dumps({...}))
print(json.dumps(result, ensure_ascii=False, indent=2))
```

> **环境变量**：可通过 `POKEMON_CALC_SKILL_ROOT` 指定 Skill 根目录；`POKEMON_CALC_DATA_DIR` 覆盖数据目录。

### 命令示例

```bash
# 基础查询（仅需位置参数）
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟

# 命名参数方式（推荐，避免括号错位）
python scripts/query.py calc 超级喷火龙Y 气象球 超级胡地 --field_ov '{"weather":"Sun"}'
python scripts/query.py calc 密勒顿 电气上升 故勒顿 --field_ov '{"terrain":"Electric"}'
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟 --field_ov '{"weather":"Sun","terrain":"Electric"}'
python scripts/query.py calc 超级喷火龙Y 热风 超级胡地 \
  --att_ov '{"evs":{"sp_attack":252}}' \
  --field_ov '{"weather":"Sun","format":"Doubles"}'

# optimize 也使用命名参数
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko

# 能力点数（SP）模式：Champions 规则
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko --mode sp

# find-move 支持数据来源过滤
python scripts/query.py find-move 顺风 --source champions  # 仅 Champions M-B 规则
python scripts/query.py find-move 顺风 --source gen9       # 仅 Gen9 正作数据

# filter-pokemon 按属性/种族值/特性筛选
python scripts/query.py filter-pokemon --type 火 --type 龙 --min-stat speed 100
python scripts/query.py filter-pokemon --type 水 --max-stat hp 60 --ability 悠游自如
```

> **`--source` 过滤说明**：`find-move` 默认返回全国图鉴（Gen9 + Champions）所有能学会该招式的宝可梦。传入 `--source champions` 仅返回 Champions M-B 规则可用宝可梦；传入 `--source gen9` 排除 Champions 专属宝可梦，仅保留 Gen9 正作数据。
>
> **`types` 字段**：`find-move` 返回的每个宝可梦条目均包含 `"types"` 数组，可直接用于属性筛选（如"找出能学会顺风的恶系宝可梦"），无需二次查询。

### filter-pokemon 命令说明

```bash
python scripts/query.py filter-pokemon [OPTIONS]
```

按属性、种族值、特性筛选宝可梦。

| 参数 | 说明 | 示例 |
|------|------|------|
| `--type` | 属性（可多次指定，AND 关系） | `--type 火 --type 龙` |
| `--min-stat` | 最小基础种族值 | `--min-stat speed 100` |
| `--max-stat` | 最大基础种族值 | `--max-stat hp 60` |
| `--ability` | 特性（可多次指定，OR 关系） | `--ability 悠游自如` |

**返回值字段**：
- `count`: 匹配数量
- `filters`: 实际生效的筛选条件
- `results`: 匹配宝可梦列表，每个条目包含 `name_zh`、`name_en`、`pokedex_id`、`types`、`base_stats`、`abilities`

**筛选规则**：
- 多个 `--type` 之间为 AND 关系（宝可梦必须同时具有所有指定属性）
- 多个 `--ability` 之间为 OR 关系（任意形态拥有其中一个特性即可）
- `--min-stat` 和 `--max-stat` 的统计项名称为：`hp`、`attack`、`defense`、`sp_attack`、`sp_defense`、`speed`

### 天气联动招式（引擎自动处理）

以下招式的威力/属性会随天气/场地自动变化。**LLM 唯一需要做的事：在 `field_override` 中传入天气或场地。具体威力变化由引擎自动计算，LLM 禁止自行推演或在回答中写出中间计算式。**

| 招式 | 说明 |
|------|------|
| 气象球 / Weather Ball | 天气联动招式，需确认 weather 字段 |
| 大地波动 / Terrain Pulse | 场地联动招式，需确认 terrain 字段 |
| 电气上升 / Rising Voltage | 电气场地联动招式 |
| 精神强念 / Expanding Force | 精神场地联动招式 |
| 薄雾爆炸 / Misty Explosion | 薄雾场地联动招式 |
| 重力苹果 / Grav Apple | 重力联动招式 |

### 队友阵亡联动招式

| 招式 | 说明 |
|------|------|
| 扫墓 / Last Respects | 每有 1 名队友阵亡，威力 +50。需通过 `move_override.fainted_allies` 传入阵亡数 |

> **使用示例**：`--move_ov '{"fainted_allies": 1}'` 表示已阵亡 1 名队友，威力 = 50 + 50 × 1 = 100。

### calc 返回值关键字段

```json
{
  "damage_range": [55, 66],
  "damage_rolls": [55, 55, 57, 57, 58, 58, 60, 60, 60, 61, 61, 63, 63, 64, 64, 66],
  "type_effectiveness": 1.0,
  "stab_applied": true,
  "burn_applied": false,
  "ko_chance": "约 6.2% 概率一击必杀",
  "attacker_info": {"name_zh": "...", "stats": {...}, "evs": {...}, "nature": "..."},
  "defender_info": {"name_zh": "...", "stats": {...}, "current_hp": 130, "max_hp": 130},
  "total_damage_range": [110, 132],
  "move_hits": 2,
  "attacker_auto_preset": null,
  "defender_auto_preset": "Bulky Tera Grass"
}
```

- `damage_range` / `damage_rolls` 为**单次打击**（多段招式）
- `total_damage_range` / `total_damage_rolls` 为**多段合计**，判断秒杀时优先引用
- `type_effectiveness` 反映**实际生效属性**经过属性相克后的原始倍率（已包含 Ate/Ize 特性、气象球、大地波动等导致的类型转换；如 格斗 vs 恶/钢 = 4.0），**不包含**抗性树果、Solid Rock、Filter 等后续修正。判断道具是否生效时，应对比 `damage_range` 是否减半，而非观察 `type_effectiveness` 是否变化
- `attacker_auto_preset` / `defender_auto_preset`：当用户未指定配置或只给出部分配置（如性格、某项努力值）时，引擎自动从 setdex 匹配最相似的预设，用其 **evs / nature / ivs** 补全未指定字段；若用户完全未指定配置，还会同时采用该预设的 **特性**。道具**不参与**自动兜底。若该宝可梦不在 setdex 中（共 189 只），值为 `null`。Agent 在回答中若发现该字段非 null，必须声明："未指定努力值按 VGC 热门预设 `{preset_name}` 补全"

### calc-raw 快速填空模板

```bash
python scripts/query.py calc-raw \
  --att '{"name":"ATT_NAME","level":50,"stats":ATT_STATS,"types":ATT_TYPES,"ability":"ATT_ABILITY","nature":"ATT_NATURE","current_hp":ATT_HP,"max_hp":ATT_HP}' \
  --move '{"name":"MOVE_NAME","base_power":BP,"type":"MOVE_TYPE","category":"CATEGORY"}' \
  --def '{"name":"DEF_NAME","level":50,"stats":DEF_STATS,"types":DEF_TYPES,"ability":"DEF_ABILITY","nature":"DEF_NATURE","current_hp":DEF_HP,"max_hp":DEF_HP}' \
  --field '{"weather":"Sun"}'
```

字段精简原则：calc-raw 只读取传入的字段。至少传入 `name`, `level`, `stats`, `types`, `ability`, `nature`, `current_hp`, `max_hp` 即可。

**`is_spread` 自动补全**：若 `move_json` 省略了 `is_spread` 但提供了 `name` 或 `name_zh`，系统会自动从招式数据补全该值。若用户显式传入 `is_spread`，优先使用用户值。

### optimize 返回值关键字段

```json
{"success": true, "target": "ohko", "stat": "sp_attack", "optimal_ev": 252, "optimal_sp": 0, "damage_range": [130, 156]}
```

`optimal_ev`（默认 EV 模式）在 LLM 回答时必须转换为**能力值描述**（如"特攻能力值需要达到 177"），并可标注 SP 等价（"252 努力值 = 32 能力点数"）。若用户以 SP 提问并加 `--mode sp`，则引用 `optimal_sp`。禁止只说数值而不给能力值。

### survivability 命令说明

```bash
python scripts/query.py survivability <defender> <attacker_stat> <category> [def_ov] [field_ov]
```

- **用途**：给定防御方能力值（或宝可梦名称）和攻击方物攻/特攻能力值，反查**无攻击方加成**（无 STAB、道具、特性、天气/场地）下防御方能承受的最大招式基础威力。
- **输出字段**：`safe_bp`（KO 概率 < 15% 的最大威力）、`absolute_safe_bp`（KO 概率 = 0% 的最大威力）、`defender`（含最终能力值）、`defender_boosts`（最终生效的能力等级）。
- **输入方式**：传名称自动推导 Lv.50 默认能力值：`survivability 烈咬陆鲨 200 Physical`；直接传能力值：`def_ov '{"raw_stats":{"hp":185,"defense":85}}'`。`def_ov` 支持 `boosts` 和 `setup_moves`（详见上方 setup_moves 说明），例：`survivability 水箭龟 200 Special --def_ov '{"setup_moves":["冥想"]}'`。
- **LLM 使用规则**：只引用引擎返回的 `safe_bp` 和 `absolute_safe_bp`，不做任何中间推导。引擎输出为属性相克倍率 1.0 的基准值。用户追问以下问题时，必须调用对应工具重算，禁止凭内部知识作答：

  | 用户追问 | 必须调用的工具 |
  |---------|--------------|
  | "X 属性招式打过去会怎样" | `type <atk> <def_types>` 查询倍率，再将结果除以对应倍率 |
  | "加上 STAB 后是多少" | `calc` 重新计算（不可手算 STAB） |
  | "如果带命玉/头带呢" | `calc` 重新计算（道具修正由引擎处理） |
  | "XX 宝可梦的防御能力值和这个一样吗" | `pokemon <name>` + `compute-stats` 查种族值 |

## 3. 执行工作流

### 3.1 通用流程

```
1. 解析意图 → 百科查询 / 属性相克 / 伤害计算 / 努力值优化
2. 名称规范化 → 别名映射、形态确认（未指定则默认"一般"形态）
3. 执行对应命令并解析结果
```

### 3.2 伤害计算强制工作流（calc / optimize）

**执行任何伤害计算命令前，必须先输出 `<plan>` 标签进行结构化思考。**

#### Step 0: 强制 <plan> 标签（不可跳过）

```markdown
<plan>
1. 提取指令信息：攻方 = [填入标准名称] | 守方 = [填入标准名称] | 招式 = [填入标准名称]
2. 环境决策强制检查（仅限用户明确提及或继承自上一轮对话）：
   - 用户是否明确提及天气或场地？[是 / 否，若是请列出具体名称]
   - 用户是否明确提及单打 / 双打？[是 / 否。若否，强制推断为 Doubles]
3. 危险动作核对（强制自我确认）：
   - 我是否试图在 plan 阶段预设能力值、努力值、性格或伤害数字？[必须填 否]
   - 我是否打算凭内部记忆解释属性相克、特性效果或招式机制？[必须填 否]
4. 即将执行的精确命令：[在此处写出完整的 `python scripts/query.py calc ...` 命令]
</plan>
```

> **多轮状态继承**：若上一轮对话中已确定环境条件（如晴天），且用户本轮未提及环境变化，则在 `<plan>` 中标注"继承自上一轮"，并在 `--field_ov` 中继续传入该环境条件。

> **规则**：未输出 `<plan>` 标签，不得执行任何伤害计算命令。
> **规则**：`<plan>` 中禁止出现任何具体数值（如"252 特攻"、"伤害 120"）。所有数值必须等 `calc` 返回后提取。

#### Step 1: 提取实体

攻击方宝可梦、招式、防御方宝可梦。

#### Step 2: 名称规范化

确认标准中文名/英文名，确定形态（未指定则默认"一般"形态）。

**别名处理规则**：`data/aliases.json` 已收录常见俗称（如"钢兵"→"仆刀将军"、"抗斗果"→"巧可果"），`normalize.py` 在所有查询命令的底层自动完成映射。**Agent 无需预先转换别名，直接使用用户提供的原始名称作为参数传入即可，以查询的结果为准。**

**形态查询与消歧规则**：

部分宝可梦存在多形态（如 Mega 进化、地区形态、原始回归等）。`pokemon` 命令返回的数据中，`forms` 字段列出所有可用形态。当用户输入的名称可能对应多个形态时，按以下工作流处理：

1. **先执行 `pokemon <name>` 查询**，查看返回的 `forms` 列表和 `form_selection_note`。
2. **LLM 根据上下文推断用户意图的形态**（如用户说"洗翠火暴兽"则选"洗翠的样子"，说"火暴兽"则选默认"火暴兽"）。
3. **在 `calc` / `optimize` 的 `att_override` 或 `def_override` 中传入 `"form_name"`**，明确指定形态名称。

```json
// 指定洗翠形态（火+幽灵，HP 73）
{"form_name": "洗翠的样子", "item": "讲究围巾"}

// 指定 Mega 形态（火+飞行，特性日照）
{"form_name": "超级喷火龙Ｙ", "evs": {"sp_attack": 252}}
```

**规则**：
- `form_name` 的值必须是 `pokemon` 命令返回的 `forms[].name` 中的某一个，大小写敏感。
- 不传 `form_name` 时，默认使用 `_find_form_index` 推断的形态（通常是第一个形态或索引匹配的形态）。
- **严禁**传入 `"form"` 字段（已废弃），`Pokemon` dataclass 不支持该参数。

**示例工作流**（洗翠火暴兽 vs 超级胡地）：

```bash
# Step 1: 查询形态列表
python scripts/query.py pokemon 洗翠火暴兽
# 返回 form_selection_note: "该宝可梦存在 2 种形态：火暴兽, 洗翠的样子。..."

# Step 2: LLM 根据"洗翠"推断选"洗翠的样子"，执行 calc
python scripts/query.py calc 超级胡地 广域战力 洗翠火暴兽 \
  --att_ov '{"evs":{"sp_attack":252},"nature":"内敛"}' \
  --def_ov '{"item":"讲究围巾","form_name":"洗翠的样子"}' \
  --field_ov '{"format":"Doubles"}'
```

#### Step 3: 环境条件检查（强制逐项确认）

| # | 检查项 | 必须传入的条件 | 传入位置 |
|---|--------|---------------|---------|
| 3.1 | 天气 (weather) | 用户明确提及天气词汇；或攻击方特性为天气特性；或使用气象球/大地波动等联动招式 | `field_override` |
| 3.2 | 场地 (terrain) | 用户明确提及场地词汇；或使用场地联动招式（电气上升/精神强念/薄雾爆炸/大地波动） | `field_override` |
| 3.3 | 对战模式 (format) | 用户提及"单打" → Singles；否则默认 Doubles | `field_override` |
| 3.4 | 墙壁 (screen) | 用户提及光墙/反射壁/极光幕 | `field_override` |
| 3.5 | 岩钉/撒菱 | 用户提及隐形岩/撒菱 | `field_override` |
| 3.6 | 其他场地效果 | 用户提及帮助/友情防守/蓄电池/能量点/灾祸系列等 | `field_override` |

> `weather` 和 `terrain` 是两个**完全独立**的字段，可以同时存在。例如：`{"weather":"Sun","terrain":"Electric"}`

> 攻击方特性（如"日照"）**不会自动设置** field.weather，必须显式构造 `{"weather":"Sun"}`。

#### Step 4: 配置推断

用户未指定性格/努力值/道具时，根据宝可梦种族值推断角色类型，套用默认配置：

| 角色类型 | 默认能力点数（SP） | 默认性格 | 默认道具 |
|---------|-----------|---------|---------|
| 物理攻击手 | 32攻击/32速度 | 爽朗（+速度 -特攻） | 气势披带 |
| 特殊攻击手 | 32特攻/32速度 | 胆小（+速度 -攻击） | 气势披带 |
| 物攻坦克 | 32HP/32防御 | 淘气（+防御 -特攻） | 剩饭 |
| 特攻坦克 | 32HP/32特防 | 慎重（+特防 -攻击） | 剩饭 |
| 辅助/控速手 | 32HP/32速度 | 爽朗/胆小 | 气势披带 |
| 空间打手（低速） | 32HP/32攻击 | 勇敢（+攻击 -速度） | 气势披带 |
| 天气/场地手 | 32HP/32速度 | 爽朗/胆小 | 气势披带 |

> 默认配置以 SP 表述（单项满 32）。实际传入 `--att_ov` 时用 `sps` 字段（如 `{"sps":{"attack":32,"speed":32}}`），适配层自动按 `8×SP-4` 转为 EV（32→252），与传统 252 分配完全等价。若用户显式给出 252 等 EV 数值，则用 `evs` 字段原样传入。

**推断优先级**：用户明确指定 > 角色类型推断。无论使用何种默认配置，回答开头必须声明假设。

**配置覆盖铁律**：无论任何默认推断规则（包括未过签形态的 0 点数规则、Mega 形态默认道具规则），**用户的显式指定拥有最高优先级**。若用户指定了"252特攻"（用 `evs` 字段）或"32特攻"（用 `sps` 字段）或特定道具，必须严格在 `--att_ov` 中传入对应字段与数值，不再使用默认配置。

**形态可用性警告规则**：

- 若 `_data_source == "gen9"` 且 `is_unobtainable == true`：
  > ⚠️ 该形态在 Gen9 标准对战中不可用，以下结果为理论计算。

- 若 `_data_source == "champions"` 且 `is_unobtainable == true`：
  > ⚠️ 该形态基于 Champions M-B 规则数据（2026-06-24 更新）。若您询问的是 Gen9 规则，结果可能不适用。

- 若 `_data_source == "champions"` 且 `is_unobtainable == false`：
  > 无需警告

- **Mega 形态默认道具**：引擎自动根据形态名推导默认携带的 Mega 石（如 `超级喷火龙Ｙ` → `喷火龙进化石Ｙ`，`原始盖欧卡` → `原始回归宝珠`）。若用户显式指定其他道具，按配置覆盖铁律处理。

#### Step 5: 命令选择

```
标准宝可梦（Gen9可用）+ 名字已知      → calc
未过签宝可梦（Mega等）且 calc 可用    → calc（引用 warning）
未过签宝可梦且 calc 报错             → pokemon → compute-stats → calc-raw
自定义假设（"如果HP150/特攻180"）     → calc-raw
```

#### Step 6: 构造命令并执行

- 一次性构造完整命令，包含所有覆盖参数
- 多段攻击招式（如双翼）：calc 自动返回单次 + 合计总伤害
- 性格未指定时的对比场景：同时计算两种常见性格（如爽朗 vs 固执），输出能力值对比表

#### Step 7: 参数一致性校验

构造命令后，对照 `<plan>` 中的环境推断检查 `--field_ov` 内容：

- 若 plan 推断出 weather/terrain/format 不为空，则 `--field_ov` 绝对不能是 `{}` 或省略
- 若 plan 推断出无环境，则 `--field_ov` 可以省略

> **常见错误**：plan 推断出晴天，但 `--field_ov` 漏传。这会遗漏天气加成，导致伤害结果严重偏低。

#### Step 8: 异常处理与重试

若命令返回错误信息（如 `not found`、JSON 解析错误、参数无效）：

1. **绝对禁止编造补救结果** —— 不得输出"大概"、"估计"等替代数字
2. **重新生成 `<plan>`** —— 分析报错原因（名称拼写？JSON 格式？字段名错误？）
3. **修正参数后重试** —— 修正后再次执行命令
4. **若再次失败** —— 原样输出报错信息给用户，说明无法完成计算

#### Step 9: 结果解析与回答

按文档末尾「输出格式铁律」模板组织回答。使用命令返回的精确数字，禁止编造。

## 4. 输出格式

### 4.1 百科查询回答

一句话总结核心信息，可附关键数据表格。

### 4.2 伤害计算标准回答结构

**执行 `calc` 后，严格按照文档末尾的「输出格式铁律」模板组织回答。**

必须包含六个二级标题（结论摘要 / 攻击方详细信息 / 防御方详细信息 / 招式信息 / 环境条件 / 伤害计算结果），按顺序输出，不得遗漏。若用户询问能力点数/努力值优化，追加「能力点数优化结果」。

多段攻击招式（如双翼）：`damage_range` 为单次伤害，`total_damage_range` 为合计伤害，判断秒杀时优先引用 `total_damage_range`。回答时必须转换为**能力值描述**，禁止直接输出努力值。

### 4.3 多方案对比输出格式

当存在多个合理配置时：

```markdown
## 方案对比

| 配置 | 攻击能力值 | 单次伤害 | 总伤害 | KO 概率 |
|------|-----------|---------|--------|---------|
| 爽朗 | 157 | 55～65 | 110～130 | 约 6.25% |
| 固执 | 172 | 60～71 | 120～142 | 约 75% |
```

表格中只写能力值，不写努力值。

## 5. 附录

### 5.1 数据来源与版本策略

采用双层数据架构：

| 层级 | 来源 | 覆盖范围 | 优先级 |
|------|------|----------|--------|
| 第一层 | 《宝可梦冠军》(Pokémon Champions) M-B 规则（2026-06-24 更新） | 361 种形态 | **高** |
| 第二层 | Gen9（朱紫）正作数据 | 全国图鉴 1~1025 | 低 |

当 Champions 数据与 Gen9 正作数据存在差异时，以 Champions 为准。查询结果中的 `"_data_source"` 字段标识具体来源（`"champions"` 或 `"gen9"`）。

数据中覆盖全国图鉴 1~1025 号，**包含所有形态**（含 Mega、原始回归等），不区分世代过签状态。伤害计算时不过签过滤。

### 5.2 能力点数（SP）与努力值（EV）双视图

本 Skill 底层始终以**努力值（EV）**存储与计算（保留完整 4 EV 精度），同时提供《宝可梦冠军》(Pokémon Champions) 的**能力点数（SP）**作为输入与展示视图。两者是同一配置的双向等价表述，引擎自动换算，无精度损失。

| 系统 | 总点数 | 单项上限 | 步进 | 对应能力值增长（Lv.50, IV=31） |
|------|--------|----------|------|-------------------------------|
| 能力点数（SP） | 66 | 32 | 1 | 每 1 SP = +1 能力值 |
| 努力值（EV） | 508 | 252 | 4 | 首个 +1 需 4 EV，之后每 8 EV = +1 |

**双向换算公式**（Lv.50, IV=31 精确成立）：

- SP → EV：`EV = 8 × SP - 4`（SP=0 时 EV=0）
- EV → SP：`SP = (EV + 4) // 8`

| SP | 等效 EV | 能力值增量 |
|----|--------|-----------|
| 1 | 4 | +1 |
| 13 | 100 | +13 |
| 31 | 244 | +31 |
| 32 | 252 | +32 |

> 关键：第一个能力点只需 4 EV，之后每 8 EV 一点，因此 **32 SP = 252 EV**（不是 256）。两种表述指向完全相同的能力值。

**术语规范**：
- **优先 SP 表述**：面向用户的回答默认使用能力点数（如"特攻点满 32"），符合 Champions 习惯。
- 用户提及"能力点数""SP""32""66"时，在 override 中使用 **`sps` 字段**（如 `{"sps":{"sp_attack":32}}`），适配层自动按 `8×SP-4` 转为 EV（32→252）。
- 用户提及"努力值""252""4""508"等 EV 关键词时，在 override 中使用 **`evs` 字段**（如 `{"evs":{"sp_attack":252}}`），原样传入。
- **`sps` 与 `evs` 可并存**，同一能力项 `sps` 优先。两者取其一即可，优先匹配用户话术。
- 回答中同时标注两种表述，格式为"32 能力点数（= 252 努力值）"；优先强调能力值描述（如"特攻能力值需要达到 172"）。
- `calc` / `calc-raw` / `compute-stats` 返回 JSON 中，`evs` 字段为底层原始 EV，`sps` 字段为换算后的 SP 展示值。展示时优先引用 `sps`。

**命令示例**：

```bash
# 用户以 SP 表述（推荐）：用 sps 字段，引擎自动转 252 EV
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟 --att_ov '{"sps":{"sp_attack":32}}'

# 用户以传统 EV 表述：直接用 evs 字段
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟 --att_ov '{"evs":{"sp_attack":252}}'

# optimize 默认 EV 模式；Champions SP 优化用 --mode sp
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko --mode sp
```

**返回值字段说明**：

`optimize` 命令始终返回两套字段以兼容双模式：

```json
// EV 模式（--mode ev，默认）
{
  "success": true,
  "optimal_ev": 252,
  "remaining_evs": 256,
  "optimal_sp": 0,
  "remaining_sp": 0
}

// SP 模式（--mode sp）
{
  "success": true,
  "optimal_ev": 0,
  "remaining_evs": 0,
  "optimal_sp": 25,
  "remaining_sp": 41
}
```

未使用模式的字段固定为 0，避免解析歧义。

### 5.4 常见实体词汇启动列表（Vocabulary Priming）

> **强制声明**：以下词汇列表仅用于实体识别和名称映射。严禁在回答中自行解释任何机制或效果。遇到这些词汇时，必须原样或按映射关系传递给 `query.py` 查询后引用。

* 常见道具与树果俗称：命玉（生命宝珠）、头带/CB（讲究头带）、眼镜/CS（讲究眼镜）、围巾/Scarf（讲究围巾）、剩饭（吃剩的东西）、腰带/Sash（气势披带）、突击背心/AV、弱策（弱点保险）、抗火果（千香果）、抗水果（烛木果）、抗电果（罗子果）、抗草果（番荔果）、抗冰果（腰木果）、抗斗果（巧可果）、抗毒果（棱瓜果）、抗地果（葫苏果）、抗飞果（乐芭果）、抗超果（芭亚果）、抗虫果（莲蒲果）、抗岩果（霹霹果）、抗鬼果（佛柑果）、抗龙果（烛龙果）、抗恶果（刺耳果）、抗钢果（穹犀果）、抗仙果（香罗果）、抗一般果（投鲜果）等 18 系抗性树果。
* 常见招式俗称：击掌（击掌奇袭）、UT（急速折返）、VS（伏特替换）、看我嘛（Follow Me）、愤怒粉（Rage Powder）、顺风（Tailwind）、空间/TR（戏法空间）、挑衅（Taunt）、广防（广域防守）、快防（快速防守）、保护（守住）。
* 常见特性俗称：威吓（Intimidate）、恶作剧（恶作剧之心）、疾风（疾风之翼）、女王（女王威严）、再生力（Regenerator）、叶绿素（Chlorophyll）、轻快（悠游自如）、夸克充能（Quark Drive）、古代活性（Protosynthesis）、强子引擎（Hadron Engine）、终结之地（Desolate Land）、始源之海（Primordial Sea）。
* 常见战术术语：STAB/本系、补盲、确一/OHKO、确二/2HKO、乱数、耐久三维、极速、满速、极限低速、速度线。

> **易混淆属性相克提醒（必须通过 `type` 命令查询确认）**：
> - 超能力 → 幽灵：**效果一般（1.0x）**，不是 0 倍
> - 格斗/普通 → 幽灵：**无效（0x）**
> - 地面 → 飞行：**无效（0x）**
> - 电 → 地面：**无效（0x）**

---

## 输出格式铁律（最终输出模板）

> **强制指令**：本 Skill 的最终输出必须严格复制以下模板结构。将括号内的占位符替换为引擎返回的真实数据。严禁擅自增删任何二级标题或改变顺序。

**回答前必须声明的假设**（不可省略）：

1. **对战环境声明**：`本次计算环境：[用户指定 / 默认 Doubles]。`
2. **数据来源声明**：`攻方数据来源：attacker_info._data_source | 守方数据来源：defender_info._data_source`
3. **未过签形态警告**（若 `is_unobtainable == true`）：
   - Gen9 不可用 → `⚠️ 该形态在 Gen9 标准对战中不可用，以下结果为理论计算。`
   - Champions 不可用 → `⚠️ 该形态基于 Champions M-B 规则数据（2026-06-24 更新）。若您询问的是 Gen9 规则，结果可能不适用。`
4. **默认配置推断清单**（当用户未指定性格/努力值/道具时）：
   `假设声明：以下参数未由用户明确指定，使用角色类型默认推断：`
   `- 性格：[推断值] — 推断依据：[角色类型]`
   `- 能力点数：[推断值]`
   `- 道具：[推断值]`
   `若实际配置不同，伤害结果可能有变化。`

**禁止的做法**：省略对战环境声明 / 省略数据来源声明 / 笼统写"使用了默认配置"而不列出具体参数 / 将推断参数作为绝对事实陈述。

### 结论摘要

先回答用户核心问题（如"能不能接下""能否秒杀"）。

### 攻击方详细信息

使用 `calc` 返回的 `attacker_info` 构建完整表格。

| 项目 | 数值 |
|------|------|
| 属性 | {属性1} / {属性2} |
| 特性 | {当前特性}（可选：{特性1} / {特性2} / {特性3}） |
| 等级 | Lv.{level} |
| 种族值 | HP {hp} / 攻击 {atk} / 防御 {def} / 特攻 {spa} / 特防 {spd} / 速度 {spe} |
| 个体值 | 全 {iv}（默认 31，若有 0 则标注） |
| 能力点数 | HP {hp_sp} / 攻击 {atk_sp} / 防御 {def_sp} / 特攻 {spa_sp} / 特防 {spd_sp} / 速度 {spe_sp} |
| 性格 | {nature}（{+修正项} / {-修正项}） |
| 实际能力值 | HP {hp_stat} / 攻击 {atk_stat} / 防御 {def_stat} / 特攻 {spa_stat} / 特防 {spd_stat} / 速度 {spe_stat} |
| 道具 | {item} |
| 太晶化 | {是/否}，太晶属性：{tera_type} |
| 能力等级变化 | 攻击 {atk_boost} / 防御 {def_boost} / 特攻 {spa_boost} / 特防 {spd_boost} / 速度 {spe_boost} |
| 状态异常 | {status} |

> **能力点数取值规则**：
> - "能力点数"行取自 `calc` 返回的 `sps` 字段（0~32 整数），底层 `evs` 字段为原始 EV。
> - 若用户用传统 EV 表述提问（如"252 特攻"），在"能力点数"行后追加一行标注等价关系：`> 注：252 特攻努力值 = 32 能力点数（SP），能力值完全相同`。
> - 若用户直接用 SP 提问或未指定，无需追加该注释。

> **特性显示规则**：
> - 所有形态：**必须同时输出**"特性"（`ability` 字段）和"全部可选特性"（`all_abilities` 字段）
> - 用户指定特性时，当前特性为用户指定值；未指定时，当前特性为默认特性（`all_abilities` 列表第一项）
> - Mega / 原始回归形态同样适用此规则

### 防御方详细信息

使用 `calc` 返回的 `defender_info` 构建完整表格。

| 项目 | 数值 |
|------|------|
| 属性 | {属性1} / {属性2} |
| 特性 | {当前特性}（可选：{特性1} / {特性2} / {特性3}） |
| 等级 | Lv.{level} |
| 种族值 | HP {hp} / 攻击 {atk} / 防御 {def} / 特攻 {spa} / 特防 {spd} / 速度 {spe} |
| 个体值 | 全 {iv}（默认 31，若有 0 则标注） |
| 能力点数 | HP {hp_sp} / 攻击 {atk_sp} / 防御 {def_sp} / 特攻 {spa_sp} / 特防 {spd_sp} / 速度 {spe_sp} |
| 性格 | {nature}（{+修正项} / {-修正项}） |
| 实际能力值 | HP {hp_stat} / 攻击 {atk_stat} / 防御 {def_stat} / 特攻 {spa_stat} / 特防 {spd_stat} / 速度 {spe_stat} |
| 道具 | {item} |
| 太晶化 | {是/否}，太晶属性：{tera_type} |
| 能力等级变化 | 攻击 {atk_boost} / 防御 {def_boost} / 特攻 {spa_boost} / 特防 {spd_boost} / 速度 {spe_boost} |
| 状态异常 | {status} |
| 当前 HP / 最大 HP | {current_hp} / {max_hp} |

### 招式信息

使用 `calc` 返回的招式数据构建完整表格。

| 项目 | 数值 |
|------|------|
| 属性 | {type} |
| 分类 | {物理/特殊/变化} |
| 基础威力 | {base_power} |
| 计算威力 | {effective_power} |
| 命中 | {accuracy} |
| 打击次数 | {hits} |
| 引擎修正链简述 | {description} |
| 广域招式 | {是/否} |

> **计算威力说明**：引擎根据传入的环境条件自动计算最终威力。直接引用引擎返回的 `effective_power` 或 `description` 中的威力值，禁止自行推导中间步骤。

### 环境条件

使用 `calc` 返回的 `field` 信息构建完整表格。

| 项目 | 数值 |
|------|------|
| 天气 | {weather} |
| 场地 | {terrain} |
| 对战模式 | {Singles / Doubles} |
| 光墙/反射壁/极光幕 | {是/否} |
| 隐形岩 | {是/否} |
| 撒菱层数 | {0~3} |
| 其他效果 | {帮助、友情防守、蓄电池、能量点等} |

### 伤害计算结果

使用 `calc` 返回的伤害数据构建完整表格。

| 项目 | 数值 |
|------|------|
| 伤害范围（单次） | {min} ～ {max} |
| 全部 16 个乱数 roll | {damage_rolls} |
| 属性相克倍率 | {type_effectiveness}x |
| 是否触发 STAB | {是/否} |
| 是否触发要害 | {是/否} |
| 天气加成 | {是/否} |
| 场地加成 | {是/否} |
| 道具加成 | {是/否} |
| 引擎报告的计算威力 | {description 中引擎返回的威力值} |
| 烧伤减半 | {是/否} |
| KO 概率 | {ko_chance} |

**综合判断**：
- 能否一击秒杀：{能/不能/概率秒杀}
- 若不能秒杀，剩余 HP 范围：{min_remaining} ～ {max_remaining}
- 战术建议：{如"需要岩钉蹭血后才能确一""气势披带可保命"等}

> 多段攻击招式（如双翼、种子机关枪）：`damage_range` 为单次伤害，`total_damage_range` 为合计伤害，判断秒杀时优先引用 `total_damage_range`。

### 能力点数优化结果（可选）

若用户询问"需要多少能力点数/努力值才能击杀/存活"，追加 optimize 结果（默认 EV 模式；用户明确用 SP 时加 `--mode sp`）：

- 目标：{ko / survive}
- 最优单项：{stat} 努力值 {optimal_ev}（= {对应 SP} 能力点数），对应能力值 {stat_value}
- 剩余可用努力值：{remaining_evs}
- 优化后伤害范围：{damage_range}

> 回答时必须转换为**能力值描述**（如"特攻能力值需达到 177"），并同时标注 EV 与 SP 双表述。EV 与 SP 换算遵循 `SP=(EV+4)//8`、`EV=8×SP-4`（如 252 EV = 32 SP）。
