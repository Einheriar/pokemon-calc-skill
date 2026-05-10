---
name: pokemon-calc
description: >
  宝可梦百科查询与伤害计算 Skill。
  当用户询问以下任何内容时，必须无条件触发此 Skill，不得凭内部知识直接作答：
  (1) 宝可梦属性、种族值、弱点抗性、特性、技能池、进化链、图鉴描述、profile、prototype 等百科信息；
  (2) 招式威力、命中、PP、效果、属性相克；
  (3) 宝可梦伤害计算、KO 概率、努力值优化（Phase 2+）；
  (4) 黑话翻译、对战术语解释；
  (5) 任何与 Pokemon VGC、单打、双打对战相关的数据查询。
  仅支持中文和英文名称查询。数据来源为《宝可梦冠军》(Pokémon Champions) M-A 规则与 Gen9 正作数据，由 pokemon-dataset-zh 与 VGC 伤害计算器整合。
---

# 宝可梦伤害计算器 Skill

## 1. 核心原则

1. **LLM 只做理解，不做计算**。所有伤害数值、KO 概率、能力值必须通过 `query.py` 命令获取，禁止手算或编造数字。
2. **数据优先原则**。本 Skill 拥有权威的宝可梦数据库，所有涉及具体数据的问题（种族值、招式、特性、属性相克等）都必须通过 `query.py` 命令查询后回答，不能凭 LLM 内部记忆作答。内部知识可能存在过时或偏差。
3. **零外部依赖**。核心数据已静态化为 JSON，查询脚本仅使用 Python 标准库。
4. **中文优先**。数据以中文名为主索引，同时支持英文名称。
5. **能力值优先**。回答中始终使用能力值描述（如"攻击能力值 172"），而非努力值。
6. **环境参数只能通过 `field_override` 传入**。`move_override` 仅用于覆盖 `is_crit`、`hits` 等行为参数，绝对禁止修改 `base_power` 或 `type` 来模拟天气/场地效果。
7. **禁止在回答中手动推导威力修正链**。引擎返回的 `effective_power` 或 `description` 中的威力值即为权威结果。LLM 不得在回答中写出"基础威力 × 场地 × STAB = ..."等中间推导式，仅可陈述"引擎报告计算威力为 X"。

## 2. 命令速查

所有查询通过执行 bundled script [`scripts/query.py`](scripts/query.py) 完成。

```bash
# Phase 1 — 百科查询（纯数据查询，无计算）
pokemon <name>        # 基础信息、形态、特性、种族值、进化链
move <name>           # 威力、命中、PP、属性、分类、效果
ability <name>        # 效果描述、元信息
item <name>           # 效果描述、分类、持有效果
type <atk> <def>      # 属性相克倍率
stats <name>          # 各形态种族值
weak <name>           # 弱点、抗性、免疫
learnset <name>       # 升级/TM/遗传/教学招式
evo <name>            # 进化链与超级进化
pokedex <name>        # 各版本图鉴描述
profile <name>        # 外形描述、原型考据、多语言词源
find-move <move>      # 反向查询：能学会该招式的所有宝可梦
preset <pokemon> [name] # 列出预设配置或获取具体配置

# Phase 2 — 伤害计算与优化
calc <att> <move> <def> [att_ov] [move_ov] [def_ov] [field_ov]       # 快捷伤害计算（Lv.50）
calc-raw <att_json> <move_json> <def_json> [field_json]              # 纯参数计算
compute-stats <base_stats> --evs <evs> --ivs <ivs> --nature <nature> --level <level>  # 种族值+配置 → 能力值
optimize <att> <move> <def> [goal] [target] [threshold] [att_ov] [def_ov] [field_ov]  # 努力值优化
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

// move_override — 仅限行为参数，禁止改 base_power / type
{"is_crit": false, "hits": 1}

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

- `setup_moves` 是 `att_override` 的字段，接收变化类招式名称数组
- 引擎自动查询 `moves.json` 中的 `stat_changes` 字段，应用以下效果：
  - 能力等级变化（如诡计→特攻+2，剑舞→攻击+2）
  - 天气/场地设置（如求雨→Rain，电气场地→Electric）
  - HP 回复（如自我再生→回复50% HP）
  - 状态异常赋予（如电磁波→麻痹）
- **禁止同时传入 `setup_moves` 和对应的手动 `boosts`/`weather`/`terrain`**，避免冲突
- 若招式无 `stat_changes` 数据（如保护、替身），引擎静默跳过

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
import json, sys
sys.path.insert(0, "pokemon-calc/scripts")
from query import cmd_calc

result = cmd_calc(
    "ATT_NAME", "MOVE_NAME", "DEF_NAME",
    json.dumps({"evs": {"sp_attack": 252}}),  # att_override
    json.dumps({}),                            # move_override
    json.dumps({}),                            # def_override
    json.dumps({"terrain": "Psychic"})         # field_override
)
print(json.dumps(result, ensure_ascii=False, indent=2))
```

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
```

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
  "move_hits": 2
}
```

