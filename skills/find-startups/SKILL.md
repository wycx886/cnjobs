---
name: find-startups
description: Discover and verify new entrants for a specified market, including startups, new investment firms, spinouts, and genuinely new corporate ventures or research teams. Use for supplementary startup prospecting, emerging organizations, new GP teams, founder spinouts, or first-wave leads. Handoff to map-sectors and compose-profile after finding companies (then find-person, then find-channels). Note investment firms display under Financial Institutions and their formal discovery entry is find-investors; this skill only flags new VC teams as supplementary leads and never assigns them operating sectors.
---

# Find Startups · 新进玩家寻源

寻找指定市场中的新进机构或新形成的业务／研究单元。地域、行业、主题、时间和用途由当前任务决定；中国和 AI 是本仓库当前资料的使用场景，不是本 Skill 的固定门槛。

## 1. 确定范围与研究单位

读取任务给定的 `geography`、`market_or_theme`、`sectors`、`as_of`、`purpose`。能够由上下文确定时直接采用并说明；关键边界缺失时简短澄清，同时整理不依赖答案的线索。

先确认研究的是集团、法人、基金管理机构、具体业务团队、实验室还是项目。新进相对于所选市场判断，不用固定成立年份、上市、有无外部融资一个条件决定：

- **创业公司**：经营型新进玩家（`operating_organization` 且 `player_group: "new_entrant"`），在看板展示于“创业公司”。
- **金融机构（仅作补充线索）**：新 GP 团队、独立新投资机构也是机构目标，原团队案例和当前机构业绩分开。投资机构（`organization_type: "investment_firm"`）在看板中统一展示于“**金融机构**”，不归入创业公司或现有巨头；正式金融机构寻源入口是 [find-investors](../find-investors/SKILL.md)。本 Skill 在发现创业公司时可顺带识别新 GP 团队作为补充线索，但机构圈定、Tier 与 logo 交给该 Skill。

若任务主要寻找成熟平台、既有供应商或行业运营商，转用 [find-incumbents](../find-incumbents/SKILL.md)。成熟母公司不自动决定旗下新单元的归类；对有明确新目标与活动证据的孵化团队或拆分项目，本 Skill 可继续判断，不能把每个部门或产品都算成新创业机构。

## 2. 发现并核实候选

从具名产品／研究活动、创始团队、新机构公告、孵化与拆分信息、融资或客户披露寻找线索。先查稳定 ID、历史名称与别名，避免一个品牌更名或同一项目不同阶段被重复建档。

优先官网、公告、监管／登记、原始论文与官方代码、公开产品和客户材料；再用可靠报道补足。将事实、编辑判断和未确认消息分开。成立、登记、品牌启用、基金首关、内部立项和法律拆分分别注明口径。

- 大厂项目与团队：按 [共同的组织归属 SOP](../find-incumbents/references/corporate-ventures.md)，区分内部团队、实验室、产品项目、子公司、正式拆分与前员工创业。
- 新投资机构：按 [新 VC SOP](references/new-vc-spinouts.md)，核实团队原平台、当前策略、独立形成与案例归因。
- 本仓库的分类与投资归因：见 [分类参考](references/taxonomy-and-vc-rubric.md)；其 AI 赛道仅适用于经营型机构，投资机构不设赛道编号。

融资不是发现目标的必要条件。没有研究不能标“未找到融资”；内部资源与独立股权融资分开。只有确认内部身份且有来源时，当前契约才允许 `not_applicable`；媒体报道保留其证据强度，不能改成官方确认。

## 3. 输出候选与交接流程

每项至少交接：名称／别名、稳定 ID 或待定标记、研究单位、所选市场、主要业务／目标、新进理由、团队或母平台关系、公开活动与资本口径、来源及日期、仍待核实内容。

分为可研究候选、待核实和应转交已有玩家的对象；不自行制造质量排名、个人适配评分或收益。没有可靠主体与活动证据的线索先留私人草稿。

在机构确定后，按方法论标准链路交接：
1. **赛道与档案**：交接给 [map-sectors](../map-sectors/SKILL.md)（仅经营型机构归入既有 01–10 赛道，投资机构无 category_id）与 [compose-profile](../compose-profile/SKILL.md)（建立规范档案 `data/companies/<id>.json`）。
2. **核心人物（优先）**：交接给 [find-person](../find-person/SKILL.md) 优先挖掘核心人物（创始人/CEO/CTO/科学家/业务VP）及其公开专业主页（当前创业公司人物重点优先补齐）。
3. **公开渠道**：最后交接给 [find-channels](../find-channels/SKILL.md) 填充机构公开触达渠道模板（官网、官招链接、邮箱、BOSS直聘、猎聘、LinkedIn 企业主页）。

## 4. 适配本仓库

先读 `data/index.json`、`data/views/first-wave.md` 和 [数据模型](../../data/README.md)。完整记录统一保存在 `data/companies/`，经营型与投资机构由 `organization_type` 区分。金融机构的正式圈定与 Tier 见 [find-investors](../find-investors/SKILL.md)；本 Skill 仍可读取 `data/lists/vcs.json`，按 `company_id` 关联完整档案和来源，沿公开融资公告与已披露投资方发现候选。同时参考 `data/lists/incumbents.json` 查找大厂新孵化或拆分单元。参考名单属于数据，不在 Skill 中维护第二份名单。

```bash
python3 tools/query.py --entity organizations --wave first
python3 tools/audit_entities.py --player-group new_entrant --summary
python3 tools/scaffold_entity.py --entity company --id candidate-org --name "待核实机构" --category 04
```

共享脚手架默认只输出未核实草稿；`--save-draft` 才保存到配置的私人工作区，不直接写入公共库。当前公共数据以中国 AI 机会为主题；若任务超出其主题或分类，先在私人工作区交付通用研究 JSON／Markdown，或按明确任务扩充契约，不强塞进某个 AI 赛道。

正式记录用 `targeting.player_group`、`wave`、理由及来源表达编辑判断。原事实核查日期、关系核查日期和分类日期分别保留；资料不足用 `unresolved`／`watchlist`，不因导入或整理提升核验状态。生成版不可手改。

```bash
.venv/bin/python tools/validate.py
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
```

研究方法与第三方参考见 [方法说明](../find-incumbents/references/research-methods.md)。发现公司后依次交接 `map-sectors` / `compose-profile`、`find-person` 与 `find-channels`；不因完成名单而自动采集外部渠道、发消息、投递或预约。个人目的、偏好和沟通只保存在私人工作区。
