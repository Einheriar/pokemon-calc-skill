# pokemon-calc 命令详细参考

> 本文件为 SKILL.md 的按需参考，不自动加载。当需要 `meta` / `filter-pokemon` / `survivability` / `calc-raw` / `find-move` 的参数细节，或在 Windows 环境下执行命令时，先阅读本文件。

## meta 命令说明

```bash
python scripts/query.py meta [target] [--top N] [--online] [--source tournament|ladder|ingame|showdown]
                           [--format singles|doubles]
                           [--usage] [--teams] [--pokemon 名] [--player 名]
                           [--tournament 名] [--stats [--placing-max N]] [--teammates 名]
```

统一的环境情报查询入口。默认源（tournament）来自 pokecamp.cc 聚合的 Limitless 公开赛事统计（滚动 30 天窗口）；`--source ladder` / `showdown` 接入天梯数据（见下文「--source 参数」）。

### 智能推断规则

`meta` 不带 `--usage` / `--teams` 时，按位置参数自动推断查询模式：

| 位置参数 | 推断模式 | 等价写法 |
|----------|---------|---------|
| 空 | 使用率排行 | `meta --usage` |
| 宝可梦名（中/英/别名） | 单只宝可梦使用率详情 | `meta --usage <名>` |
| 纯数字 N | 第 N 支队伍详情（天梯源下则为"天梯第 N 名是谁"的名次反查） | `meta --teams <N>` / `meta --source ladder <N>` |

带 `--teams` 强制走队伍查询模式，带 `--usage` 强制走使用率查询模式。两者同时给出时 `--teams` 优先；显式 `--usage` 优先于 `--pokemon` 等过滤标志（此时 `--pokemon <名>` 的值作为使用率详情的查询对象，等价于 `meta <名>`）。`--top` 缺省按模式取值：使用率查询默认 20，队伍列表默认 12（硬上限 50）。

### 使用率查询（默认模式）

```bash
python scripts/query.py meta [--top N] [--online]         # 使用率总排行
python scripts/query.py meta <name> [--online]            # 单只宝可梦环境详情
```

- **不带名称**：返回使用率总排行，每条含 `rank`、`name_zh`、`usage_percent`、`win_rate`、`team_count`。
- **带名称**：返回单只宝可梦的环境详情：使用率排名、胜率、Top 12 常用招式、Top 8 特性、Top 8 道具、Top 8 性格、Top 8 能力点数（SP）分配推荐、Top 12 常见队友，均带百分比。
- **`--online`**：实时拉取 pokecamp 最新数据（单只查询只多下载该只的详情，约 23 KB）；结果缓存到 `data/cache/`；网络失败自动回退内置快照。

### 队伍查询（`--teams`）

```bash
python scripts/query.py meta --teams [--top N] [--online]              # 近期赛事队伍列表
python scripts/query.py meta --teams <N>                               # 第 N 支队伍完整配置
python scripts/query.py meta --teams --pokemon <名> [--top N]          # 全量检索
python scripts/query.py meta --teams --player <名>                     # 按选手检索
python scripts/query.py meta --teams --tournament <名>                 # 按赛事检索
python scripts/query.py meta --teams --stats [--placing-max N] [--tournament <名>]  # 出现率排行
python scripts/query.py meta --teams --stats --pokemon <名>            # 道具/特性/招式/性格占比
python scripts/query.py meta --teams --teammates <名>                  # 队友共现排行
```

当前窗口的**全量队伍**（约 9,000+ 支，含完整明细）已内置为 `data/teams_full.json.gz`，首次全量查询自动派生本地 SQLite 索引（一次性数秒，之后离线可用）。

- **不带参数**：按赛事日期降序列出前 12 支队伍（与 pokecamp 赛事队伍页首页一致）。列表与 `meta --teams <N>` 详情同源同序（均来自本地 SQLite 索引），编号一一对应。
- **`meta --teams <N>`**：全量列表按日期降序第 N 支的完整配置（每只宝可梦的道具、特性、4 个招式、性格，均为中英文双语）。
- **`--pokemon <名>`**（或位置参数直接写宝可梦名 + `--teams`）：在全量队伍中检索使用该宝可梦的队伍（默认前 12 条，硬上限 50）。
- **`--player <名>` / `--tournament <名>`**：按选手名 / 赛事名（子串匹配）检索，可互相组合。
- **`--stats`**：全量队伍的出现率排行（默认前 20），可加 `--placing-max 8`（仅统计前八队伍）或 `--tournament <名>`（单赛事）做子集聚合。与使用率同口径同数据集（已数值验证一致），此查询的价值在于子集统计与交叉验证。
- **`--stats --pokemon <名>`**：该宝可梦在全量队伍中的道具 / 特性 / 招式 / 性格占比。
- **`--teammates <名>`**：该宝可梦的队友共现排行（默认前 12）。
- **`--online`**：增量更新（下载队伍列表 gzip 约 1.3 MB + 仅抓取新增赛事的明细），**仅在用户显式要求最新/当前热门队伍时使用**；带 24 小时节流；失败回退缓存/内置数据且 `meta.online_error` 会给出失败原因，必须告知用户。
- 队伍详情不含能力点数分配；如需加点参考，用 `meta <宝可梦名>` 查看该宝可梦的 SP 分配推荐。

