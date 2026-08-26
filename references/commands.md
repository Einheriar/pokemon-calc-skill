# pokemon-calc 命令详细参考

> 本文件为 SKILL.md 的按需参考，不自动加载。当需要 `usage` / `teams` / `filter-pokemon` / `survivability` / `calc-raw` / `find-move` 的参数细节，或在 Windows 环境下执行命令时，先阅读本文件。

## usage 命令说明

```bash
python scripts/query.py usage [name] [--top N] [--online]
```

查询《宝可梦冠军》M-B 规则当前赛事环境的使用率统计（pokecamp.cc / Limitless 公开赛事数据，滚动 30 天窗口）。

- **不带名称**：返回使用率总排行，每条含 `rank`、`name_zh`、`usage_percent`、`win_rate`、`team_count`。
- **带名称**（中文/英文/别名均可）：返回单只宝可梦的环境详情——使用率排名、胜率、Top 12 常用招式、Top 8 特性、Top 8 道具、Top 8 性格、Top 8 能力点数（SP）分配推荐、Top 12 常见队友，均带百分比。
- **`--online`**：实时拉取 pokecamp 最新数据（单只查询只多下载该只的详情，约 23 KB）；结果缓存到 `data/cache/`；网络失败自动回退内置快照。
- **`meta` 字段**：`origin`（snapshot/cache/online）、`date_range`（数据窗口）、`tournament_count` / `team_count`（样本量）。回答时必须引用 `date_range` 说明数据时效。

### teams 命令说明

```bash
python scripts/query.py teams [query] [--top N] [--pokemon 名] [--player 名]
                          [--tournament 名] [--stats [--placing-max N]]
                          [--teammates 名] [--online]
```

查询赛事真实队伍（pokecamp.cc / Limitless 公开赛事数据）。当前窗口的**全量队伍**（约 9,000+ 支，含完整明细）已内置为 `data/teams_full.json.gz`，首次全量查询自动派生本地 SQLite 索引（一次性数秒，之后离线可用）。

- **不带参数**：按赛事日期降序列出前 12 支队伍（与 pokecamp 赛事队伍页首页一致），每条含赛事名、日期、选手、名次、战绩与 6 只宝可梦名称。
- **`teams <N>`**：全量列表按日期降序第 N 支的完整配置（每只宝可梦的道具、特性、4 个招式、性格，均为中英文双语）。
- **`teams --pokemon <名>`**（或位置参数直接写宝可梦名）：在全量队伍中检索使用该宝可梦的队伍，返回摘要列表（默认前 12 条，硬上限 50）。
- **`teams --player <名>` / `--tournament <名>`**：按选手名 / 赛事名（子串匹配）检索，可互相组合。
- **`teams --stats`**：全量队伍的出现率排行（默认前 20），可加 `--placing-max 8`（仅统计前八队伍）或 `--tournament <名>`（单赛事）做子集聚合。与 `usage` 的使用率同口径同数据集（已数值验证一致），此命令的价值在于子集统计与交叉验证。
- **`teams --stats --pokemon <名>`**：该宝可梦在全量队伍中的道具 / 特性 / 招式 / 性格占比（由队伍明细本地聚合）。
- **`teams --teammates <名>`**：该宝可梦的队友共现排行（默认前 12）。
- **`--online`**：增量更新（下载队伍列表 gzip 约 1.3 MB + 仅抓取新增赛事的明细），**仅在用户显式要求最新/当前热门队伍时使用**；失败回退缓存/内置数据且 `meta.online_error` 会给出失败原因，必须告知用户。
- 队伍详情不含能力点数分配；如需加点参考，用 `usage <宝可梦名>` 查看该宝可梦的 SP 分配推荐。

### usage / teams 示例

```bash
python scripts/query.py usage --top 10        # 使用率前十
python scripts/query.py usage 仆刀将军          # 单只宝可梦环境详情
python scripts/query.py teams                 # 近期赛事队伍（前 12 支）
python scripts/query.py teams 1               # 全量列表第 1 支队伍完整配置
python scripts/query.py teams --pokemon 幽尾玄鱼  # 全量检索：哪些队伍用了幽尾玄鱼
python scripts/query.py teams --player Sooner   # 某选手的全部队伍
python scripts/query.py teams --stats --placing-max 8  # 前八队伍的出现率排行
python scripts/query.py teams --stats --pokemon 烈咬陆鲨  # 烈咬陆鲨的道具/特性/招式占比
python scripts/query.py teams --teammates 炽焰咆哮虎     # 炽焰咆哮虎的常见队友
python scripts/query.py usage 仆刀将军 --online  # 强制拉取最新数据
```

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

