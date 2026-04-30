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
├── SKILL.md              # Skill 使用说明与 LLM 规范
├── README.md             # 本文件（技术文档）
├── data/
│   ├── pokemon.json      # 宝可梦百科数据（1025 只）
│   ├── moves.json        # 招式数据（782 个，含 SV 全世代）
│   ├── abilities.json    # 特性数据
│   ├── type_chart.json   # 18x18 属性相克表
│   └── name_index.json   # 中英文名称索引
└── scripts/
    ├── query.py          # 主查询入口（12 个子命令）
    ├── damage.py         # 伤害计算引擎
    ├── ko_chance.py      # KO 概率计算
    ├── ev_optimizer.py   # 努力值优化搜索
    ├── models.py         # 数据模型（Pokemon, Move, Field, DamageResult）
    ├── build_item_index.py   # 道具索引构建工具
    ├── check_data.py         # 数据完整性检查
    ├── test_damage.py        # 伤害计算单元测试
    ├── test_ko.py            # KO 概率单元测试
    └── test_ev_optimizer.py  # 努力值优化单元测试
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
| `type <atk> <def>` | 攻击属性 防御属性 | 属性相克倍率与描述 | JSON 对象 |
| `stats <name>` | 宝可梦名 | 各形态种族值与总和 | JSON 对象 |
| `weak <name>` | 宝可梦名 | 弱点、抗性、免疫列表 | JSON 对象 |
| `learnset <name>` | 宝可梦名 | 升级/TM/遗传/教学招式 | JSON 数组 |
| `evo <name>` | 宝可梦名 | 进化链与超级进化 | JSON 对象 |
| `pokedex <name>` | 宝可梦名 | 各版本图鉴描述 | JSON 数组 |
| `profile <name>` | 宝可梦名 | 外形描述、原型考据、多语言词源 | JSON 对象 |
| `find-move <move>` | 招式名 | 反向查询：能学会该招式的所有宝可梦 | JSON 数组 |
| `calc <attacker> <move> <defender> [att_override] [move_override] [def_override]` | 攻击方 招式 防御方 | 快速伤害计算（默认 Lv.50） | JSON 对象 |
| `optimize <attacker> <move> <defender> [goal] [target] [threshold] [att_override] [def_override]` | 攻击方 招式 防御方 目标 阈值 确信度 | 努力值优化搜索 | JSON 对象 |

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

---

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

## 数据资产清单

| 文件 | 条目数 | 来源 | 说明 |
|------|--------|------|------|
| `data/pokemon.json` | 1025 | `pokemon-dataset-zh` | 宝可梦百科数据（含 profile、prototype、图鉴、技能池、进化链） |
| `data/moves.json` | 782 | `pokemon-dataset-zh` + `script_res/move_data.js` | 招式数据。以 `MOVES_SV` 为权威来源补全了全部 SV 世代招式 |
| `data/abilities.json` | ~307 | `pokemon-dataset-zh` | 特性数据（含效果描述、拥有者列表） |
| `data/type_chart.json` | 18x18 | `script_res/` | 属性相克表 |
| `data/name_index.json` | ~4000 | 自动生成 | 中英文名称双向索引（pokemon + moves + abilities） |

### 数据修复记录

- **2026-04-30**: `moves.json` 从 349 条补充至 **782 条**。关键修复：从 `script_res/move_data.js` 的 `MOVES_SV` 提取全部 712 个招式，与现有数据合并，解决了"双翼"（Dual Wingbeat）等大量 SV 世代招式缺失的问题。

---

## 使用示例

```bash
# 百科查询
python scripts/query.py stats 喷火龙
python scripts/query.py type 水 火
python scripts/query.py weak Charizard

# 伤害计算
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟
python scripts/query.py calc 化石翼龙 "Dual Wingbeat" 胡地 '{"evs":{"attack":252,"speed":252}}' '{}' '{"evs":{}}'

# 努力值优化
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 ko ohko guaranteed
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 survive survive guaranteed
```

---

## 依赖

- Python 3.10+
- 仅使用标准库（`json`, `math`, `pathlib`, `typing`, `dataclasses` 等）
- 无需 pip/uv 安装任何第三方包

---

## 测试

```bash
python scripts/test_damage.py
python scripts/test_ko.py
python scripts/test_ev_optimizer.py
```
