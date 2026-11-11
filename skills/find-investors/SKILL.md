---
name: find-investors
description: Define and update the Tier 1/Tier 2 universe of Chinese VC, PE and other relevant equity investment firms, label tiers with cross-referenced public rankings, fetch official logos, and discover portfolio companies. Use as the default first step for company discovery, before company profiles and people research. Hand off investment-firm profiles to compose-profile, operating portfolio companies to map-sectors/compose-profile, and people to find-person.
---

# Find Investors · 金融机构寻源与 Portfolio

先圈定中国 Tier 1 / Tier 2 的 VC、PE 等金融机构，再顺着它们的投资组合发现公司。发现公司的默认起点是出资人，不是零散新闻里的创业公司。地域、主题和用途由当前任务决定；本仓库当前公共数据聚焦中国 AI 与科技投资机构。

本 Skill 只做三件事：**圈定机构 → 打有来源的 Tier → 沿 portfolio 发现公司并回写融资轮次**。人物留给 [find-person](../find-person/SKILL.md)，不在本环节提前铺开。

## 1. 何时使用

- 需要建立或更新中国 VC、PE、CVC、产业基金及相关股权投资机构的发现网。
- 需要给已建档投资机构补充 `tier`、官方 logo 或 `portfolio[]`。
- 需要沿基金投资组合找公司，并为公司补齐成立时间与融资轮次。
- 已有 `find-startups` / `find-incumbents` 的线索，需要回到金融机构主路径继续扩展时。

如果任务主要研究单家公司的产品、团队或渠道，转用 [compose-profile](../compose-profile/SKILL.md) 或 [find-channels](../find-channels/SKILL.md)。

## 2. 范围先放大

不限于纯 AI 基金，也不只收录精品新兴基金。以中国 VC / PE / 相关金融机构为发现网，重点是**能通向科技与 AI 公司的出资人**：

- 综合 VC、成长基金、PE、并购基金、母基金／政府引导基金中实际做直投的机构。
- 企业战投（CVC）、产业资本与金融机构下设的股权投资平台，边界按真实投资主体核实。
- 有清晰策略和公开投资活动的专业基金、新锐基金；现有 25 家样本不够，不能把样本当全集。
- 同一机构只维护一份 `data/companies/<id>.json`；品牌、团队和法律主体分清层级，不按办公地建副本。

参考榜单只是发现入口，不是市场全集。机构是否纳入以可核实的公开投资活动和主体边界为准。

## 3. Tier 规则（编辑判断，不是官方排名）

字段为 `tier`，取值 `tier1` / `tier2` / `unlisted`。`group`（`emerging` / `established`）是组织成熟度，与 Tier 不是同一轴，不要互相替代。

**证据要求**：至少交叉参考两份近年公开榜单，或一份榜单加机构官网／权威报道；单份榜单不能单独定 Tier 1。必须实际访问页面，并在 `tier.basis` 写明榜单名称、年份或期次、URL，以及该机构被如何提及；`tier.source_ids` 指向本记录 `sources[]` 的机构级来源，`tier.labelled_at` 记录打标日期。

建议参考类型（以实际可访问页面为准）：

- 清科中国股权投资年度排名（VC / PE 等分类）。
- 投中（ChinaVenture）年度机构榜。
- 其他可公开访问的年度股权投资机构榜、协会或交易所公开资料。

行业媒体盘点、单篇融资新闻和机构自述只能作辅证。访问失败、榜单缺失或只有单一来源时，保留 `unlisted` 并说明依据不足；不要猜榜单内容。

建议口径：

| 取值 | 口径 |
| --- | --- |
| `tier1` | 近年多份权威股权投资榜单中稳定靠前，或被交叉引用的综合性主力机构 |
| `tier2` | 上述榜单中经常出现、有清晰策略与可核公开活动，但交叉引用不如第一档稳定；包含公开存在的专业或新锐基金 |
| `unlisted` | 已建档但榜单依据不足；不强行打档 |

