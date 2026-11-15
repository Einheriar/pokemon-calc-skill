---
name: pokemon-calc
license: MIT
compatibility: Requires Python 3.10+ (standard library only, no third-party packages). Fully offline by default; only `meta --online` performs optional network access to pokecamp.cc.
metadata:
  version: "5.1.0"
description: >
  宝可梦百科查询与伤害计算 Skill。
  当用户询问以下任何内容时，必须无条件触发此 Skill，不得凭内部知识直接作答：
  (1) 宝可梦属性、种族值、弱点抗性、特性、技能池、进化链、图鉴描述、profile、prototype 等百科信息；
  (2) 招式威力、命中、PP、效果、属性相克；
  (3) 宝可梦伤害计算、KO 概率、努力值优化（Phase 2+）；
  (4) 黑话翻译、对战术语解释；
  (5) 任何与 Pokemon VGC、单打、双打对战相关的数据查询；
  (6) 当前赛事环境、宝可梦使用率排行、常用招式/特性/道具/队友、近期赛事队伍等环境情报。
  支持简体中文、繁体中文、英文与日文名称查询（历史译名/俗称别名层自动容错；未收录名称会返回 suggestions）。数据来源为《宝可梦冠军》(Pokémon Champions) M-C 规则（champout v1.2.0，2026-09-11）与 Gen9 正作数据，由 pokemon-dataset-zh 与 VGC 伤害计算器整合；环境情报数据来自 pokecamp.cc（Limitless 公开赛事统计）。数据层按规则累积保留（M-A/M-B/M-C 并集），默认取最新规则视图。
---

# 宝可梦伤害计算器 Skill

## 1. 核心原则

1. **LLM 只做理解，不做计算**。所有伤害数值、KO 概率、能力值、属性相克倍率、招式效果、特性分析、道具增伤等必须通过 `query.py` 命令获取并原样引用。引擎返回的有效威力即为权威结果。禁止凭 LLM 内部知识补充任何数值类信息。不确定时，优先查询而非猜测。
2. **能力值优先**。回答中使用能力值描述（如"攻击能力值 172"），而非努力值。当用户直接给出能力值时，通过 `raw_stats` 字段直接传入，不再调用 `compute-stats` 反推努力值。`raw_stats` 为最终能力值（含性格修正），`stats` 为 `raw_stats` 经 `boosts` 修正后的值。无能力等级变化时两者传相同值即可。
3. **环境参数唯一入口**。环境条件（天气、场地、对战模式等）一律经 `field_override` 传入。`move_override` 仅用于行为参数（`is_crit`、`hits`、`fainted_allies`、`times_affected`），不修改 `base_power` 或 `type`——引擎已强制校验（白名单之外的字段被忽略并在响应 `warning` 中列出，`hits` 夹紧 1-10）。原始参数输入请用 `calc-raw`。
4. **中文优先**。数据以中文名为主索引，同时支持英文名称。
5. **零外部依赖**。核心数据已静态化为 JSON，查询脚本仅使用 Python 标准库。环境查询命令（`meta`）默认读取内置快照（离线可用）；仅当用户显式要求最新数据时才加 `--online` 按需联网（pokecamp.cc，仅用标准库 `urllib`），网络失败自动回退快照，并在回答中注明数据来源与日期。

## 2. 命令速查

所有查询通过执行 bundled script [`scripts/query.py`](scripts/query.py) 完成。

> **并发与状态**：查询之间相互独立、无共享状态（每次调用为独立进程，数据不跨调用残留）——互不依赖的多个查询可并行发起；单次查询通常 1 秒内返回。

> **路径解析说明**：脚本通过 `__file__` 动态定位自身目录，并自动查找同级目录下的 `data/` 文件夹。若 Skill 被安装到其他位置，可通过设置环境变量 `POKEMON_CALC_DATA_DIR` 显式指定数据目录。

> **参考文件使用规则**：本文件只含高频刚需内容。以下情况**先 Read 对应参考文件再执行**：
> - 使用 `meta` / `filter-pokemon` / `survivability` / `calc-raw` / `find-move --source`，或需要更多命令示例、Windows 环境执行方式 → [`references/commands.md`](references/commands.md)
> - 需要 SP/EV 换算公式与对照表、optimize 双模式返回字段、数据来源完整说明 → [`references/mechanics.md`](references/mechanics.md)