- `damage_range` / `damage_rolls` 为**单次打击**（多段招式）
- `total_damage_range` / `total_damage_rolls` 为**多段合计**，判断秒杀时优先引用

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
{"success": true, "target": "ohko", "stat": "sp_attack", "optimal_ev": 252, "damage_range": [130, 156]}
```

`optimal_ev` 在 LLM 回答时必须转换为**能力值描述**（如"特攻能力值需要达到 177"），禁止直接说"252 特攻努力值"。

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
1. 意图：{百科查询 / 伤害计算 / 努力值优化}
2. 实体：攻方={name} | 招式={name} | 守方={name}
3. 环境推断：
   - 天气：{Sun/Rain/Sand/Hail/Snow/无}（依据：用户本轮提及 / 继承自上一轮对话 / 特性暗示 / 招式联动 / 无）
   - 场地：{Electric/Grassy/Misty/Psychic/无}（依据同上）
   - 对战模式：{Singles/Doubles}（默认 Doubles）
4. 配置推断：
   - 攻方/守方配置 = 待 calc 命令返回后，从 attacker_info 和 defender_info 提取（禁止在 plan 阶段预设具体数值）
5. 命令选择：{calc / calc-raw / optimize}
6. 参数构造：--field_ov '{"weather":"Sun","format":"Doubles"}'（仅传入需要覆盖的字段）
</plan>
```

> **多轮状态继承**：若上一轮对话中已确定环境条件（如晴天），且用户本轮未提及环境变化，则在 `<plan>` 中标注"继承自上一轮"，并在 `--field_ov` 中继续传入该环境条件。

> **规则**：未输出 `<plan>` 标签，不得执行任何伤害计算命令。

#### Step 1: 提取实体

攻击方宝可梦、招式、防御方宝可梦。

#### Step 2: 名称规范化

确认标准中文名/英文名，确定形态（未指定则默认"一般"形态）。别名由 `data/aliases.json` 和 `normalize.py` 自动处理。

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

| 角色类型 | 默认努力值 | 默认性格 | 默认道具 |
|---------|-----------|---------|---------|
| 物理攻击手 | 252攻击/252速度/4HP | 爽朗（+速度 -特攻） | 气势披带 |
| 特殊攻击手 | 252特攻/252速度/4HP | 胆小（+速度 -攻击） | 气势披带 |
| 物攻坦克 | 252HP/252防御/4攻击 | 淘气（+防御 -特攻） | 剩饭 |
| 特攻坦克 | 252HP/252特防/4特攻 | 慎重（+特防 -攻击） | 剩饭 |
| 辅助/控速手 | 252HP/252速度/4任意 | 爽朗/胆小 | 气势披带 |
| 空间打手（低速） | 252HP/252攻击/4防御 | 勇敢（+攻击 -速度） | 气势披带 |
| 天气/场地手 | 252HP/252速度/4任意 | 爽朗/胆小 | 气势披带 |

**推断优先级**：用户明确指定 > 角色类型推断。无论使用何种默认配置，回答开头必须声明假设。

**配置覆盖铁律**：无论任何默认推断规则（包括未过签形态的 0 努力值规则、Mega 形态默认道具规则），**用户的显式指定拥有最高优先级**。若用户指定了"252特攻"或特定道具，必须严格在 `--att_ov` 中传入该值，不再使用默认配置。

