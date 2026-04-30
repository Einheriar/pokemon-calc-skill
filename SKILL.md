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

## 可用工具

所有查询通过执行 bundled script [`scripts/query.py`](scripts/query.py) 完成。

| 命令 | 参数 | 用途 |
|------|------|------|
| `pokemon <name>` | 宝可梦中文/英文名 | 基础信息、形态、特性、种族值、进化链 |
| `move <name>` | 招式中文/英文名 | 威力、命中、PP、属性、分类、效果描述 |
| `ability <name>` | 特性中文/英文名 | 效果描述、元信息 |
| `type <atk> <def>` | 攻击属性 防御属性 | 属性相克倍率与描述 |
| `stats <name>` | 宝可梦名 | 各形态种族值与总和 |
| `weak <name>` | 宝可梦名 | 弱点、抗性、免疫列表 |
| `learnset <name>` | 宝可梦名 | 升级/TM/遗传/教学招式 |
| `evo <name>` | 宝可梦名 | 进化链与超级进化 |
| `pokedex <name>` | 宝可梦名 | 各版本图鉴描述 |
| `profile <name>` | 宝可梦名 | 外形描述、原型考据、多语言词源 |
| `find-move <move>` | 招式名 | 反向查询：能学会该招式的所有宝可梦 |
| `calc <attacker> <move> <defender> [att_override] [move_override] [def_override]` | 攻击方 招式 防御方 | 快速伤害计算（默认 Lv.50） |
| `optimize <attacker> <move> <defender> [goal] [target] [threshold] [att_override] [def_override]` | 攻击方 招式 防御方 目标 阈值 确信度 | 努力值优化搜索 |

### 使用方式

调用 `query.py` 时，命令与参数以空格分隔；若参数本身包含空格，用引号包裹。

示例（执行脚本）：
```bash
python scripts/query.py stats 喷火龙
python scripts/query.py type 水 火
python scripts/query.py weak Charizard
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟 "{\"evs\":{\"sp_attack\":252},\"item\":\"木炭\"}" "{}" "{\"evs\":{\"sp_defense\":252}}"
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 ko ohko guaranteed
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 survive survive guaranteed
```

### calc 命令详解

`calc` 用于快速伤害计算，参数为：
1. `attacker`：攻击方宝可梦中文/英文名
2. `move`：招式中文/英文名
3. `defender`：防御方宝可梦中文/英文名
4. `att_override`（可选）：JSON 对象覆盖攻击方默认值
5. `move_override`（可选）：JSON 对象覆盖招式默认值
6. `def_override`（可选）：JSON 对象覆盖防御方默认值

### optimize 命令详解

`optimize` 用于自动搜索最优努力值分配：
1. `attacker`：攻击方宝可梦中文/英文名
2. `move`：招式中文/英文名
3. `defender`：防御方宝可梦中文/英文名
4. `goal`（可选）：`ko` / `survive` / `survive_bulk`
5. `target`（可选）：`ohko` / `2hko` / `3hko` / `survive` / `survive_2hko`
6. `threshold`（可选）：`guaranteed`（最差乱数）/ `likely`（平均乱数）
7. `att_override`（可选）：JSON 对象覆盖攻击方
8. `def_override`（可选）：JSON 对象覆盖防御方

示例：
```bash
# 最少多少特攻努力值才能一击击杀水箭龟？
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 ko ohko guaranteed

# 最少多少防御努力值才能扛住喷射火焰？
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 survive survive guaranteed

# 最优 HP + 防御分配来扛住喷射火焰？
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 survive_bulk survive guaranteed
```

默认可覆盖字段：
- Pokemon：`level`, `evs`, `ivs`, `nature`, `ability`, `item`, `types`, `boosts`, `status`, `is_terastalize`, `tera_type`, `is_dynamax`
- Move：`base_power`, `type`, `category`, `is_crit`, `hits`

示例覆盖 JSON：
```json
{"level":50,"evs":{"hp":252,"attack":252,"defense":4},"nature":"固执","ability":"坚硬脑袋","item":"讲究头带","is_terastalize":true,"tera_type":"钢"}
```

LLM 应将用户自然语言中的参数提取为上述 JSON 格式，然后调用 `calc` 或 `optimize`。

## LLM 职责边界

### LLM 负责

1. 从用户问题中识别意图（百科查询 / 属性相克 / 伤害计算准备）
2. 提取并规范化名称：
   - 将别名、简称映射到标准中文名（如 "老喷" → "喷火龙"）
   - 识别英文名称并保留原样
3. 选择正确的 `query.py` 子命令
4. 对脚本返回的 JSON 结果进行自然语言总结，保留关键数字

### LLM 不负责

1. 任何数值计算（倍率乘法、伤害公式、概率推导）
2. 属性相克判断（必须使用 `query.py type` 或 `weak`）
3. 编造不存在的数据

## 查询流程

1. **解析用户意图**：判断是需要百科信息、属性相克、还是伤害计算
2. **名称规范化**：确定宝可梦/招式/特性的标准中文名
3. **执行查询**：构造 `python scripts/query.py <cmd> <args>` 并运行
4. **结果总结**：将 JSON 结果转化为用户友好的中文回复

## 名称规范化规则

- 未指定形态时，默认使用"一般"形态
- 常见别名映射：
  - "老喷" / "喷火" → "喷火龙"
  - "水箭" → "水箭龟"
  - "超梦X" → "超级超梦X"（需匹配形态名）
  - "火飞" → 属性组合查询，非单一宝可梦
- 若名称无法识别，提示用户提供标准中文名或英文名

## 当前阶段

- **Phase 1（百科查询）**：已可用。支持属性/弱点/种族值/招式/特性/进化链/图鉴/技能池/反向查询。
- **Phase 2（伤害计算）**：已可用。支持通过 `calc` 命令进行快速伤害计算，返回 16 个乱数 roll 的伤害范围、属性相克倍率、是否触发 STAB/烧伤/要害/特性修正等。KO 概率计算（1HKO~9HKO）也已集成。
- **Phase 3（努力值优化）**：已可用。支持通过 `optimize` 命令自动搜索最优努力值分配（单攻/单防/HP+防御联合优化）。

## 数据说明

数据位于 `data/` 目录下：
- `pokemon.json` — 1025 只宝可梦完整百科数据（~17.6 MB）
- `moves.json` — 349 个招式（~0.5 MB）
- `abilities.json` — 307 个特性（~0.7 MB）
- `type_chart.json` — 18×18 属性相克表
- `name_index.json` — 中文名/英文名 → 数据键索引

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
