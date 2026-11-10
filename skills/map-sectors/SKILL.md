---
name: map-sectors
description: Assign one primary category_id from the existing data/taxonomy.json map when profiling a company, or review section boundaries across the dashboard. Use for sector mapping, taxonomy placement, or deciding which existing 01–10 section a company belongs to. Do not create new categories or reclassify the whole dataset.
---

# Map Sectors · 赛道图谱与分区

把一个机构放入既有的 `data/taxonomy.json` 主赛道，供看板第二层分区与档案展示。分类是编辑地图，不是机构官方标准，也不是市场排名。

## 1. 读取既有地图

先读 `data/taxonomy.json` 与当前公司 JSON 的 `category_id`、`focus`、`products`。主赛道固定为 `01`–`10`；已有 `category_id` 不要因为一次任务随意改写。需要校对边界时同时看 [分类视图](../../data/views/taxonomy.md) 和 [数据模型](../../data/README.md)。

现有地图的方法参考：

- Sequoia Capital, *Generative AI’s Act Two*：按使用场景组织应用层，另看 LLM 开发栈 — https://sequoiacap.com/article/generative-ai-act-two/
- a16z, *Emerging Architectures for LLM Applications*：区分模型、算力、编排、数据与应用 — https://a16z.com/emerging-architectures-for-llm-applications/
- a16z-infra, *LLM App Stack*：工程生态清单，不是企业投资名单 — https://github.com/a16z-infra/llm-app-stack

这些参考说明地图的组织方法；`data/taxonomy.json` 的 10 个主赛道是本仓库的编辑分类，不是上述机构发布的官方分类。

## 2. 只选一个主赛道

按主要产品交付选择一个 `category_id`，写回公司 JSON。跨层业务放在 `focus`、`products` 与细分方向里，不要为了覆盖面重复计数。

- 先看客户实际购买什么：可复用模型、算力底座、开发工具、个人应用、生成工具、企业软件、零售营销、机器人、消费硬件、科学智能。
- 无把握时保留现有分类并说明缺口；不把公司硬塞进“看起来接近”的赛道。
- 不为单个公司新增赛道、改 `taxonomy.json` 的编号或重排全集。确需修订方法或链接时另开任务，并保持来源与日期。
- 分类判断与业务事实分开记录；改分类不刷新 `checked_at`，也不伪造新来源。

## 3. 交付

更新 `data/companies/<id>.json` 的 `category_id`，必要时补充 `focus` 与 `products` 的来源支持，然后：

```bash
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
```

看板会按既有主赛道自动分区；空赛道隐藏。不要把 `player_group == "unresolved"` 的公司挪进创业公司分区来填满赛道。档案写作见 [compose-profile](../compose-profile/SKILL.md)。