**未过签/Mega 形态例外**：
- 使用 **0 努力值 + 勤奋性格** 作为默认配置，并在回答中注明"该形态在标准对战中不可用，以下结果为理论计算"。`calc` 返回 JSON 中的 `"warning"` 字段必须原样引用。
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

按第 4 节"输出格式"组织回答。使用命令返回的精确数字，禁止编造。

## 4. 输出格式

### 4.1 百科查询回答

一句话总结核心信息，可附关键数据表格。

### 4.2 伤害计算标准回答结构

> **回答结构铁律**：执行 calc 命令后，你的最终回答**必须严格包含**以下 Markdown 标题，不得遗漏任何一个。利用标题的自回归惯性强制输出完整表格。
>
> 必须包含的标题（按顺序）：
> 1. `## 结论摘要` —— 先回答用户核心问题（如"能不能接下""能否秒杀"）
> 2. `## 攻击方详细信息` —— 必须附带完整表格（使用 calc 返回的 attacker_info）
> 3. `## 防御方详细信息` —— 必须附带完整表格（使用 calc 返回的 defender_info）
> 4. `## 招式信息` —— 必须附带完整表格
> 5. `## 环境条件` —— 必须附带完整表格
> 6. `## 伤害计算结果` —— 必须附带完整表格
>
> 若用户询问努力值优化，追加 `## 努力值优化结果`。

#### 1. 前言：假设声明（强制不可省略）

**必须包含的内容**：
- 任何未过签形态的警告（`warning` 字段原样引用）
- **默认配置推断清单**：当用户未明确指定性格/努力值/道具时，逐条列出系统推断的具体参数及推断依据

若涉及未过签形态，**首先输出**：
```
⚠️ 该形态在 Gen9 标准对战中不可用，以下结果为理论计算。
```

**推断参数显式列出示例**：

> **假设声明**：以下参数未由用户明确指定，使用角色类型默认推断：
> - 性格：爽朗（+速度 -特攻）— 推断依据：烈箭鹰为物理速攻型
> - 努力值：252攻击 / 252速度 / 4HP
> - 道具：气势披带
> - 对战模式：Doubles（VGC 默认）
>
> 若实际配置不同，伤害结果可能有变化。

**禁止的做法**：
- 笼统地写"使用了默认配置"而不列出具体参数
- 将推断参数作为绝对事实陈述，不声明为"推断"

#### 第一部分：攻击方详细信息

```
## 攻击方：{宝可梦名}

| 项目 | 数值 |
|------|------|
| 属性 | {属性1} / {属性2} |
| 特性 | {当前特性} |
| 等级 | Lv.{level} |
| 种族值 | HP {hp} / 攻击 {atk} / 防御 {def} / 特攻 {spa} / 特防 {spd} / 速度 {spe} |
| 个体值 | 全 {iv}（默认 31，若有 0 则标注） |
| 努力值 | HP {hp_ev} / 攻击 {atk_ev} / 防御 {def_ev} / 特攻 {spa_ev} / 特防 {spd_ev} / 速度 {spe_ev} |
| 性格 | {nature}（{+修正项} / {-修正项}） |
| 实际能力值 | HP {hp_stat} / 攻击 {atk_stat} / 防御 {def_stat} / 特攻 {spa_stat} / 特防 {spd_stat} / 速度 {spe_stat} |
| 道具 | {item} |
| 太晶化 | {是/否}，太晶属性：{tera_type} |
| 能力等级变化 | 攻击 {atk_boost} / 防御 {def_boost} / 特攻 {spa_boost} / 特防 {spd_boost} / 速度 {spe_boost} |
| 状态异常 | {status} |
```

> **特性显示规则**：
> - 普通形态：可追加"全部可选特性"行（该宝可梦所有可获得特性）
> - Mega / 原始回归形态：**严格只输出"特性"一行，禁止输出"全部可选特性"**。`all_abilities` 来自普通形态，与 Mega 专属特性无关

#### 第二部分：防御方详细信息

结构同第一部分，追加：

```
| 当前 HP / 最大 HP | {current_hp} / {max_hp} |
```

#### 第三部分：招式信息