```bash
# Phase 0 — 名称解析（不确定规范英文名时先用它）
lookup <name>         # 多语名 → 规范英文标识符（宝可梦/招式/特性/道具），返回 {input, canonical_en, entity_type}
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
filter-pokemon [--type <type> ...] [--min-stat <stat> <n>] [--max-stat <stat> <n>] [--ability <ability> ...]
                        # 宝可梦筛选：按属性（AND）、种族值范围、特性（OR）过滤。详见 references/commands.md
preset <pokemon> [name] # 列出预设配置或获取具体配置

# Phase 2 — 伤害计算与优化
calc <att> <move> <def> [att_ov] [move_ov] [def_ov] [field_ov]       # 快捷伤害计算（Lv.50）
calc-raw <att_json> <move_json> <def_json> [field_json]              # 纯参数计算（模板见 references/commands.md）
compute-stats <base_stats> --evs <evs> --ivs <ivs> --nature <nature> --level <level>  # 种族值+配置 → 能力值
optimize <att> <move> <def> [goal] [target] [threshold] [att_ov] [def_ov] [field_ov]  # 努力值优化
survivability <defender> [attacker_stat] <category> [--def_ov JSON] [--field_ov JSON]  # 中性承伤威力反查；攻方能力值默认 200

# Phase 3 — 环境情报查询（pokecamp.cc 赛事 + 天梯数据，详见 references/commands.md）
# 意图路由速记：用户说"天梯/排位"→ 只查 --source ladder；说"比赛/赛事"→ 只查默认源；
#              不指明来源 → 天梯+赛事双查，天梯为主（完整规则见下方「意图路由」）
meta [--top N] [--online]                    # 当前环境使用率总排行（默认前 20）
meta <name> [--online]                       # 单只宝可梦赛事统计：使用率排名、常用招式/特性/道具/性格/能力点数分配/常见队友（默认源=赛事，勿用于回答天梯问题）
meta --teams [--top N] [--online]            # 近期赛事队伍列表（默认前 12 支，按赛事日期降序）
meta --teams <N>                             # 第 N 支队伍的完整配置（道具/特性/招式/性格）
meta --teams --pokemon <名> [--top N]        # 全量检索：当前窗口哪些队伍用了这只宝可梦
meta --teams --player <名>                   # 按选手名检索其全部队伍
meta --teams --tournament <名>               # 按赛事名检索（可与 --pokemon 组合）
meta --teams --stats [--placing-max N] [--tournament <名>]  # 全量队伍出现率排行（前 20；可加子集条件）
meta --teams --stats --pokemon <名>          # 该宝可梦在全量队伍中的道具/特性/招式/性格占比
meta --teams --teammates <名>                # 该宝可梦在全量队伍中的队友共现排行（前 12）
meta --source ladder [--format singles|doubles] [--top N] [--online]   # 官方实机排位名次（日更；仅有名次，无使用率/胜率）
meta --source ladder <name> [--format ...] --online                    # 该宝可梦官方天梯配招/道具/特性/性格/努力（真实百分比，需 --online）
meta --source showdown [--format ...]        # Showdown 天梯月报（含使用率，滞后一个月）
meta --source <tournament|ladder|ingame|showdown>  # 数据源：tournament=赛事（默认），ladder/ingame=官方排位，showdown=Showdown 天梯
```

> **数据性质说明**：`meta` 默认源（tournament）来自 pokecamp.cc 聚合的 Limitless 公开赛事统计（滚动 30 天窗口），属于**赛事数据**。内置快照为 M-B 窗口（2026-08-26 抓取，`meta.format` 如实标注），与全局 M-C 规则声明存在滞后；需要最新窗口时加 `--online`。`--source ladder`（等价 `ingame`）为 Pokémon Champions **官方实机排位**数据（最新赛制，约 1~3 天更新）：总榜**只有名次**（`rank_only: true`，官方不公布使用率/胜率），单只详情的配招/道具/特性/性格/努力分配为真实百分比（需 `--online`）；`--source showdown` 为 Showdown 天梯月报（含使用率，`meta.month` 注明月份，滞后一个月）。天梯源用 `--format singles|doubles` 切换单/双打（默认双打，输出 `meta.format_note` 会注明），不支持 `--teams` 等队伍查询。全量队伍数据（当前窗口全部 9,000+ 支队伍，含每队 6 只宝可梦的道具/特性/招式/性格明细）已作为压缩包**内置发布**（`data/teams_full.json.gz`），首次执行全量查询时自动派生本地 SQLite 索引（一次性，数秒，之后离线可用）；所有查询输出硬上限 50 条，原始数据与索引永不进入上下文。回答中注明数据窗口（`meta.date_range`）与来源（`meta.origin`：snapshot=内置数据，cache=此前在线拉取的缓存，online=本次实时拉取）。
>
> **智能推断规则**：`meta` 不带任何标志时，按位置参数自动推断——纯数字 → 队伍详情（天梯源下为"第 N 名是谁"的名次反查）；宝可梦名 → 单只使用率详情；空 → 使用率排行。带 `--teams` 强制走队伍查询，带 `--usage` 强制走使用率查询。旧命令 `usage` / `teams` 仍可用（自动转发到 `meta`，输出 deprecation 警告）。
>
> **意图路由（默认双查，天梯为主、赛事为辅）**：用户问环境类问题且不指明来源时，**默认同时发两条查询**——天梯（`--source ladder`）为主、赛事（默认源）为辅，回答按【官方天梯】【赛事】分门别类组织：
> - "某宝可梦怎么配招 / 带什么道具" → `meta --source ladder <名>` + `meta <名>`（用户要求最新时各加 `--online`）
> - "环境里谁最热门 / 现在谁最强 / 大家都用什么" → `meta --source ladder` + `meta`
> - "天梯/排位第 N 名是谁" → `meta --source ladder <N>`（名次反查）
> - 用户**显式**说"比赛/赛事" → 只查 tournament（`meta` / `meta --teams` 系列）；显式说"天梯/排位" → 只查 ladder
> - 需要天梯的**使用率数字**时改用 `--source showdown`（ladder 总榜只有名次），并注明 `meta.month` 滞后一个月
> - 离线双查时天梯侧只有名次（单只天梯配招需 `--online`），话术注明"天梯配招需在线查询"；赛事侧配招离线齐全
>
> **`--online` 使用规则**：只有当用户**显式要求**"最新/当前/热门队伍/实时"等时效性数据时才允许加 `--online`，其他情况一律使用内置数据。`meta --teams --online` 为增量更新（队伍列表 gzip 约 1.3 MB + 仅抓取新增赛事的明细），且有 24 小时节流——距上次成功拉取不足 24 小时时直接复用现有索引、不发起网络请求（返回 `meta.note` 会注明），但仍不得主动触发。若在线拉取失败，返回值 `meta.online_error` 含有失败原因，**必须在回答中原样告知用户失败原因**，并说明已回退到内置/缓存数据及其日期。

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

