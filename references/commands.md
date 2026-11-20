# pokemon-calc 命令详细参考

> 本文件为 SKILL.md 的按需参考，不自动加载。当需要 `speed` / `meta` / `filter-pokemon` / `survivability` / `calc-raw` / `find-move` 的参数细节，或在 Windows 环境下执行命令时，先阅读本文件。

## 多语言名称

```powershell
python scripts/query.py lookup 'Rock Slide' --locale fr
python scripts/query.py move Éboulement
python scripts/query.py lookup 'Flash Fire' --locale es-419
python scripts/query.py lookup Charge --input-locale fr --locale de
python scripts/query.py calc 'Méga-Dracaufeu X' Éboulement Florizarre --locale fr
```

宝可梦、形态、招式、特性和道具接受数据中已核实的简中、繁中、英、日、法、德、意、西及韩文名称。`es-ES` 和 `es-419` 的名称都可直接输入。遇到多个候选时按实体类型查询或确认名称。

有些名称在不同语言中拼写相同，例如法语 `Charge` 对应英文 `Tackle`，西班牙和拉美的 `Remolino` 分别对应 `Whirlwind` 和 `Whirlpool`。`lookup` 和 `calc` 可用 `--input-locale` 优先按输入名称的语言识别。混用多种输入语言时，可以先用 `lookup` 分别确认。`lookup --entity move` 等可把候选限定为指定类型。省略输入语言时沿用已有名称匹配顺序。

`lookup` 默认返回 `input`、`canonical_en`、`entity_type`。`--locale` 可用于 `lookup` 和 `calc`，按需返回游戏译名。首版新增地区标记为 `fr`、`de`、`it`、`es-ES`、`es-419`、`ko`。`es` 等同于 `es-ES`，输入名称可以与显示语言不同。`lookup` 的 `display_name` 和 `display_locale` 表示实际采用的译名和语言。`calc` 的 `localized_names` 在 `attacker`、`defender`、`move` 下提供 `name` 和 `locale`，攻守方还可返回实际形态、特性或道具。缺译名时读取可用的游戏名称，按实际语言标记回退。

输出中的规则、威力、命中、伤害和补丁日期应读取对应的结构化字段。`--locale` 请求显示名称，响应的 JSON 键与说明正文继续沿用原有格式。

## Champions 平衡补丁版本

```powershell
python scripts/query.py --patch baseline move 岩崩
python scripts/query.py calc 烈焰猴 火焰拳 巨钳螳螂 --patch 2026-12-02
python scripts/query.py find-move 嬉闹 --patch 2026-12-02
```

`--patch` 可放在命令前或后。省略时，默认选择随 Skill 发布的最高日期补丁 ID，按打包版本决定，不读取当前日期或联网检查。`baseline` 表示补丁前的 Champions 基线，`2026-12-02` 固定使用「2026-12-2宝可梦冠军平衡性补丁」。补丁只用于 Champions 数据，Gen9 正作记录不套用。

被补丁实际影响的查询或计算结果会在对应实体信息上带 `balance_patch`，其中包含最近贡献补丁的 ID、名称、生效日和官方来源；`balance_changes` 逐项列出修改字段和值，并标明来源补丁。计算时，招式改动位于 `move_info`，显式启用的火力提升位于对应一方的 `attacker_info` / `defender_info`。新增学招在 `learnset` 中通过 `added_moves` 标明，在 `find-move` 命中项通过 `added_to_forms` 标明。没有受补丁影响的实体不显示补丁标记。查询使用的补丁版本应与计算使用的版本一致，回答时引用脚本返回的补丁来源。

本补丁把招式命中率作为更新后的字段返回，但 `calc` 不把命中概率折进伤害范围或 KO 概率。畏缩概率不参与伤害模拟。引火的 Mega 继承效果通过计算态 `fire_boost` 表达，应由用户输入是否已触发；仅指定特性名不会推断触发状态。`calc-raw` 接收用户提供的招式参数，不读取补丁招式数值；其 `fire_boost` 状态仍会校验是否有支持的补丁。坚毅的查询结果会说明替身穿透，但伤害引擎不模拟替身承伤。