```
## 招式：{招式名}

| 项目 | 数值 |
|------|------|
| 属性 | {type} |
| 分类 | {物理/特殊/变化} |
| 基础威力 | {base_power} |
| 计算威力 | {effective_power} |
| 命中 | {accuracy} |
| 打击次数 | {hits} |
| 效果 | {effect_description} |
| 广域招式 | {是/否} |

> **计算威力说明**：引擎根据传入的环境条件自动计算最终威力。以下为引擎返回的计算结果：
> 基础威力 {base_power} → 引擎计算威力 {effective_power}
>
> LLM 禁止自行推导中间步骤（如"基础威力 × 场地 × STAB = ..."），仅可陈述引擎报告的最终值。
```

#### 第四部分：环境条件

```
## 环境条件

| 项目 | 数值 |
|------|------|
| 天气 | {weather} |
| 场地 | {terrain} |
| 对战模式 | {Singles / Doubles} |
| 光墙/反射壁/极光幕 | {是/否} |
| 隐形岩 | {是/否} |
| 撒菱层数 | {0~3} |
| 其他效果 | {帮助、友情防守、蓄电池、能量点等} |
```

#### 第五部分：伤害计算结果

```
## 伤害计算结果

| 项目 | 数值 |
|------|------|
| 伤害范围（单次） | {min} ～ {max} |
| 全部 16 个乱数 roll | {damage_rolls} |
| 属性相克倍率 | {type_effectiveness}x |
| 是否触发 STAB | {是/否} |
| 是否触发要害 | {是/否} |
| 天气加成 | {是/否}（晴天火系 ×1.5 / 雨天水系 ×1.5 / 沙暴岩系 ×1.5） |
| 场地加成 | {是/否}（电气场地电系 ×1.3 / 青草场地草系 ×1.3 / 薄雾场地龙系 ×0.5 / 精神场地超能系 ×1.3） |
| 道具加成 | {是/否}（生命宝珠 ×1.3 / 讲究头带/眼镜 ×1.5 等） |
| 特性加成 | {是/否}（日照/强子引擎/古代活性等） |
| 烧伤减半 | {是/否} |
| KO 概率 | {ko_chance} |

### 结论

{综合判断}
- 能否一击秒杀：{能/不能/概率秒杀}
- 若不能秒杀，剩余 HP 范围：{min_remaining} ～ {max_remaining}
- 战术建议：{如"需要岩钉蹭血后才能确一""气势披带可保命"等}
```

多段攻击招式（如双翼、种子机关枪）：`damage_range` 为单次伤害，`total_damage_range` 为合计伤害，判断秒杀时优先引用 `total_damage_range`。

#### 第六部分（可选）：努力值优化建议

若用户询问"需要多少努力值才能击杀/存活"，追加 optimize 结果：

```
## 努力值优化结果

- 目标：{ko / survive}
- 最优单项：{stat} 努力值 {optimal_ev}，对应能力值 {stat_value}
- 剩余可用努力值：{remaining_evs}
- 优化后伤害范围：{damage_range}
```

> 回答时必须转换为**能力值描述**，禁止直接输出努力值。

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
| 第一层 | 《宝可梦冠军》(Pokémon Champions) M-A 规则 | 323 种形态 | **高** |
| 第二层 | Gen9（朱紫）正作数据 | 全国图鉴 1~1025 | 低 |

当 Champions 数据与 Gen9 正作数据存在差异时，以 Champions 为准。查询结果中的 `"_data_source"` 字段标识具体来源（`"champions"` 或 `"gen9"`）。

数据中覆盖全国图鉴 1~1025 号，**包含所有形态**（含 Mega、原始回归等），不区分世代过签状态。伤害计算时不过签过滤。

### 5.2 已实现的修正

- 属性相克：18 属性完整相克表，含 Stellar、Freeze-Dry、Flying Press 等特殊规则
- STAB / 太晶化：含 Adaptability、星晶属性加成
- 特性修正：含 30+ 种攻击/防御特性（Overgrow/Blaze/Torrent、Huge Power、Guts、Protosynthesis 等）
- 道具修正：生命宝珠、讲究头带/眼镜、突击背心、进化奇石、深海的牙齿/鳞片、厚骨棒、光粉等
- 场地/天气：晴天/雨天/沙暴/下雪、青草/电气/薄雾/精神场地
- Ate/Ize 特性：Pixilate / Aerilate / Refrigerate / Galvanize / Normalize 类型转换 + 威力提升
- 抗性树果：16 种树果在效果拔群时触发
- 其他：烧伤减半、要害 1.5x、能力等级变化、重力、光墙/反射壁/极光幕

