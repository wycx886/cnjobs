# cn_ai_opp

面向 Agent 的机构研究与机会跟进开源框架。围绕 **“找公司（Companies）→ 找渠道（Channels）→ 找核心人物（Key People）”** 的三步方法论（Three-Step Opportunity Methodology）构建；主题、地域与行业由任务指定。当前公共数据集聚焦中国 AI 创业公司、大厂创新单元与活跃 VC 机构。

```text
skills/  三步法核心 Skills、赛道归入、公司档案与本地工作区
data/    正式公共 JSON（data/companies/）、寻源底表、Schema 契约与自动生成的阅读视图
tools/   共用查询、构建、校验、公开边界检查及自动化测试
```

---

## 核心方法论：三步机会发现与触达（The 3-Step Methodology）

本仓库将行业研究、商务拓展与求职跟进提炼为三个正交的步骤，每个步骤封装为独立的 Skill，共用同一套底层机构档案（`data/companies/*.json`）：

| 步骤 | 核心问题 | 对应 Skill | 解决什么问题与如何执行 |
| --- | --- | --- | --- |
| **1. 找公司与机构**<br>*(Find Companies)* | **有哪些值得关注的机构？** | [find-startups](skills/find-startups/SKILL.md)<br>[find-incumbents](skills/find-incumbents/SKILL.md) | **双轨寻源**：`find-startups` 发现创业机构、新设独立 VC 与大厂新孵化／拆分单元，不设固定成立年份限制；`find-incumbents` 发现已有玩家（成熟科技平台、软硬件巨头及具体业务团队）。 |
| **2. 找机构渠道**<br>*(Find Channels)* | **有哪些公开渠道可以 Approach？** | [find-channels](skills/find-channels/SKILL.md) | **机构级入口**：核实每家机构的官方网站、官方招聘站（`careers_url`）、公开招聘/BP/商务邮箱，以及在 **BOSS 直聘、猎聘** 等招聘平台上的公开认证企业主页。 |
| **3. 找核心人物**<br>*(Find Person)* | **有哪些核心人物，去哪里直接建联？** | [find-person](skills/find-person/SKILL.md) | **人物级建联**：锁定机构的 **Key People**（创始人/CEO/CTO、首席科学家、商业化/业务 VP、VC 创始/管理合伙人），核实他们在 **LinkedIn**（直接 Connect / Link）、**X (Twitter)**（互动或 DM）、**GitHub**、**即刻** 上的公开主页与建联策略（详见 [核心人物建联指南](skills/find-person/references/person-outreach.md)）。 |
| **本地管理**<br>*(Private Workspace)* | **如何管理我自己的跟进记录？** | [setup-workspace](skills/setup-workspace/SKILL.md) | **公私物理隔离**：在本地被 Git 忽略的 `workspace/` 中维护个人履历、目标偏好、LinkedIn/BOSS 沟通进展与邮件草稿，绝不外流至公共仓库。 |

---

## 快速导航（从这里开始）

| 需求 | 入口 |
| --- | --- |
| **Agent 规则与任务路由** | [AGENTS.md](AGENTS.md) |
| **第一步：寻找新进创业机构、新 VC 与拆分项目** | [find-startups](skills/find-startups/SKILL.md) · [新进 VC 识别 SOP](skills/find-startups/references/new-vc-spinouts.md) |
| **第一步：寻找已有玩家、大厂实验室与业务团队** | [find-incumbents](skills/find-incumbents/SKILL.md) · [大厂项目与拆分 SOP](skills/find-incumbents/references/corporate-ventures.md) |
| **第二步：核查机构公开渠道（官网 / 邮箱 / BOSS / 猎聘）** | [find-channels](skills/find-channels/SKILL.md) · [公开渠道采集 SOP](skills/find-channels/references/layer2-research.md) |
| **第三步：核查核心人物与 LinkedIn / X 直接建联** | [find-person](skills/find-person/SKILL.md) · [核心人物建联指南](skills/find-person/references/person-outreach.md) |
| **浏览自动生成的中国 AI 与 VC 公开资料** | [统一机器索引](data/index.json) · [阅读总目录](data/views/README.md) · [第一波新进名单](data/views/first-wave.md) · [VC 机构目录](data/views/vcs.md) |
| **筛选、搜索并展开机构档案** | [交互看板](data/views/dashboard.html) · 第一层先分 **创业公司／现有巨头／金融机构**（未归类单独放置），第二层按既有 01–10 赛道分区；再搜索、按城市／批次筛选，查看核心人物、渠道与来源 |
| **归入既有赛道 / 维护公司档案** | [map-sectors](skills/map-sectors/SKILL.md) · [compose-profile](skills/compose-profile/SKILL.md) · 只写 `data/companies/<id>.json`，页面与索引由 `build.py` 生成 |
| **查看数据契约、查询工具与 Git 同步边界** | [数据模型说明](data/README.md) · [工具与同步说明](tools/README.md) |

