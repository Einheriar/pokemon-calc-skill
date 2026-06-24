<div align="right">
  🇺🇸 English |
  <a href="./README_CN.md">🇨🇳 简体中文</a>
</div>

# pokemon-calc: Pokédex & Damage Calculator for AI Agents

Traditional Pokémon damage calculators are web apps or tools built for humans. `pokemon-calc` is a purpose-built computation engine designed for **AI Agents (Large Language Models)**.

By providing standardized pure-function CLI interfaces and fully localized static data, this project eliminates the **numerical hallucinations** that LLMs commonly produce when handling complex multiplicative modifiers in Pokémon battles (type matchups × abilities × items × weather × terrain).

---

## Core Values

### 1. Designed for Agents: LLM Understands, Engine Computes

Large language models excel at intent recognition and parameter extraction, but they inevitably fail at numerical calculations involving extensive table lookups and multi-level modifiers. This project decouples the two responsibilities:

- **LLM's Job**: Parse natural language (e.g. "Can Life Orb max SpA Mega Charizard Y OHKO max SpD Amoonguss in Sun?") into structured JSON parameters.
- **Engine's Job**: Receive parameters, execute deterministic calculations covering 40+ modifiers (STAB, weather, items, Tera, etc.), and return exact damage ranges and KO probabilities.
- **Pure-Function Interface**: All queries and calculations flow through a single entry point, `query.py`, with well-defined JSON In / JSON Out semantics. This makes it trivial to wrap as a GPTs Action, Dify plugin, or MCP (Model Context Protocol) tool.

### 2. 100% Local & Zero External Dependencies

No database configuration, no external API calls (avoiding network latency and token consumption). Truly out-of-the-box:

