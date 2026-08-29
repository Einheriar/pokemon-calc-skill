# pokemon-calc Skill 技术文档

## 设计原则

1. **LLM 只做理解，不做计算**
   LLM 仅负责将用户的自然语言请求转化为结构化参数，所有伤害数值计算由固定 Python 程序完成。

2. **零外部依赖**
   核心计算模块仅使用 Python 标准库，不依赖 numpy、pandas 等重型库。

3. **数据静态化**
   将 JS 数据文件一次性提取为 JSON，运行时直接加载，不解析 JS。

4. **纯函数接口**
   计算函数为纯函数，输入输出明确，便于测试和集成。

5. **中文优先，能力值优先**
   数据以中文名为主索引，同时支持英文名称。在回答中始终使用能力值描述，将用户输入的努力值转换为能力值呈现。

6. **全国图鉴百科 + Gen9 伤害计算**
   百科查询数据（`pokemon.json`）覆盖全国图鉴（1~1025 号），包含所有世代的宝可梦信息。伤害计算引擎（`damage.py`）默认以 **Gen9（朱紫）** 规则执行，使用的招式数据来自 `MOVES_SV`。若用户询问的宝可梦在 Gen9 中未过签，百科信息仍可正常查询，但伤害计算会按 Gen9 规则处理（如招式威力、特性效果等以 Gen9 为准）。

7. **招式数据权威来源**
   伤害计算相关的招式数据以 `script_res/move_data.js` 的 `MOVES_SV` 为唯一权威来源，而非 `pokemon-dataset-zh`。

---

## 目录结构

```
pokemon-calc/
├── SKILL.md              # Skill 使用说明与 LLM 行为规范
├── DEVELOPER.md          # 本文件（技术文档）
├── data/
│   ├── pokemon.json      # 宝可梦百科数据（1025 只）
│   ├── moves.json        # 招式数据（782 个，含 SV 全世代）
│   ├── abilities.json    # 特性数据
│   ├── type_chart.json   # 18x18 属性相克表
│   ├── name_index.json   # 中英文名称索引
│   ├── setdex.json       # VGC 预设配置（189 只，264 个预设）
│   ├── aliases.json      # 玩家俗称 → 标准名称映射
│   ├── usage_stats.json  # 环境使用率快照（pokecamp.cc / Limitless 赛事数据）
│   ├── meta_teams.json   # 近期赛事队伍快照（前 12 支，pokecamp.cc / Limitless 赛事数据）
│   └── teams_full.json.gz # 全量赛事队伍内置包（当前窗口全部队伍 + 完整明细，gzip 压缩）
└── scripts/
    ├── query.py          # 主查询入口（百科 + calc + preset + optimize + meta）
    ├── damage.py         # 伤害计算引擎
    ├── ko_chance.py      # KO 概率计算
    ├── ev_optimizer.py   # 努力值优化搜索
    ├── models.py         # 数据模型（Pokemon, Move, Field, DamageResult）
    ├── normalize.py      # 输入标准化层（别名/拼写纠正）
    ├── pokecamp_source.py # 环境数据源模块（可插拔；快照/缓存/在线三层）
    └── teams_index.py    # 全量队伍本地 SQLite 索引（从内置包派生，gitignored）
```


---

## 脚本 I/O 规范

### 1. query.py（主查询入口）

所有查询通过执行 `query.py` 完成，命令与参数以空格分隔。

#### 子命令列表