// move_override — 仅限行为参数，不改 base_power / type（引擎已强制校验，非法字段进 warning）
{"is_crit": false, "hits": 1, "fainted_allies": 0, "times_affected": 0}

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

- `setup_moves` 是 `att_override` 的字段，接收变化类招式名称数组（如 `["诡计", "求雨"]`）。引擎自动解析并应用招式效果（能力等级变化、天气/场地设置等），重复强化后能力等级始终夹紧在 −6～+6。
- 未知招式名会出现在响应 `warning` 中；已识别但没有结构化效果的变化招式按未建模机制跳过。`setup_moves` 不是数组或元素不是字符串时返回错误。
- `calc` / `calc-raw` / `optimize` 的 JSON 参数必须合法且顶层为对象；解析失败会返回 `error`，不会静默套用默认配置。
- `is_terastalize` 必须为 JSON 布尔值；开启时必须同时给出有效 `tera_type`。太晶属性支持中文、繁体、英文大小写及“星愿”兼容别名，未知类型返回 `error`，不要用字符串 `"false"` 表示关闭。
- `setup_moves` 与手动的 `boosts`/`weather`/`terrain` 二选一，不要同时传入，避免冲突。

**field_override 取值**：
- `weather`: Sun / Rain / Sand / Hail / Snow / Strong Winds / Harsh Sun / Heavy Rain
- `terrain`: Electric / Grassy / Misty / Psychic
- `format`: Singles / Doubles
- 墙壁/辅助特性/灾祸系列等：布尔开关，见 `field_override` JSON 示例

### 命令示例

```bash
# 基础查询（仅需位置参数）
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟

# 命名参数方式（推荐，避免括号错位）
python scripts/query.py calc 超级喷火龙Y 热风 超级胡地 \
  --att_ov '{"evs":{"sp_attack":252}}' \
  --field_ov '{"weather":"Sun","format":"Doubles"}'
```

> 更多示例（天气/场地联动、optimize、find-move --source、filter-pokemon、usage/teams、Windows 临时脚本）见 [`references/commands.md`](references/commands.md)。

### 天气/场地/队友阵亡联动招式（引擎自动处理）

以下招式的威力/属性会随天气/场地/阵亡数自动变化。**LLM 只需在 `field_override` / `move_override` 中传入对应参数，威力变化由引擎自动计算，回答中不写中间计算式。**

- 天气联动：气象球（需确认 weather；攻击方持万能伞只在晴天／雨天下保持一般属性与原威力，沙暴／冰雹／雪天仍正常变化）；场地联动：大地波动、电气上升、精神强念、薄雾爆炸（需确认 terrain；大地波动威力翻倍还要求攻击方接地）；重力联动：重力苹果。**以上为常见示例，非穷举**——引擎 `base_power_func` 覆盖更多动态威力招式（陀螺球、重磅冲撞、喷火、辅助力量、祸不单行、杂技、愤怒之拳、水蒸气等），直接 `calc` 即可。万能伞的攻防区别、水蒸气四组合及特性例外见 `references/mechanics.md`。
- 扫墓 / Last Respects：每有 1 名队友阵亡威力 +50，通过 `move_override` 传入阵亡数，如 `--move_ov '{"fainted_allies": 1}'` → 威力 100
- 愤怒之拳 / Rage Fist：每被击中 1 次威力 +50，通过 `move_override` 传入 `--move_ov '{"times_affected": 2}'`

### calc 返回值关键字段

