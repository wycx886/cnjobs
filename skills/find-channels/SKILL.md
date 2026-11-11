---
name: find-channels
description: Find and verify public organization-level channels using a standard 6-slot dynamic template (official site, careers link, recruitment email, BOSS Zhipin, Liepin, and LinkedIn company page). Final touchpoint step of the opportunity methodology after key-person discovery. Never guess URLs or emails. Organization accounts only; route personal profiles to find-person.
---

# Find Channels · 机构公开触达渠道

本 Skill 对应方法论的最后落地通道（**找公司 → 公司档案 → 找核心人物 → 找渠道**）：在确定目标机构（[find-startups](../find-startups/SKILL.md) ／ [find-incumbents](../find-incumbents/SKILL.md)）、建立公司档案（[compose-profile](../compose-profile/SKILL.md)）并优先完成核心人物研究（[find-person](../find-person/SKILL.md)）之后，核实**机构级（Organization-level）公开触达入口**。具体创始人、高管或 VC 合伙人的个人主页（LinkedIn `/in/`、X、GitHub 等）由 [find-person](../find-person/SKILL.md) 维护。

渠道信息被视为由 Agent 后续核实并填充的**动态模板**。公开企业主页与官方入口属于公司资料，已核实后直接更新 `data/companies/<id>.json`；个人聊天、简历和投递进展才属于私人 `applications`。公开研究不要求读取履历、求职偏好、私人工作区配置，也不先写私人 `inbox/`。

## 1. 机构公开渠道的六槽位动态模板

针对每家目标机构，维护标准 6 槽位模板。**绝不按域名或命名规则猜测 URL 或邮箱**，所有槽位必须来自实际访问核验并记录对应证据：

| 槽位 | 渠道类别 (`layer`) | 平台标识与核验对象 | 说明与约束 |
| --- | --- | --- | --- |
| **1. 官方网站** | `official` | `website`（`contacts.website` 或 `channels`） | 机构正式官网入口，核对主体与 ICP 备案 |
| **2. 官招/投递链接** | `official` | `careers_url`（`contacts.careers_url` 或 `channels`） | 官方招聘站点、ATS 投递页面或人才入库入口 |
| **3. 招聘邮箱** | `official` | `recruitment_email`（存入 `contacts.recruitment_email`） | 页面明确注明的招聘/求职专用邮箱，不猜前缀 |
| **4. BOSS 直聘企业主页** | `recruitment_platform` | `boss_zhipin` | 机构在 BOSS 直聘认证的公开企业主页（`owner.scope: "organization"`） |
| **5. 猎聘企业主页** | `recruitment_platform` | `liepin` | 机构在猎聘认证的公开企业主页（`owner.scope: "organization"`） |
| **6. LinkedIn 企业主页** | `professional_social` | `linkedin` | **LinkedIn 公司主页**（`layer` 固定为 `professional_social`，`owner.scope: "organization"`；个人主页 `/in/` 交由 [find-person](../find-person/SKILL.md)） |

可用审计工具输出覆盖情况或任务模板：

```bash
python3 skills/find-channels/scripts/audit_channels.py --entity companies --wave all --summary
python3 skills/find-channels/scripts/audit_channels.py --entity companies --wave all --offset 0 --limit 20 --template
```

## 2. 核实并直接更新公司资料

1. **核对主体归属**：核对平台页面中的机构名称、官网、地区和工商/运营主体，区分同名公司、品牌、集团与子公司。复用正式记录的名称／别名；新发现的主体名称需先以公开证据确认，再补充别名。
   `owner.name` 保存网页实际观察到的机构名称，不改写成目标公司标签。集团主页、其他城市法人及相关销售公司可保留为关联入口，但目标单元对应关系未证实时只能标 `partial`，并在 `notes` 说明待核实项；不得把集团／产品名称补成地区单元的同一主体别名来通过校验。
2. **区分入口用途与严禁猜测**：记录稳定的企业主页、实际核查日期、证据标题与来源。招聘、BP、商务、客服等邮箱用途严格分开，**绝不按域名格式猜测邮箱或拼接 URL**。
地区岗位、办公室或地区招聘法人只在主公司内说明适用范围；不另建同名地区公司。关联法人的渠道仍保留原主体和未确认状态，不能因归并而提升为集团已确认入口。