| 命令 | 参数 | 用途 | 返回值 |
|------|------|------|--------|
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
| `filter-moves [--type ...] [--category ...] [--min-power n] [--max-power n]` | 筛选条件 | 按属性/分类/威力范围筛选招式 | JSON 对象 |
| `filter-pokemon [--type ...] [--min-stat stat n] [--max-stat stat n] [--ability ...]` | 筛选条件 | 按属性（AND）/种族值范围/特性（OR）筛选宝可梦 | JSON 对象 |
| `preset <pokemon> [preset_name]` | 宝可梦名 [预设名] | 列出/获取 VGC 预设配置 | JSON 对象 |
| `calc <attacker> <move> <defender> [att_override] [move_override] [def_override] [field_override]` | 攻击方 招式 防御方 | 快速伤害计算（默认 Lv.50，支持 preset 覆盖） | JSON 对象 |
| `compute-stats <base_stats> [evs] [ivs] [nature] [level]` | 种族值 JSON | 从配置计算能力值 | JSON 对象 |
| `calc-raw <attacker_json> <move_json> <defender_json> [field_json]` | 完整参数 JSON | 纯参数伤害计算（不查名字） | JSON 对象 |
| `optimize <attacker> <move> <defender> [goal] [target] [threshold] [att_override] [def_override] [field_override]` | 攻击方 招式 防御方 | 努力值优化搜索 | JSON 对象 |
| `survivability <defender> <attacker_stat> <category> [def_override] [field_override]` | 防御方 攻击方能力值 分类 | 等效威力反查（无加成最大可承受招式威力） | JSON 对象 |
| `meta [target] [--top N] [--online] [--source tournament\|ladder\|ingame\|showdown] [--format singles\|doubles] [--usage] [--teams] [--pokemon 名] [--player 名] [--tournament 名] [--stats [--placing-max N]] [--teammates 名]` | 宝可梦名 / 序号（可选） | 统一环境情报：使用率排行 / 单只详情 / 队伍列表 / 全量检索 / 出现率聚合 / 队友共现 / 天梯排行（pokecamp.cc 赛事 + 天梯数据） | JSON 对象 |
| `usage [name] [--top N] [--online]` | （deprecated，自动转发到 `meta --usage`） | 环境使用率排行 / 单只详情 | JSON 对象 |
| `teams [query] [--top N] [--pokemon 名] [--player 名] [--tournament 名] [--stats [--placing-max N]] [--teammates 名] [--online]` | （deprecated，自动转发到 `meta --teams`） | 赛事队伍查询 | JSON 对象 |


#### calc 命令 I/O

**输入参数**

| 位置 | 参数名 | 类型 | 必填 | 说明 |
|------|--------|------|------|------|
| 1 | `attacker` | string | 是 | 攻击方宝可梦中文/英文名 |
| 2 | `move` | string | 是 | 招式中文/英文名 |
| 3 | `defender` | string | 是 | 防御方宝可梦中文/英文名 |
| 4 | `att_override` | JSON string | 否 | 覆盖攻击方默认配置 |
| 5 | `move_override` | JSON string | 否 | 覆盖招式默认配置 |
| 6 | `def_override` | JSON string | 否 | 覆盖防御方默认配置 |

**att_override / def_override 可覆盖字段**

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

**move_override 可覆盖字段**

```json
{
  "base_power": 80,
  "type": "飞行",
  "category": "Physical",
  "is_crit": false,
  "hits": 1
}
```

**返回值 JSON Schema**

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
  "burn_applied": false
}
```

#### optimize 命令 I/O

**输入参数**

| 位置 | 参数名 | 类型 | 必填 | 说明 |
|------|--------|------|------|------|
| 1 | `attacker` | string | 是 | 攻击方宝可梦名 |
| 2 | `move` | string | 是 | 招式名 |
| 3 | `defender` | string | 是 | 防御方宝可梦名 |
| 4 | `goal` | string | 否 | `ko` / `survive` / `survive_bulk`（默认 `ko`） |
| 5 | `target` | string | 否 | `ohko` / `2hko` / `3hko` / `survive` / `survive_2hko`（默认 `ohko`） |
| 6 | `threshold` | string | 否 | `guaranteed`（最差乱数）/ `likely`（平均乱数）（默认 `guaranteed`） |
| 7 | `att_override` | JSON string | 否 | 覆盖攻击方配置 |
| 8 | `def_override` | JSON string | 否 | 覆盖防御方配置 |

**返回值 JSON Schema**

```json
{
  "goal": "ko",
  "target": "ohko",
  "threshold": "guaranteed",
  "result": "found",
  "optimized_evs": {"attack": 252},
  "damage_range": [130, 156],
  "description": "攻击能力值 172（对应 252 攻击努力值）可保证一击击杀"
}
```

---

### 2. damage.py（伤害计算引擎）

**核心函数签名**

```python
def calculate_damage(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    gen: int = 9,
) -> DamageResult:
```

**输入模型**

- `Pokemon`: 包含 name, level, base_stats, evs, ivs, nature, ability, item, types, boosts, status 等
- `Move`: 包含 name, base_power, type, category, hits, is_crit, makes_contact 等
- `Field`: 包含 weather, terrain, format, is_reflect, is_light_screen 等场地条件

**输出模型（DamageResult）**

```python
@dataclass
class DamageResult:
    damage: list[int]          # 16 个乱数 roll 的伤害值（已排序）
    min_damage: int
    max_damage: int
    description: str
    is_critical: bool
    type_effectiveness: float
    stab_applied: bool
    burn_applied: bool