- `damage_range` / `damage_rolls` 为**单次打击**（多段招式）；`total_damage_range` / `total_damage_rolls` 为**多段合计**，判断秒杀时引用后者
- 黑夜魔影、地球上投、蛮干、愤怒门牙、一击必杀等固定伤害招式返回单一确定结果：先检查属性/特性/道具免疫，再按等级、固定数值或当前 HP 计算，不套用普通威力、攻击、防御、烧伤或墙壁公式
- 愤怒门牙／自然之怒／大灾难按目标当前 HP 的一半向下取整；未免疫且目标仍存活时至少造成 1 点伤害。
- 半血招式的 KO 预测逐次按剩余 HP 重算。回复与持续伤害顺序未建模的组合会明确提示无法可靠计算；蛮干／搏命未模拟重复使用的状态变化。`optimize` 对这些招式的多次使用目标返回 `unsupported: true`，不要据此给出确定的两击／三击方案。
- `ko_chance` 按各乱数分支独立维护 HP 与树果状态，先判击倒再触发树果，并在多击之间应用回合末恢复／伤害；魔法防守免疫隐形岩和撒菱伤害，钉刺与青草场地回复使用统一接地判定
- 非星晶太晶后的接地、场地效果与天气防御／持续伤害使用太晶属性，星晶保留原属性。钉子默认按本回合太晶前的入场状态结算；原属性仍保留用于 STAB，不要把太晶后的属性覆盖回原属性字段。
- 太晶化后的太晶爆发固定采用太晶属性，不再受妖精皮肤、飞行皮肤、一般皮肤等属性转换或对应威力加成影响；未太晶时按普通招式处理。
- 太晶甲壳先保留完整属性免疫／抗性，仅将满足条件的满血中立或效果拔群攻击降为效果不佳；破格等忽略特性时不触发甲壳。
- 符合条件的太晶同属性招式在威力修正后有 60 威力下限；先制、原生多段与指定的 HP 动态威力招式豁免。星晶仅在该属性增幅尚未消耗时应用，下限由引擎判断，不手动改招式威力。
- 星晶用 `stellar_boosted_types` 数组表示已消耗增幅的属性，默认空数组；星晶太晶爆发命中后双攻降一级。`next_state` 返回后续强化、增幅消耗、一次性效果标记和道具状态，天气／场地在其 `field_override` 中；这不是随机伤害后的 HP。连续攻击 KO 与优化由引擎逐击重算，复杂多段或回合末组合无法可靠建模时明确提示限制。
- 星晶太晶爆发的自降会应用有效特性的唱反调／单纯规则，并夹紧至 −6～+6；本次伤害使用的强化与命中后 `next_state` 分开读取。
- 厄诡椪的水井／火灶／础石面具在对应形态对所有伤害招式增伤，不只增强面具属性；持有的面具不可被拍落。碧草面具形态没有额外的持有道具。
- 太乐巴戈斯星晶太晶输入自动采用星晶形态的种族值与默认特性；厄诡椪保留面具形态身份，太晶后默认采用面影辉映。显式特性、能力值、HP 和道具覆盖优先，仍允许理论组合。
- 英文 Mega 形态名称及常见连字符别名会按具体形态解析，包含截至 M-C 的 Z Mega；明确请求的 Mega 不可见或不存在时返回未找到，不能回落普通形态。
- `tera_effects_applied` 默认 `false`：归零化境在太晶触发时清除天气／场地，面影辉映按形态强化一次。已发动后再出现的天气／场地、或已包含强化的快照须传 `true`。晶光星群、棘藤棒和觉醒之舞的动态属性、分类及扩散信息直接读 `move_info`。
- 化学变化气体通过统一有效特性判定影响伤害和 KO，保留不可压制特性与特性护具例外；计算快照仍保存原配置特性，方便续算与解释。
- 紧张感／人马一体会阻止对方抗性树果及回复树果，阻止时不减伤、不回复也不消耗；气体和护具通过有效特性判定影响该规则。
- 普通亲子爱与回复树果的 KO 按分击顺序结算，先判倒下再回复；子击倍率在基础伤害阶段应用。缺少分击数据或涉及尚未建模的 HP 依赖／回合末组合时明确提示限制。
- 无关天气／气闸压制天气影响但不清除天气，伤害和 KO 读取相应生效天气；`field_info` 在存在差异时给出 `effective_weather`／`weather_suppressed`，续算仍使用实际场地。Mega Sol 的招式天气与回合末环境分开处理。
- 招式的拳、声音、切割、风和弹类标签采用 Champions 原始分类覆盖，锋锐／铁拳等按当前数据计算，不沿用 Gen9 记忆推断招式是否获得加成。
- `type_effectiveness` 反映**实际生效属性**经过属性相克后的原始倍率（已包含 Ate/Ize 特性、气象球、大地波动等导致的类型转换；如 格斗 vs 恶/钢 = 4.0），**不包含**抗性树果、Solid Rock、Filter 等后续修正。判断道具是否生效时，对比 `damage_range` 是否减半，而非观察 `type_effectiveness` 是否变化
- `move_info` / `field_info` / `modifiers`：招式（属性/分类/基础与生效威力/命中/段数）、环境（天气/场地/光墙/钉刺）与双方强化·状态·太晶回显——输出模板中的招式/环境表直接取自这三个键，不要凭记忆补数值。`move_info` 由引擎结构化返回最终招式副本：气象球、太晶爆发等动态属性／分类与 `effective_power` 均为实际计算值，不依赖原始招式或描述文本解析
- 2-5 段变段招式（乱击、岩石爆击、飞水手里剑、鳞射等，数据层 `hits: "multi"`）：引擎按期望段数 3 段估算 `total_damage_range`，响应 `warning` 会注明；用户问"5 段全中"时用 `--move_ov '{"hits": 5}'` 显式指定
- `attacker_auto_preset` / `defender_auto_preset`：当用户未指定配置或只给出部分配置（如性格、道具、特性）时，引擎自动从 setdex 匹配预设，用其 **evs / nature / ivs** 补全未指定字段；若用户完全未指定配置，还会同时采用该预设的 **特性**。**形态永不切换**——问水箭龟就是水箭龟。若该宝可梦不在 setdex 中（共 207 只），值为 `null`。回答中若该字段非 null，声明："未指定努力值按热门预设 `{preset_name}` 补全"。
- **部分指定努力值时不套预设**：override 中出现任一努力类字段（`evs` / `sps` / `raw_stats` / `stats`）时，预设完全跳过——用户给的分配就是完整分配，未指定项 = 0 努力、无修正性格。例："32 HP 能力点数的咆哮虎" 就是 HP32/其余 0，不补其余耐久。回答中无需声明预设假设。
- `attacker_auto_item` / `defender_auto_item`：auto-preset 命中且预设道具为**纯增伤道具**（生命宝珠/讲究头带/讲究眼镜/达人带/力量头带/博识眼镜）时自动套用并在回答开头声明："假设携带 `{item}`（来自热门配置）"；其余道具（文柚果、披带、树果等判定触发类）一律不兜底，保持无道具基线。用户显式指定的道具永远优先。
- 携带进化奇石时，`calc` 会从内置进化链按当前形态判断资格，红／蓝条纹野蛮鲈鱼不会继承白条纹的进化资格；`can_evolve` 显式覆盖优先，通常无需手工传入。地区、Mega、起源、王冠等形态会保留引擎形态身份，物种／形态限定道具与拍落判定按实际形态处理。
- 预设优先级：天梯热门套（`天梯双打热门配置`，官方实机排位双打 Top50 提炼）优先于旧 VGC 预设参与 auto 匹配；旧预设仍可经 `preset <名> <套名>` 显式引用。