## speed 速度计算器

```powershell
python scripts/query.py speed 超级雷电兽 --pokemon_ov '{"nature":"内敛","sps":{"speed":32}}'
python scripts/query.py speed --value 187 --range 10
python scripts/query.py speed 187 --range 0
python scripts/query.py speed 龙头地鼠 --pokemon_ov '{"nature":"爽朗","sps":{"speed":32},"ability":"拨沙"}' --field_ov '{"weather":"Sand"}'
python scripts/query.py speed 超级雷电兽 --pokemon_ov '{"nature":"内敛","sps":{"speed":32}}' --field_ov '{"is_tailwind":true}' --range 5
```

- 名称模式：固定 50 级，默认全部 0 投入、31 IV、勤奋性格，不使用自动或显式预设。`--pokemon_ov` 支持 `form_name`、`nature`、`evs`、`sps`、`ivs`、`boosts`、`item`、`ability`、`ability_on`、`status`。SP／EV 的相同能力项以 SP 为准。其他能力项的投入也可传入，以准确判断古代活性／夸克充能的最高项。
- 常规速度回答省略等级。[满速] 用 32 速度 SP 和不修正速度的性格，[极速] 用 32 速度 SP 和加速性格。性格、投入及个体值以用户明确指定的配置为准。
- `--field_ov` 为已有 Field 参数，天气／场地的英文枚举不区分大小写，例如 `Sun`、`Rain`、`Sand`、`Electric`。能力等级用 `boosts.speed`；碎裂铠甲触发一次要显式传 `2`。轻装已触发要传 `ability:"轻装"`、`ability_on:true`，并保持当前无道具。天气特性不自动设置天气。
- 已有数值模式：`--value N` 或纯数字位置参数表示**最终实战速度**，允许 0～10000 的整数；不能同时指定宝可梦或非空配置／环境覆盖。数值不再应用围巾或天气修正。
- `--range N` 为非负整数，默认 5。对最终实战速度 S 查闭区间 `[max(0,S-N), min(10000,S+N)]`；0 仅同速，空窗口不扩展。不按档位数筛选，不隐式截断窗口内条目。
- 文件覆盖：`--pokemon_ov_file`、`--field_ov_file`，UTF-8 JSON 文件优先于对应行内参数。文件缺失、非法 JSON、未知形态／枚举／字段均明确报错。
- 顺风通过 `--field_ov '{"is_tailwind":true}'` 指定，必须为 JSON 布尔值，默认 false。此字段是速度计算器专用的目标一侧状态，不施加给其他宝可梦，也不扩展伤害命令的 Field 字段。顺风加入共享实际速度模块的倍率链，在最终取整和麻痹处理之前结算；计算后仍按最终 `effective_speed` 自动查 ±N 范围。关闭或不传时保持原结果，不批量修改 574 条参照的速度或条件。
- 不模拟顺风回合倒计时、戏法空间或对手配置引起的场上状态变化。戏法空间不会在本命令中改变数值或参照关系；其他未支持字段仍拒绝。

返回 `panel_speed`、`staged_speed`、`effective_speed`，以及配置摘要和 `references`。`references.matches` 只含窗口内配置，每项有 `speed`、`name`、`profile`、`condition`、`delta` 和 `relation`。**delta = 参照速度 − 用户实战速度**；正数参照更快、负数参照更慢，0 同速。这是速度数值比较，不推断先制招式等实际行动顺序。

精选参照为 M-C 规则下用户于 2026-11-19 确定的 574 条配置。按每项原有条件展示天气、围巾和特性，名单只用于速度比较。窗口为空时说明无命中。参照文件缺失或损坏时说明查询错误，并保留已算出的速度。

数据由脚本从 `data/speed_tiers.json` 读取，LLM 不读取整表。Windows 引号受 shell 影响时优先使用覆盖文件。

## meta 命令说明

