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
│   ├── moves.json        # 招式数据（781 个，含 SV 全世代）
│   ├── abilities.json    # 特性数据
│   ├── type_chart.json   # 18x18 属性相克表
│   ├── name_index.json   # 中英文名称索引
│   ├── setdex.json       # VGC 预设配置（207 只，314 个预设：旧 VGC 预设 + 天梯双打 Top50 热门套）
│   ├── aliases.json      # 玩家俗称 → 标准名称映射
│   ├── usage_stats.json  # 环境使用率快照（pokecamp.cc / Limitless 赛事数据）
│   ├── meta_teams.json   # 近期赛事队伍快照（前 12 支，pokecamp.cc / Limitless 赛事数据）
│   └── teams_full.json.gz # 全量赛事队伍内置包（当前窗口全部队伍 + 完整明细，gzip 压缩）
└── scripts/
    ├── query.py          # 主查询入口（百科 + calc + lookup + preset + optimize + meta）
    ├── damage.py         # 伤害计算引擎（内部全英文枚举，经 engine_enums）
    ├── tera_effects.py   # 专属太晶触发效果与动态招式规则
    ├── battle_effects.py # 有效特性、树果阻断、环境／招式天气共用规则
    ├── speed_effects.py  # 实际速度，供动态威力和速度比较使用
    ├── ko_chance.py      # KO 概率计算
    ├── ev_optimizer.py   # 努力值优化搜索
    ├── models.py         # 数据模型（Pokemon, Move, Field, DamageResult）
    ├── engine_enums.py   # 引擎枚举单一来源（属性/性格/状态中英映射 + 纯解析函数）
    ├── display_zh.py     # 中文渲染层（全部面向用户的中文文案集中于此）
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
| `lookup <name>` | 宝可梦/招式/特性/道具 中英日名 | 轻量解析：返回 `{input, canonical_en, entity_type}`；未命中返回 error + suggestions | JSON 对象 |
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
| `survivability <defender> [attacker_stat] <category> [--def_ov JSON] [--field_ov JSON]` | 防御方 可选攻击方能力值 分类 | 中性承伤反查（能力值默认 200，50 级、1×、无本系、非要害、单发；配置与触顶字段见 references/commands.md） | JSON 对象 |
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

**move_override 可覆盖字段（白名单，V4.9.1 起引擎强制校验）**

`calc` 命令仅接受行为参数；白名单之外的字段（如 `base_power`/`type`/`category`）会被
**忽略**并在响应 `warning` 中列出（不静默）。`hits` 夹紧到 1-10 并告警。
需要直接改威力/属性/分类时使用 `calc-raw`（设计使然，不做白名单校验）。

```json
{
  "is_crit": false,
  "hits": 1,
  "fainted_allies": 0,
  "times_affected": 0
}
```

- `times_affected`：Rage Fist（愤怒之拳）已受击次数，威力 = 50 × (times_affected + 1)。
- 太晶输入：`is_terastalize` 仅接受 JSON 布尔值，开启时须指定合法的 `tera_type`（18 属性或 Stellar，接受中英繁体及英文大小写）。
- `stellar_boosted_types: []` 保存星晶已消耗首次增幅的属性，必须为有效属性名数组；默认空数组。`tera_effects_applied: false` 保存本次太晶触发效果是否已结算，必须为 JSON 布尔值。
- 太晶响应新增 `next_state`：`attacker`／`defender` 各含 `boosts`、`stellar_boosted_types`、`tera_effects_applied`、`item`；`field_override` 含实际 `weather`／`terrain`。这些字段可合并回原配置继续计算，HP 须另按实际伤害更新。`modifiers` 表示本次攻击使用的强化，`next_state` 表示攻击后的状态，星晶太晶爆发自降不会提前影响本次伤害。
- 响应 `warning` 字段还可能包含：SP 超限提示（`sps` > 32 或负数）、
  不可用形态提示（is_unobtainable）。

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

**auto-preset 自动兜底语义（V4.8.15 起）**

当宝可梦在 setdex 中且 override 未显式指定 `preset` 时，`calc` 自动匹配预设并返回额外字段：

| 字段 | 说明 |
|------|------|
| `attacker_auto_preset` / `defender_auto_preset` | 命中的预设名；未命中则不出现 |
| `attacker_auto_item` / `defender_auto_item` | 预设道具被自动套用时的道具中文名（仅白名单道具，见下）；未套用则不出现 |

选择规则：

1. **优先级分层**：只比较 `priority` 最高的预设层（天梯热门套 `priority: 1`，旧预设缺省 0），层内按 EV/方向相似度打分。
2. **部分指定努力值 → 完全跳过**：override 含 `evs` / `sps` / `raw_stats` / `stats` 任一字段时不套预设（用户给的分配即完整分配，未指定项 = 0 努力 + 无修正性格）。
3. **填充范围**：`evs` / `nature` / `ivs`（键级合并，用户值优先）；完全空配置时额外采用预设 `ability`。
4. **道具白名单**：仅纯增伤道具自动套用（Life Orb、Choice Band、Choice Specs、Expert Belt、Muscle Band、Wise Glasses）并以 `*_auto_item` 上报；判定触发类（文柚果、气势披带、树果等）与不加伤道具（讲究围巾）不兜底。用户显式指定的道具永远优先。
5. **形态永不切换**：预设中的 `form_name` 不参与 auto 填充（问水箭龟永远是水箭龟）；仅在用户显式引用 `preset` 时生效（如天梯套将 Mega 形态的 `form_name` 带入计算）。

**计算态与配置回显（V5.1.1 起）**

`calc`／`calc-raw` 保留双方配置中的特性和实际场地。气体、破格和护具通过有效特性规则作用于计算，不将配置里的特性清空。无关天气／气闸压制环境天气时，`field_info.weather` 仍是场上天气，并补充 `effective_weather: null`、`weather_suppressed: true`。Mega Sol 的招式天气单独计算，环境天气仍用于天气特性、天气增防和回合末结算。

陀螺球／电球及分析的比较使用实际速度，包括有效天气／场地特性、速度道具与麻痹等。`stats.speed` 回显仍是已应用能力等级的能力值，不把临时修正写回；调用者不要预先再乘这些倍率。普通连续攻击含可触发树果时，KO／优化使用逐击概率，`guaranteed` 要求全部分支满足，`likely` 要求至少 50%；静态场景保留原平均伤害契约。

#### preset 命令