不得把 Tier 写成官方排名、收益排名或个人推荐分数；不得把整份受版权保护的榜单正文抄进仓库。只记录本库用到的机构、它们出现在哪份榜单、以及链接。判断流程与参考类型见 [榜单与 Tier 口径](references/tier-and-rankings.md)。

## 4. 官方 Logo

机构建档后，优先用扩展后的工具从官网或机构官方页面取官方 logo：

```bash
python3 tools/fetch_logos.py --id <id>
```

- 覆盖创业公司和有官网的 `investment_firm`；投资机构不再被跳过。
- 写入 `data/views/assets/logos/<id>.<ext>` 和 `data/views/assets/logos/manifest.json`。
- 只取 apple-touch-icon、favicon、og:image 或明确的官方 logo；不接 Clearbit 等第三方 logo CDN。
- 找不到可靠图像就跳过，看板显示文字占位；**不生成假 logo**。

## 5. Portfolio 与公司档案

沿机构官网投资组合、公司公告、监管／交易所披露和可靠报道收集 portfolio，写入投资机构档案的 `portfolio[]`：

- `company_name`：披露中的公司名称。
- `company_id`：仅当本仓库已有对应经营型档案时填写稳定 ID，否则 `null`。
- `round` / `announced_on`：按披露原文与日期记录；没有披露填 `null`，不擅自规范轮次，不编日期。
- `role`：`lead` / `participant` / `undisclosed`；参与不等于领投。
- `attribution`：`current_firm` / `prior_firm`；原平台案例不能算当前机构业绩。
- `source_ids`：本机构记录中的机构级来源，至少 1 个；`notes` 写口径限制。

对被投公司：

1. 已在库中的公司回写到其 `data/companies/<id>.json`，不要另建副本。
2. 公司档案除简介外，重点补 `founded`（`year` + `basis`）和 `investment.rounds[]`。
3. `investment.rounds[]` 记录原文轮次名、披露日期、原文金额 `amount_text`、投资方与来源；没有披露就留空，不编数字、不编轮次。投资方 `firm_id` 仅在本仓库已有该投资机构档案时填写。
4. IPO 不等于已退出；参与不等于领投；媒体报道不升级为官方确认。

新发现且尚未建档的经营型公司，交给 [map-sectors](../map-sectors/SKILL.md) 与 [compose-profile](../compose-profile/SKILL.md) 建档；本 Skill 不批量创建空壳公司。

## 6. 交接与本仓库适配

- 新机构／新公司档案：交给 [compose-profile](../compose-profile/SKILL.md)，唯一源为 `data/companies/<id>.json`。
- 经营型被投公司赛道归入：交给 [map-sectors](../map-sectors/SKILL.md)；投资机构没有 `category_id`。
- 核心人物：留给 [find-person](../find-person/SKILL.md)，本 Skill 不采集人物。
- 公开渠道：档案建立后交给 [find-channels](../find-channels/SKILL.md)。
- 新 VC 的团队与拆分背景仍可参考 [新 VC SOP](../find-startups/references/new-vc-spinouts.md)，但正式金融机构寻源入口是本 Skill；`find-startups` / `find-incumbents` 只作补充寻源。

仓库内先读 `data/index.json`、已有 `data/companies/*.json` 和 [字段说明](../../data/README.md)，按稳定 ID 与别名去重。`data/lists/vcs.json` 仍是共用寻源名单，只引用完整档案，不复制机构事实；名单不自动等于 Tier 名单。

```bash
python3 tools/query.py --entity investors --json
python3 tools/query.py --id <id>
python3 tools/fetch_logos.py --id <id>
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
.venv/bin/python tools/check_public.py
```

正式变更先校验、再生成阅读版、最后检查共享边界。绝不编造机构、投资关系、融资金额、轮次或来源 URL；不因整理、打 Tier 或导入刷新旧事实日期。