### optimize 返回值关键字段

`optimal_ev`（默认 EV 模式）在回答中转换为**能力值描述**（如"特攻能力值需要达到 177"），并可标注 SP 等价（"252 努力值 = 32 能力点数"），不要只给数值。若用户以 SP 提问并加 `--mode sp`，则引用 `optimal_sp`（双模式返回字段详见 references/mechanics.md）。`remaining_evs` / `remaining_sp` 已扣除搜索属性之外的原配置分配；搜索属性只按新最优值计算一次。

精神冲击／精神击破／圣剑仍属特殊招式：攻击优化搜索特攻，防守优化搜索物防；冰鳞按特殊分类减伤，不因命中物防而失效。

太晶化太晶爆发的攻击优化会分别搜索攻击与特攻路线，并按候选能力值重新决定物理／特殊分类；返回满足目标的最小 EV／SP 路线。

星晶／太晶甲壳等状态连续攻击使用逐击概率：`guaranteed` 要求全部随机伤害分支满足目标，`likely` 要求至少 50% 概率，并回显 `ko_probability`／`survival_probability`（百分数）。普通静态场景的 `likely` 继续使用平均伤害。优化不包含入场钉子或回合末回复／持续伤害。

## 3. 执行工作流

### 承伤反查的默认口径（survivability）

- 用户问「不加耐久能顶多大威力的技能」「特防端能接多少」等未指定具体招式的承伤问题时，使用 `survivability`。未指定攻方能力值时，**物攻端默认攻击 200，特攻端默认特攻 200**；明确指定时使用用户给出的值。未指定物理或特殊端时分别查询两端，不自行猜测。
- 默认条件固定为：双方 50 级、防御方满血、属性倍率 1×、无本系、非要害、单次单发（双打单体，不套扩散减伤），双方无自身特性与道具效果，无天气、场地、墙或辅助加成。「不加耐久」按零耐久努力、31 IV、性格不修正耐久；不套热门预设。用户显式给出的配置和环境优先，实际条件以 `defender` / `field_info` / `defender_boosts` / `attacker_boosts` 回显为准。
- **稳接**：`safe_bp`，一击击倒概率严格小于 15%；**绝对安全**：`absolute_safe_bp`，非要害时一击击倒概率为零。两者均不保证承受要害。数值全部引用命令输出，不手算，不通过抗性倍率折算旧结果。
- 回答开头声明攻方能力值及中性、无本系的比较条件，给出防御方 HP、对应防御能力值、临界威力与伤害范围。若对应 `*_bp_capped` 为 true，写「至少能承受 `search_max_bp` 威力，搜索已触顶，真实上限未确定」，不可将其表述为最大值；威力为 0 表示搜索范围内连最低威力也不满足条件。
- `evs` / `sps` / `ivs` / `nature` 和最终能力值覆盖均可使用；等级固定 50。不支持的覆盖字段、无效 JSON 和配置冲突会报错，应修正输入后重试。需要指定真实招式、属性、本系、道具或自身特性时使用 `calc`，不要将中性反查当作具体招式的伤害结论。详细参数见 `references/commands.md`。

### 3.1 通用流程

```
1. 解析意图 → 百科查询 / 属性相克 / 伤害计算 / 努力值优化 / 中性承伤反查
2. 名称规范化 → 别名映射、形态确认（未指定则默认"一般"形态）
3. 执行对应命令并解析结果
```

### 3.2 伤害计算工作流（calc / optimize）

**执行任何伤害计算命令前，必须先输出 `<plan>` 标签进行结构化思考。**

#### Step 0: 输出 <plan> 标签

```markdown
<plan>
1. 提取指令信息：攻方 = [填入标准名称] | 守方 = [填入标准名称] | 招式 = [填入标准名称]
2. 环境决策检查（仅限用户明确提及或继承自上一轮对话）：
   - 用户是否明确提及天气或场地？[是 / 否，若是请列出具体名称]
   - 用户是否明确提及单打 / 双打？[是 / 否。若否则推断为 Doubles]
3. 危险动作核对：
   - 我是否试图在 plan 阶段预设能力值、努力值、性格或伤害数字？[填 否]
   - 我是否打算凭内部记忆解释属性相克、特性效果或招式机制？[填 否]
4. 即将执行的精确命令：[在此处写出完整的 `python scripts/query.py calc ...` 命令]
</plan>
```

> **多轮状态继承**：若上一轮对话中已确定环境条件（如晴天），且用户本轮未提及环境变化，则在 `<plan>` 中标注"继承自上一轮"，并在 `--field_ov` 中继续传入该环境条件。

> `<plan>` 中不写具体数值（如"252 特攻"、"伤害 120"），数值在 `calc` 返回后提取。

#### Step 1: 提取实体

攻击方宝可梦、招式、防御方宝可梦。

#### Step 2: 名称规范化

确认标准中文名/英文名，确定形态（未指定则默认"一般"形态）。

**别名处理规则**：`data/aliases.json` 已收录常见俗称（如"钢兵"→"仆刀将军"、"抗斗果"→"巧可果"），`normalize.py` 在所有查询命令的底层自动完成映射。**Agent 无需预先转换别名，直接使用用户提供的原始名称作为参数传入即可，以查询的结果为准。**