setdex 预设条目字段：`level`、`evs`、`nature`、`ability`、`item`、`moves`、`ivs`（可选）及天梯套扩展字段 `priority`（int，auto 匹配分层用）、`usage_pct`（该套依据的天梯最高占比分配使用率）、`source`（数据来源与日期）、`form_name`（天梯特指形态，仅显式引用时生效）。扩展字段为透明度元数据，计算端忽略。

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
    damage: list[int]          # 已排序；普通单击 16 个，亲子爱独立乱数合计 256 个
    min_damage: int
    max_damage: int
    description: str
    is_critical: bool
    type_effectiveness: float
    stab_applied: bool
    burn_applied: bool
    move: Optional[Move]           # Final move used for the current attack
    effective_power: Optional[int]
    attacker_used: Optional[Pokemon]
    defender_used: Optional[Pokemon]
    attacker_after: Optional[Pokemon]
    defender_after: Optional[Pokemon]
    field_state: Optional[Field]
    field_used: Optional[Field]   # 本次有效环境；field_state 保留实际场地
    hit_damage_rolls: Optional[list[list[int]]] # 普通亲子爱逐击乱数，供树果 KO 使用
```

**已实现的修正**

- 属性相克（含 Stellar、Freeze-Dry、Flying Press 等特殊规则）
- STAB / 太晶化（含 Adaptability、星晶属性加成）
- 特性修正（30+ 种：Overgrow/Blaze/Torrent、Huge Power、Guts、Protosynthesis 等）
- 道具修正（生命宝珠、讲究头带/眼镜、突击背心、进化奇石、深海的牙齿/鳞片等）
- 场地/天气（晴天/雨天/沙暴/下雪、青草/电气/薄雾/精神场地）
- Ate/Ize 特性（Pixilate / Aerilate / Refrigerate / Galvanize / Normalize）
- 抗性树果（18 种；对应超有效伤害减半，Chilan Berry 对一般属性命中生效；紧张感／人马一体可阻止触发）
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
    *,
    battle_context: tuple[Pokemon, Pokemon, Move, Field] | None = None,
) -> str:
```

**输入**

- `damage`: `calculate_damage` 返回的 16 个乱数 roll 列表
- `move`: 攻击招式
- `defender`: 防御方宝可梦
- `field`: 场地条件
- `is_bad_dreams`: 是否处于噩梦状态
- `battle_context`: 原始双方、招式与实际场地，供有效特性／天气及状态逐击重算；公开命名／原始参数命令自动提供。只有合计多段伤害、缺少逐击数据时不能可靠判断回复果 KO。

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
    stellar_boosted_types: list[str]
    tera_effects_applied: bool
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
    is_multi_hit: bool = False  # Native move property, independent of hit override
    priority: int = 0
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
    move: Optional[Move]
    effective_power: Optional[int]
    attacker_used: Optional[Pokemon]
    defender_used: Optional[Pokemon]
    attacker_after: Optional[Pokemon]
    defender_after: Optional[Pokemon]
    field_state: Optional[Field]