### --source 参数

```bash
python scripts/query.py meta --source tournament   # 默认：赛事数据（pokecamp.cc / Limitless）
python scripts/query.py meta --source ladder       # 官方实机排位（等价 ingame，日更，仅名次）
python scripts/query.py meta --source showdown     # Showdown 天梯月报（含使用率，滞后一个月）
```

| 源 | 性质 | 时效 | 使用率 | 单只详情 | 队伍查询 |
|---|---|---|---|---|---|
| `tournament`（默认） | Limitless 公开赛事统计 | 滚动 30 天，日更 | ✅ 含胜率 | ✅（`--online` 更全） | ✅ |
| `ladder` / `ingame` | Pokémon Champions 官方实机排位 | 最新赛制，约 1~3 天 | ❌ **仅名次**（`rank_only: true`） | ✅ 配招/道具/特性/性格/努力为真实百分比（**需 `--online`**），队友仅名次 | ❌ |
| `showdown` | Showdown 天梯月报（cutoff 1760） | 月更，滞后一个月 | ✅ 无胜率 | ✅（**需 `--online`**） | ❌ |

- 天梯源用 `--format singles|doubles` 切换单打/双打排行（默认 `doubles`，输出 `meta.format_note` 会注明当前赛制与切换方法）；对 tournament 源无效（limitless 仅双打）。
- 天梯源数据锁定最新赛制（当前 M-B），不随赛事 regulation 变化。
- 天梯总榜为纯名次/使用率表；ingame 的名次按物种计（Mega 形态并入基础形态，行内 `includes_mega: true` 标注），showdown 的 Mega 形态为 Smogon 独立统计口径、保持分行。
- 天梯源与 `--teams`/`--stats`/`--teammates`/`--player`/`--tournament` 组合会返回友好错误（天梯没有赛事队伍概念）。
- `--online`：天梯总榜每次抓取约 230 KB（24 小时节流，复用缓存）；单只天梯详情约 127 KB（gzip），按宝可梦缓存 24 小时，失败回退缓存/内置快照（`meta.online_error` 会给出失败原因）。

### meta 字段

所有返回值含 `meta` 字段：`origin`（snapshot/cache/online）、`date_range`（数据窗口）、`tournament_count` / `team_count`（样本量）。回答时必须引用 `date_range` 说明数据时效。天梯源额外含 `source_kind`（ingame/showdown）、`battle_format`（singles/doubles）、`format_note`（当前赛制提醒）；ingame 含 `rank_only: true`、`season`、`data_version`，showdown 含 `month`、`cutoff`、`raw_count`。

### 旧命令兼容

旧命令 `usage` 和 `teams` 仍可用，自动转发到 `meta` 并输出 deprecation 警告：

```bash
python scripts/query.py usage 仆刀将军        # 等价于 meta 仆刀将军
python scripts/query.py teams --pokemon 幽尾玄鱼  # 等价于 meta --teams --pokemon 幽尾玄鱼
```

### meta 示例

```bash
python scripts/query.py meta --top 10                        # 使用率前十
python scripts/query.py meta 仆刀将军                         # 单只宝可梦环境详情
python scripts/query.py meta --teams                          # 近期赛事队伍（前 12 支）
python scripts/query.py meta --teams 1                        # 全量列表第 1 支队伍完整配置
python scripts/query.py meta --teams --pokemon 幽尾玄鱼        # 全量检索：哪些队伍用了幽尾玄鱼
python scripts/query.py meta --teams --player Sooner          # 某选手的全部队伍
python scripts/query.py meta --teams --stats --placing-max 8  # 前八队伍的出现率排行
python scripts/query.py meta --teams --stats --pokemon 烈咬陆鲨  # 烈咬陆鲨的道具/特性/招式占比
python scripts/query.py meta --teams --teammates 炽焰咆哮虎     # 炽焰咆哮虎的常见队友
python scripts/query.py meta 仆刀将军 --online                # 强制拉取最新数据
python scripts/query.py meta --source ladder                  # 官方实机排位名次榜（双打，前 20）
python scripts/query.py meta --source ladder --format singles # 官方实机排位单打名次榜
python scripts/query.py meta --source ladder 仆刀将军 --online  # 仆刀将军官方天梯配招/道具/性格/努力
python scripts/query.py meta --source showdown                # Showdown 天梯使用率月报（滞后一个月）
python scripts/query.py meta --source showdown 仆刀将军 --online  # Showdown 月报口径的单只详情
```