- **Embedded Static Data**: ~38 MB of preprocessed JSON data (National Dex #1–1025, 782 moves, abilities, VGC sets, etc.) all bundled inside.
- **Minimal Runtime**: Python 3.10+ standard library only. **No** `numpy`, **no** `pandas`, **no** `pip install` of any kind. Clone and run — ideal as a lightweight submodule for any AI agent project.

---

## Installation & Usage

This project is an Agent Skill that can be installed into any AI coding assistant or agent framework that supports custom skills.

### Install as a Skill

Assuming you have cloned this repo and are at the repository root.

#### Codex

```bash
mkdir -p "$CODEX_HOME/skills"
cp -R pokemon-calc "$CODEX_HOME/skills/"
```

Usage example:

```text
Use $pokemon-calc to check if Mega Charizard Y can OHKO Amoonguss under sun.
```

#### Claude Code

Supports either global or project-level installation.

Global:

```bash
mkdir -p "$HOME/.claude/skills"
cp -R pokemon-calc "$HOME/.claude/skills/"
```

Project-level:

```bash
mkdir -p .claude/skills
cp -R pokemon-calc .claude/skills/
```

In prompts, explicitly request this skill, for example:

```text
Please use the pokemon-calc skill to run a damage calc.
```

#### Hermes Agent

Tested and verified to work with Hermes Agent. Install the Skill folder into your Agent's skills directory and reference it in conversations.

### Use as a Standalone CLI Tool

Even without an Agent framework, you can run it directly from the command line:

```bash
cd pokemon-calc
python scripts/query.py calc Charizard Flamethrower Blastoise
```

---

## Quick Start

After cloning, no dependencies to install — just run with Python:

### 1. Encyclopedia & Mechanics Queries

```bash
# Query base stats and typing
python scripts/query.py stats Hisuian Decidueye

# Query move mechanics
python scripts/query.py move Expanding Force

# Query type matchup
python scripts/query.py type Fairy Steel
```

### 2. Damage Calculation Engine

Combines positional arguments with named override parameters.

```bash
# Basic quick calc (defaults to Lv.50 Doubles)
python scripts/query.py calc Charizard Flamethrower Blastoise

# Complex calc with environment and config overrides (JSON)
python scripts/query.py calc "Mega Charizard Y" Heat Wave "Mega Alakazam" \
  --att_ov '{"evs":{"sp_attack":252},"nature":"Modest"}' \
  --def_ov '{"item":"Choice Scarf"}' \
  --field_ov '{"weather":"Sun","format":"Doubles"}'
```

Sample response (excerpt):

```json
{
  "damage_range": [130, 154],
  "ko_chance": "Approx. 93.8% chance to OHKO",
  "type_effectiveness": 1.0,
  "stab_applied": true
}
```

### 3. EV Reverse Optimization

```bash
# Search for minimum SpA EVs needed to guarantee the OHKO
python scripts/query.py optimize Charizard Flamethrower Blastoise --goal ko --target ohko
```

---

## Real-World Examples

> The following examples are shown in Chinese to preserve the authentic interaction style of this Skill, which defaults to Chinese queries.

### Example 1: Mega Charizard Y Heat Wave vs Mega Alakazam in Sun

**User:** 252特攻的mega喷火龙Y，性格修正特攻，晴天下打热风技能，能打mega胡地多少血？

**Agent's `<plan>`:**

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

**Agent's final answer (excerpt):**

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
> **综合判断**：超级胡地特防 125 且 HP 仅 130，面对晴天下超级喷火龙Y的热风非常脆弱。虽然大部分情况不会被确一，但残血时基本必死。

---

### Example 2: Hisuian Decidueye Triple Arrows vs Kingambit with Chople Berry

**User:** 洗翠狙射树枭，252攻击，性格修正攻击，打三连箭，防守方是252HP，带抗斗果的的钢兵，钢兵能不能接？

**Agent's final answer (excerpt):**

> ## 结论摘要
>
> **对仆刀将军（Kingambit）：不能 OHKO，确定 2HKO。** 携带抗斗果（巧可果）的 252HP 仆刀将军可以稳稳接下洗翠狙射树枭的三连箭，最少剩 51 血。
>
> **对劈斩司令（Bisharp）：约 31.2% 概率 OHKO，多数情况接下后残血。**
>
> ---
>
> ### 攻击方详细信息
>
> | 项目 | 数值 |
> |------|------|
> | 属性 | 草 / 格斗 |
> | 特性 | 茂盛（可选：茂盛 / 远隔） |
> | 等级 | Lv.50 |
> | 种族值 | HP 88 / 攻击 112 / 防御 80 / 特攻 95 / 特防 95 / 速度 60 |
> | 个体值 | 全 31 |
> | 努力值 | HP 0 / 攻击 252 / 防御 0 / 特攻 0 / 特防 0 / 速度 0 |
> | 性格 | 固执（+攻击 / -特攻） |
> | 实际能力值 | HP 163 / 攻击 **180** / 防御 100 / 特攻 103 / 特防 115 / 速度 80 |
> | 道具 | 无 |
> | 太晶化 | 否 |
>
> ### 防御方详细信息（仆刀将军 Kingambit）
>
> | 项目 | 数值 |
> |------|------|
> | 属性 | 恶 / 钢 |
> | 特性 | 不服输（可选：不服输 / 大将 / 压迫感） |
> | 等级 | Lv.50 |
> | 种族值 | HP 100 / 攻击 135 / 防御 120 / 特攻 60 / 特防 85 / 速度 50 |
> | 个体值 | 全 31 |
> | 努力值 | HP 252 / 其余 0 |
> | 性格 | 勤奋（无修正） |
> | 实际能力值 | HP **207** / 防御 **140** |
> | 道具 | **巧可果（抗斗果，格斗伤害减半）** |
> | 当前 HP / 最大 HP | 207 / 207 |
>
> ### 伤害计算结果（对仆刀将军）
>
> | 项目 | 数值 |
> |------|------|
> | 伤害范围（单次） | 132 ～ 156 |
> | 属性相克倍率 | 4.0x（格斗 vs 恶/钢） |
> | 是否触发 STAB | 是 |
> | 道具加成（巧可果） | 是，伤害减半 |
> | KO 概率 | **确定 2 击必杀** |
> | 最大伤害占 HP 比 | 156 / 207 = **75.4%** |
>
> **综合判断**：
> - **不能一击秒杀**。最小剩余 HP = 207 - 156 = **51**
> - 必为 2HKO，巧可果有效保命
>
> ### 伤害计算结果（对劈斩司令 Bisharp）
>
> | 项目 | 数值 |
> |------|------|
> | 伤害范围（单次） | 152 ～ 182 |
> | KO 概率 | **31.2% 概率一击必杀** |
> | 最小/最大剩余 HP | -10（秒杀） / **20**（存活） |
>
> **综合判断**：有 31.2% 概率被 OHKO，约 68.8% 概率接下并剩 2～20 血（残血）。
>
> ## 总结
>
> 带巧可果的 252HP 仆刀将军可以稳稳接下洗翠狙射树枭的三连箭，确认为 2HKO，最小剩 51 血，绝不被 OHKO。若用户本意是原始劈斩司令，则有约 31.2% 概率被 OHKO。

---

## Domain Features

Despite being a low-level engine, it makes no compromises on competitive rule coverage:

- **Full National Dex & Dual-Layer Data Architecture**: Supports all forms of #1–1025 (including Mega, Primal, regional forms). Underlying data integrates Gen9 (Scarlet/Violet) official data with *Pokémon Champions* M-B rules (updated 2026-06-24).
- **VGC Battle Presets**: 264 pre-built sets across 189 Pokémon. When the LLM encounters a query without explicit EVs, it can fall back to a preset.
- **EV Reverse Optimizer**: Not just damage calculation — it can "work backwards" to find the minimum EV investment needed to achieve OHKO, 2HKO, or survival benchmarks.
- **Human-Language Tolerance (Normalize Layer)**: Built-in alias mappings for player slang (e.g. "Charizard" ↔ "老喷", "Life Orb" ↔ "命玉", "Chople Berry" ↔ "抗斗果"), lowering the burden on LLM entity extraction.

---

## Architecture & Workflow

```text
User's natural-language question
       |
       v
+---------------+
|   AI Agent    | Understands semantics, extracts entities & params, queries pokedex
+-------+-------+
        | Builds complete CLI command (JSON overrides)
        v
+---------------+
|   query.py    | Single CLI entry point
+-------+-------+
        | Routes to sub-commands
        v
+---------------+
|   damage.py   | Pure-parameter deterministic calculator (reads local data/*.json)
+-------+-------+
        | Returns exact numerical result (DamageResult JSON)
        v
+---------------+
|   AI Agent    | Formats JSON into natural language, tables, or analysis
+-------+-------+
        |
        v
Final professional answer to user
```

---

## Developer & Integration Guide

If you want to integrate this engine into your own LLM application, refer to:

- **[`SKILL.md`](./SKILL.md)**: The System Prompt written specifically for LLMs. Contains complete behavior specifications, chain-of-thought (`<plan>`) requirements, and tool-call definitions. Inject its contents directly into your Agent Prompt to teach the LLM how to use this engine.
- **[`DEVELOPER.md`](./DEVELOPER.md)**: Human-facing technical documentation with full I/O specifications, JSON Schema definitions, and internal architecture details.

---

## Data Sources & Credits

- **Gen 1–9 Pokédex Data**: Crawled from [42arch/pokemon-dataset-zh](https://github.com/42arch/pokemon-dataset-zh)
- ***Pokémon Champions* (M-B Rules) Data**: Game ROM extraction and parsing from [projectpokemon/champout](https://github.com/projectpokemon/champout)
- **VGC Damage Calculator Frontend Logic**: Ported and refactored from the [VGC Damage Calculator](https://professorsidon.github.io/VGC-Damage-Calculator-Chinese/) JavaScript engine

---

## Credits

This project was built with **vibe coding** by [Kimi K2.6](https://kimi.moonshot.cn).

## License

MIT License