3. **写入结构化 `channels`**：将已核实的公开入口写入该公司 `channels`，证据写入 `sources` 并标 `scope: "channel"`。原业务 `checked_at`、其他事实与既有渠道保持原意，重复核查更新同一入口，不制造副本。
4. **如实报告缺口**：未找到、访问受限或主体无法确定时，在本次研究报告中逐公司列明平台、实际检查日期与缺口，不写成 `confirmed`，也不创建私人 application 或 inbox 记录。
5. **不把短期 JD 当企业主页**：`channels` 专门存稳定的机构级入口，不能用两周就下线的单个岗位链接冒充企业主页。

`channels[]` 只记录机构网页入口，`owner.scope` 固定 `organization`。公开邮箱值仍放在 `contacts` 的相应用途字段，以实际披露页面提供证据，不把邮箱猜成招聘用途；`mailto:` 不能冒充网页 URL。个人姓名、职务、履历和主页只维护在公司 `people[]`。

字段契约详见 [数据模型](../../data/README.md)。

## 3. 批量校验与原子写入工具

采集 Agent 可直接编辑公司 JSON 后校验，也可把已经核实的招聘平台企业主页观察 JSON 经标准输入交给 [update_layer2.py](scripts/update_layer2.py)，直接更新公司档案，不经过私人目录。

输入契约见 [channel-batch.schema.json](../../data/schemas/channel-batch.schema.json)：顶层 `schema_version: 1`、`public_only: true`、`entries`；每项包含 `entity_type`、`entity_id`、`platform`、`url`、`observed_name`、`checked_at`、`evidence_title`、`verification_status: "confirmed"`。

此批量工具仅接收主体已核实且与目标名称／有证据别名匹配的观察；集团与地区单元的关联线索应直接编辑 JSON，保留实际 `owner.name`、`partial` 状态和缺口说明后校验。更新同一入口时同步修正主体证据，不沿用旧的归属描述。

```bash
# 将采集程序实际观察到的 JSON 输出通过管道交给此命令，直接原子更新公司档案：
.venv/bin/python skills/find-channels/scripts/update_layer2.py --apply
```

复核同一入口时，当前 `source_ids` 与 `historical_source_ids` 分开保存，旧来源的支持内容和日期不覆盖。打不开的新观察不能替换成 `confirmed`；保留原核查日的旧确认时，在备注中写明本轮访问限制。

## 4. 完成校验

```bash
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
```

汇报已更新公司／平台与未解决项，公共资料可随仓库同步 GitHub。通用采集参考见 [执行参考](references/layer2-research.md)。

采集 Agent 可直接编辑公司 JSON 后校验，也可把已经核实的招聘平台企业主页观察 JSON 经标准输入交给 [update_layer2.py](scripts/update_layer2.py)，直接更新公司档案，不经过私人目录。

输入契约见 [channel-batch.schema.json](../../data/schemas/channel-batch.schema.json)：顶层 `schema_version: 1`、`public_only: true`、`entries`；每项包含 `entity_type`、`entity_id`、`platform`、`url`、`observed_name`、`checked_at`、`evidence_title`、`verification_status: "confirmed"`。

此批量工具仅接收主体已核实且与目标名称／有证据别名匹配的观察；集团与地区单元的关联线索应直接编辑 JSON，保留实际 `owner.name`、`partial` 状态和缺口说明后校验。更新同一入口时同步修正主体证据，不沿用旧的归属描述。

```bash
# 将采集程序实际观察到的 JSON 输出通过管道交给此命令，直接原子更新公司档案：
.venv/bin/python skills/find-channels/scripts/update_layer2.py --apply
```

复核同一入口时，当前 `source_ids` 与 `historical_source_ids` 分开保存，旧来源的支持内容和日期不覆盖。打不开的新观察不能替换成 `confirmed`；保留原核查日的旧确认时，在备注中写明本轮访问限制。

## 4. 完成校验

```bash
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
```

汇报已更新公司／平台与未解决项，公共资料可随仓库同步 GitHub。通用采集参考见 [执行参考](references/layer2-research.md)。
