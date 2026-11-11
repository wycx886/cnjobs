---
name: map-sectors
description: Assign one primary category_id from the existing data/taxonomy.json map for operating organizations, or review section boundaries across the dashboard. Use for sector mapping, taxonomy placement, or deciding which existing 01–10 section an operating company belongs to. Investment firms have no category_id and are grouped by existing fields (group, coverage, stage); do not invent sectors for them. Do not create new categories.
---

# Map Sectors · 赛道图谱与分区

把经营型机构归入既有的 `data/taxonomy.json` 主赛道，供看板第二层分区与档案展示。分类是编辑地图，不是机构官方标准，也不是市场排名。

> [!IMPORTANT]
> **适用范围限制**：01–10 主赛道**仅适用于经营型机构（`operating_organization`）**。金融机构／投资机构（`investment_firm`）**没有 `category_id`**，在看板中展示于“金融机构”顶层分区，按其自身的既有字段（如 `group`：`emerging` / `established`、`coverage`、`stage` 等）进行组织与展示，**绝不能为金融机构编造或指派 01–10 赛道**。

## 1. 读取既有地图（唯一源 `taxonomy.json`）

先读 `data/taxonomy.json` 与当前公司 JSON 的 `category_id`、`focus`、`products`。主赛道固定为 `01`–`10`；已有 `category_id` 不要因为一次任务随意改写。

- **单一事实源**：`data/taxonomy.json` 是 10 个主赛道、边界与子类的唯一维护源，数据契约见 [数据模型](../../data/README.md)。投资机构与经营型机构分类维度和归因口径见 [分类与案例归因参考](../find-startups/references/taxonomy-and-vc-rubric.md)，不重复维护多套分类定义。
- 现有地图的方法参考（启发分类架构，但 01–10 为本仓库编辑地图，非对方官方发布）：
  - Sequoia Capital, *Generative AI’s Act Two*：按使用场景组织应用层，另看 LLM 开发栈 — https://sequoiacap.com/article/generative-ai-act-two/
  - a16z, *Emerging Architectures for LLM Applications*：区分模型、算力、编排、数据与应用 — https://a16z.com/emerging-architectures-for-llm-applications/
  - a16z-infra, *LLM App Stack*：工程生态清单，不是企业投资名单 — https://github.com/a16z-infra/llm-app-stack

## 2. 经营型机构：只选一个主赛道

按主要产品交付选择一个 `category_id`（`01`–`10`），写回公司 JSON。跨层业务放在 `focus`、`products` 与细分方向里，不要为了覆盖面重复计数。

- 先看客户实际购买什么：可复用模型（01）、算力底座（02）、开发工具（03）、个人应用与搜索（04）、生成创作工具（05）、企业软件（06）、零售营销（07）、机器人与具身智能（08）、消费硬件（09）、科学智能（10）。
- 无把握时保留现有分类并说明缺口；不把公司硬塞进“看起来接近”的赛道。
- 不为单个公司新增赛道、改 `taxonomy.json` 的编号或重排全集。确需修订方法或链接时另开任务，并保持来源与日期。
- 分类判断与业务事实分开记录；改分类不刷新 `checked_at`，也不伪造新来源。

## 3. 交付

更新 `data/companies/<id>.json` 的 `category_id`，必要时补充 `focus` 与 `products` 的来源支持，然后：

```bash
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
```

看板会按既有主赛道自动分区；空赛道隐藏。不要把 `player_group == "unresolved"` 的公司挪进创业公司分区来填满赛道。档案写作见 [compose-profile](../compose-profile/SKILL.md)；后续核心人物研究见 [find-person](../find-person/SKILL.md)；公开渠道维护见 [find-channels](../find-channels/SKILL.md)。
