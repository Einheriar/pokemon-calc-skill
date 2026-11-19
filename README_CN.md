<div align="right">
  <a href="./README.md">🇺🇸 English</a> |
  🇨🇳 简体中文
</div>

# pokemon-calc: 面向 AI Agent 的宝可梦百科与伤害计算 Skill

**v5.2.0** 新增速度计算器：计算后自动附上附近速度线，正负范围可调，并支持顺风修正。详见 [speed 命令](references/commands.md#speed-速度计算器)。

传统宝可梦伤害计算器是给"人"用的网页或 App，而 `pokemon-calc` 是专为 **AI Agent (大语言模型)** 量身定制的底层计算 Skill。

本项目通过标准化的 CLI 接口和可复现的本地计算，降低 LLM 在宝可梦对战计算中编造数值的风险。计算结果应以 CLI 返回为准；这不能消除模型在解释结果或补充建议时出错的可能。

对已收录对应别名的实体，可使用简体中文、繁体中文、英文或日文名称查询。输出以中文说明为主，JSON 字段名使用英文规范键；没有 `--lang` 参数，自然语言翻译与回答由调用它的 Agent 负责。实体覆盖范围以本地数据为准。

## 这个 Skill 能做什么

支持两套加点体系：传统 Gen9 **努力值**（252/4/508 规则）与《宝可梦冠军》**能力点数 SP**（32/1/66 规则）。

### 百科与机制查询

| 功能 | 你可以这样问 |
|------|-------------|
| 查询宝可梦基础信息 | "喷火龙的种族值和属性是什么？" |
| 查询属性相克 | "妖精系打钢系效果怎么样？" |
| 查询招式详情 | "热风威力多少？命中和效果是什么？" |
| 查询特性效果 | "日照特性有什么效果？" |
| 查询持有道具 | "气势披带和讲究围巾有什么区别？" |
| 查询技能池 | "喷火龙能学会哪些火系招式？" |
| 查询进化链 | "伊布怎么进化成仙子伊布？" |
| 查询图鉴描述 | "梦幻在各代图鉴里怎么描述的？" |
| 查询热门配置 | "喷火龙有什么常用的 VGC 配置？" |

### 环境情报（默认离线快照）

环境查询统一走 `meta` 命令。默认读取随仓库提供的离线快照；快照覆盖范围和规则因数据源而异，不能视为同一赛制或实时数据：赛事使用率与队伍为 M-C、2026-10-16 至 2026-11-16，含 312 条使用率记录、135 场赛事、134 场有队伍数据，共 6,469 支完整队伍；官方实机天梯为 M-C、截至 2026-11-16（data version `20261116083343008`）的 262 条名次快照。只合并 `isMega=true` 且 `linkId` 明确指向对应非 Mega 形态的 Mega 行；其他非 Mega 形态，包括雌雄和地区形态，分别保留。Showdown 为 M-C、2026-10 月报（cutoff 1760，共 289 项）。单只天梯配招详情需联网获取。

| 功能 | 你可以这样问 |
|------|-------------|
| 使用率排行（`meta`） | "捆绑快照中使用率最高的宝可梦是谁？" |
| 单只赛事详情（`meta <名>`） | "捆绑赛事快照中，仆刀将军有哪些常见招式、道具和队友？" |
| 赛事队伍（`meta --teams`） | "已收录的赛事快照里有哪些队伍？" |
| 队友共现（`meta --teams --teammates`） | "在捆绑赛事快照里，炽焰咆哮虎最常和谁组队？" |
| 官方实机排位名次（`meta --source ladder [--format singles\|doubles]`） | "截至 2026-11-16 的天梯排位快照中谁排名最高？"（262 条，仅名次） |
| 天梯单只配招（`meta --source ladder <名> --online`） | "仆刀将军天梯最常带的 4 个招式是什么？" |
| Showdown 天梯月报（`meta --source showdown`） | "捆绑的 Showdown 月报（2026-10）中使用率是多少？"（cutoff 1760，月份见返回值） |

数据由 [pokecamp.cc](https://pokecamp.cc) 等来源整理。`meta` 默认使用捆绑快照；显式添加 `--online` 才会请求在线数据。赛事使用率排名刷新失败时，先回退到完整蒸馏后的在线缓存，再回退到捆绑快照；原始端点缓存不会冒充新鲜的完整结果。返回的 `meta.origin` 与 `meta.online_error` 标明实际使用的数据来源及在线请求错误。

使用 `--online` 且在线排名查询成功时，单只赛事环境详情可能把排名数据与单只宝可梦详情分开获取：`meta.origin`、`meta.date_range`、`meta.format` 描述排名数据；尝试单只详情查询时，`meta.detail_origin`、`meta.detail_fetched_at`、`meta.detail_date_range`、`meta.detail_format`、`meta.detail_online_error` 描述详情来源。两部分的数据来源和日期可能不同，回答排名/使用率与招式/道具/特性/能力点数配置时应分别引用对应元数据。`--source ladder`/`ingame` 是官方实机排位数据，离线快照仅有名次，单只配招/道具/性格/努力详情需 `--online`；`--source showdown` 是 Showdown 天梯月报，`--source showdown --online` 会请求 Showdown 对应规则的数据。天梯源支持 `--format singles|doubles`（默认双打），不支持队伍查询。旧命令 `usage` / `teams` 仍可用（自动转发到 `meta` 并输出弃用警告）。

### 伤害计算与优化

| 功能 | 你可以这样问 |
|------|-------------|
| 快速伤害计算 | "晴天下超级喷火龙Y的热风能打超级胡地多少？" |
| 努力值优化 | "喷火龙要多少特攻努力值才能确一水箭龟？" |
| 能力点数优化 | "宝可梦冠军（SP 系统：66/32/1）下喷火龙要加多少特攻 SP 才能确一水箭龟？" |
| 等效威力反查 | "对手宝可梦物攻能力值 200，我 185 HP 的地龙能扛多大基础威力的物理招式？" |
| 能力值计算 | "95攻击种族值、252努力值、固执性格、Lv.50 是多少攻击？" |
| 速度计算器 | "超级雷电兽内敛、32 速度 SP 的能力值是多少？附近正负 5 有哪些参照？" |

---

## 核心价值

### 1. 专为 Agent 设计：LLM 只做理解，不做计算

大语言模型擅长意图识别和参数提取，但在涉及大量查表和多级修正的数值计算时几乎必然出错。本项目采用解耦设计：

- **LLM 的工作**：将用户的自然语言（例如："晴天下，带命玉的满特攻 Mega 喷火龙 Y 用大字爆炎打极限特耐的暴露菇能秒吗？"）解析为结构化的 JSON 参数。
- **本引擎的工作**：接收参数，按已实现的常见对战修正（如 STAB、天气、道具、太晶化）进行确定性计算，并返回伤害乱数范围与 KO 概率；支持范围以引擎实现和查询结果为准，不代表覆盖所有机制。
- **纯函数接口**：所有查询与计算均通过单一入口 `query.py` 完成，输入输出结构明确（JSON In, JSON Out），极易被封装为 GPTs Action、Dify 插件或 MCP (Model Context Protocol) 工具。

### 2. 默认离线与仅依赖 Python 标准库

百科、计算及捆绑环境快照默认可离线使用；查询不会自动访问外部 API。`meta --online` 会请求在线数据；单只天梯配招详情需显式添加此选项，失败时按命令支持情况回退到快照或缓存。是否消耗模型 Token 取决于调用它的 Agent 和平台。

- **内聚静态数据**：`data/` 文件合计 34,636,873 字节（34.64 MB，十进制，19 个文件；不含运行时缓存）。包含图鉴、招式、特性、VGC 预设、环境快照和精选速度参照等数据，具体覆盖以各数据文件为准。
- **极简运行环境**：仅使用 Python 3.10+ 标准库。**不需要**安装 `numpy`、`pandas`，甚至不需要 `pip install` 任何第三方包。克隆即可运行，极为适合作为轻量级子模块集成到各类 AI 智能体项目中。

---

## 安装与使用

本项目是一个 Agent Skill，可直接安装到支持自定义 Skill 的 AI 编程助手或 Agent 框架中。

### 作为 Skill 安装

把仓库克隆到对应 Agent 的 skills 目录，并将目标文件夹命名为 `pokemon-calc`。各 Agent 的发现与加载机制不同，请按其官方文档配置：

```bash
git clone https://github.com/Einheriar/pokemon-calc-skill.git "$HOME/.claude/skills/pokemon-calc"  # Claude Code（全局；项目级用 .claude/skills/）
git clone https://github.com/Einheriar/pokemon-calc-skill.git "$HOME/.agents/skills/pokemon-calc"   # Codex
git clone https://github.com/Einheriar/pokemon-calc-skill.git "$HOME/.hermes/skills/pokemon-calc"  # Hermes Agent
```

Codex 和 Claude Code 的全局目录分别为 `~/.agents/skills/` 和 `~/.claude/skills/`；Hermes Agent 可使用 `~/.hermes/skills/`，具体加载方式见 [Hermes Agent 官方文档](https://hermes-agent.nousresearch.com/docs/user-guide/skills)。随后在对话中显式请求使用此 Skill，例如 `Use pokemon-calc to check if Mega Charizard Y can OHKO Amoonguss under sun.`。不同框架的发现和调用方式并不完全相同。

### 作为独立 CLI 工具使用

即使不接入任何 Agent 框架，也可直接作为命令行工具使用。尚未克隆时，将独立 Skill 仓库克隆为 `pokemon-calc` 并进入该目录；若已克隆独立 Skill 仓库，则直接从仓库根目录运行：

```bash
# 尚未克隆独立 Skill 仓库时：
git clone https://github.com/Einheriar/pokemon-calc-skill.git pokemon-calc
cd pokemon-calc
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟
# 已克隆独立 Skill 仓库时，在仓库根目录运行：
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟
```

---

## 快速上手

克隆项目后，无需安装任何依赖，直接使用 Python 运行：

### 1. 百科与机制查询

```bash
# 查询种族值与属性
python scripts/query.py stats 洗翠狙射树枭

# 查询招式详细机制
python scripts/query.py move 广域战力

# 查询属性克制关系
python scripts/query.py type 妖精 钢
```

### 2. 伤害计算引擎

采用位置参数与命名参数（覆盖配置）结合的方式。

```bash
# 基础快捷计算（默认 Lv.50 Doubles 环境）
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟

# 带复杂环境与配置覆盖的计算 (JSON 格式)
python scripts/query.py calc 超级喷火龙Y 热风 超级胡地 \
  --att_ov '{"evs":{"sp_attack":252},"nature":"内敛"}' \
  --def_ov '{"evs":{},"nature":"勤奋","form_name":"超级胡地"}' \
  --field_ov '{"weather":"Sun","format":"Doubles"}'
```

上面的多行写法使用 Bash 的 `\` 续行符。Windows PowerShell 用户可改用单行命令，或按 [`references/commands.md`](./references/commands.md) 使用 `--*_file` 参数传入 JSON。

返回示例（节选）：

```json
{
  "damage_range": [111, 132],
  "ko_chance": "12.5% 概率一击必杀",
  "type_effectiveness": 1.0,
  "stab_applied": true
}
```

> 说明：上例对攻守双方都显式指定了努力值，所以双方均跳过预设。未指定努力配置时，引擎可自动套用该侧的 setdex 预设（天梯热门套优先），并在返回值中以 `attacker_auto_preset` / `defender_auto_preset` 标注命中套名；预设携带纯增伤道具时另以 `attacker_auto_item` / `defender_auto_item` 标注。某一侧 override 一旦指定任一努力类字段（`evs`/`sps`/`raw_stats`/`stats`），该侧跳过预设。

### 3. 努力值 / 能力点数优化

支持两套能力值分配系统：Gen9 标准努力值（默认）和《宝可梦冠军》(Pokémon Champions) 能力点数（SP）。

```bash
# Gen9 努力值模式（默认）：搜索达到确一目标所需的最低特攻努力值；若目标不可达会返回失败结果
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko

# Champions 能力点数模式（SP）：搜索达到确一目标所需的最低特攻 SP；若目标不可达会返回失败结果
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko --mode sp
```

这两个示例在当前默认配置下会返回 `success: false`，说明即使达到搜索上限也无法确一；优化结果会随查询参数变化。

| 模式 | 参数 | 总点数 | 单项上限 | 步进 | Lv.50 能力值增长 |
|------|------|--------|----------|------|----------------|
| Gen9 努力值 | `--mode ev`（默认） | 508 | 252 | 4 | 每项能力按 4 EV 步进；能力值增量还取决于等级、个体值、种族值和性格取整 |
| Champions 能力点数 | `--mode sp` | 66 | 32 | 1 | `SP>0` 时对应 `EV=8×SP−4`，`SP=0` 对应 `EV=0`；实际能力值增量受等级、个体值和性格取整影响 |

---

## 完整对话示例

### 示例：超级喷火龙Y 热风 vs 超级胡地

**用户提问：** 252特攻的mega喷火龙Y，性格修正特攻，晴天下打热风技能，能打mega胡地多少血？

**Agent 的 `<plan>`：**

```text
<plan>
1. 提取指令信息：攻方 = 超级喷火龙Y | 守方 = 超级胡地 | 招式 = 热风
2. 环境决策强制检查：
   - 用户明确提及天气：是，晴天（Sun）
   - 用户明确提及单打/双打：否，强制推断为 Doubles
3. 危险动作核对：
   - 我是否试图在 plan 阶段预设能力值、努力值、性格或伤害数字？否
   - 我是否打算凭内部记忆解释属性相克、特性效果或招式机制？否
4. 即将执行的精确命令：
   python scripts/query.py calc 超级喷火龙Y 热风 超级胡地 --att_ov '{"evs":{"sp_attack":252},"nature":"内敛","form_name":"超级喷火龙Ｙ"}' --field_ov '{"weather":"Sun","format":"Doubles"}'
</plan>
```

**Agent 最终回答（节选）：**

> ## 结论摘要
>
> 252 特攻努力值、内敛性格的超级喷火龙Y，在晴天下对超级胡地使用热风，**伤害范围 111～132**。超级胡地最大 HP 为 130，因此**有 12.5% 的概率一击必杀**（16 个乱数中 130 和 132 两个 roll 可击杀）。
>
> ### 攻击方详细信息
>
> | 项目 | 数值 |
> |------|------|
> | 属性 | 火 / 飞行 |
> | 特性 | 日照（可选：日照） |
> | 等级 | Lv.50 |
> | 种族值 | HP 78 / 攻击 104 / 防御 78 / 特攻 159 / 特防 115 / 速度 100 |
> | 个体值 | 全 31 |
> | 努力值 | HP 0 / 攻击 0 / 防御 0 / 特攻 252 / 特防 0 / 速度 0 |
> | 性格 | 内敛（特攻↑ / 攻击↓） |
> | 实际能力值 | HP 153 / 攻击 111 / 防御 98 / 特攻 **232** / 特防 135 / 速度 120 |
> | 道具 | 喷火龙进化石Ｙ |
> | 太晶化 | 否 |
> | 能力等级变化 | 全 0 |
> | 状态异常 | 无 |
>
> ### 防御方详细信息
>
> | 项目 | 数值 |
> |------|------|
> | 属性 | 超能力 |
> | 特性 | 复制（可选：复制） |
> | 等级 | Lv.50 |
> | 种族值 | HP 55 / 攻击 50 / 防御 65 / 特攻 175 / 特防 105 / 速度 150 |
> | 个体值 | 全 31 |
> | 努力值 | 全 0 |
> | 性格 | 勤奋（无修正） |
> | 实际能力值 | HP **130** / 攻击 70 / 防御 85 / 特攻 195 / 特防 125 / 速度 170 |
> | 道具 | 胡地进化石 |
> | 太晶化 | 否 |
> | 能力等级变化 | 全 0 |
> | 状态异常 | 无 |
> | 当前 HP / 最大 HP | 130 / 130 |
>
> ### 伤害计算结果
>
> | 项目 | 数值 |
> |------|------|
> | 伤害范围（单次） | 111 ～ 132 |
> | 属性相克倍率 | 1.0x |
> | 是否触发 STAB | 是 |
> | 天气加成 | 是（晴天火系威力 ×1.5） |
> | KO 概率 | **12.5% 概率一击必杀** |
>
> **综合判断**：结论仅适用于上述已计算的配置与环境。

---

## 领域功能特性

底层引擎覆盖常见查询场景，具体支持范围以实现和查询结果为准：

- **图鉴与双层数据架构**：收录全国图鉴 1~1025 号的宝可梦数据与部分形态（包括 Mega、原始回归和地区形态；不承诺穷尽所有形态）。底层整合 Gen9（朱紫）数据与《宝可梦冠军》规则数据（当前 M-C，champout v1.2.0 / 2026-09-11）。Champions 形态带有引入规则标签（M-A/M-B/M-C）。
- **VGC 实战预设**：当前内置 208 个 setdex 种类键、314 个对战预设——264 个旧预设及 50 个完整官方实机双打天梯 Top50 热门套（来源日期为 2026-11-16，50 条单只宝可梦详情均已取得，2026-11-17 构建）。爱管侍与幽尾玄鱼的雄性、雌性战斗形态分别配置，不互相套用。auto-preset 优先使用适配当前形态的天梯套，priority 字段分层共存；配置某一侧的努力类字段会跳过该侧预设，形态不会自动切换。
- **努力值逆向优化 (EV Optimizer)**：不仅能算伤害，还能"反推"努力值。自动搜索满足"确一 (OHKO)"或"确二生存"目标的最低努力值配置。
- **人类语言容错 (Normalize 层)**：内置"老喷"、"命玉"、"抗斗果"等玩家俗称与官方标准译名的自动映射，另覆盖 ROM 官方译名变体（如"迭失棺"→死神棺、"霸道熊猫"→流氓熊猫），降低 LLM 实体提取的难度。

---

## 架构与工作流

```text
用户自然语言提问
      |
      v
+---------------+
|  AI Agent     | 负责理解语义、提取实体与参数、查询百科补全缺失信息
+-------+-------+
        | 构建完整 CLI 命令 (JSON 覆盖参数)
        v
+---------------+
|   query.py    | 命令行单一入口
+-------+-------+
        | 路由分发
        v
+---------------+
|   damage.py   | 纯参数驱动的固定计算程序（调用本地 data/*.json）
+-------+-------+
        | 返回精确数值结果 (DamageResult JSON)
        v
+---------------+
|  AI Agent     | 将 JSON 数据格式化为自然语言、表格及当前问题所需的说明
+-------+-------+
        |
        v
给用户的最终专业回答
```

---

## 开发者与集成指南

如果你想将此项目集成到你的大模型应用中，请参阅以下文档：

- **[`SKILL.md`](./SKILL.md)**：这是专门写给 LLM 读的 System Prompt（系统指令）。包含了完整的行为规范、思维链（`<plan>`）要求和工具调用定义。直接将其内容注入到你的 Agent Prompt 中即可让 LLM 掌握如何使用本引擎。
- **[`DEVELOPER.md`](./DEVELOPER.md)**：人类开发者技术文档，包含完整的 I/O 规范、JSON Schema 定义与内部架构说明。

---

## 数据来源与致谢

- **1~9 世代宝可梦百科数据**：爬虫数据来自 [42arch/pokemon-dataset-zh](https://github.com/42arch/pokemon-dataset-zh)
- **《宝可梦冠军》(Pokémon Champions) 规则数据（当前 M-C）**：游戏 ROM 抓取与解析来自 [projectpokemon/champout](https://github.com/projectpokemon/champout)（v1.2.0）
- **VGC 伤害计算器前端逻辑**：基于 [VGC Damage Calculator](https://professorsidon.github.io/VGC-Damage-Calculator-Chinese/) 的 JavaScript 引擎移植与重构
- **环境情报数据（使用率 / 赛事队伍）**：来自 [pokecamp.cc](https://pokecamp.cc)（数据源于 Limitless 公开赛事统计），特此致谢

> **爬虫说明**：本项目对 pokecamp.cc 的访问是克制的按需抓取，并非批量爬虫——只在用户显式要求最新数据（`--online`）或维护者定期刷新内置快照时发起少量请求，结果一律本地缓存复用，不遍历站点页面，并遵守其 robots.txt。若 pokecamp.cc 方面对此有任何疑虑，请提交 Issue 联系，我们会及时调整。

---

## 致谢

本项目由 [Kimi K2.6](https://kimi.moonshot.cn) 通过 **vibe coding** 方式构建。

## 许可证

MIT License