---

## 数据如何组织与流转

1. **统一机构档案（Companies）**：所有完整公共档案统一维护在 `data/companies/*.json`（通过 `organization_type` 区分经营型机构 `operating_organization` 与投资机构 `investment_firm`）。参考寻源名单在 `data/lists/vcs.json` 与 `data/lists/incumbents.json`；赛道分类在 `data/taxonomy.json`。`data/index.json` 和 `data/views/` 由 `python3 tools/build.py` 自动生成。
同一家公司统一维护，办公地不另建上海／苏州等地区公司副本；当地线索、来源与核查日期保留在主档案 `regional_notes[]`。真实独立机构和具备不同业务边界的项目分别核实；旧地区阅读链接兼容跳转到主公司。

2. **机构渠道（Channels）与核心人物（Key People）直接入库**：
   - `channels[]` 只保存机构入口（官网、官招、BOSS直聘／猎聘企业主页及机构官方社媒），`owner.scope` 为 `organization`，证据标 `scope: "channel"`。
   - 核心人物身份、职务和履历统一写入 `people[]`；LinkedIn、X、GitHub 等个人主页写入该人物的 `profiles[]`。新增人物证据标 `scope: "person"`，身份与主页独立记录来源、核验状态和核查日期。原 VC 团队资料已迁入 `people[]`，迁移不代表重新核实当前职务。
   - 公开渠道与公开人物档案采集直接更新 `data/companies/<id>.json`，不经过私人 `inbox/`，也不要求初始化私人工作区。

---

## 私人工作区（Private Workspace）

Fork 使用者首次由 Agent 从简历整理 `profile.md`，提出候选职业方向，并确认行业、岗位、期望地点与用户输入的薪资口径。默认工作区只有事实、偏好、`resume/`、`applications/` 及入口／规则文件；目录程序仅创建骨架，可导入明确指定的简历：

```bash
python3 skills/setup-workspace/scripts/init_local.py --resume-file /path/to/resume.pdf
```

若已有现成的私人工作区，直接绑定路径，保持唯一档案：

```bash
python3 skills/setup-workspace/scripts/init_local.py --workspace ../my-private-workspace --use-existing
```

初始化后的工作区根目录仅有 `AGENTS.md`、`profile.md`、`preferences.md`、`resume/` 和 `applications/`。`AGENTS.md` 合并目录说明与全部个人记录规则；applications 只初始化公司路由 `index.md`，不设额外 AGENTS、README 或 inbox。拒绝先记录，归档只按用户明确要求执行。完整初始化由 Agent 接着完成：读取用户简历 → 整理事实 → 建议方向 → 确认行业、岗位、地点与薪资偏好；只创建空白目录不算完成。已有资料直接复用。

个人事实、简历、偏好、针对某位核心人物或 HR 的实际建联消息、私聊记录与投递进展只留在私人工作区（空白模板见 [setup-workspace/assets/templates](skills/setup-workspace/assets/templates/README.md)）；`workspace.local.json` 同样被 Git 忽略，绝不上传。
