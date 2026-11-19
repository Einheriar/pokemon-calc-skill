<div align="right">
  🇺🇸 English |
  <a href="./README_CN.md">🇨🇳 简体中文</a>
</div>

# pokemon-calc: Pokédex & Damage Calculator for AI Agents

**v5.2.0** adds a Speed calculator with automatic nearby benchmarks, an adjustable ± range, and Tailwind support. See the [Speed command](references/commands.md#speed-速度计算器).

Traditional Pokémon damage calculators are web apps or tools built for humans. `pokemon-calc` is a purpose-built computation engine designed for **AI Agents (Large Language Models)**.

By providing a deterministic CLI and bundled reference data, this project helps reduce the risk of numerical errors when an AI agent handles Pokémon battle modifiers such as type matchups, abilities, items, weather, and terrain. The engine computes supported cases; it does not cover every mechanic or replace careful interpretation of unsupported interactions.

## What can you ask?

Two EV/SP systems supported: traditional Gen9 **EVs** (252/4/508 rule) and Pokémon Champions **Stat Points (SP)** (32/1/66 rule).

### Encyclopedia & Mechanics

| Capability | Example question |
|------------|------------------|
| Look up a Pokémon | "What are Charizard's base stats and typing?" |
| Type matchups | "How effective is Fairy against Steel?" |
| Move details | "What's Heat Wave's power, accuracy, and effect?" |
| Ability effects | "What does Drought do?" |
| Held items | "What's the difference between Focus Sash and Choice Scarf?" |
| Learnset | "What Fire-type moves can Charizard learn?" |
| Evolution line | "How does Eevee evolve into Sylveon?" |
| Pokédex entries | "What does Mew's Pokédex entry say?" |
| VGC presets | "What are common Charizard VGC sets?" |

### Meta Environment Snapshots

Meta data is shipped as dated snapshots and does not update automatically. The battle data layer includes Pokémon Champions M-C records. Meta snapshots have separate publication dates: the bundled tournament usage and team data covers M-C from **2026-10-16 through 2026-11-16** (312 usage entries, 135 tournaments, 134 with team data, and 6,469 fully detailed teams); the bundled official in-game ladder snapshot is M-C as of **2026-11-16** (data version `20261116083343008`, 262 ranking entries) and contains rankings only. Only rows marked `isMega=true` with a `linkId` explicitly pointing to the corresponding non-Mega form are merged; other non-Mega forms, including male/female and regional battle forms, remain separate. The bundled Showdown report is M-C for **2026-10** (cutoff 1760, 289 entries). Offline meta queries use these snapshots; they do not represent live rankings or current tournament results.

| Capability | Example question |
|------------|------------------|
| Usage ranking (`meta`) | "Which Pokémon ranked highest in the bundled tournament snapshot?" |
| Per-Pokémon meta detail (`meta <name>`) | "What moves/items did Kingambit use in the bundled tournament snapshot? Who were its common teammates?" |
| Tournament teams (`meta --teams`) | "Show me teams from the bundled tournament snapshot" |
| Teammate co-occurrence (`meta --teams --teammates`) | "Who partnered Incineroar most often in the bundled snapshot?" |
| Bundled official ladder ranking (`meta --source ladder [--format singles\|doubles]`) | "What is the official in-game ladder ranking in the bundled M-C snapshot?" (rank-only; snapshot as of 2026-11-16) |
| Fresh official ladder ranking (`meta --source ladder --online`) | "What is the latest official in-game ladder ranking?" |
| Ladder build detail (`meta --source ladder <name> --online`) | "What are Kingambit's top 4 moves on the official ladder?" |
| Showdown ladder monthly report (`meta --source showdown`) | "What are the usage stats in the bundled Showdown report?" (2026-10, cutoff 1760) |

> `meta --online` requests fresh upstream data only when explicitly used and requires network access. For tournament usage rankings, a failed refresh falls back to a completed distilled online cache, then to the bundled snapshot. Raw endpoint caches are not used to present an incomplete or stale payload as a fresh result. The returned `meta.origin` and `meta.online_error` identify the source actually used and any fetch failure.
>
> With `--online`, a named tournament usage query may combine ranking data with separately fetched Pokémon details. `meta.origin`, `meta.date_range`, and `meta.format` describe the ranking data; when a detail fetch is attempted, `meta.detail_origin`, `meta.detail_fetched_at`, `meta.detail_date_range`, `meta.detail_format`, and `meta.detail_online_error` describe the detail data. Those sources and dates can differ, so use the matching metadata for usage/ranking claims versus moves, items, abilities, or spreads. Official ladder rankings are rank-only in the bundled snapshot; per-Pokémon ladder details require `--online`. Ladder sources support `--format singles|doubles` (default doubles) and do not provide tournament-team queries. `--source showdown --online` uses the Showdown source and its regulation-specific report route. Legacy `usage` / `teams` commands remain deprecated aliases for `meta`.

### Damage Calculation & Optimization

| Capability | Example question |
|------------|------------------|
| Quick damage calc | "How much does Sun Mega Charizard Y Heat Wave do to Mega Alakazam?" |
| EV optimization | "How much SpA EV does Charizard need to OHKO Blastoise?" |
| SP optimization | "Pokémon Champions (SP system: 66/32/1), how much SpA SP does Charizard need to OHKO Blastoise?" |
| Survivability lookup | "My Garchomp has 185 HP. What base power Physical/Special moves can it survive from a 200-Atk/SpA attacker?" |
| Stat computation | "What's the Attack stat of 95 base, 252 EV, Adamant, Lv.50?" |
| Speed calculator | "What's Mega Manectric's Modest max-SP Speed, and which selected benchmarks are within ±5?" |

---

## Core Values

### 1. Designed for Agents: LLM Understands, Engine Computes

Large language models can recognize intent and extract parameters, while deterministic calculation reduces arithmetic and lookup errors for supported cases. This project separates the two responsibilities:

- **LLM's Job**: Parse natural language (e.g. "Can Life Orb max SpA Mega Charizard Y OHKO max SpD Amoonguss in Sun?") into structured JSON parameters.
- **Engine's Job**: Receive parameters, apply common supported modifiers (such as STAB, weather, items, and Terastallization), and return damage ranges and KO probabilities for the modeled case.
- **Pure-Function Interface**: All queries and calculations flow through a single entry point, `query.py`, with well-defined JSON In / JSON Out semantics. This makes it trivial to wrap as a GPTs Action, Dify plugin, or MCP (Model Context Protocol) tool.

### 2. Offline by Default, with Optional Online Meta Queries

Encyclopedia, calculation, optimization, and bundled meta-snapshot queries run offline after cloning. Optional `meta --online` requests fresh upstream meta data and therefore needs network access; results are cached locally, with cache/snapshot fallback if a request fails. The agent framework may still use model tokens when interpreting a request and presenting results.

- **Bundled Data**: 34,636,873 bytes (34.64 MB, decimal) across 19 bundled data files, including Pokédex and battle data, aliases, presets, dated meta snapshots, and curated Speed references. Coverage reflects the included records; it is not a guarantee that every form or mechanic is represented.
- **Minimal Runtime**: Python 3.10+ standard library only. **No** `numpy`, **no** `pandas`, and no third-party Python packages to install.

---

## Installation & Usage

This project is an Agent Skill. The following destinations are the documented personal skill directories for [Codex](https://developers.openai.com/api/reference/cli), [Claude Code](https://code.claude.com/docs/en/skills), and [Hermes Agent](https://hermes-agent.nousresearch.com/docs/guides/work-with-skills/). Skill discovery and session refresh behavior can differ by agent.

### Install as a Skill

Create the destination's parent directory before cloning. These bash commands install it for the current user:

```bash
mkdir -p "$HOME/.agents/skills" "$HOME/.claude/skills" "$HOME/.hermes/skills"
git clone https://github.com/Einheriar/pokemon-calc-skill.git "$HOME/.agents/skills/pokemon-calc"   # Codex (user-level)
git clone https://github.com/Einheriar/pokemon-calc-skill.git "$HOME/.claude/skills/pokemon-calc"  # Claude Code (user-level)
git clone https://github.com/Einheriar/pokemon-calc-skill.git "$HOME/.hermes/skills/pokemon-calc"  # Hermes Agent
```

For project-level Codex and Claude Code installs, use `.agents/skills/pokemon-calc` and `.claude/skills/pokemon-calc` within the project. Then start a new session if needed and request the skill explicitly, for example: `Use pokemon-calc to check if Mega Charizard Y can OHKO Amoonguss under sun.` Hermes Agent's documented user skill directory is `~/.hermes/skills/`; newly installed skills are available in new sessions.

### Use as a Standalone CLI Tool

To clone into a new directory named `pokemon-calc` and run the CLI from that repository root:

```bash
git clone https://github.com/Einheriar/pokemon-calc-skill.git pokemon-calc
cd pokemon-calc
python scripts/query.py calc Charizard Flamethrower Blastoise
```

If you already cloned the repository, run `python scripts/query.py ...` from its root; the published repository root already contains `scripts/` and `data/`.

The command examples below use Bash syntax. In Windows PowerShell, run commands on one line rather than using Bash's trailing `\` continuation. See [`references/commands.md`](./references/commands.md) for Windows command examples.

---

## Quick Start

After cloning, no dependencies to install. The CLI accepts Simplified Chinese, Traditional Chinese, English, and Japanese names where those names are present in the bundled name index; coverage does not include every possible spelling or romanization. JSON field names are English, while descriptive text and display names are primarily Simplified Chinese; some fields include canonical English names. There is no `--lang` switch; an AI agent can translate or rephrase the result for the user.

### 1. Encyclopedia & Mechanics Queries

```bash
# Query stats for regular and Hisuian Decidueye
python scripts/query.py stats Decidueye

# Query move mechanics
python scripts/query.py move "Heat Wave"

# Query type matchup
python scripts/query.py type Fairy Steel
```

### 2. Damage Calculation Engine

Combines positional arguments with named override parameters.

```bash
# Basic quick calc (defaults to Lv.50 Doubles)
python scripts/query.py calc Charizard Flamethrower Blastoise

# Complex calc with environment and config overrides (JSON)
python scripts/query.py calc "Mega Charizard Y" "Heat Wave" "Mega Alakazam" \
  --att_ov '{"evs":{"sp_attack":252},"nature":"Modest","form_name":"Mega Charizard Y"}' \
  --def_ov '{"evs":{},"nature":"Hardy","form_name":"Mega Alakazam"}' \
  --field_ov '{"weather":"Sun","format":"Doubles"}'
```

Sample response (excerpt):

```json
{
  "damage_range": [111, 132],
  "ko_chance": "12.5% 概率一击必杀",
  "type_effectiveness": 1.0,
  "stab_applied": true
}
```

> Note: this example sets the attacker to 252 SpA EVs and the defender to 0 EVs with a neutral nature. Because each side's override contains a stat-investment field (`evs`), auto-presets are skipped on both sides. If an override leaves a side unspecified, a setdex preset may be applied to that side; the result reports it through `attacker_auto_preset` / `defender_auto_preset` and, when applicable, `attacker_auto_item` / `defender_auto_item`.

### 3. EV / SP Optimization

Supports both Gen9 EV system (default) and Pokémon Champions SP (Stat Points) system.

```bash
# Gen9 EV mode (default): search for SpA EVs to reach an OHKO target
python scripts/query.py optimize Charizard Flamethrower Blastoise --goal ko --target ohko

# Champions SP mode: search for SP investment to reach an OHKO target
python scripts/query.py optimize Charizard Flamethrower Blastoise --goal ko --target ohko --mode sp
```

| Mode | Flag | Total Points | Max per Stat | Step | SP-to-EV conversion |
|------|------|--------------|--------------|------|---------------------|
| Gen9 EV | `--mode ev` (default) | 508 | 252 | 4 | — |
| Champions SP | `--mode sp` | 66 | 32 | 1 | EV = 0 when SP = 0; otherwise EV = 8 × SP − 4 |

The conversion describes stored EV allocation only. Final stats also depend on base stats, level, IVs, and nature; do not infer a fixed stat increase per SP. An optimization result can be unreachable: check its `success` field and report failure rather than claiming the target is guaranteed.

---

## Real-World Example

> The following example is shown in Chinese to preserve the authentic interaction style of this Skill, which defaults to Chinese queries.

### Example: Mega Charizard Y Heat Wave vs Mega Alakazam in Sun

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
   python scripts/query.py calc 超级喷火龙Y 热风 超级胡地 --att_ov '{"evs":{"sp_attack":252},"nature":"内敛","form_name":"超级喷火龙Ｙ"}' --def_ov '{"evs":{},"nature":"勤奋","form_name":"超级胡地"}' --field_ov '{"weather":"Sun","format":"Doubles"}'
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
> **综合判断**：结论仅适用于上述已计算的配置与环境。

---

## Domain Features

The bundled data and calculation engine cover many common competitive use cases, with support bounded by the data and mechanics implemented in this release:

- **Pokédex and Champions Data**: Bundled Gen 9 data and *Pokémon Champions* rules data currently include many species and forms, including Mega and regional forms. Champions records are tagged with their introducing regulation (M-A/M-B/M-C); this does not guarantee exhaustive coverage of every species, form, or mechanic.
- **VGC Battle Presets**: 314 pre-built sets across 208 species keys in the bundled setdex: 264 legacy community sets and 50 ladder-derived sets based on the complete official in-game doubles Top 50 from **2026-11-16** (all 50 single-Pokémon details available; built on 2026-11-17). Indeedee and Basculegion male and female battle forms have separate presets. Auto-preset selection prefers the ladder-derived tier when a matching form is available. Treat presets as dated references, not live recommendations; users can provide explicit settings to skip presets for that side.
- **EV Reverse Optimizer**: Not just damage calculation — it can "work backwards" to find the minimum EV investment needed to achieve OHKO, 2HKO, or survival benchmarks.
- **Multilingual Name Input**: The name index includes Simplified Chinese, Traditional Chinese, English, and Japanese names, plus a maintained set of aliases. It does not cover every spelling, romanization, or player nickname; the CLI resolves recognized names to canonical English entity keys while text fields default to Simplified Chinese.

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
|   damage.py   | Deterministic calculator for supported parameters and mechanics (reads local data/*.json)
+-------+-------+
        | Returns deterministic results for the supported case (DamageResult JSON)
        v
+---------------+
|   AI Agent    | Formats JSON into natural language, tables, and explanations relevant to the question
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
- ***Pokémon Champions* Rules Data (currently M-C)**: Game ROM extraction and parsing from [projectpokemon/champout](https://github.com/projectpokemon/champout) (v1.2.0)
- **VGC Damage Calculator Frontend Logic**: Ported and refactored from the [VGC Damage Calculator](https://professorsidon.github.io/VGC-Damage-Calculator-Chinese/) JavaScript engine
- **Meta Environment Data (`meta` command)**: [pokecamp.cc](https://pokecamp.cc) (Limitless public tournament stats, official ladder rankings, and Showdown monthly reports) — with thanks

> **Data and online queries**: Bundled meta data are dated snapshots (see the snapshot dates above), not a live feed. The CLI contacts pokecamp.cc only when a user explicitly invokes `--online`; successful results are cached locally, and failed requests fall back to available cache/snapshot data with the actual source and error reported in `meta`. Online query results are written to the local cache and do not rewrite the bundled snapshot files.

---

## Credits

This project was built with **vibe coding** by [Kimi K2.6](https://kimi.moonshot.cn).

## License

MIT License