**多语言输入规则**：中文（简体/繁体）、英文、日文输入均合法（如 `nature:"内敛"` 与 `nature:"Modest"`、`types:["火","飞行"]` 与 `["Fire","Flying"]`、`types:["格鬥"]` 等价；繁体/日语实体名如 `閃電鳥`、`カプ・コケコ`、`１０まんボルト` 直接解析到简体规范实体，输出仍为简体）。**优先直接输出规范英文标识符**（招式/特性/道具英文名、性格英文名、属性英文名）；不确定某个名称的规范英文写法时，先执行 `lookup <名称>` 获取 `{canonical_en, entity_type}` 再用于参数。引擎内部已统一英文枚举；非法的属性/性格/状态 override 值会被入口校验拒绝并返回 `suggestions`。

**形态查询与消歧规则**：

部分宝可梦存在多形态（Mega 进化、地区形态、原始回归等）。当用户输入的名称可能对应多个形态时：

1. 先执行 `pokemon <name>` 查询，查看返回的 `forms` 列表和 `form_selection_note`。
2. 根据上下文推断用户意图的形态（如用户说"洗翠火暴兽"则选"洗翠的样子"，说"火暴兽"则选默认"火暴兽"）。
3. 在 `att_override` / `def_override` 中传入 `"form_name"` 明确指定，如 `{"form_name": "洗翠的样子", "item": "讲究围巾"}`。

**规则**：
- `form_name` 的值取自 `pokemon` 命令返回的 `forms[].name` 之一，大小写敏感。
- 不传 `form_name` 时，默认使用引擎推断的形态（通常是第一个形态或索引匹配的形态）。
- 不要传入 `"form"` 字段（已废弃），`Pokemon` dataclass 不支持该参数。

#### Step 3: 环境条件检查（逐项确认）

| # | 检查项 | 触发条件 | 传入位置 |
|---|--------|---------|---------|
| 3.1 | 天气 (weather) | 用户明确提及天气词汇；或攻击方特性为天气特性；或使用气象球/大地波动等联动招式 | `field_override` |
| 3.2 | 场地 (terrain) | 用户明确提及场地词汇；或使用场地联动招式（电气上升/精神强念/薄雾爆炸/大地波动） | `field_override` |
| 3.3 | 对战模式 (format) | 用户提及"单打" → Singles；否则默认 Doubles | `field_override` |
| 3.4 | 墙壁 (screen) | 用户提及光墙/反射壁/极光幕 | `field_override` |
| 3.5 | 岩钉/撒菱 | 用户提及隐形岩/撒菱 | `field_override` |
| 3.6 | 其他场地效果 | 用户提及帮助/友情防守/蓄电池/能量点/灾祸系列等 | `field_override` |

> `weather` 和 `terrain` 是两个**完全独立**的字段，可以同时存在。例如：`{"weather":"Sun","terrain":"Electric"}`

> 攻击方特性（如"日照"）**不会自动设置** field.weather，需要显式构造 `{"weather":"Sun"}`。

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

**推断优先级**：用户明确指定 > 角色类型推断。无论使用何种默认配置，回答开头声明假设。

**配置覆盖原则**：用户的显式指定始终优先于任何默认推断规则（包括未过签形态的 0 点数规则、Mega 形态默认道具规则）。若用户指定了"252特攻"（用 `evs` 字段）或"32特攻"（用 `sps` 字段）或特定道具，在 `--att_ov` 中照原样传入对应字段与数值，不再套用默认配置。

**形态可用性警告规则**：

- 若 `_data_source == "gen9"` 且 `is_unobtainable == true`：
  > ⚠️ 该形态在 Gen9 标准对战中不可用，以下结果为理论计算。

- 若 `_data_source == "champions"` 且 `is_unobtainable == true`：
  > ⚠️ 该形态基于 Champions M-C 规则数据（champout v1.2.0，2026-09-11）。若您询问的是 Gen9 规则，结果可能不适用。

- 若 `_data_source == "champions"` 且 `is_unobtainable == false`：
  > 无需警告

- **Mega 形态默认道具**：引擎自动根据形态名推导默认携带的 Mega 石（如 `超级喷火龙Ｙ` → `喷火龙进化石Ｙ`，`原始盖欧卡` → `原始回归宝珠`）。若用户显式指定其他道具，按上述覆盖原则处理。

#### Step 5: 命令选择

```
标准宝可梦（Gen9可用）+ 名字已知      → calc
未过签宝可梦（Mega等）且 calc 可用    → calc（引用 warning）
未过签宝可梦且 calc 报错             → pokemon → compute-stats → calc-raw
自定义假设（"如果HP150/特攻180"）     → calc-raw
```

#### Step 6: 构造命令并执行

- 一次性构造完整命令，包含所有覆盖参数
- 性格未指定时的对比场景：同时计算两种常见性格（如爽朗 vs 固执），输出能力值对比表

#### Step 7: 参数一致性校验

构造命令后，对照 `<plan>` 中的环境推断检查 `--field_ov` 内容：

- 若 plan 推断出 weather/terrain/format 不为空，则 `--field_ov` 不能是 `{}` 或省略
- 若 plan 推断出无环境，则 `--field_ov` 可以省略

> **常见错误**：plan 推断出晴天，但 `--field_ov` 漏传。这会遗漏天气加成，导致伤害结果严重偏低。

#### Step 8: 异常处理与重试

若命令返回错误信息（如 `not found`、JSON 解析错误、参数无效）：