```

**已实现的修正**

- 属性相克（含 Stellar、Freeze-Dry、Flying Press 等特殊规则）
- STAB / 太晶化（含 Adaptability、星晶属性加成）
- 特性修正（30+ 种：Overgrow/Blaze/Torrent、Huge Power、Guts、Protosynthesis 等）
- 道具修正（生命宝珠、讲究头带/眼镜、突击背心、进化奇石、深海的牙齿/鳞片等）
- 场地/天气（晴天/雨天/沙暴/下雪、青草/电气/薄雾/精神场地）
- Ate/Ize 特性（Pixilate / Aerilate / Refrigerate / Galvanize / Normalize）
- 抗性树果（16 种，效果拔群时触发 0.5x 修正）
- 其他：烧伤减半、要害 1.5x、能力等级变化、重力、光墙/反射壁/极光幕

---

### 3. ko_chance.py（KO 概率计算）

**核心函数签名**

```python
def get_ko_chance_text(
    damage: list[int],
    move: Move,
    defender: Pokemon,
    field: Field,
    is_bad_dreams: bool = False,
) -> str:
```

**输入**

- `damage`: `calculate_damage` 返回的 16 个乱数 roll 列表
- `move`: 攻击招式
- `defender`: 防御方宝可梦
- `field`: 场地条件
- `is_bad_dreams`: 是否处于噩梦状态

**输出**

- 人类可读的 KO 概率描述字符串（如"约 93.8% 几率 2次攻击击杀"）

---

### 4. ev_optimizer.py（努力值优化）

**核心函数签名**

```python
def optimize_evs(
    attacker: Pokemon,
    defender: Pokemon,
    move: Move,
    field: Field,
    goal: str = "ko",        # "ko" | "survive" | "survive_bulk"
    target: str = "ohko",    # "ohko" | "2hko" | "3hko" | "survive" | "survive_2hko"
    threshold: str = "guaranteed",  # "guaranteed" | "likely"
) -> dict:
```

**功能**

- `ko` + `ohko`: 搜索最少攻击/特攻努力值以一击击杀
- `ko` + `2hko`/`3hko`: 搜索最少攻击努力值以多击击杀
- `survive`: 搜索最少防御/特防努力值以扛住一击
- `survive_bulk`: 联合搜索 HP + 防御的最优分配以扛住一击

**输出**

返回包含 `optimized_evs`, `damage_range`, `description` 的字典。

### 5. models.py（数据模型）

定义以下 dataclass：

```python
@dataclass
class Pokemon:
    name: str
    level: int = 50
    base_stats: dict[str, int]
    evs: dict[str, int]
    ivs: dict[str, int]
    nature: str
    ability: str
    item: str
    types: list[str]
    boosts: dict[str, int]
    status: Optional[str]
    is_terastalize: bool
    tera_type: Optional[str]
    is_dynamax: bool
    can_evolve: bool
    weight: float

@dataclass
class Move:
    name: str
    base_power: int
    type: str
    category: str          # Physical / Special / Status
    hits: int = 1
    is_crit: bool = False
    makes_contact: bool = False
    has_recoil: bool = False
    is_punch: bool = False
    is_sound: bool = False
    is_slice: bool = False
    is_wind: bool = False
    is_bullet: bool = False
    ignores_burn: bool = False
    is_spread: bool = False
    is_ohko: bool = False
    is_z: bool = False

@dataclass
class Field:
    weather: Optional[str]
    terrain: Optional[str]
    format: str = "Singles"
    is_reflect: bool = False
    is_light_screen: bool = False
    is_aurora_veil: bool = False
    is_gravity: bool = False
    is_stealth_rock: bool = False
    spikes: int = 0
    # ... 以及其他双打/场地条件

@dataclass
class DamageResult:
    damage: list[int]
    min_damage: int
    max_damage: int
    description: str
    is_critical: bool
    type_effectiveness: float
    stab_applied: bool
    burn_applied: bool
