---
name: compose-profile
description: Research and fill a company dossier in the canonical data/companies/<id>.json record, including identity, focus, products, locations, already-structured investment fields and sources. Use when composing or updating a company profile, or when preparing data for the generated dashboard. Never invent funding, people, or URLs; HTML is generated from JSON.
---

# Compose Profile · 公司档案

公司档案的唯一维护源是 `data/companies/<id>.json`。看板、Markdown 与索引都由 `build.py` 从该 JSON 生成；不要另建平行档案，也不要手改生成页面。

## 1. 先查已有档案

读取 `data/index.json`、目标公司 JSON、[公司契约](../../data/schemas/company.schema.json) 和 [字段说明](../../data/README.md)。复用稳定 `id`，先查别名与旧 ID，避免为同一公司新建副本。经营型机构与投资机构统一放 `data/companies/`，用 `organization_type` 区分。

## 2. 填充既有字段

按契约补齐或核对：

- 身份与边界：`name`、`aliases`、`organization_type`、`targeting`、必要的 `organizational_context`。
- 业务与位置：`focus`、`products`、`locations_text`、`regional_notes[]`。地区线索留在主档案，不另建上海／苏州公司副本。
- 投资：只写已有来源支持的 `investment` 与 `representative_cases`；自筹、内部资源、产业资本与独立股权融资分开，参与不等于主导。
- 渠道与人物：机构入口只写 `channels[]`；核心人物只写 `people[]`，个人主页在 `people[].profiles[]`。没有核实就留空，不猜账号。
- 来源：每个事实使用真实可访问的公开 URL、支持内容、公开日期（未知用 `null`）与实际核查日期。

绝不编造公司、人物、职务、融资数字、投资关系或来源 URL。缺失值不表示确定不存在；保持原有核查日期，整理不刷新旧事实。

## 3. Logo

有公司官网时，可从 `contacts.website`（或官方 `channels` website）抓取 apple-touch-icon、favicon、og:image 或明确的页头 logo，保存为派生视图资产 `data/views/assets/logos/<id>.<ext>` 并记录来源。不要使用 Clearbit 等第三方 logo CDN；找不到可用图像时使用看板的文字占位，不要生成假 logo。

```bash
python3 tools/fetch_logos.py --id <id>
```

该工具只处理创业公司，幂等跳过已有文件，并在 `data/views/assets/logos/manifest.json` 记录来源、抓取日期或跳过原因。

## 4. 生成与校验

```bash
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
.venv/bin/python tools/check_public.py
```

看板档案顺序为：身份与简介 → 核心人物 → 业务／投资字段 → 公开渠道模板 → 地区与来源。核心人物暂缺时保留“待 find-person 补充”的位置。赛道归入见 [map-sectors](../map-sectors/SKILL.md)；人物研究见 [find-person](../find-person/SKILL.md)；渠道核查见 [find-channels](../find-channels/SKILL.md)。
