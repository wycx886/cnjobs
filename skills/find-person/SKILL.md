---
name: find-person
description: Find and verify founders, executives, researchers, business leads and investment partners for target organizations, with public professional profiles and identity evidence. Core people discovery is the most important step; prioritize operating startups where people[] is currently empty. Write identities and personal profiles only to company people[]; organization accounts belong to find-channels.
---

# Find Person · 核心人物与公开专业主页

在方法论（**找公司 → 公司档案 → 找核心人物 → 找渠道**）中，核心人物（Key People）是**最重要、最有价值的信息**：锁定他们是谁，以及他们在公开专业平台上的主页与直接联系入口。

这是公开人物研究，可按任务独立开展，不要求先完成全部机构渠道。主题、地域、人物角色与用途由任务确定，不限 AI、某个行业、模型或采集工具。实际建联与投递是另一项个人任务。

> [!IMPORTANT]
> **当前重点优先级**：当前公共数据集中，金融机构（VC）的人物已部分迁入 `people[]`，而绝大多数经营型创业公司（`operating_organization` 且 `player_group: "new_entrant"`）的 `people[]` 目前仍为空白。**创业公司的核心人物（创始人/CEO/CTO、首席科学家、业务与商业化负责人）是当前的最高优先级补齐对象**。

## 1. 选择研究对象

读仓库 `AGENTS.md`、`data/index.json` 与目标公司 JSON，复用机构 ID 和已有 `people[]`。新进机构与已有巨头的寻源分别见 [find-startups](../find-startups/SKILL.md) 与 [find-incumbents](../find-incumbents/SKILL.md)；档案维护见 [compose-profile](../compose-profile/SKILL.md)。按任务覆盖创始人、CEO／CTO、研究负责人、业务及商业化负责人，或 VC 创始／管理合伙人和相关投资团队。

人物只维护在公司档案的 `people[]`；原 VC `team[]` 已迁入其中。迁移人物的 `partial` 标记和原日期只表示既有资料，不等于重新核实当前职务或已找到主页。不要因为知道姓名就猜测社媒账号。

```bash
python3 skills/find-person/scripts/audit_people.py --wave all --summary
python3 skills/find-person/scripts/audit_people.py --entity operating --wave first --missing-only
```

## 2. 交叉核实身份与主页

- 先确认“是谁、当前属于哪家机构、担任何职”，再定位公开专业主页；当前职务、原平台与历史履历分开。以机构官方人物介绍、本人公开介绍、官方论文／代码或可核对的公开报道交叉确认。
- 至少实际读取个人主页和一处不同 URL 的身份支持材料；不同 URL 本身不证明两项材料可靠或互相独立。保留标题、支持内容、公开日期及真实核查日期，核实每项拟写入的身份事实。
- LinkedIn 使用 `/in/<person>`，公司页属于机构渠道；X 使用账号主页而非帖子／搜索页；GitHub 使用个人账号而非项目仓库。GitHub API `/users/<handle>` 对机构账号也会返回数据，须实际核对 `type` 为 `User`，不能仅凭 URL 形状确认个人；API 账号类型证据也不能单独替代身份和当前任职核验。
- 论文平台、即刻、知乎与个人网站同样核对姓名、机构和职业活动。同名、访问受限或现职存疑时，在报告说明缺口，不补造 `confirmed`。

机构官方 LinkedIn／X／GitHub 账号交给 [find-channels](../find-channels/SKILL.md)，不得塞进人物资料。私人电话、微信、聊天截图与个人求职状态不属于公共研究。

## 3. 直接更新 `people[]`

公司档案 `data/companies/<id>.json` 使用 [人物契约](../../data/schemas/person.schema.json)：

| 位置 | 内容 |
| --- | --- |
| `people[].name`、`role`、`background`、`previous_firms` | 姓名、职务、公开背景及原平台；未知字段用 `null` 或空数组，不编造 |
| 人物的 `source_ids`、`checked_at`、`verification_status`、`notes` | 身份事实的独立依据、日期和限制 |
| `people[].profiles[]` | 平台、个人主页 URL、核查日期、状态、来源与备注；GitHub 另记实查的 `account_type: "User"` |
| `sources[]` | 新人物证据标 `scope: "person"`，不刷新公司业务日期或用于投资案例归因 |

可直接编辑后校验，也可向 [update_people.py](scripts/update_people.py) 传入 [人物批次](../../data/schemas/person-batch.schema.json)：顶层 `schema_version: 1`、`public_only: true`、`entries`。每项含机构类型和 ID、人物姓名、职务／背景／原平台、平台和主页 URL、实际核查日期、页面标题、`verification_status: "confirmed"`，以及 `identity_evidence` 支持材料。每份材料含 `title`、`url`、`supports`、`published_date`（未知用 `null`）、`checked_at`；支持材料不能重复个人主页来凑证据。GitHub 须附个人账号 API 的真实观察。

```bash
# 从采集程序的实际公开观察 JSON 读取，无需私人工作区或 inbox：
.venv/bin/python skills/find-person/scripts/update_people.py --apply
```

也可使用 `--batch-file PATH`；不带 `--apply` 时仅预览。工具按 URL 与支持内容保留人物证据，避免两个人共用团队页时覆盖彼此依据；被替换的旧证据记入 `historical_source_ids`，不冒充当前核查依据。工具拒绝错误平台、旧日期、重复身份／主页和不完整证据，全部输入验证后才写入；并发改动会被保留。它不联网验证内容，采集者仍需实际核对证据。不要用空值在补主页时悄悄清除既有履历；需要纠正旧事实时连同来源一并明确修改。

### 可选：人物照片

`people[].photo` 可选项，仅在确实下载到可公开使用的照片时填写；没有照片就保留看板的单字头像框，不猜图、不用私人照片。字段为：`path`（`assets/people/<person-id>.<jpg|jpeg|png|webp>`，相对 `data/views/`，须 < 400 KB）、`source_url`（实际下载的图片文件 https 地址）、`page_url`（照片公开出现的页面：官方团队页、新闻页或本人公开主页）、`checked_at`、`source_ids`（引用同档案 `sources[]`，与人物证据同规则）。看板人物卡会显示照片并在角标保留“图源”链接；`tools/validate.py` 校验文件存在与体积。

## 4. 完成研究与交接

```bash
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
```

阅读版自动展示人物身份状态、来源、原日期与主页。汇报新增或更新的人物、已核实主页和缺口；不把迁移旧人物当作新采集成果。

核心人物核实完成后，机构的公开触达通道（官网、官招、招聘邮箱、BOSS直聘、猎聘、LinkedIn 企业主页）交由 [find-channels](../find-channels/SKILL.md) 补充动态模板。

如用户另行要求准备建联，参考 [草稿指南](references/person-outreach.md)。读取私人事实和偏好、生成定制消息或记录真实进展按私人工作区规则执行；本 Skill 不授权发送邀请、私聊、投递或预约。