### 双查模式（LLM 意图路由，非 CLI 参数）

用户问"怎么配招 / 谁最热门"且不指明来源时，默认**连发两条查询**，天梯为主、赛事为辅，回答分【官方天梯】【赛事】两节组织：

```bash
# "仆刀将军怎么配招？"
python scripts/query.py meta --source ladder 仆刀将军          # 天梯名次（--online 时含天梯配招）
python scripts/query.py meta 仆刀将军                          # 赛事使用率/胜率/配招

# "现在环境里谁最热门？"
python scripts/query.py meta --source ladder                   # 天梯名次榜
python scripts/query.py meta                                   # 赛事使用率榜
```

用户显式说"比赛/赛事"时只查 tournament，显式说"天梯/排位"时只查 ladder。离线双查时天梯侧只有名次（单只天梯配招需 `--online`）。

## filter-pokemon 命令说明

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

**示例**：

```bash
python scripts/query.py filter-pokemon --type 火 --type 龙 --min-stat speed 100
python scripts/query.py filter-pokemon --type 水 --max-stat hp 60 --ability 悠游自如
```

## survivability 命令说明

```bash
python scripts/query.py survivability <defender> <attacker_stat> <category> [def_ov] [field_ov]
```

反向查询：给定防御方和攻击方能力值，求防御方能稳定承受的最大无加成招式威力。

- `defender`：防御方宝可梦名（中/英）
- `attacker_stat`：攻击方攻击/特攻能力值（整数）
- `category`：`physical` 或 `special`
- `def_ov`：可选，防御方覆盖 JSON（同 calc 的 def_override）
- `field_ov`：可选，环境覆盖 JSON

**返回值**：
- `safe_bp`：防御方能稳定承受的最大基础威力（不触发要害）
- `absolute_safe_bp`：即使触发要害也能承受的最大基础威力
- `reference_damage`：临界威力下的伤害范围

**示例**：

```bash
python scripts/query.py survivability 烈咬陆鲨 200 physical
python scripts/query.py survivability 仆刀将军 180 special '{"evs":{"hp":252,"sp_defense":4}}'
python scripts/query.py survivability 炽焰咆哮虎 150 physical '{}' '{"weather":"sun"}'
```

## calc-raw 快速填空模板

```json
// attacker / defender
{
  "name": "宝可梦名",
  "level": 50,
  "raw_stats": {"hp": 175, "attack": 140, "defense": 90, "sp_attack": 60, "sp_defense": 100, "speed": 130},
  "ability": "特性名",
  "item": "道具名",
  "nature": "性格",
  "boosts": {"attack": 0},
  "is_terastalize": false,
  "tera_type": null
}

// move
{
  "name": "招式名",
  "is_crit": false,
  "hits": 1
}

// field
{
  "format": "Doubles",
  "weather": null,
  "terrain": null,
  "is_magic_room": false,
  "is_wonder_room": false,
  "is_gravity": false,
  "is_trick_room": false,
  "side_conditions": {}
}
```

## find-move 补充说明

```bash
python scripts/query.py find-move <招式名> [--source champions|gen9]
```

返回能学会该招式的所有宝可梦（含 `types` 字段）。`--source` 过滤数据来源：`champions` 仅返回 Champions 规则内的宝可梦，`gen9` 仅返回 Gen9 正作数据的宝可梦。

## 命令执行环境兼容性

Windows PowerShell 中直接运行：

```powershell
python scripts/query.py calc 喷火龙 热风 水箭龟
python scripts/query.py calc 喷火龙 热风 水箭龟 '{}' '{}' '{}' '{"weather":"sun"}'
```

命名参数方式（推荐，避免括号错位）：

```powershell
python scripts/query.py calc --attacker 喷火龙 --move 热风 --defender 水箭龟 --field-ov '{\"weather\":\"sun\"}'
```

能力点数（SP）模式：Champions 规则下，1 SP = +1 能力值（Lv.50），32 SP = 252 EV。在 override 中使用 `sps` 字段：

```json
{"sps": {"hp": 4, "attack": 32, "speed": 32}}
```