- **用途**：给定防御方能力值（或宝可梦名称）和攻击方物攻/特攻能力值，反查**无攻击方加成**（无 STAB、道具、特性、天气/场地）下防御方能承受的最大招式基础威力。
- **输出字段**：`safe_bp`（KO 概率 < 15% 的最大威力）、`absolute_safe_bp`（KO 概率 = 0% 的最大威力）、`defender`（含最终能力值）、`defender_boosts`（最终生效的能力等级）。
- **输入方式**：传名称自动推导 Lv.50 默认能力值：`survivability 烈咬陆鲨 200 Physical`；直接传能力值：`def_ov '{"raw_stats":{"hp":185,"defense":85}}'`。`def_ov` 支持 `boosts` 和 `setup_moves`（见 SKILL.md setup_moves 说明），例：`survivability 水箭龟 200 Special --def_ov '{"setup_moves":["冥想"]}'`。
- **LLM 使用规则**：只引用引擎返回的 `safe_bp` 和 `absolute_safe_bp`，不做任何中间推导。引擎输出为属性相克倍率 1.0 的基准值。用户追问以下问题时，必须调用对应工具重算，禁止凭内部知识作答：

  | 用户追问 | 必须调用的工具 |
  |---------|--------------|
  | "X 属性招式打过去会怎样" | `type <atk> <def_types>` 查询倍率，再将结果除以对应倍率 |
  | "加上 STAB 后是多少" | `calc` 重新计算（不可手算 STAB） |
  | "如果带命玉/头带呢" | `calc` 重新计算（道具修正由引擎处理） |
  | "XX 宝可梦的防御能力值和这个一样吗" | `pokemon <name>` + `compute-stats` 查种族值 |

## calc-raw 快速填空模板

```bash
python scripts/query.py calc-raw \
  --att '{"name":"ATT_NAME","level":50,"stats":ATT_STATS,"types":ATT_TYPES,"ability":"ATT_ABILITY","nature":"ATT_NATURE","current_hp":ATT_HP,"max_hp":ATT_HP}' \
  --move '{"name":"MOVE_NAME","base_power":BP,"type":"MOVE_TYPE","category":"CATEGORY"}' \
  --def '{"name":"DEF_NAME","level":50,"stats":DEF_STATS,"types":DEF_TYPES,"ability":"DEF_ABILITY","nature":"DEF_NATURE","current_hp":DEF_HP,"max_hp":DEF_HP}' \
  --field '{"weather":"Sun"}'
```

字段精简原则：calc-raw 只读取传入的字段。至少传入 `name`, `level`, `stats`, `types`, `ability`, `nature`, `current_hp`, `max_hp` 即可。

**`is_spread` 自动补全**：若 `move_json` 省略了 `is_spread` 但提供了 `name` 或 `name_zh`，系统会自动从招式数据补全该值。若用户显式传入 `is_spread`，优先使用用户值。

## find-move 补充说明

> **`--source` 过滤说明**：`find-move` 默认返回全国图鉴（Gen9 + Champions）所有能学会该招式的宝可梦。传入 `--source champions` 仅返回 Champions M-B 规则可用宝可梦；传入 `--source gen9` 排除 Champions 专属宝可梦，仅保留 Gen9 正作数据。
>
> **`types` 字段**：`find-move` 返回的每个宝可梦条目均包含 `"types"` 数组，可直接用于属性筛选（如"找出能学会顺风的恶系宝可梦"），无需二次查询。

```bash
python scripts/query.py find-move 顺风 --source champions  # 仅 Champions M-B 规则
python scripts/query.py find-move 顺风 --source gen9       # 仅 Gen9 正作数据
```

## 命令执行环境兼容性

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

## 其他命令示例集

```bash
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
```