```

---

### 6. pokecamp_source.py（环境数据源模块）

`meta` 命令的数据访问层，可插拔设计（旧命令 `usage` / `teams` 自动转发到 `meta`）：

- **数据源**：`PokecampSource` 类封装 pokecamp.cc 的静态 JSON 端点（Champions 规则 M-B）；注册在 `SOURCES` 字典中，经 `get_source()` 获取。新增/更换数据源时实现同一组 fetch 方法并注册即可，`query.py` 无需改动。
- **三层数据**：内置快照（`data/usage_stats.json` / `data/teams_full.json.gz`）→ 在线缓存（`data/cache/`，gitignore）→ 实时拉取（`--online`，仅标准库 `urllib`，尊重 `HTTP_PROXY`/`HTTPS_PROXY`，请求 gzip 传输压缩）。网络失败沿反方向回退，返回的 `meta.origin` 标明实际来源（snapshot/cache/online），且 `meta.online_error` 携带失败原因供上层汇报用户。
- **--source 参数**：`--source tournament`（默认）走 pokecamp.cc 赛事数据；`--source ladder`/`ingame` 走官方实机排位数据（仅名次，日更）；`--source showdown` 走 Showdown 天梯月报（含使用率，月更滞后）。天梯源支持 `--format singles|doubles`（默认双打），不支持队伍类查询。
- **天梯数据层**（V4.8.09 新增）：总榜走 `pokemon-page/{ingame|showdown}.json` 轻量端点（约 230 KB），蒸馏后内置快照 `data/ladder_ingame.json`（39 KB）/ `data/ladder_showdown.json`（72 KB），维护者脚本 `cache/build_ladder_stats.py`。ingame 蒸馏时按 `speciesIdentifier` 合并 Mega 展开行，并丢弃 pokecamp 为统一结构填充的占位字段（usagePercent=0/teamCount=1/winRate=null），快照只保留真实名次。单只天梯详情走 `_next/data/{buildId}/.../pokemon/{id}.json`（gzip 约 127 KB/只，按宝可梦缓存 24h；buildId 从页面 HTML 自动发现并缓存，404 时重新发现重试一次），ingame 读 `detailBySource.ingame.inGameReferenceByFormat[format]`（配招/道具/特性/性格/努力为真实百分比，队友仅名次），showdown 读 `smogonReferenceByFormat[format]`；名称翻译复用响应内嵌的 itemMap/abilityMap/moveMap/teammateMap。天梯源 regulation 锁定最新赛制常量 `LADDER_REGULATION`（当前 m-b）。已知上游：championsbattledata.com（官方排位数据的社区发布方，内容一致），仅作备选参考，不接入。
- **蒸馏函数**：`distill_usage_snapshot()` / `distill_teams_snapshot()` / `distill_teams_full()` 同时被构建脚本（`cache/build_usage_stats.py`、`cache/build_teams_pack.py`）和在线模式复用，保证快照与在线结果结构一致；`meta_snapshot_from_pack()` 可从全量包直接派生前 12 支的轻量快照。
- **在线查询成本**：`meta <name> --online` 只多下载该只宝可梦的详情（约 23 KB）；`meta --teams --online` 为增量更新——下载队伍列表（原始约 15 MB、gzip 传输约 1.3 MB）+ 仅抓取缓存中缺失的赛事明细（`fetch_team_details_cached()` 按赛事永久缓存，0.15 s 请求间隔），teams.json 内容哈希未变时跳过索引重建；并有 24 小时节流（`ONLINE_MIN_INTERVAL_SEC`）——距上次成功拉取不足 24 小时时不发起任何网络请求，直接复用现有索引并在 `meta.note` 注明。
- **爬虫礼仪**：仅在用户显式 `--online` 或维护者刷新快照时发起请求；结果本地缓存；不批量遍历站点；遵守 robots.txt。

### 7. teams_index.py（全量队伍本地索引）

`meta --teams` 全量查询的本地索引层（纯标准库 `sqlite3`，不 import pokecamp_source）：

- **派生自内置包**：`data/teams_full.json.gz`（维护者用 `cache/build_teams_pack.py` 构建，含当前窗口全部队伍与道具/特性/性格/招式明细、EN→ZH 名称映射）。首次全量查询时 `ensure_index()` 自动派生 `data/cache/teams_index.db`（gitignored，约 30 MB，可删可重建）；包内容哈希变化时自动重建。
- **Schema**：`tournaments` / `teams` / `team_pokemon`（含道具、特性、Mega 前特性、性格、太晶属性）/ `team_pokemon_moves` 四表 + `meta` 表（构建时间、内容哈希、来源、名称映射）。
- **查询接口**（全部硬上限 50 条，保证输出 KB 级）：`find_teams()`（宝可梦/选手/赛事筛选）、`aggregate_pokemon_usage()`（出现率，支持 `--placing-max` / 单赛事子集）、`aggregate_teammates()`（队友共现）、`aggregate_pokemon_builds()`（单只宝可梦的道具/特性/招式/性格占比）、`get_team_detail()`（单队完整明细）。
- **口径验证**：`aggregate_pokemon_usage()` 的出现率与 pokecamp 预计算的 `usage_percent` 同口径同数据集（实测精确吻合）；偶发微小差异源于抓取时刻不同（滚动窗口日内更新）。

---

## 数据资产清单

| 文件 | 条目数 | 来源 | 说明 |
|------|--------|------|------|
| `data/pokemon.json` | 1025 | `pokemon-dataset-zh` | 宝可梦百科数据（含 profile、prototype、图鉴、技能池、进化链） |
| `data/moves.json` | 782 | `pokemon-dataset-zh` + `script_res/move_data.js` | 招式数据。以 `MOVES_SV` 为权威来源补全了全部 SV 世代招式 |
| `data/abilities.json` | ~307 | `pokemon-dataset-zh` | 特性数据（含效果描述、拥有者列表） |
| `data/type_chart.json` | 18x18 | `script_res/` | 属性相克表 |
| `data/name_index.json` | ~4000 | 自动生成 | 中英文名称双向索引（pokemon + moves + abilities + items） |
| `data/setdex.json` | 189 只 / 264 预设 | `script_res/setdex_ncp-g9.js` | VGC 预设配置（性格、努力值、道具、特性、招式参考） |
| `data/aliases.json` | 22 条 | 手工维护 | 玩家俗称 → 标准名称映射（"老喷"→"喷火龙" 等） |
| `data/usage_stats.json` | 299 只 | pokecamp.cc（Limitless 赛事统计） | 环境使用率快照：排名、胜率、Top 招式/特性/道具/性格/SP 分配/队友（由 `cache/build_usage_stats.py` 构建） |
| `data/meta_teams.json` | 12 支 | pokecamp.cc（Limitless 赛事统计） | 近期赛事队伍轻量快照：全量索引不可用时的兜底（由 `cache/build_teams_pack.py` 从全量包派生） |
| `data/teams_full.json.gz` | 9,250 支 / 150 赛事 | pokecamp.cc（Limitless 赛事统计） | 全量赛事队伍内置包（gzip，约 1.4 MB）：全部队伍 + 道具/特性/性格/招式明细 + EN→ZH 名称映射；首次查询派生本地 SQLite 索引（由 `cache/build_teams_pack.py` 构建，原始数据留存于 gitignored 的 `pokecamp_data/`） |
| `data/ladder_ingame.json` | 208 只 | pokecamp.cc（官方实机排位） | 天梯名次快照（39 KB）：单/双打名次，Mega 已并入基础物种，占位字段已丢弃（由 `cache/build_ladder_stats.py` 构建） |
| `data/ladder_showdown.json` | 283 只 | pokecamp.cc（Showdown 天梯月报） | Showdown 使用率快照（72 KB）：单/双打名次 + 使用率，`meta.month` 注明月份（由 `cache/build_ladder_stats.py` 构建） |


### 数据修复记录

- **2026-04-30**: `moves.json` 从 349 条补充至 **782 条**。关键修复：从 `script_res/move_data.js` 的 `MOVES_SV` 提取全部 712 个招式，与现有数据合并，解决了"双翼"（Dual Wingbeat）等大量 SV 世代招式缺失的问题。

---

## 使用示例

```bash
# 百科查询
python scripts/query.py stats 喷火龙
python scripts/query.py type 水 火
python scripts/query.py weak Charizard