### 5.3 field_override 字段参考

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

| 用户可能描述 | 传入字段 |
|-------------|---------|
| 晴天/雨天/沙暴/下雪/暴风雪/大日照/大雨/强风 | `weather` |
| 电气场地/青草场地/薄雾场地/精神场地 | `terrain` |
| 单打/双打 | `format` |
| 重力 | `is_gravity` |
| 反射壁 | `is_reflect` |
| 光墙 | `is_light_screen` |
| 极光幕 | `is_aurora_veil` |
| 友情防守 | `is_friend_guard` |
| 蓄电池 | `is_battery` |
| 能量点 | `is_power_spot` |
| 钢之意志 | `is_steely_spirit` |
| 顺风（攻击方） | `is_tailwind_atk` |
| 顺风（防御方） | `is_tailwind_def` |
| 化学变化气体 | `is_neutralizing_gas` |
| 灾祸之简 | `is_sword_of_ruin` |
| 灾祸之鼎 | `is_beads_of_ruin` |
| 灾祸之剑 | `is_tablets_of_ruin` |
| 灾祸之玉 | `is_vessel_of_ruin` |
| 隐形岩 | `is_stealth_rock` |
| 撒菱 | `spikes`（0~3） |
| 盐腌 | `is_salt_cure` |
| 帮助 | `is_helping_hand` |

> 字段含义由底层引擎处理，LLM 只需根据用户描述传入对应开关即可。

### 5.4 对战机制速览

#### 单打 vs 双打核心差异

| 维度 | 单打（6选3） | 双打（6选4 / VGC） |
|------|-------------|-------------------|
| 核心逻辑 | 联防重于联攻 | 联攻优先于联防 |
| 换人 | 核心战略 | 频率降低，保护招式更常用 |
| 广域招式 | 无衰减 | 对每只目标威力 ×0.75 |
| 墙壁效果 | 伤害 ×0.5 | 伤害 ×0.67（约 2/3） |

#### 关键机制修正速查

| 机制 | 效果 | 常见触发方式 |
|------|------|-------------|
| 顺风 | 己方速度翻倍，持续4回合 | 风妖精（恶作剧之心）、化石翼龙等 |
| 戏法空间 | 速度顺序反转，持续5回合 | 奇麒麟、布莉姆温、青铜钟等 |
| 日照/晴天 | 火系 ×1.5，水系 ×0.5 | 煤炭龟、固拉多、故勒顿 |
| 降雨/雨天 | 水系 ×1.5，火系 ×0.5 | 大嘴鸥、盖欧卡 |
| 电气场地 | 电系 ×1.3 | 密勒顿（强子引擎自动开启） |
| 精神场地 | 超能系 ×1.3 | 爱管侍等 |
| 青草场地 | 草系 ×1.3 | 轰擂金刚猩、奥利瓦等 |
| 薄雾场地 | 龙系 ×0.5 | 卡璞·鳍鳍等 |
| 太晶化 | 一次性属性改变 | 每场战斗仅可使用一次 |
| 太晶本系 | 太晶属性与原有本系一致 → 招式威力 ×2 | — |
| 太晶非本系 | 太晶属性与原有本系不同 → 招式威力 ×1.5 | — |

### 5.5 常见术语速查表

#### 道具类

| 中文名 | 英文名 | 效果 | 常见称呼 |
|--------|--------|------|---------|
| 气势披带 | Focus Sash | 满HP时不会被一击秒杀 | 腰带、Sash |
| 讲究头带 | Choice Band | 攻击 ×1.5，锁定招式 | 头带、CB |
| 讲究眼镜 | Choice Specs | 特攻 ×1.5，锁定招式 | 眼镜、CS |
| 讲究围巾 | Choice Scarf | 速度 ×1.5，锁定招式 | 围巾、Scarf |
| 生命宝珠 | Life Orb | 招式威力 ×1.3，每回合损10%HP | 命玉、LO |
| 剩饭 | Leftovers | 每回合回复 1/16 HP | 剩饭 |
| 突击背心 | Assault Vest | 特防 ×1.5，不能使用变化招式 | 背心、AV |
| 弱点保险 | Weakness Policy | 被弱点攻击时攻击/特攻+2 | 弱策、WP |
| 气势头带 | Focus Band | 10% 概率一击不死 | 头带（易与气势披带混淆） |

