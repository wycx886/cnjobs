---
name: compose-profile
description: Research and fill a company dossier in the canonical data/companies/<id>.json record, separating operating-org fields from investment-firm fields. Use when composing or updating a company profile, fetching official logos for startups or investment firms, or preparing data for the generated dashboard. Never invent funding, tiers, people, or URLs; HTML is generated from JSON.
---

# Compose Profile · 公司档案

公司档案的唯一维护源是 `data/companies/<id>.json`。交互看板、Markdown 与机器索引都由 `python3 tools/build.py` 从该 JSON 自动生成；不要另建平行档案，也不要手改生成页面。

本 Skill 处于方法论第二阶段（**找公司 → 公司档案 → 找核心人物 → 找渠道**）：在确定目标机构后，规范建立或维护底层档案。

## 1. 先查已有档案与 Tier 1 分类

读取 `data/index.json`、目标公司 JSON、[公司契约](../../data/schemas/company.schema.json) 和 [字段说明](../../data/README.md)。复用稳定 `id`，先查别名与旧 ID，避免为同一公司新建副本。

机构按 Tier 1 区分类型：
- **创业公司**：`organization_type: "operating_organization"`，`player_group: "new_entrant"`。
- **现有巨头**：`organization_type: "operating_organization"`，`player_group: "incumbent"`。
- **金融机构**：`organization_type: "investment_firm"`。

## 2. 字段填充（严格区分经营型机构与投资机构）

经营型机构与投资机构统一保存在 `data/companies/<id>.json`，但两者适用的业务字段严格分开：

### 通用基础字段
- `id`：稳定小写 ASCII ID，与文件名一致。
- `name` / `aliases`：当前正式名称与历史/别名。
- `organization_type`：`operating_organization` 或 `investment_firm`。
- `targeting`：编辑判断对象（`player_group`、`wave`、`rationale`、`source_ids`、`labelled_at`）。
- `contacts`：既有公开联系方式（如官方网站 `website`、公开邮箱等）。
- `channels[]`：机构级公开渠道（官网、官招链接、邮箱、BOSS直聘、猎聘、LinkedIn 企业主页等 6 个槽位，见 [find-channels](../find-channels/SKILL.md)）。
- `sources[]`：真实可访问的公开证据（URL、标题、支持内容、公开日期 `published_date`、实际核查日期 `checked_at`；新增渠道证据标 `scope: "channel"`，人物证据标 `scope: "person"`）。

### 经营型机构（`operating_organization`）专有字段
- `category_id`：01–10 既有主赛道（由 [map-sectors](../map-sectors/SKILL.md) 映射；金融机构无此字段）。
- `focus`：主营业务方向与核心技术简述。
- `products`：主要产品、技术交付或代表模型。
- `locations_text`：公开城市记录；地区细节、本地线索与分部证据收进主档案 `regional_notes[]`，不按城市建副本。
- `founded`（可选）：成立时间口径 `{ "year": int|null, "basis": string }`；不用融资、品牌启用或登记日期替代成立年份。
- `investment`：历史融资披露与核验状态（`confirmed_disclosure` / `partial` / `not_found` / `not_applicable`，内部项目经证实后可为 `not_applicable`）。可选 `rounds[]` 逐轮记录：`round` 按披露原文，`announced_on` 可空，`amount_text` 只保留来源原文金额，`investors[]` 的 `firm_id` 仅在本仓库已有投资机构档案时填写，`source_ids` 至少 1 个；没有披露就不建 `rounds`。
- `organizational_context`（可选）：针对大厂关联项目、实验室、子公司或拆分机构的形态与母平台关系（按 [大厂项目 SOP](../find-incumbents/references/corporate-ventures.md)）。

### 金融机构／投资机构（`investment_firm`）专有字段
- `group`：分组（如 `emerging` / `established` 等历史描述性分组；**没有 `category_id`，不填 01–10 赛道**）。
- `coverage`：覆盖角色（`role: "main"` / `"watchlist"` / `"adjacent"`）及纳入原因 `reason`。
- `founded`：成立年份口径与依据。
- `tier`（可选）：有来源的 Tier 编辑判断 `{ "level": "tier1" | "tier2" | "unlisted", "basis", "source_ids", "labelled_at" }`。至少交叉参考两份近年公开榜单或一份榜单加官网／权威报道；单份榜单不能定 Tier 1。写明榜单名称、年份或期次与链接；`group` 是组织成熟度，与 Tier 不是同一轴。
- `stage`：主要投资阶段（如早期、成长等）。公司融资轮次与已披露投资方只记录在经营型公司档案的 `investment.rounds[].investors[]`（投资方 `firm_id` 可回指本机构），不在机构档案另建投资组合清单。
- `representative_cases`：代表投资案例，严格区分原平台案例（`prior_firm`）与当前机构案例（`current_firm`）。
- `recent_activity`：近期活跃度（投资、募资、退出或组织公告）。
- `why_follow`：编辑跟进价值分析。
- `difference`：差异化策略与能力。
- `people`：投资合伙人与核心团队（原 VC `team` 已迁入此处）。

绝不编造公司、人物、职务、融资数字、投资关系或来源 URL。缺失值不表示确定不存在；保持原有核查日期，整理不刷新旧事实。

## 3. Logo 提取（创业公司与投资机构）

有官网时，可从 `contacts.website`（或官方 `channels` website）抓取 apple-touch-icon、favicon、og:image 或明确的页头 logo，保存为派生视图资产 `data/views/assets/logos/<id>.<ext>` 并记录来源。不要使用 Clearbit 等第三方 logo CDN；找不到可用图像时使用看板的文字占位，不要生成假 logo。

```bash
python3 tools/fetch_logos.py --id <id>
```

> [!NOTE]
> `tools/fetch_logos.py` 默认处理**创业公司**（`operating_organization` 且 `player_group == "new_entrant"`）以及所有**有官网的 `investment_firm`**；传入 `--id` 时投资机构不再被跳过。现有巨头等其他类型仍不纳入默认采集。工具幂等跳过已有文件，并在 `data/views/assets/logos/manifest.json` 记录来源、抓取日期或跳过原因。

## 4. 生成、校验与交接

```bash
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
.venv/bin/python tools/check_public.py
```

看板档案展示顺序为：**身份与简介 → 核心人物 → 业务／投资字段 → 公开渠道模板 → 地区与来源**。
档案创建或更新后，按方法论推进：
1. 赛道归入见 [map-sectors](../map-sectors/SKILL.md)（仅经营型机构）。
2. 档案建立后，优先交接给 [find-person](../find-person/SKILL.md) 补充核心人物（当前创业公司人物最优先）。
3. 最后交接给 [find-channels](../find-channels/SKILL.md) 填充公开渠道模板。