# 伤害计算（快捷模式）
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟
python scripts/query.py calc 化石翼龙 "Dual Wingbeat" 胡地 '{"evs":{"attack":252,"speed":252}}' '{}' '{"evs":{}}'

# 使用预设配置
python scripts/query.py preset 烈箭鹰
python scripts/query.py calc 烈箭鹰 Brave\ Bird 喷火龙 '{"preset":"Sharp Beak Set"}'

# 纯参数模式（未过签宝可梦）
python scripts/query.py pokemon 超级喷火龙Y
python scripts/query.py compute-stats '{"hp":78,"attack":104,"defense":78,"sp_attack":159,"sp_defense":115,"speed":100}' '{"sp_attack":252}' '{}' '内敛' 50
python scripts/query.py calc-raw '{"name":"超级喷火龙Y","level":50,"stats":{...}}' '{"name":"热风",...}' '{"name":"超级胡地",...}' '{"weather":"Sun"}'

# 努力值优化
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 ko ohko guaranteed
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 survive survive guaranteed
```


---

## 依赖

- Python 3.10+
- 仅使用标准库（`json`, `math`, `pathlib`, `typing`, `dataclasses` 等）
- 无需 pip/uv 安装任何第三方包
- 联网说明：默认完全离线。仅 `meta --online`（含旧命令 `usage --online` / `teams --online`）使用标准库 `urllib.request` 按需访问 pokecamp.cc（尊重 `HTTP_PROXY`/`HTTPS_PROXY` 环境变量），失败自动回退内置快照

---

## 测试

回归测试脚本位于 `../cache/` 目录：

```bash
python cache/regression_test.py       # Preset / 形态 / setup_moves 等，36 例
python cache/test_usage_stats.py      # usage 环境查询（离线快照 + 在线回退，14 例）
python cache/test_teams_index.py      # 全量队伍索引（建库/筛选/聚合/增量抓取/回退，12 例）
python cache/test_meta_command.py     # meta 统一命令（推断/alias/--source，16 例）
python cache/test_ladder_source.py    # 天梯数据源（ladder/showdown 排行、单双打、Mega 合并、蒸馏/节流，23 例）
python cache/test_field_overrides.py  # 场地参数覆盖专项（30 用例）
python cache/test_filter_moves.py     # filter-moves 命令测试（14 例）
```

旧版专项测试已归档于 `cache/archive/`（15 个，仅作历史参考，不再维护）。

---

## 版本历史

版本号与 git commit 历史一致。仅记录有真实意义的功能/修复变动，跳过纯临时存档与琐碎备份。

### 4.8.09（2026-08-29）

`meta` 接入天梯数据源，落地 4.8.04 预留的 `--source` 扩展点。核心变更：

- **两个天梯源上线**：`--source ladder`（等价 `ingame`）为 Pokémon Champions 官方实机排位数据（最新赛制 M-B，约 1~3 天更新）；`--source showdown` 为 Showdown 天梯月报（含使用率，月更滞后一个月）。均来自 pokecamp.cc 新增的 `pokemon-page/{source}.json` 轻量端点（约 230 KB），不建索引、不打压缩包。
- **`--format singles|doubles`**：天梯源单/双打排行切换（默认双打，输出 `meta.format_note` 提醒）；对 tournament 源无效。
- **rank-only 语义**：官方排位总榜仅公布名次（pokecamp 填充的 usagePercent/teamCount/winRate 为占位常量，蒸馏时全部丢弃，快照只留真实名次），输出为纯名次表并带 `rank_only: true`；Mega 展开行按物种合并（`includes_mega` 标注）。
- **单只天梯详情**：经 `_next/data/{buildId}` SSG 数据路由获取（gzip 约 127 KB/只，按宝可梦缓存 24h；buildId 自动发现、404 重试一次），配招/道具/特性/性格/努力分配为真实百分比（需 `--online`）。
- **组合校验**：天梯源与 `--teams`/`--stats`/`--teammates`/`--player`/`--tournament` 组合返回友好错误（天梯无赛事队伍概念）。
- **测试**：新增 `cache/test_ladder_source.py`（21 例：CLI 排行/单双打/Mega 合并/占位字段隔离/快照字段 + 蒸馏/节流/buildId 单元测试），全部通过；meta 16 例、usage 14 例、teams 索引 12 例、回归 36 例无破坏。

### 4.8.04（2026-08-29）

合并 `usage` / `teams` 为统一的 `meta` 命令，消除"天梯 vs 赛事"术语歧义。核心变更：

- **统一入口**：`meta [target] [--top N] [--online] [--source ...] [--usage|--teams] [--pokemon/--player/--tournament/--stats/--teammates ...]`。不带标志时按位置参数智能推断：空 → 使用率排行，宝可梦名 → 单只详情，纯数字 → 队伍详情。`--usage` / `--teams` 可强制指定模式；显式 `--usage` 优先于 `--pokemon` 等过滤标志。`--top` 缺省按模式取值（使用率 20 / 队伍列表 12，硬上限 50）。
- **队伍列表与详情同源**：`meta --teams` 无参列表改走本地 SQLite 索引，与 `meta --teams <N>` 详情共享同一数据源与排序，消除 `--online` 增量更新后"列表编号 vs 详情编号"错位的隐患；轻量快照 `meta_teams.json` 降级为索引不可用时的兜底。旧 `cmd_usage` / `cmd_teams` 函数改为对 `cmd_meta` 的瘦委托包装（保留供既有测试直接调用）。
- **`--source` 框架**：`--source tournament`（默认）走 pokecamp.cc 赛事数据；`--source ladder` 预留用于未来接入游戏内天梯/排位数据，当前返回友好错误（含 `source_requested` / `source_available` 字段）。数据访问层 `pokecamp_source.py` 的 `SOURCES` 注册表已支持按名称注册新数据源。
- **向后兼容**：旧命令 `usage` / `teams` 仍可用，自动转发到 `meta` 并向 stderr 输出 deprecation 警告。
- **术语澄清**：所有文档统一将 pokecamp.cc 数据标注为"赛事数据"（tournament data），明确区分于游戏内天梯/排位数据（ladder data）。
- **测试**：新增 `cache/test_meta_command.py`（15 例：推断规则、alias 转发、--source 校验、deprecation 警告、默认条数、列表/详情同源一致性），全部通过；回归 36 例、usage 14 例、teams 索引 12 例无破坏。

### 4.8.02（2026-08-26）

`teams --online` 增加 24 小时节流（`ONLINE_MIN_INTERVAL_SEC`）：距上次成功拉取不足 24 小时时不发起任何网络请求，直接复用现有索引并在 `meta.note` 注明；避免用户反复触发最新数据查询时重复下载队伍列表。新增节流测试，teams 索引测试 12/12 通过。

### 4.8.01（2026-08-26）

修复 `teams_full.json.gz` 提交进仓库时被 EOL 规范化损坏的问题：根 `.gitattributes` 的 `pokemon-calc/** text eol=lf` 把 gzip 当文本处理了，新增 `*.gz binary` / `*.db binary` 规则（位于目录级 text 规则之后）并重新提交完好文件。

### 4.8.00（2026-08-26）

`teams` 升级为全量队伍索引。维护者本地构建全量数据包 `data/teams_full.json.gz`（当前滚动 30 天窗口全部 9,250 支队伍 / 150 个赛事，含每队 6 只宝可梦的道具、特性、性格、4 招式明细与 EN→ZH 名称映射，gzip 后约 1.4 MB）随仓库内置发布；首次全量查询时自动派生本地 SQLite 索引（新模块 `scripts/teams_index.py`，DB 约 30 MB、gitignored、可随时重建）。新增查询：`teams --pokemon/--player/--tournament` 全量检索、`teams --stats`（出现率排行，支持 `--placing-max` / 单赛事子集）、`teams --stats --pokemon`（单只宝可梦全量道具/特性/招式/性格占比）、`teams --teammates`（队友共现）；`teams <N>` 改走索引返回完整明细。`--online` 改为增量更新（队伍列表 gzip 约 1.3 MB + 仅抓取新增赛事明细，按赛事永久缓存；teams.json 内容哈希未变则跳过重建）。所有查询输出硬上限 50 条。维护者脚本 `cache/build_teams_pack.py`（原始数据留存 gitignored 的 `pokecamp_data/`，取代 `build_meta_teams.py` 的抓取路径并同时产出 `meta_teams.json`）。新增测试 `cache/test_teams_index.py`（11 例全过），usage 14 例与回归 36 例无破坏。

### 4.7.00（2026-08-26）

新增环境情报查询（Phase 3）：`usage` 命令（使用率总排行 / 单只宝可梦的常用招式、特性、道具、性格、SP 分配推荐、常见队友）与 `teams` 命令（近期赛事队伍列表 / 完整配置 / 按宝可梦筛选，默认前 12 支）。数据来自 pokecamp.cc（Limitless 公开赛事统计，滚动 30 天窗口），以内置快照（`data/usage_stats.json` 299 只、`data/meta_teams.json` 12 支）离线保底，`--online` 可按需实时拉取并本地缓存、失败自动回退快照。数据访问层为可插拔模块 `scripts/pokecamp_source.py`，快照由 `cache/build_usage_stats.py` / `cache/build_meta_teams.py` 构建。Smogon 数据不入 Skill（仅作者本地分析用，见仓库 `smogon_data/`，未提交）。新增测试 `cache/test_usage_stats.py`（14 例全过），回归 36 例无破坏。

### 4.6.00（2026-08-19）

能力值分配改为 SP/EV 双视图体系。底层仍存储并计算原始 EV（保留 4 EV 精度）；override 新增 `sps` 字段（Champions 能力点数，`EV = 8×SP - 4`，32 SP = 252 EV，与 `evs` 并存且优先）；`calc`/`calc-raw`/`compute-stats` 返回 JSON 新增 `sps` 展示字段（`SP = (EV+4)//8`）；`optimize --mode` 默认恢复为 `ev`。SKILL 回答话术优先使用能力点数表述。测试 192/192 通过。

### 4.5.12（2026-07-10）

性格表修复：`lonely` 键带前导空格导致怕寂寞性格失效、`顽皮`/`乐天` 降低能力方向错误、缺 4 个无修正性格，修正为官方 25 性格完整表。KO 概率撒菱判断补充 Eelevate 特性免疫。`calculate_damage` 入口复制 move 防止优化器循环污染。测试 186/186。

### 4.5.7（2026-06-30）

系统性数据审计修复。关键修复：moves.json 约 55% 招式类型字段为英文导致晴天/雨天/属性道具/特性检查全部静默失效，新增英中映射归一化；实现斗争心、乘风、中毒激升、受热激升、干燥皮肤、焦香之躯等缺失特性；合并雷电拳重复条目。

### 4.5.6（2026-06-30）

SKILL.md 结构优化：合并核心原则 9→5 条消除语义重叠，修复双反引号语法错误，删除重复定义段落，805 行精简至 685 行。

### 4.5.4（2026-06-29）

新增 `survivability` 等效威力反查命令：给定防御方能力值与攻击方物攻/特攻，二分搜索无加成条件下的最大可承受招式威力（safe_bp / absolute_safe_bp 双安全线）。

### 4.5.2（2026-06-29）

修复妖精气场伤害加成未生效。首次引入 Champions SP 加点计算方式（optimize `--mode sp`，SP×8 直接转 EV，32 SP 上限）。后续 4.6.00 修正了换算公式并改为双视图设计。

### 4.5.0（2026-06-24）

适配 Champions M-B 规则：新增 6 个原创特性数据与伤害加成实现（龙皮肤一般→龙×1.2、火焰鬃毛火系×1.5、超级日光视为晴天、鳗鳗高升免疫地面），新增 4 个 patch 数据文件与运行时合并逻辑，Champions 数据优先加载。

### 4.4.4（2026-05-26）

`calc`/`calc-raw` 支持 `raw_stats` 字段直接传入最终能力值，跳过 EV/IV 反推。

### 4.4.2（2026-05-20）

新增 `filter-moves` 命令，支持按属性/分类/威力范围组合筛选招式。同日实现亲子爱特性（两段攻击，第二段 1/4 威力）与 Setdex 预设自动兜底匹配。

### 4.4.0（2026-05-15）

修复 pokemon.json 中 10 个条目 name_zh 编码乱码与 name_index.json 22 个 broken 映射；修复形态名称显示（"洗翠的样子"正确组合为"洗翠狙射树枭"）。

### 4.3.0（2026-05-14）

新增 `filter-pokemon` 命令，支持按属性/种族值范围/特性筛选宝可梦。

### 4.2.0（2026-05-14）

全特性修复 Phase 2：补全超级发射器、技术高手、强行、硬爪、强壮之颚、沙之力、分析、Supreme Overlord 等威力/攻击修正特性；新增 `ability_on` 动态激活字段。

### 4.0.0（2026-05-10）

架构大改动：moves.json 全部 242 个变化类招式添加 `stat_changes` 结构化标注，`query.py` 新增 `setup_moves` 集成实现剑舞/诡计等强化效果自动应用；修复扫墓/Last Respects 队友阵亡增威；抗性树果 Ghost/Dark 映射交叉错位修复。

### 3.9（2026-05-09）

修复 compute-stats 命名参数路由 Bug（性格名被映射到 ivs_json 导致性格修正丢失）；修复数据层中文与引擎层英文格式不匹配导致大量特性/道具/招式效果静默失效；修复双属性防御方属性相克倍率被重复计算的 Bug。

### 3.8（2026-05-09）

修复多属性宝可梦伤害计算 Bug 与特性不生效 Bug。

### 3.7（2026-05-08）

SKILL.md 漏斗形重构：1305 行压缩至 618 行，输出模板移至文档末尾，引入强制 `<plan>` 标签工作流，默认对战模式改为 Doubles。

### 3.6（2026-05-07）

首次整合《宝可梦冠军》(Pokémon Champions) M-B 规则数据，新增 4 个 patch 文件，Champions 数据优先于 Gen9 基础数据加载。

### 3.5（2026-05-07）

引入中间标准化层：新增 aliases.json 玩家俗称映射与 normalize.py，所有 resolve 函数接入标准化容错。新增 Setdex 预设配置功能（189 只宝可梦 264 个 VGC 预设）。

### 3.0（2026-05-01）

项目结构重组：scripts/ 仅保留 5 个核心运行时脚本，测试与工具归档至 cache/。修复形态选择索引与全角/半角匹配问题。

### 2.2（2026-05-01）

修复天气/场地参数无法识别的问题。

### 2.0（2026-04-30）

moves.json 从 349 条补充至 782 条（从 MOVES_SV 提取），补全 78 个分散招式 is_spread 标记。

### 1.0（2026-04-30）

初始版本：百科查询（Phase 1）、伤害计算引擎移植（Phase 2）、努力值优化（Phase 3）、等效威力反查（Phase 4）全部完成。