```

---

### 6. pokecamp_source.py（环境数据源模块）

`meta` 命令的数据访问层，可插拔设计（旧命令 `usage` / `teams` 自动转发到 `meta`）：

- **数据源**：`PokecampSource` 类封装 pokecamp.cc 的静态 JSON 端点（Champions 规则，当前 M-C）；注册在 `SOURCES` 字典中，经 `get_source()` 获取。新增/更换数据源时实现同一组 fetch 方法并注册即可，`query.py` 无需改动。
- **三层数据**：内置快照（`data/usage_stats.json` / `data/teams_full.json.gz`）→ 在线缓存（`data/cache/`，gitignore）→ 实时拉取（`--online`，仅标准库 `urllib`，尊重 `HTTP_PROXY`/`HTTPS_PROXY`，请求 gzip 传输压缩）。网络失败沿反方向回退，返回的 `meta.origin` 标明实际来源（snapshot/cache/online），且 `meta.online_error` 携带失败原因供上层汇报用户。
- **--source 参数**：`--source tournament`（默认）走 pokecamp.cc 赛事数据；`--source ladder`/`ingame` 走官方实机排位数据（仅名次，日更）；`--source showdown` 走 Showdown 天梯月报（含使用率，月更滞后）。天梯源支持 `--format singles|doubles`（默认双打），不支持队伍类查询。
- **天梯数据层**（V4.8.09 新增）：总榜走 `pokemon-page/{ingame|showdown}.json` 轻量端点（约 230 KB），蒸馏后内置快照 `data/ladder_ingame.json`（39 KB）/ `data/ladder_showdown.json`（72 KB），维护者脚本 `cache/build_ladder_stats.py`。ingame 蒸馏时按 `speciesIdentifier` 合并 Mega 展开行，并丢弃 pokecamp 为统一结构填充的占位字段（usagePercent=0/teamCount=1/winRate=null），快照只保留真实名次。单只天梯详情走 `_next/data/{buildId}/.../pokemon/{id}.json`（gzip 约 127 KB/只，按宝可梦缓存 24h；buildId 从页面 HTML 自动发现并缓存，404 时重新发现重试一次），ingame 读 `detailBySource.ingame.inGameReferenceByFormat[format]`（配招/道具/特性/性格/努力为真实百分比，队友仅名次），showdown 读 `smogonReferenceByFormat[format]`；名称翻译复用响应内嵌的 itemMap/abilityMap/moveMap/teammateMap。天梯源 regulation 按数据源解析自 `data/regulation_manifest.json`（`pokecamp_source.ladder_regulation(kind)`）：官方实机排位 `ingame` 随新规则即时切换（当前 M-C），Showdown 月报 `showdown` 可能滞后一个规则（当前 M-B），因此不共用一个常量。已知上游：championsbattledata.com（官方排位数据的社区发布方，内容一致），仅作备选参考，不接入。
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
| `data/pokemon.json` | 1025 | `pokemon-dataset-zh` | 宝可梦百科数据（含 profile、prototype、图鉴、技能池、进化链）。forms 共 1320 个，其中 1131 个带规则推导并经 PokeAPI varieties 验证的 `name_en`（phase2 Step 2，报告 `cache/audit/form_name_en_report.md`） |
| `data/moves.json` | 781 | `pokemon-dataset-zh` + `script_res/move_data.js` | 招式数据。以 `MOVES_SV` 为权威来源补全了全部 SV 世代招式；`name_ja` 781/781 全覆盖（phase2 Step 1 经共享快照补全 431 条；唯一 PokeAPI 缺口 超极巨百火焚野=キョダイヒャッカ 经用户查证确认后填补） |
| `data/abilities.json` | 313 | `pokemon-dataset-zh` | 特性数据（含效果描述、拥有者列表） |
| `data/items.json` | 1386 | `pokemon-dataset-zh/item_list.json`（`cache/build_item_index.py` 生成） | 消费侧道具数据（phase2 Step 3）：英文规范名主键，`{name_zh, name_ja, name_en, effect, category}`，55 条带中文效果文本（自 query.py `_ITEM_EFFECTS` 逐字迁入）；`cmd_item` 读此文件。解析侧仍走 name_index items 段，两者职责分离。迁移完整性由 `cache/test_items_data.py` 守护 |
| `data/type_chart.json` | 18x18 | `script_res/` | 属性相克表。**决策登记（phase2 Step 4，2026-09-13）**：不加英文键——引擎加载时已经 `engine_enums.TYPE_ZH_TO_EN` 转为英文键，数据文件加英文键属双键冗余，反增一致性维护负担且零行为收益；官方克制表对账（check_data）已守护其正确性 |
| `data/name_index.json` | ~7500 | 自动生成 | 中英文名称双向索引（pokemon + moves + abilities + items）；items 段含日文键 1387 个（ja 解析复用）。与 items.json 同源不同职责：解析侧索引 vs 消费侧数据 |
| `data/setdex.json` | 207 只 / 314 预设 | `script_res/setdex_ncp-g9.js` + `cache/build_ladder_presets.py` | VGC 预设配置（性格、努力值、道具、特性、招式参考）。264 个旧 VGC 预设（Reg D/E 时代）+ 50 个天梯热门套 `天梯双打热门配置`（官方实机排位双打 Top50，2026-08-30，`priority: 1`；性格取聚合排行榜首——数据源 spread 行不带性格） |
| `data/aliases.json` | 2699 条（pokemon 1033 / moves 545 / abilities 293 / items 820 / natures 8） | 手工维护 + `cache/gen_rom_name_aliases.py` + zh-Hant/特性性格/招式旧名批次 | 输入容错别名（旧名→现行名、繁体、俗称）。守卫 `cache/check_aliases.py`；来源注记 `cache/alias_sources.md`。2026-09-13 name_audit Step 5 起：9 种宝可梦显示名更新为 2020 官方现行名（迭失棺/霸道熊猫/谜拟丘/狡小狐/猾大狐/电音婴/迭失板/多边兽２型/乙型），旧名转别名 |
| `data/champions_pokemon_patch.json` 等 4 件 | pokemon 231 / moves 778 / learnset 231 物种（含各形态） | `cache/build_champions_patch.py`（champout/ ROM 数据） | Champions 补丁层（当前 M-C）：形态名与本库命名体系对齐（纯外观形态已按数值比对剔除）、每个形态带 `regulation` 引入规则标签（M-A/M-B/M-C）、learnset 为 `{stem: {form: [moves]}}` 嵌套结构（按形态隔离，231 物种全覆盖）。重建后必跑 `cache/check_champions_patch.py`；`cache/champions_build_report.json` 为构建报告 |
| `data/regulation_manifest.json` | 3 条规则 + 数据源映射 | 手工维护 | 规则身份与顺序的唯一来源：`current`（当前规则）、`regulations[].order`（顺序）、`sources`（各数据源发布的规则）。运行时经 `scripts/regulations.py` 读取；新增/插入规则只改此文件 |
| `data/usage_stats.json` | 299 只 | pokecamp.cc（Limitless 赛事统计） | 环境使用率快照：排名、胜率、Top 招式/特性/道具/性格/SP 分配/队友（由 `cache/build_usage_stats.py` 构建） |
| `data/meta_teams.json` | 12 支 | pokecamp.cc（Limitless 赛事统计） | 近期赛事队伍轻量快照：全量索引不可用时的兜底（由 `cache/build_teams_pack.py` 从全量包派生） |
| `data/teams_full.json.gz` | 9,250 支 / 150 赛事 | pokecamp.cc（Limitless 赛事统计） | 全量赛事队伍内置包（gzip，约 1.4 MB）：全部队伍 + 道具/特性/性格/招式明细 + EN→ZH 名称映射；首次查询派生本地 SQLite 索引（由 `cache/build_teams_pack.py` 构建，原始数据留存于 gitignored 的 `pokecamp_data/`） |
| `data/ladder_ingame.json` | 231 只 | pokecamp.cc（官方实机排位，M-C） | 天梯名次快照（43 KB）：单/双打名次，Mega 已并入基础物种，占位字段已丢弃（由 `cache/build_ladder_stats.py` 构建） |
| `data/ladder_showdown.json` | 283 只 | pokecamp.cc（Showdown 天梯月报） | Showdown 使用率快照（72 KB）：单/双打名次 + 使用率，`meta.month` 注明月份（由 `cache/build_ladder_stats.py` 构建） |


### 数据修复记录

- **2026-04-30**: `moves.json` 从 349 条补充至 **781 条**。关键修复：从 `script_res/move_data.js` 的 `MOVES_SV` 提取全部 712 个招式，与现有数据合并，解决了"双翼"（Dual Wingbeat）等大量 SV 世代招式缺失的问题。

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
python cache/golden_baseline.py --check # 黄金快照（60 场景逐字节比对，重构/改引擎前后必跑）
python cache/regression_test.py       # Preset / 形态 / setup_moves 等，36 例
python cache/test_auto_preset_partial_ev.py  # auto-preset 语义（部分努力跳过/优先级/道具白名单/形态稳定，23 例）
python cache/test_usage_stats.py      # usage 环境查询（离线快照 + 在线回退，14 例）
python cache/test_teams_index.py      # 全量队伍索引（建库/筛选/聚合/增量抓取/回退，12 例）
python cache/test_meta_command.py     # meta 统一命令（推断/alias/--source，16 例）
python cache/test_ladder_source.py    # 天梯数据源（ladder/showdown 排行、单双打、Mega 合并、蒸馏/节流，23 例）
python cache/test_field_overrides.py  # 场地参数覆盖专项（30 用例）
python cache/test_filter_moves.py     # filter-moves 命令测试（14 例）
python cache/test_regulation_and_forms.py  # 规则模型与形态（20 例）
python cache/test_audit_fixes.py      # V4.9.1 审核修复回归（25 例）
python cache/test_round2_fixes.py     # V4.9.2 第二轮修复回归（32 例）
python cache/test_survivability.py    # 中性承伤反查（默认值、临界点、配置、校验与 CLI）
python cache/test_items_data.py       # items.json 迁移完整性（131 效果逐字 + cmd_item 兼容，4 例）
python cache/test_ja_query.py         # 日语查询（四实体类正例/归一化/歧义防御/zh-en 回归，11 例）
python cache/test_zh_hant.py          # 繁体输入（Tier 1 实体名抽样 + Tier 2 属性/性格枚举全量，14 例）
```

完整回归还包含 `cache/` 顶层全部 `test_review_*.py`、`test_tera_*.py`、`test_ogerpon_mask.py` 和 `test_fix511_*.py`。后者覆盖本次 13 项审查反例与交互，分组及运行方法见 `cache/README.md`；不运行 `archive/` 或历史 `audit510_*_probe.py` 的旧错误预期。