#### 招式类

| 中文名 | 英文名 | 效果 | 常见称呼 |
|--------|--------|------|---------|
| 击掌奇袭 | Fake Out | +3优先度，30%畏缩，首回合限用 | 击掌、Fake Out |
| 急速折返 | U-turn | 造成伤害后换人 | UT、U-turn |
| 伏特替换 | Volt Switch | 电系急速折返 | VS、Volt Switch |
| 看我嘛 | Follow Me | 吸引对方单体攻击 | 看我嘛 |
| 愤怒粉 | Rage Powder | 虫系看我嘛，草系免疫 | 愤怒粉 |
| 顺风 | Tailwind | 己方速度翻倍，持续4回合 | 顺风 |
| 戏法空间 | Trick Room | 速度顺序反转，持续5回合 | 空间、TR |
| 再来一次 | Encore | 强制目标连续使用上回合招式 | 再来一次 |
| 挑衅 | Taunt | 3回合内目标不能使用变化招式 | 挑衅 |
| 帮助 | Helping Hand | 队友招式威力 ×1.5 | 帮助、HH |
| 广域防守 | Wide Guard | 保护己方免受广域招式伤害 | 广防 |
| 快速防守 | Quick Guard | 保护己方免受先制招式伤害 | 快防 |
| 守住 | Protect | 本回合不受大部分招式伤害 | 保护 |
| 替身 | Substitute | 消耗25%HP制造替身 | 替身 |

#### 特性类

| 中文名 | 英文名 | 效果 | 常见称呼 |
|--------|--------|------|---------|
| 威吓 | Intimidate | 出场降低对方全体物攻1级 | 威吓 |
| 恶作剧之心 | Prankster | 变化招式优先度+1 | 恶作剧 |
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

#### 其他术语

| 术语 | 含义 |
|------|------|
| STAB | Same Type Attack Bonus，同属性招式威力 ×1.5 |
| 本系 | 与宝可梦属性一致的招式，享受 STAB |
| 补盲 | 弥补打击面盲点的非本系招式 |
| 确一 / OHKO | 一击击杀（One Hit Knock Out） |
| 确二 / 2HKO | 两击击杀 |
| 乱数 | 伤害公式中 85~100 的随机整数，共16个取值 |
| 耐久三维 | HP、防御、特防的统称 |
| 极速 | 252努力 + 加速性格 |
| 满速 | 252努力 无性格修正 |
| 极限低速 | 0努力 + 减速性格（空间用） |
| 速度线 | 特定配置下的速度实数值，用于判断先后手 |

### 5.6 交互式配置确认流程

当用户首次提出伤害计算请求且配置信息不完整时：

1. **执行默认计算**：基于推断规则或预设配置给出首份结果，回答开头明确标注假设的配置
2. **主动提示缺失信息**：若关键配置可能影响结论，提示"以上计算假设防御方为 0 努力值配置。若实际配置不同，结果可能有变化。需要我重新计算吗？"
3. **支持快速调整**：用户可通过自然语言快速调整（如"胡地加了 252HP"），直接修改 evs 重新执行 calc
4. **支持预设切换**：当存在多种合理配置时提供对比，如"该宝可梦常见配置有两种：`Sash Set` 和 `Bulk Set`。当前计算使用 `Sash Set`，需要切换吗？"

禁止行为：禁止在未标注假设的情况下直接给出结果；禁止在用户未明确指定时默认使用满努力值配置；禁止忽略用户未指定的重要参数。

### 5.7 当前阶段

- **Phase 1（百科查询）**：已可用
- **Phase 2（伤害计算）**：已可用（calc / calc-raw / compute-stats）
- **Phase 3（努力值优化）**：已可用（optimize）