1. **绝对禁止编造补救结果** —— 不用"大概"、"估计"等替代数字
2. 重新生成 `<plan>`，分析报错原因（名称拼写？JSON 格式？字段名错误？）
3. 修正参数后重试
4. 若再次失败，原样输出报错信息给用户，说明无法完成计算

#### Step 9: 结果解析与回答

按文档末尾「最终输出模板」组织回答，使用命令返回的精确数字。

## 4. 输出格式

### 4.1 百科查询回答

一句话总结核心信息，可附关键数据表格。

### 4.2 伤害计算标准回答结构

执行 `calc` 后，按文档末尾的「最终输出模板」组织回答：包含六个二级标题（结论摘要 / 攻击方详细信息 / 防御方详细信息 / 招式信息 / 环境条件 / 伤害计算结果），按顺序输出，不遗漏。若用户询问能力点数/努力值优化，追加「能力点数优化结果」。

**结构化字段优先**：模板中的每一项都标注了它来自 calc 响应的哪个字段（如 `move_info.type`、`field_info.weather`、`type_effectiveness`）——**直接引用这些字段的真实值**填表，不要凭记忆或从 description 转述改写；`description` 是引擎给的人类可读附注，用于核对与战术判断行文，不作为数字来源。

回答中使用**能力值描述**，不直接输出努力值。

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

采用双层数据架构：《宝可梦冠军》(Pokémon Champions) Champions 规则数据（最新为 M-C，champout v1.2.0 / 2026-09-11；231 物种 / 347 种形态）**优先于** Gen9（朱紫）正作数据（全国图鉴 1~1025）。规则数据按引入规则累积保留（M-A 275 / M-B 38 / M-C 34 种形态），默认展示最新规则的完整并集。查询结果中的 `"_data_source"` 字段标识具体来源（`"champions"` 或 `"gen9"`）。数据包含所有形态（含 Mega、原始回归等），伤害计算时不过签过滤。`meta` 使用独立的 pokecamp.cc 赛事数据层。完整说明见 [`references/mechanics.md`](references/mechanics.md)。

### 5.2 能力点数（SP）与努力值（EV）双视图

本 Skill 底层始终以**努力值（EV）**存储与计算，同时提供 Champions 的**能力点数（SP）**作为输入与展示视图，两者等价（**32 SP = 252 EV**，换算 `EV = 8×SP - 4`，无精度损失）。

**术语规范**：
- **优先 SP 表述**：面向用户的回答默认使用能力点数（如"特攻点满 32"），符合 Champions 习惯。
- 用户提及"能力点数""SP""32""66"时，在 override 中使用 **`sps` 字段**（如 `{"sps":{"sp_attack":32}}`），适配层自动按 `8×SP-4` 转为 EV（32→252）。
- 用户提及"努力值""252""4""508"等 EV 关键词时，在 override 中使用 **`evs` 字段**（如 `{"evs":{"sp_attack":252}}`），原样传入。
- **`sps` 与 `evs` 可并存**，同一能力项 `sps` 优先。两者取其一即可，优先匹配用户话术。
- 回答中同时标注两种表述，格式为"32 能力点数（= 252 努力值）"；优先强调能力值描述（如"特攻能力值需要达到 172"）。
- `calc` / `calc-raw` / `compute-stats` 返回 JSON 中，`evs` 字段为底层原始 EV，`sps` 字段为换算后的 SP 展示值。展示时优先引用 `sps`。

> 换算公式推导、SP↔EV 对照表、optimize 双模式返回字段详见 [`references/mechanics.md`](references/mechanics.md)。

### 5.3 常见实体词汇启动列表（Vocabulary Priming）

> **说明**：以下词汇列表仅用于实体识别和名称映射。遇到这些词汇时传给 `query.py` 查询后引用，不自行解释机制或效果。

* 常见道具俗称：命玉（生命宝珠）、头带/CB（讲究头带）、眼镜/CS（讲究眼镜）、围巾/Scarf（讲究围巾）、剩饭（吃剩的东西）、腰带/Sash（气势披带）、突击背心/AV、弱策（弱点保险）。18 系"抗X果"抗性树果俗称（抗火果/抗水果/抗斗果……）由 normalize 自动映射，无需记忆对应关系。
* 常见招式俗称：击掌（击掌奇袭）、UT（急速折返）、VS（伏特替换）、看我嘛（Follow Me）、愤怒粉（Rage Powder）、顺风（Tailwind）、空间/TR（戏法空间）、挑衅（Taunt）、广防（广域防守）、快防（快速防守）、保护（守住）。
* 常见特性俗称：威吓（Intimidate）、恶作剧（恶作剧之心）、疾风（疾风之翼）、女王（女王威严）、再生力（Regenerator）、叶绿素（Chlorophyll）、轻快（悠游自如）、夸克充能（Quark Drive）、古代活性（Protosynthesis）、强子引擎（Hadron Engine）、终结之地（Desolate Land）、始源之海（Primordial Sea）。
* 常见战术术语：STAB/本系、补盲、确一/OHKO、确二/2HKO、乱数、耐久三维、极速、满速、极限低速、速度线。

> **易混淆属性相克提醒（以 `type` 命令查询为准）**：
> - 超能力 → 幽灵：**效果一般（1.0x）**，不是 0 倍
> - 格斗/普通 → 幽灵：**无效（0x）**
> - 地面 → 飞行：**无效（0x）**
> - 电 → 地面：**无效（0x）**

---

## 最终输出模板

> 伤害计算的回答按此模板组织：将占位符替换为引擎返回的真实数据，不增删二级标题，不改变顺序。

**回答开头先声明假设**：