```bash
python scripts/query.py meta [target] [--top N] [--online] [--source tournament|ladder|ingame|showdown]
                           [--format singles|doubles]
                           [--usage] [--teams] [--pokemon 名] [--player 名]
                           [--tournament 名] [--stats [--placing-max N]] [--teammates 名]
```

统一的环境情报查询入口。默认源（tournament）来自 pokecamp.cc 聚合的 Limitless 公开赛事统计。当前内置快照为 M-C、2026-10-16 至 2026-11-16；`--online` 的滚动窗口和日期可能变化。`--source ladder` / `showdown` 接入各自的天梯数据（见下文「--source 参数」）。

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
- **`--online`**：请求在线使用率数据并写入本地缓存。排名刷新失败时，依次回退到完整蒸馏后的在线使用率缓存和捆绑快照；原始 `index` / `teams_page` 缓存不会被拼接成一条看似新鲜的完整结果。
- **单只详情来源**：在线排名查询成功后，单只详情会单独请求并缓存。响应中的 `meta.origin` / `date_range` / `format` 描述排名数据；`meta.detail_origin` / `detail_fetched_at` / `detail_date_range` / `detail_format` 描述单只详情。在线详情失败时会使用该宝可梦已有的完整详情缓存（`detail_origin: "cache"`）或保留排名结果并报告 `detail_origin: "unavailable"` 与 `detail_online_error`。两部分来源和日期可能不同，应按字段分别说明。

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

当前内置的**全量队伍**（6,469 支；135 场赛事元数据中，134 场包含队伍数据，这 134 场的队伍详情齐全，缺失详情数为 0）已打包在 `data/teams_full.json.gz`，另有前 12 支轻量快照 `data/meta_teams.json`。首次全量查询自动派生本地 SQLite 索引（之后可离线查询）。

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
python scripts/query.py meta --source showdown     # Showdown 天梯月报（含使用率，月份见 meta.month）
python scripts/query.py meta --source showdown --online  # 在线请求 Showdown 来源的月报
```

| 源 | 性质 | 时效 | 使用率 | 单只详情 | 队伍查询 |
|---|---|---|---|---|---|
| `tournament`（默认） | Limitless 公开赛事统计 | 内置 M-C 快照：2026-10-16 至 2026-11-16（312 条使用率，135 场赛事，134 场含队伍详情，6,469 支队伍）；在线数据按滚动窗口返回 | ✅ 含胜率 | ✅（`--online` 可请求单只详情） | ✅ |
| `ladder` / `ingame` | Pokémon Champions 官方实机排位 | 内置 M-C 快照截至 2026-11-16，data version `20261116083343008` | ❌ **仅名次**（`rank_only: true`；262 条；仅 `isMega=true` 且 `linkId` 明确指向对应非 Mega 形态的行合并，其他非 Mega 形态独立保留） | ✅ 配招/道具/特性/性格/努力为真实百分比（**需 `--online`**），队友仅名次 | ❌ |
| `showdown` | Showdown 天梯月报（cutoff 1760） | M-C、`meta.month=2026-10`，`meta.raw_count=1,649,648` 个原始样本计数，蒸馏为 289 条宝可梦记录 | ✅ 无胜率 | ✅（**需 `--online`**） | ❌ |

- 天梯源用 `--format singles|doubles` 切换单打/双打排行（默认 `doubles`，输出 `meta.format_note` 会注明当前赛制与切换方法）；对 tournament 源无效（limitless 仅双打）。
- 天梯的在线请求按来源使用对应的规则与路由：`ingame` 读取官方实机排位源，`showdown` 读取 Showdown 月报源。两者的规则版本可能不同，以返回的 `meta.source_kind`、`meta.regulation` 和 Showdown 的 `meta.month` 为准；不要把一个来源的规则套到另一个来源。
- 天梯总榜为纯名次/使用率表；ingame 仅当来源行 `isMega=true` 且 `linkId` 明确关联到相应非 Mega 形态时才合并（行内 `includes_mega: true` 标注），其他非 Mega 形态包括雌雄和地区形态均独立保留；showdown 的 Mega 形态为 Smogon 独立统计口径、保持分行。
- 官方天梯离线快照仅含名次，单只配招与 SP 分配详情需 `--online`；报表中的“未获取”表示详情尚未拉取，属于预期状态，并非脚本故障。
- 天梯源与 `--teams`/`--stats`/`--teammates`/`--player`/`--tournament` 组合会返回友好错误（天梯没有赛事队伍概念）。
- `--online`：ingame 与 showdown 的天梯总榜分别缓存，约 230 KB，按 24 小时窗口复用/刷新；单只详情约 127 KB（gzip），使用共享的 `ladder_detail_<id>.json` 原始详情缓存，缓存项保留 source 与 regulation 信息，按 24 小时窗口复用/刷新。失败时回退缓存/内置快照（`meta.online_error` 会给出失败原因）。

### meta 字段

所有返回值含 `meta` 字段：`origin`（snapshot/cache/online）、`date_range`（数据窗口）、`tournament_count` / `team_count`（适用时的赛事样本量）。使用率单只详情响应还可能包含 `detail_origin`、`detail_fetched_at`、`detail_date_range`、`detail_format`、`detail_online_error`；它们描述单只细节，与总体排名的 `origin`、`date_range`、`format` 分开。回答时按所引用的数据字段说明相应来源和日期。天梯源额外含 `source_kind`（ingame/showdown）、`regulation`、`battle_format`（singles/doubles）、`format_note`；ingame 含 `rank_only: true`、`season`、`data_version`，showdown 含 `month`、`cutoff`、`raw_count`。

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
python scripts/query.py meta --source showdown                # 捆绑 Showdown 月报（2026-10；月份见 meta.month）
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
python scripts/query.py survivability <defender> [attacker_stat] <category> [--def_ov JSON] [--field_ov JSON]
```