数据校验（非测试套件，数据更新后必跑）：`python cache/check_data.py`、`python cache/check_index.py`；重跑过 `cache/build_champions_patch.py` 后还需 `python cache/check_champions_patch.py`（9 断言）；引擎改动后还需 `python cache/check_engine_enums.py`（含太晶、有效特性和速度共用模块；不得含中文字符串字面量，注释除外）；别名更新后还需 `python cache/check_aliases.py`（别名层常驻守卫：目标存在/段内键唯一/空值自指/别名≠活规范名，任何违规非零退出；别名悬空检查的权威输出，name_audit 只消费不重复实现）；display_zh.py 或 engine_enums 表变更后还需 `python cache/check_display_names.py`（Tier 1 显示层嵌名交叉验证：IMMUNITY 字典严格对账/EOT 前缀词切分校验/枚举表一致性/嵌名清单落盘 cache/audit/tier1_embedded_names.md）。

旧版专项测试已归档于 `cache/archive/`（15 个，仅作历史参考，不再维护）。

## 性能与并发

调用模型为**每次查询一个独立 CLI 进程**（`python query.py <命令>`），无常驻服务。实测基线（Windows / Python 3.11.5，2026-09-13）：

| 指标 | 实测值 | 说明 |
|------|--------|------|
| 冷 CLI 调用（端到端） | ~0.77s | Python 启动 ~50ms + import ~115ms + 全量 JSON 加载 ~383ms（33.5MB）+ 计算/输出 ~10ms |
| calc（同进程热查询） | ~1.9ms/次 | 纯内存计算 |
| resolve_* / lookup 热查询 | 0.3~0.7ms/次 | 哈希查找；ja 索引首次构建 2ms（懒加载，2118 键） |
| 内存 | ~140MB/进程 | 33.5MB JSON 解析后 ~112MB Python 对象 + 解释器 |
| 并发 | 6 路并行 calc 1.45s（串行 4.42s） | 多进程多核并行；12 路混合 2.29s |

**并发安全模型**：查询之间无共享状态、无锁、无跨请求残留——并发只需受 CPU 核数与内存（~140MB × 并发数）约束。同一进程内多线程**读取**亦安全：全局数据仅在懒加载初始化时写入一次，之后全部只读，初始化竞态良性（并行构建产物一致，赋值原子）。跨查询持久化的只有磁盘缓存（`data/cache/teams_index.db`、`--online` 网络缓存），与内存无关。

如需低延迟高并发场景（如 Web 服务），可加常驻进程包装（一次性 ~0.5s 加载后单查询 ~2ms）；当前 Agent Skill 的 CLI 模型对 LLM 调用方式已足够。

---

## 发布到独立仓库（subtree split）