1. **对战环境声明**：`本次计算环境：[用户指定 / 默认 Doubles]。`
2. **数据来源声明**：`攻方数据来源：attacker_info._data_source | 守方数据来源：defender_info._data_source`
3. **未过签形态警告**（若 `is_unobtainable == true`）：
   - Gen9 不可用 → `⚠️ 该形态在 Gen9 标准对战中不可用，以下结果为理论计算。`
   - Champions 不可用 → `⚠️ 该形态基于 Champions M-C 规则数据（champout v1.2.0，2026-09-11）。若您询问的是 Gen9 规则，结果可能不适用。`
4. **默认配置推断清单**（当用户未指定性格/努力值/道具时）：
   `假设声明：以下参数未由用户明确指定，使用角色类型默认推断：`
   `- 性格：[推断值] — 推断依据：[角色类型]`
   `- 能力点数：[推断值]`
   `- 道具：[推断值]`
   `若实际配置不同，伤害结果可能有变化。`
   若 auto-preset 自动套用了增伤道具（`attacker_auto_item` 非 null），在声明中注明："道具 {item} 来自热门配置假设，实际配置不同则结果有变化"。

避免：省略对战环境声明 / 省略数据来源声明 / 笼统写"使用了默认配置"而不列出具体参数 / 将推断参数作为绝对事实陈述。

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
> - 所有形态：同时输出"特性"（`ability` 字段）和"全部可选特性"（`all_abilities` 字段）
> - 用户指定特性时，当前特性为用户指定值；未指定时，当前特性为默认特性（`all_abilities` 列表第一项）
> - Mega / 原始回归形态同样适用此规则

### 防御方详细信息

按上方「攻击方详细信息」表格的相同行结构逐项输出防御方数据（取自 `defender_info`），表格末尾追加一行 `| 当前 HP / 最大 HP | {current_hp} / {max_hp} |`。不省略任何一行，不与攻击方合并为一张表，防御方为独立的二级标题章节。「能力点数取值规则」与「特性显示规则」对防御方同样适用。

### 招式信息

使用 `calc` 返回的 `move_info` 构建完整表格，每项直接引用响应字段。

| 项目 | 数值（响应字段） |
|------|------|
| 属性 | {move_info.type} |
| 分类 | {move_info.category} |
| 基础威力 | {move_info.base_power} |
| 计算威力 | {move_info.effective_power} |
| 命中 | {move_info.accuracy} |
| 打击次数 | {move_info.hits} |
| 广域招式 | {move_info.is_spread}（是/否） |
| 引擎修正链简述 | {description——人类可读附注，引用原文不转述} |

> **计算威力说明**：引擎根据传入的环境条件自动计算最终威力。直接引用引擎返回的 `effective_power` 或 `description` 中的威力值，不推导中间步骤。

### 环境条件

使用 `calc` 返回的 `field_info` 构建完整表格，每项直接引用响应字段（布尔/枚举值转为"是/否/无"表述）。

| 项目 | 数值（响应字段） |
|------|------|
| 天气 | {field_info.weather}（null = 无） |
| 场地 | {field_info.terrain}（null = 无） |
| 对战模式 | {field_info.format} |
| 光墙/反射壁/极光幕 | {field_info.is_light_screen / is_reflect / is_aurora_veil} |
| 隐形岩 | {field_info.is_stealth_rock} |
| 撒菱层数 | {field_info.spikes} |
| 其他效果 | {field_info.is_helping_hand / is_friend_guard / is_battery / is_power_spot——按"帮助/友情防守/蓄电池/能量点"表述，null/False 略过} |

### 伤害计算结果

使用 `calc` 返回的顶层字段构建完整表格，每项直接引用响应字段。

| 项目 | 数值（响应字段） |
|------|------|
| 伤害范围（单次） | {damage_range[0]} ～ {damage_range[1]} |
| 全部 16 个乱数 roll | {damage_rolls} |
| 属性相克倍率 | {type_effectiveness}x |
| 是否触发 STAB | {stab_applied}（是/否） |
| 是否触发要害 | {is_critical}（是/否） |
| 天气加成 | {从 description 判断——响应无独立字段} |
| 场地加成 | {从 description 判断——响应无独立字段} |
| 道具加成 | {从 description 判断——响应无独立字段} |
| 引擎报告的计算威力 | {description 中引擎返回的威力值} |
| 烧伤减半 | {burn_applied}（是/否） |
| KO 概率 | {ko_chance} |

**综合判断**：
- 能否一击秒杀：{能/不能/概率秒杀}
- 若不能秒杀，剩余 HP 范围：{min_remaining} ～ {max_remaining}
- 战术建议：{如"需要岩钉蹭血后才能确一""气势披带可保命"等}

> 多段攻击招式（如双翼、种子机关枪）：`damage_range` 为单次伤害，`total_damage_range` 为合计伤害，判断秒杀时引用 `total_damage_range`。

### 能力点数优化结果（可选）

若用户询问"需要多少能力点数/努力值才能击杀/存活"，追加 optimize 结果（默认 EV 模式；用户明确用 SP 时加 `--mode sp`）：

- 目标：{ko / survive}
- 最优单项：{stat} 努力值 {optimal_ev}（= {对应 SP} 能力点数），对应能力值 {stat_value}
- 剩余可用努力值：{remaining_evs}
- 优化后伤害范围：{damage_range}

> 回答中转换为**能力值描述**（如"特攻能力值需达到 177"），并同时标注 EV 与 SP 双表述。EV 与 SP 换算遵循 `SP=(EV+4)//8`、`EV=8×SP-4`（如 252 EV = 32 SP）。