中性承伤反查：给定防御方和攻击方能力值，求满足安全阈值的最大招式威力。未指定攻方能力值时默认 **200**，用户指定的值优先。默认双方 50 级、防御方满血、属性倍率固定 1×、无本系、非要害、单次单发、双打单体，无自身特性、道具、天气、场地、墙和辅助加成。保留真实防御方属性，以便用户显式指定沙暴、雪天等条件时正确应用防御修正。

- `defender`：防御方宝可梦名（支持名称解析层的多语言/别名），或含 `raw_stats` / `stats` 的 JSON 对象。
- `attacker_stat`：可省略，攻击方攻击/特攻能力值，必须为正整数，默认 200。
- `category`：必填，`Physical` 或 `Special`，不区分大小写。不明确物理/特殊端时分别查询两端。
- `--def_ov`：防御方覆盖 JSON，仅支持 `evs` / `sps` / `ivs` / `nature` / `raw_stats` / `stats` / `boosts` / `setup_moves` / `current_hp` / `max_hp` / `level`。不传时 0 EV、31 IV、性格不修正耐久、满血、不套预设；`level` 只能为 50。按名称查询时，部分最终能力值覆盖叠加在已计算的默认或用户配置上，未指定能力项保留计算值；`raw_stats` 与 `stats` 不可同时提供。JSON 防御方须给出 HP 和当前端防御的最终能力值，不再接受 EV/SP/IV/性格配置。自身特性、道具等不支持字段会报错，需要此类具体对战条件请使用 `calc`。
- `--field_ov`：环境覆盖 JSON，支持 `format` / `weather` / `terrain` / `is_gravity` / `is_reflect` / `is_light_screen` / `is_aurora_veil` / `is_friend_guard` / `is_helping_hand` / `is_battery` / `is_power_spot` / `is_flower_gift_atk` / `is_flower_gift_spd` / `is_sword_of_ruin` / `is_beads_of_ruin` / `is_tablets_of_ruin` / `is_vessel_of_ruin`。枚举不区分大小写，开关须为布尔值。钉刺、回合末伤害等不属于单发直伤反查，不接受对应字段。
- `--def_ov_file` / `--field_ov_file`：从 UTF-8 文件读取 JSON，优先于对应内联参数；无法读取时直接报错，不回退默认条件。
- `setup_moves` 支持可解析的、含结构化效果的招式名（如冥想）；与手动 `boosts` / 天气 / 场地二选一。未知或未支持效果的招式、非法 JSON、错误字段及不合法数值会明确报错。

