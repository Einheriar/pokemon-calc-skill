# pokemon-calc 机制细节参考

> 本文件为 SKILL.md 的按需参考，不自动加载。当需要 SP/EV 换算细节、optimize 双模式返回字段，或数据来源的完整说明时，先阅读本文件。

## 能力点数（SP）与努力值（EV）双视图

本 Skill 底层始终以**努力值（EV）**存储与计算（保留完整 4 EV 精度），同时提供《宝可梦冠军》(Pokémon Champions) 的**能力点数（SP）**作为输入与展示视图。两者是同一配置的双向等价表述，引擎自动换算，无精度损失。

| 系统 | 总点数 | 单项上限 | 步进 | 对应能力值增长（Lv.50, IV=31） |
|------|--------|----------|------|-------------------------------|
| 能力点数（SP） | 66 | 32 | 1 | 每 1 SP = +1 能力值 |
| 努力值（EV） | 508 | 252 | 4 | 首个 +1 需 4 EV，之后每 8 EV = +1 |

**双向换算公式**（Lv.50, IV=31 精确成立）：

- SP → EV：`EV = 8 × SP - 4`（SP=0 时 EV=0）
- EV → SP：`SP = (EV + 4) // 8`

| SP | 等效 EV | 能力值增量 |
|----|--------|-----------|
| 1 | 4 | +1 |
| 13 | 100 | +13 |
| 31 | 244 | +31 |
| 32 | 252 | +32 |

> 关键：第一个能力点只需 4 EV，之后每 8 EV 一点，因此 **32 SP = 252 EV**（不是 256）。两种表述指向完全相同的能力值。

**命令示例**：

```bash
# 用户以 SP 表述（推荐）：用 sps 字段，引擎自动转 252 EV
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟 --att_ov '{"sps":{"sp_attack":32}}'

# 用户以传统 EV 表述：直接用 evs 字段
python scripts/query.py calc 喷火龙 喷射火焰 水箭龟 --att_ov '{"evs":{"sp_attack":252}}'

# optimize 默认 EV 模式；Champions SP 优化用 --mode sp
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko
python scripts/query.py optimize 喷火龙 喷射火焰 水箭龟 --goal ko --target ohko --mode sp
```

**optimize 返回值字段说明**：

`optimize` 命令始终返回两套字段以兼容双模式：

```json
// EV 模式（--mode ev，默认）
{
  "success": true,
  "optimal_ev": 252,
  "remaining_evs": 256,
  "optimal_sp": 0,
  "remaining_sp": 0
}

// SP 模式（--mode sp）
{
  "success": true,
  "optimal_ev": 0,
  "remaining_evs": 0,
  "optimal_sp": 25,
  "remaining_sp": 41
}
```

未使用模式的字段固定为 0，避免解析歧义。

## 数据来源与版本策略

采用双层数据架构：

| 层级 | 来源 | 覆盖范围 | 优先级 |
|------|------|----------|--------|
| 第一层 | 《宝可梦冠军》(Pokémon Champions) M-B 规则（2026-06-24 更新） | 361 种形态 | **高** |
| 第二层 | Gen9（朱紫）正作数据 | 全国图鉴 1~1025 | 低 |

当 Champions 数据与 Gen9 正作数据存在差异时，以 Champions 为准。查询结果中的 `"_data_source"` 字段标识具体来源（`"champions"` 或 `"gen9"`）。

数据中覆盖全国图鉴 1~1025 号，**包含所有形态**（含 Mega、原始回归等），不区分世代过签状态。伤害计算时不过签过滤。

### 环境情报数据层（usage / teams）

`usage` / `teams` 命令的数据独立于上述百科数据层：

| 项目 | 说明 |
|------|------|
| 来源 | pokecamp.cc（聚合 Limitless 公开赛事统计） |
| 规则 | 《宝可梦冠军》VGC 2026 规则 M-B（双打） |
| 样本 | 滚动 30 天窗口内的公开赛事队伍（样本量见 `meta.tournament_count` / `meta.team_count`） |
| 更新 | 内置数据随版本更新；`--online` 可实时拉取（按需请求，结果本地缓存） |
| 性质 | 赛事环境统计，非官方游戏内天梯数据，也非模拟器数据 |

两条命令的数据形态与分工：

| 命令 | 内置数据 | 能回答的问题 |
|------|---------|-------------|
| `usage` | `data/usage_stats.json`：299 只宝可梦的站点预计算统计（排名、胜率、Top 招式/特性/道具/性格、**SP 能力点数分配推荐**、队友） | "谁最热门"、"X 怎么加点/带什么" |
| `teams` | `data/teams_full.json.gz`：当前窗口**全量队伍**（9,000+ 支，含每队 6 只的道具/特性/性格/招式明细），首次全量查询自动派生本地 SQLite 索引（`data/cache/teams_index.db`，可删可重建）；`data/meta_teams.json` 为前 12 支的轻量兜底 | "哪些队伍用了 X"、"某选手的队伍"、"前八队伍里谁最热门"（子集统计）、"X 最常和谁组队" |

注意：队伍数据**不含 SP/努力值分配**（teams.json 本身没有），加点类问题一律走 `usage <宝可梦名>`；两边的出现率同口径同数据集（已数值验证吻合），`teams --stats` 的价值在于子集聚合（`--placing-max` / `--tournament`）。所有 teams 查询输出硬上限 50 条，原始数据与索引不进入上下文。
