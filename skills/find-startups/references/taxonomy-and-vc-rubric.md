# 机构分类与案例归因参考

## Tier 1 机构分类与第二维度

机构顶层按 Tier 1 划分为三类：
1. **创业公司**：经营型新进机构（`operating_organization` + `player_group: "new_entrant"`）。
2. **现有巨头**：经营型已有玩家（`operating_organization` + `player_group: "incumbent"`）。
3. **金融机构**：投资机构（`organization_type: "investment_firm"`）。在看板中独立展示于“金融机构”顶层分区，不混入前两者。

编辑分类不等于已核实的成立年份、当前法律独立性或投资价值结论，`labelled_at` 与原事实 `checked_at` 分开。不把统一年份、上市状态或有无 VC 资金当作唯一门槛。

## 经营型机构赛道（01–10 仅适用于经营型）

01–10 主赛道**仅适用于经营型机构（`operating_organization`）**；**投资机构没有 `category_id`**，绝不能为投资机构编造或指派 01–10 赛道。

赛道归入方法由 [map-sectors](../../map-sectors/SKILL.md) 定义；赛道名称、边界和子类的唯一维护源是 [data/taxonomy.json](../../../data/taxonomy.json)。具体数据契约见 [数据模型](../../../data/README.md)。此处不维护平行分类，消除多处维护带来的分叉风险。

## 投资机构组织与归因

投资机构按自身既有字段（`group` 如 `emerging` / `established`、`coverage`、`stage`）进行分组与展示。

新团队识别见 [新进 VC SOP](new-vc-spinouts.md)，完整披露边界见 [VC 方法](investment-cases.md)。

- `prior_firm`：投资人／团队在原机构的案例。原平台的知名案例不能自动记成新机构业绩，参与也不自动等于主导。
- `current_firm`：可归属于当前投资机构的案例；并不等于某一只基金的投资。
- 成立、管理人登记、首期基金设立或首关、品牌更名、独立运营各自记录口径。
- IPO、后续融资、账面估值和已实现退出分别说明；没有公开 DPI／IRR 时不推算。

现有 cohort 是历史描述性分组，由 `group`、`founded.year` 派生；它不作为第一波新进判断的年份门槛。`coverage.role` 表示主要样本、观察或相邻范围，也不是收益评级。缺少成熟退出不是新 GP 被排除的理由。