本目录通过 `git subtree split` 同步到独立仓库 [Einheriar/pokemon-calc-skill](https://github.com/Einheriar/pokemon-calc-skill)（本地 remote 名 `pokemon-calc`，默认分支 `main`）。在**本仓库根目录**、master 分支上执行：

```bash
git subtree split -P pokemon-calc -b pokemon-calc-branch
git push pokemon-calc pokemon-calc-branch:main
```

- **耗时**：全量重放 master 全部历史，约 2 分钟起，且随总提交数线性增长（Windows 上 git-subtree 逐提交 spawn 子进程，成本偏高）。更新频率低，可接受，属正常现象。
- **缓存**：`.git/subtree-cache/` 是 split 的工作缓存，删掉可自动重建（重建那次会从慢开始）。**不要**在 split 运行中途 Ctrl+C——容易留下半截缓存，下次更慢；让它跑完。
- **勿加 `--rejoin`**：会往 master 线性历史里塞合成 merge 提交（噪音），当前 master 零 merge，保持干净。
- 若未来推送变频繁、单次超过约 10 分钟，再考虑增量拆分方案（自定义 `rev-list`+`commit-tree` 脚本），届时按当时历史形态另写。

---

## 版本历史

版本号与 git commit 历史一致。仅记录有真实意义的功能/修复变动，跳过纯临时存档与琐碎备份。

### 5.1.1（2026-11-15）

- 修复复审全部 13 项：星晶自降的唱反调／单纯、太晶触发／甲壳与护具、波导防护、Champions 招式分类、英文 Mega 解析、亲子爱回复果、普通状态优化、树果阻断、有效特性／天气、实际速度和陀螺球公式。
- 共用规则覆盖气体／破格／护具，保留配置及实际场地；KO 对抗性果只消费一次。普通亲子爱逐击处理树果；复杂状态多段明确限制。实际速度计入能力等级、天气／场地、道具、麻痹及万能伞边界。347 形态全量验收另纠正超坏星旧别名。
- 新增 22 套专项，全部 **56 套回归、60 个黄金场景、6 项检查通过**后更新版本。黄金仅亲子爱一项按正确子击倍率阶段定点更新，独立数值断言通过，其余 59 项不变。计划及逐问题提交见 `plans/PLAN_2026-11-15_v5.1.1_audit_fixes.md` 和当天 CHANGELOG。

### 5.1.0（2026-11-15）

- 太晶专项补齐输入校验、太晶爆发转换保护、太晶甲壳完整相克／特性忽略，以及 60 威力保底与豁免。
- 新增星晶每属性消耗、太晶爆发自降及 `next_state`；KO 和优化逐次重算。补齐太乐巴戈斯形态、归零化境、晶光星群，以及厄诡椪面具、面影辉映、棘藤棒和觉醒之舞。
- 新增 11 套专项，全部 34 套回归、60 个黄金场景、6 项数据检查通过。黄金仅两项太晶场景按规则定点更新，独立卷积验证概率；其余 58 项不变。新增状态字段向后兼容，复杂状态多段／回合末组合仍明确提示限制。
- 按问题独立本地提交，全部验证通过后由 5.0.5 更新至 5.1.0。详见 `plans/PLAN_2026-11-15_tera_system.md` 与当天 CHANGELOG。

### 5.0.5（2026-11-15）

- 二次审查修复：恢复魔法防守的钉子免疫；精神冲击类防守优化与引擎共用防御项判断，冰鳞继续按特殊分类减伤；进化奇石资格按当前形态匹配进化链。
- 万能伞按攻防双方和效果分别处理，修正气象球、水蒸气、日光束、绯红脉动与已有晴雨特性结算，保留古代活性和队友花之礼例外。命中／充能等边界见 `references/mechanics.md`。
- 半血伤害最少 1 点，KO 逐次重算剩余 HP；蛮干／搏命的重复使用及复杂回复／持续伤害顺序明确提示限制。优化器对相关多次使用目标返回 `unsupported: true`。自然之怒英文名弯引号在适配层规范化。
- 太晶当前属性统一用于接地、场地及天气效果，原属性 STAB 保留；钉子按本回合太晶前入场状态结算。
- 全部 23 套回归、60 个黄金场景及 6 项数据检查通过，新增专项共 54 例；黄金快照无需修改。详见 `plans/CHANGELOG_2026-11-15.md`。

### 5.0.4（2026-11-15）

- 系统性修复已有伤害、KO、优化与输入处理错误：拆分精神冲击类招式的攻击分类与目标防御，校正太晶规则、动态招式修正、固定伤害、形态身份和最终招式回显。
- KO 计算按乱数分支独立维护 HP／树果状态；优化器扣除其他已分配 EV／SP；命令严格校验 JSON，伤害计算在私有副本上执行，不再污染调用方对象。
- 新增 `cache/test_engine_correctness_2026_11_15.py` 47 例专项回归；15 套现行回归、60 个黄金场景及全部数据／索引／补丁／枚举／别名／显示检查通过，781 个内置招式 smoke 无异常。黄金基线仅星晶太晶爆发属性回显与沙暴 2HKO 概率两处按修复结果定点更新。详见 `plans/CHANGELOG_2026-11-15.md`。

### 5.0.3（2026-10-15）

- 修复 `survivability` 的一般属性探针导致抗性/免疫污染结果。引擎新增私有 `_neutral_damage` 参数，仅由承伤反查启用，属性倍率固定 1×；保留真实属性及显式环境的防御修正，普通 `calc` 默认行为不变。
- 攻方能力值可省略，默认 200；兼容原显式参数用法和分类大小写。固定双方 50 级、无本系、非要害、单次单发；`safe_bp` 为 KO 概率 <15%，`absolute_safe_bp` 为非要害 KO=0，修正文档中的要害安全误述。
- 防御方 EV/SP/IV/性格、最终能力值及 HP 覆盖生效，不套自动预设。补严格输入校验、强化与环境冲突检查、覆盖文件读取失败保护、真实条件回显。
- 返回独立触顶标记 `safe_bp_capped` / `absolute_safe_bp_capped`、`search_max_bp` 和临界 KO 概率。上限仍为 500；触顶只能解释为下界。
- 新增 `cache/test_survivability.py` 专项回归，登记于测试清单。无数据补丁更新。

### 5.0.2（2026-09-16）

修复 ingame 天梯 `includes_mega` 误标并重刷天梯快照。`pokecamp_source.py` 合并循环
`else` 分支原无条件标 `includes_mega = True`，默认「同 speciesIdentifier 第二行必为
Mega」，致 19 只多形态物种（雌雄/地区/洛托姆/尺寸形态，如幽尾玄鱼、爱管侍、风速狗、
清洗洛托姆等）被误标含 Mega；改为仅当遇到真实 Mega 行才标记。重刷 `ladder_ingame.json`
后 `includes_mega: true` 由 95 降至 76 只，真实 Mega 物种标记不变；`ladder_showdown.json`
随本次一并重刷。顺带修正 `test_ladder_format_singles` 硬编码旧快照单打榜首（数据漂移）。
详见 `plans/CHANGELOG_2026-09-16.md`。

### 5.0.0（2026-09-13）

2026-09-12 计划族（alias_layer / zh_hant_support / phase2 / phase3）+ name_audit 独立质量流程全部实施，输入侧多语言大重构。执行 `plans/archive/EXECUTION_PLAYBOOK_2026-09-12[已实施].md`；详见 `plans/CHANGELOG_2026-09-13.md`。

- **解析语言支持矩阵（query 语言矩阵）**：

  | 实体 | 简体中文 | 英文 | 日文 | 备注 |
  |---|---|---|---|---|
  | 宝可梦（物种级） | ✓ | ✓ | ✓（1025/1025 name_ja） | ja 走运行时 `_build_ja_index()`（方案 b），`normalize_ja` 确定性归一（半角数字/中点/长音符），歧义 MISS 不静默择一 |
  | 招式 | ✓ | ✓ | ✓（781/781） | 第二批随 phase2 接入；唯一缺口 超极巨百火焚野=キョダイヒャッカ 经用户确认填补 |
  | 特性 | ✓ | ✓ | ✓（313/313） | 同上机制 |
  | 道具 | ✓ | ✓ | ✓（复用 name_index items 日文键 + 归一化重扫） | 1387 日文键原生可用 |
  | 属性/性格/状态 | ✓（+别名） | ✓ | — | 状态枚举英文本就是唯一输入契约；繁体全可用（22 条映射 + 21 条简繁同形） |

  解析优先级不变：zh/en 规范名 > ja > 别名/模糊；输出永远简体。黄金快照 60/60 逐字节不变。

- **数据层增补**（只加不改）：`data/items.json` 新建（1386 条，`_ITEM_EFFECTS` 131 键自 query.py 逐字迁出，`cmd_item` 改读数据层）；moves `name_ja` 补 431 条（交叉验证 349/349 一致后经共享快照补全）；forms `name_en` 1131 条（规则推导 + PokeAPI varieties slug 机械验证）。
- **共享基准**：`cache/pokeapi_names.json` 四语快照入库（物种 1025/1025、特性 312/313、招式 780/781、道具 1071/1386；miss 清单留档 `cache/_meta.miss`）。`cache/fetch_pokeapi_names.py` 断点续抓可复现。
- **SKILL.md 行为契约变更（phase3 Step 2）**：frontmatter 语言声明改为"简体中文、繁体中文、英文与日文"；输出模板三表（招式/环境/伤害结果）逐项标注响应字段路径（move_info.* / field_info.* / 顶层字段），结构化字段优先、description 降为核对用附注。命令与响应结构零改动。
- **别名层**：守卫 `cache/check_aliases.py` 常驻（DEVELOPER 数据校验清单登记）；种子 `地狱突刺→深渊突刺`；4 条反向别名按 PokeAPI 证据翻正。
- **新测试**：`test_items_data.py`（4 例）、`test_ja_query.py`（11 例）；`check_data.py` 增 name_ja 两态检查。
- **登记未处理 → 已由 name_audit 结案**：更名物种显示名、树果配对、BubbleBeam、磷火/鬼火各条于同日 name_audit Step 5 落地（见下）；上游 item_list.json 树果配对仍为旧值，`--with-index` 重建前须先修上游。

**人工批准批次（同日）**：繁体 Tier 1 入库（aliases.json 195→2608；形态推导字符映射由共享快照 hans/hant 成对名称对齐推导、出现 ≥2 次才采纳）；繁体 Tier 2 枚举（`TYPE_ZH_HANT_TO_EN` 8 / `NATURE_ZH_HANT_TO_EN` 14，PokeAPI×52poke 双源 0 不一致）；特性/性格别名（abilities 293 / natures 8）并修复 natures 别名段无运行时消费点问题；SKILL 语言声明同步。

**name_audit（Step 1–5 全部完成）**：新增 `check_display_names.py` Tier 1 嵌名守卫（57 条清单）；`check_names.py` 机械 diff（439 条，基准缺口留档）；只读子代理 58 条全部带 52poke 证据裁决（error 28 / variant 26 / unsure 4 → `cache/audit/flagged.json`），主线独立抽查 5 条全一致；Step 5 经用户批准落地——9 种宝可梦显示名更新为 2020 官方现行名（stem 不动、旧名转别名并反转 4 条反向别名）、树果索引配对修正 10 处/清理 4 混键、抗X果别名语义联动修正 11 条、20 条招式旧名别名、4 条 PokeAPI 缺口用户确认。

**收尾**：SKILL.md 增并发与状态说明、DEVELOPER.md 增「性能与并发」节（实测基线）。终态：黄金快照 60/60、7 守卫 + 14 套件全绿、aliases.json 2699 条。

### 4.9.3（2026-09-12）

引擎英文化 + 多语言转换层重构（Phase 1，见 `plans/archive/PLAN_2026-09-12_engine_english_multilang_EXECUTION[已实施].md`）。行为保持重构：60 场景黄金快照逐字节比对驱动（`cache/golden_baseline.py --check`）。

- **架构**：数据层（中文主键）→ 适配层（唯一翻译点：query.py/normalize.py + engine_enums/display_zh）→ 引擎（全英文枚举，与 damage_SV.js 同构）→ 输出（JSON 主体回显数据层语言 + 中文 description）。
- **新增模块**：`engine_enums.py`（18 属性 `T.*` 常量与中英映射、25 性格英文名表与别名容错、状态常量、`resolve_type_en`/`resolve_nature_en` 纯解析函数，全引擎唯一映射来源）；`display_zh.py`（引擎全部面向用户的中文文案集中于此，含 description 模板与 KO 过程文案）。
- **引擎**：damage.py/ko_chance.py/models.py 内部表示全面英文化（136+8 处类型字面量 → `T.*`；性格表/别名表/类型表迁至 engine_enums；`calculate_damage` 入口统一规范化 types/move.type/tera 输入）；`_ITEM_BOOST_MAP`/`_BERRY_ALIASES` 与全部双语道具比较的 zh 分支清除（道具输入由适配层 `_normalize_item_input` 统一规范化为英文，calc 与 calc-raw 双路径）。
- **适配层**：`query.py` 类型显示映射改由 engine_enums 派生；`calc` 在进引擎前对 types/nature/status 做白名单校验，非法值返回 `{"error", "suggestions"}`（不再静默穿透）；新增 `lookup <name>` 轻量解析命令（多语名 → 规范英文标识符）。
- **契约**：中文输入全部照旧合法；输出回显保持数据层语言（attacker_info.types/move_info.type 等）。SKILL.md 仅新增输入指引段（优先规范英文标识符 + lookup），输出模板未动。
- **测试**：新增 `cache/golden_baseline.py`（60 场景快照 + `--check`）与 `cache/check_engine_enums.py`（引擎四文件禁中文串字面量守卫）；test_round2_fixes 一用例的引擎层字面量随新契约改英文。

### 4.9.2（2026-09-12）

第二轮系统性审核修复（见 `plans/archive/PLAN_2026-09-12_round2_audit_fix[已实施].md`，V4.9.1 已先期复测通过）：

- **数据层**：type_chart.json 修正 2 处克制表错误（毒→岩石、妖精→火均误记 1.0，应为 0.5——calc/type 命令对这两组对局伤害多算一倍）；`check_data.py` 新增官方 18×18 克制表全量对账与 is_sound/is_bullet/is_wind/hits 标志对账；moves.json 补 龙箭 hits=2 与 16 个漏标标志（Eerie Spell/Barrage/Egg Bomb/Ice Ball/Octazooka/Aeroblast/Tailwind/Whirlwind 等）。
- **引擎（damage.py）**：Protosynthesis/Quark Drive 改按全能力最高项判定（原只比较攻/特攻，速度/防御最高的悖谬种特攻被虚加 30%）；Knock Off 不可摘除清单修正（Eviolite/White Herb 等 "ite" 启发式误伤，改例外集；补 Rusted Sword/Shield）；Solar Beam/Solar Blade 非晴天天气减半；电气上升/广域战力/薄雾爆炸补接地判定；亲子爱双打+扩散招式不再二段；清醒/唤醒巴掌条件翻倍；拳击手套（威力+接触豁免）；厄诡椪面具 1.2x；Fling 不可投掷道具；飘浮+铁球接地；灾祸四特性受中性气体压制；大晴天伞中文名修正为"万能伞"（原中文名为误记，英文死分支随之修复）；Flail/Reversal 精确阈值；场地种子增益不再跨调用累积（try/finally 回滚 + PB 递归 _skip_seeds）。
- **CLI 层（query.py / ev_optimizer.py）**：`_finalize_calc_pokemon` 派生 stats 并尊重显式 max_hp/current_hp（原 raw_stats+boosts 组合下 stats 为空、伤害 1-1；显式 max_hp 被 compute_raw_stats 覆盖）；`_apply_setup_moves` 同步重算 stats；calc 与 calc-raw 响应新增 `move_info`/`field_info`/`modifiers` 透明度键（SKILL.md 输出模板的招式/环境表自此有真实数据来源），accuracy 改读数据层；calc-raw 的 hits 字符串容错；survivability 的 stats/raw_stats 分离（boost 回写不再污染 raw）与 category 校验；2-5 段变段招式按期望 3 段估算并 warning；`_set_sp` 统一为 AGENTS.md 的 8×SP−4 换算；optimize 失败路径字段统一 0 + `max_invested_*`；champions 来源 find-move method 输出 "Champions"。
- **清理**：ko_chance.py 39 长度 squash 表删除（不可达）；query.py setup_moves 死代码与 resolve_move 不可达分支删除；normalize.py 重复 import 删除；`_AURA_MAP`/`_RESIST_BERRIES`/`_BERRY_ALIASES`/天气/场地映射表提模块级；`_check_seeds` 提出为模块级函数。
- **测试**：新增 `cache/test_round2_fixes.py`（32 例）；`test_regulation_and_forms.py` 的 form-key-miss 断言更新为 B4 回退语义（V4.9.1 变更未同步导致的失败，本轮修正并勘误）。

### 4.9.1（2026-09-12）

系统性代码审核修复（P0/P1 全量，见 `plans/archive/PLAN_2026-09-11_systematic_audit_fix[已实施].md`）：

- **引擎正确性（damage.py）**：
  - 移植 JS `immunityChecks` 全量免疫检查（Wonder Guard / 食草 / 引火 / 蓄电 / 飘浮 /
    大地吞噬 / 防弹 / 隔音 / 乘风 / 气球 / 大日照·下大雨绝对免疫 / Dazzling 类先制封锁 /
    精神场地先制封锁 / 食梦等），优先招式集合内置为 `_PRIORITY_MOVES`（数据层无 priority 字段）。
    免疫判定改用 Mold Breaker 感知的 `def_ability`（破格特性可正确穿透免疫）。
  - `Brine`（对手半血翻倍）与 `Venoshock`/`Barb Barrage`（对手中毒翻倍）判定拆分修正——
    原实现错误地判"攻击方自己半血"。
  - `base_power_func` 补全 JS 缺失分支：Stored Power/Power Trip（20+20×强化）、Punishment、
    Hex/Infernal Parade（对手异常 ×2）、Acrobatics（无道具 110）、Crush Grip/Wring Out/Hard Press
    （按**目标** HP 比例——JS 原文用攻击方 HP 属源码笔误，实施按游戏机制）、Triple Kick/Triple Axel
    （三段递增，按 hits 取平均每击威力）、Rage Fist（×(times_affected+1)，新增 `Move.times_affected`）、
    Tera Blast 星愿形态威力 100、Facade 状态集收紧（Burned/Paralyzed/Poisoned/Badly Poisoned）、
    Knock Off 排除不可摘除道具（Mega 石/Z 晶石/宝珠/种子等，`_cant_remove_item`）、
    Water Shuriken 改判 Battle Bond 特性。
  - Hydro Steam 晴天 1.5× 补入天气最终修正（原先反被晴天水招削弱规则砍半）；晴天伞排除改双语。
  - Punk Rock 攻击侧 1.3× 与 Steely Spirit 自身钢系 1.5× 补入 BP 修正组。
  - 双属性 effectiveness 重构（`_type_effectiveness_for` 每属性一次调用，对齐 damage_SV.js:122-123）：
    Scrappy/Ring Target/Freeze-Dry/Strong Winds 等特例此前只对第一属性生效——胆量打钢/幽灵的
    坚盾剑怪由错误 0× 修正为 0.5×。
  - 删除 Float Stone 死分支与 `base_power_func` 死参数 `turn_order`。
- **努力值优化器（ev_optimizer.py）**：`_set_ev/_set_sp` 同步清 `current_hp`（HP 池用新 max_hp，
  修系统性高估）；`optimize_bulk_evs` 统一走 `_set_ev/_set_sp`；多击招式判定补乘 `move.hits`
  （单攻/单防/联合搜索三处）；`--goal survive` 传 ko 型 target 时归一化（原直接 KeyError）。
- **KO 概率（ko_chance.py）**：`squash_multihit` 按 ko_chance.js:324-431 原文补齐 16 点表
  hits=4/6/7/8/9/10（V4.9.2 移除了 39 长度表——Python 伤害管线只产出 1/16/256 长度数组，该分支不可达）。
- **CLI 层（query.py）**：
  - `move_override` 白名单（`_MOVE_OVERRIDE_WHITELIST`）强制执行，非法字段进响应 `warning`，
    `hits` 夹紧 1-10；`calc-raw` 不受影响。
  - `main()` 两分支加 `except Exception` 兜底（输出 `{"error": ...}` 不再裸 traceback）；
    evs/ivs 等字典字段结构校验；filter-pokemon 非整数参数友好报错。
  - Champions 补丁加载区分"文件不存在"与"解析失败"（stderr 告警 + `_patch_load_error` 标记）；
    `learnset` 形态键未命中时回退基础形态键，仍失败则输出 `_data_source: gen9` +
    `_champions_patch_note`（花叶蒂案例不再静默降级）。
  - meta 四处外部数据调用 try 包裹，失败返回友好 `{"error", "meta"}` 结构。
  - SP 输入校验（>32/负数告警）；EV/SP 显示加 `sp_approx` 标记（249-251 EV → 31 SP 往返差 5-7 EV）。
- **名称归一化（normalize.py）**：清理零宽字符与空白；全角化仅用于含中文字符串（纯英文输入不再
  被误全角化）；`resolve_pokemon` 增加英文形态后缀兜底（`Charizard X` → 超级喷火龙Ｘ，含
  `_find_form_index` 半角 XYZ → 全角形态匹配）。中文裸后缀（"喷火龙Ｙ"）按设计**不**静默解析为
  Mega 形态，维持"未找到 + 建议"路径。
- **数据层（pokecamp_source.py / teams_index.py）**：详情/名单位置配对加长度失配告警
  （上游详情记录无 identity 字段，按键匹配不可行，已注明顺序假设）；teams 索引构建过滤缺 id
  脏记录；两模块 stderr 统一 UTF-8 reconfigure（GBK 控制台不崩溃）。
- **数据修复**：moves.json 为 Triple Kick/Triple Axel 补 `hits: 3`。
- **测试**：新增 `cache/test_audit_fixes.py`（25 例：白名单/免疫/威力分支/双属性/优化器/
  squash 表/学习面溯源/归一化/SP 标记/长度告警）。全部现行套件（回归 36 / auto-preset 23 /
  meta 16 / ladder 23 / teams 12 / usage 14 / field 30 / filter 14 / audit 25）通过，
  check_data / check_index 通过。

### 4.9.0（2026-09-11）

Champions 规则模型（M-A/M-B/M-C）+ champout v1.2.0 数据重建。核心变更：

- **规则模型**：新增 `data/regulation_manifest.json`（规则身份、顺序、各数据源发布规则）与 `scripts/regulations.py`（`current()` / `order_of()` / `rank_of()` / `source_regulation()` / `within()`，大小写不敏感）。规则**身份**以字符串标签（`"M-C"`）存于每条数据，**顺序**只在清单中声明，二者分离。
- **数据重建（champout v1.2.0，d2885a8 → 50e7233）**：`personal.json` 361 → 396 条，新增 35 个形态（M-C 的 Z 系 Mega：超级阿勃梭鲁Ｚ / 超级烈咬陆鲨Ｚ / 超级路卡利欧Ｚ / 超级戟脊龙，及 Mega 暴飞龙/具甲武者、新入池物种等）。每个形态由 `reg_no` 经 ROM 标签表（`rental_poke_appear_reg_ma/mb/mc`）翻译为规则标签。产出 pokemon 231 物种 / 347 形态（M-A 275 / M-B 38 / M-C 34）。
- **学习面 bug 修复（用户可见）**：学习面此前按物种作键、多形态 last-wins，导致关都九尾拿到阿罗拉九尾的冰系招式表。现改为 `{stem: {form: [moves]}}` 嵌套结构，按形态隔离；运行时 `_get_champions_learnset(stem, form_name)`、`cmd_learnset`、`_iter_moves`、`cmd_find_move` 均按形态取表。受影响 20 个物种（地区形态为主）。旧扁平结构仍兼容读取。
- **补丁 schema v2**：patch 文件写入 `_schema_version`；`check_champions_patch.py` 拆分为 3a–3f（含形态键合法性、空招式表、规则标签完整性断言），去重到有形态的物种。
- **天梯按源设规则**：移除单一 `LADDER_REGULATION` 常量，改由 `ladder_regulation(kind)` 从清单取值（`ingame` → M-C，`showdown` → M-B：Smogon 月报滞后一个规则）。`PokecampSource` 默认规则、蒸馏 fallback 亦改从清单取，消除多处硬编码。
- **隐藏规则参数**：内部 `--regulation <ID>` 提供累积视图（rank ≤ 选中规则），默认 = 最新规则全量并集（等于既有行为）。**不暴露给 LLM 查询层**（仅在 CLI 内部可用，见本文档）；作用域仅限形态/技能表可见性，不介入 `calc` 合法性判定。
- **测试**：新增 `cache/test_regulation_and_forms.py`（19 例：清单/规则标签/形态隔离/累积上限/旧格式兼容）；适配 `test_ladder_source`（按快照与按源规则断言）、`test_usage_stats`。全部现行套件（回归 36 / auto-preset 23 / meta 16 / ladder 23 / teams 12 / usage 14 / field 30 / filter 14）通过。

### 4.8.15（2026-08-30）

**champions 补丁名字污染根治**（设计文档：[`../plans/archive/PLAN_champions_name_pollution_fix_2026-08-30[已实施].md`](../plans/archive/PLAN_champions_name_pollution_fix_2026-08-30[已实施].md)）：

- **根因**：`cache/build_champions_patch.py` 把 ROM 文本表 `monsname_syn.json` 的内部出场序号误当图鉴号（图鉴 917 起错位且偏移无规律），造成 15 只跨物种名污染（狠辣椒 forms[0]=米立龙 等）、9 只译名变体、80 处形态名体系差异、23 只 learnset 静默丢失。数值计算从未受影响（stats/types/abilities 来自 `personal.json`，与名字查询无关）。
- **构建期修复**：物种匹配改纯 pokedex_id（本库 1025 stem 的图鉴号全唯一）；基础形态空名回退用本库 `forms[0].name`；形态名确定性规范化（直接命中 → 去中点 `帕底亚的样子・斗战种` → `X的样子` 前缀式 `阿罗拉雷丘`，`洛托姆的样子` 映射回基础形态）；learnset 循环复用 pokemon 侧匹配结果（`pokedex_id → stem`），learnset patch 185→208 键。无法规范化的纯外观形态按六维数值比对丢弃 48 个（彩粉蝶花纹/花洁夫人花朵/多丽米亚造型/怖思壶/霜奶仙奶香/来悲粗茶），新形态清单为空；6 只物种 patch 写空 forms（键保留以维持 learnset 对齐）。
- **运行时纵深防御**：`query.py::_apply_champions_pokemon_patch` 的 forms/stats 合并由"按索引位置"改为"按形态名匹配、未命中 append"——本库元数据（category/height/catch_rate/egg_groups）回到正确形态归属，未来 champout 顺序变化不再产生字段错配。
- **译名变体入 aliases.json**：新增 `cache/gen_rom_name_aliases.py` 自动生成（dex<917 且 ROM 名≠本库名且非另一物种名），+9 条（迭失棺→死神棺、谜拟丘→谜拟Ｑ、多边兽２型→多边兽Ⅱ 等），109→118 条；dex≥917 因索引错位不可反查（数据边界）。
- **自动化校验**：新增 `cache/check_champions_patch.py`（9 断言：形态名归属/无跨物种名/stats-forms 对齐/learnset 全覆盖/译名别名覆盖/运行时抽查），重建后必跑；构建脚本同时产出 `cache/champions_build_report.json`。4 个旧 patch 备份于 `cache/patch_backup_before_name_fix_2026-08-30/`。
- **验证**：8 套现行测试全绿 + check_data/check_index 通过；端到端（晶光花显示名/雷丘阿罗拉形态元数据/死神棺别名/狠辣椒 learnset 48 招式/天梯预设命中）全部通过。

**天梯 Top50 预设 + auto-preset 语义修复**（设计文档：[`../plans/archive/PLAN_ladder_presets_2026-08-30[已实施].md`](../plans/archive/PLAN_ladder_presets_2026-08-30[已实施].md)）：

- **auto-preset 部分指定努力值 bug 修复**：override 含 `evs`/`sps`/`raw_stats`/`stats` 任一字段时完全跳过预设——用户给的分配即完整分配，未指定项 = 0 努力 + 无修正性格；`sps` 补进构建字段白名单（此前 `{"sps":{"hp":32}}` 被误判为空配置、连特性都套预设）。
- **预设优先级**：setdex 条目支持可选 `priority`（int，缺省 0）；auto 匹配先取最高优先级层、层内打分。天梯热门套 `priority: 1` 压过旧 Reg-E 套，旧套保留可显式引用。
- **增伤道具白名单兜底**：预设道具属白名单（Life Orb / Choice Band / Choice Specs / Expert Belt / Muscle Band / Wise Glasses）时随 auto-preset 套用，返回 `attacker_auto_item` / `defender_auto_item`（中文名）；判定触发类（文柚果/披带/树果）与讲究围巾不兜底；用户显式道具永远优先。
- **形态永不切换**（用户明确规则）：auto-preset 不消费预设的 `form_name`——问水箭龟永远是水箭龟；`form_name` 仅在显式 `preset` 引用时经 `_apply_preset_to_override` 生效（白名单已含 `form_name`）。
- **天梯双打 Top50 热门套**：`cache/build_ladder_presets.py` 从官方实机排位双打 Top50（2026-08-30 数据）提炼 50 套 `天梯双打热门配置` 写入 setdex（最高占比努力分配 SP→EV + 性格（spread 行不带性格，回退聚合排行榜首）+ top 特性/道具/前4招式 + `usage_pct`/`source` 元数据），+22 只此前无预设的物种（炽焰咆哮虎、风妖精、铝钢桥龙、妙蛙花、全部 Mega 系等），setdex 189→207 只、264→314 套。Mega 形态经道具反查自动携带 `form_name`（含不规则英文名石的二层匹配），物种合并统计中的基础形态特性经形态特性表校验后丢弃（如喷火龙的 Blaze），引擎回退形态默认特性。合并前原始 setdex 备份于 `cache/setdex_backup_before_ladder_2026-08-30.json`。`--format singles` 可生成单打套 `天梯单打热门配置`（按 `singles_rank` 筛选）。
- **测试**：新增 `cache/test_auto_preset_partial_ev.py`（23 例），全部现行套件（回归 36 / meta 16 / ladder 23 / teams 12 / usage 14 / field 30 / filter 14）通过。

**文档准确性修正**：README 双语快速上手示例对齐实测值（`[111,132]`/12.5%，旧 `[130,154]/93.8%` 为历史遗留失真）并补 auto-preset 字段说明；本文件与 AGENTS 双语 / PROJECT_STATUS 的现状数据声明对齐实测（~39MB、781 招式、313 特性、name_index ~7500 条、207 只/314 预设、aliases 194 条：宝可梦 118 / 招式 3 / 道具 73）。

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

moves.json 从 349 条补充至 781 条（从 MOVES_SV 提取；实测 781，旧文误记 782），补全 78 个分散招式 is_spread 标记。

### 1.0（2026-04-30）

初始版本：百科查询（Phase 1）、伤害计算引擎移植（Phase 2）、努力值优化（Phase 3）、等效威力反查（Phase 4）全部完成。