**返回值**：
- `safe_bp`：一击击倒概率严格小于 15% 的最大基础威力（非要害）
- `absolute_safe_bp`：一击击倒概率为零的最大基础威力（非要害，**不保证承受要害**）
- `safe_damage_range`：临界威力（safe_bp）下的伤害范围
- `absolute_safe_damage_range`：绝对安全威力下的伤害范围
- `defender_boosts`：实际应用的防御方强化（回显）
- `attacker_boosts` / `setup_moves`：强化招式引起的攻方变化与实际执行的规范招式名。
- `defender`：HP、最大 HP、原始防御/特防、强化后防御/特防及 EV/SP/IV/性格回显。
- `baseline` / `field_info`：固定中性计算口径与实际生效的环境条件。
- `safe_ko_probability` / `absolute_safe_ko_probability`：对应临界威力的一击击倒概率（0～1）。若无任何正威力满足条件，对应威力为 0、伤害范围为 `[0,0]`、概率为 `null`；该范围是占位值，不表示免疫。
- `search_max_bp`：本次搜索的最大基础威力，目前为 500。
- `safe_bp_capped` / `absolute_safe_bp_capped`：对应安全线在搜索上限仍满足条件，尚未验证更高威力。为 true 时回答「至少能承受 500 威力，真实上限未确定」，不能称 500 为最大值。

> V5.0.3：修正旧版固定一般属性导致钢/岩石抗性和幽灵免疫污染反查的问题；补全默认 200、配置生效、输入校验与触顶标记。

**示例**：

```bash
python scripts/query.py survivability 超级巨金怪 special
python scripts/query.py survivability 烈咬陆鲨 200 physical
python scripts/query.py survivability 仆刀将军 180 special --def_ov '{"evs":{"hp":252,"sp_defense":4}}'
python scripts/query.py survivability 炽焰咆哮虎 150 physical --field_ov '{"weather":"Sun"}'
```

Windows 如遇命令行 JSON 引号问题，使用 `--def_ov_file` / `--field_ov_file`。

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
python scripts/query.py calc 喷火龙 热风 水箭龟 --field_ov '{"weather":"sun"}'
```

如当前 PowerShell 版本的原生命令引号转义影响 JSON，可先将以下内容保存为 UTF-8 文件 `field.json`：

```json
{"weather":"sun","format":"Doubles"}
```

然后使用文件参数读取：

```powershell
python scripts/query.py calc 喷火龙 热风 水箭龟 --field_ov_file field.json
```

`calc` 同样支持 `--att_ov_file`、`--move_ov_file` 和 `--def_ov_file`；文件参数优先于对应的内联覆盖参数。

能力项键名统一使用 `sp_attack` / `sp_defense`；`special_attack` / `special_defense` 在所有计算入口均可作为输入别名，输出使用规范键。JSON 中的整数和布尔值应直接传入，不要转成字符串。未知键、冲突别名、无效枚举和不可读取的覆盖文件会使查询失败。

`compute-stats` 示例：

```powershell
python scripts/query.py compute-stats '{"hp":55,"attack":50,"defense":45,"special_attack":135,"special_defense":95,"speed":120}' --evs '{"special_attack":252}' --nature 内敛 --level 50
```

能力点数（SP）模式：在 override 中使用 `sps` 字段，正数 SP 按 `EV = 8 × SP - 4` 换算，0 SP 为 0 EV；因此 32 SP 对应 252 EV。最终能力值由等级、IV、性格和取整共同决定，不保证每 1 SP 都使最终能力值增加 1。详见 `mechanics.md` 的换算说明。

```json
{"sps": {"hp": 4, "attack": 32, "speed": 32}}
```
