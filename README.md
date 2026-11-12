# cnjobs

面向 Agent 的机构研究与机会跟进开源框架。围绕 **“找公司（Companies）→ 公司档案（Profile & Sectors）→ 找核心人物（Key People）→ 找渠道（Channels）”** 的方法论（Opportunity Methodology）构建；主题、地域与行业由任务指定。当前公共数据集聚焦中国 AI 创业公司、大厂创新单元与活跃 VC 机构。

```text
skills/  方法论核心 Skills（找公司／档案与赛道／核心人物／公开渠道）与本地工作区
data/    正式公共 JSON（data/companies/）、寻源底表、Schema 契约与自动生成的阅读视图
tools/   共用查询、构建、校验、公开边界检查及自动化测试
lib/     DeepSeek Harness 插件入口：把上面的 skills 注册进 DSH（普通使用可忽略）
tests/   插件入口的 Node 测试
```

## 安装（Install）

两种用法共用同一份内容，互不冲突：

**1）普通仓库（任何 Agent）** — 直接 clone，按仓库根目录使用即可；Skill 是标准 `SKILL.md`，`AGENTS.md` 是通用 Agent 指令：

```bash
git clone https://github.com/wycx886/cnjobs.git
```

**2）DeepSeek Harness 插件** — 一条命令把 8 个 Skill 挂进 DSH profile，不需要 clone 到工作区：

```bash
dsh plugin --profile web add cnjobs      # npm
# 或从 GitHub 直接安装：dsh plugin --profile web add github:wycx886/cnjobs
dsh web
```

安装后 DSH 会从包内的 `skills/` 读取 skill，并在系统提示里注明框架根目录，因此 Skill 中的 `data/…`、`tools/…` 相对路径始终指向已安装副本。

Web 端在左侧栏新增 **CN Jobs** 导航项（与 Plugins / 账户额度 同一列），点击后主区域直接渲染本仓库生成的看板；会话区顶部另有 **CN Jobs** 标签页作为同一看板的会话内入口。看板由 host 半包把 `data/views/` 挂到 `/cnjobs/` 提供，数据与使用普通 clone 打开 `dashboard.html` 完全一致。卸载：

```bash
dsh plugin --profile web remove cnjobs
```

---

## 核心方法论：机会发现与触达（The Opportunity Methodology）

本仓库将行业研究、商务拓展与求职跟进提炼为结构化流程，每个步骤封装为独立的 Skill，共用同一套底层机构档案（`data/companies/*.json`）：

### 如何思考「找公司」

找公司的主路径是**先圈定金融机构，再为值得跟进的公司建档**，而不是先从零散新闻里捞创业公司。

1. **先圈定中国 Tier 1 / Tier 2 的 VC、PE 等金融机构**，范围先放大。由 [find-investors](skills/find-investors/SKILL.md) 完成。Tier 是有来源的编辑判断，不是官方排名：交叉参考清科、投中等近年公开榜单与机构官网，写明榜单名称、期次和链接；不能只凭一家榜单或印象打档。尽量从官网下载官方 logo 供看板使用；没有可靠图像就留占位，不生成假 logo，也不用 Clearbit 等第三方 logo CDN。
2. **再看这些机构投了哪些公司，并为每家公司建档**。用公司公告、监管／交易所披露和可靠报道核实值得跟进的公司。机构侧不另建投资组合清单，公司与投资方的关系记录在各公司档案的 `investment.rounds[].investors[]`（轮次名称、披露日期、已披露的投资方与金额；没有披露就留空，不编数字、不编轮次）。已在库中的公司回写到其 `data/companies/<id>.json`，并用投资方的 `firm_id` 关联到对应机构档案。
3. **最后再看这些公司里有哪些核心人物**，由 [find-person](skills/find-person/SKILL.md) 完成。人物是后续环节，不在找公司和建档之前提前铺开。

现有巨头、未出现在这些机构公开披露里的公司，仍可由 [find-incumbents](skills/find-incumbents/SKILL.md) / [find-startups](skills/find-startups/SKILL.md) 补充，但**发现公司的默认起点是金融机构**。

| 步骤 | 核心问题 | 对应 Skill | 解决什么问题与如何执行 |
| --- | --- | --- | --- |
| **1. 找公司与机构**<br>*(Find Companies)* | **有哪些值得关注的机构？** | [find-investors](skills/find-investors/SKILL.md)<br>[find-startups](skills/find-startups/SKILL.md)<br>[find-incumbents](skills/find-incumbents/SKILL.md) | **先圈定金融机构，再为值得跟进的公司建档**：`find-investors` 圈定中国 Tier 1／Tier 2 的 VC、PE 等金融机构，交叉参考公开榜单打 Tier、从官网收集 logo；公司的融资轮次与已披露投资方记录在各公司档案的 `investment.rounds[].investors[]`；`find-startups` 与 `find-incumbents` 保留为新进创业公司与现有巨头的补充寻源。投资机构（`investment_firm`）在看板统一展示于“金融机构”，不混入创业公司或现有巨头。 |
| **2. 赛道与公司档案**<br>*(Sectors & Profile)* | **属于哪个赛道？唯一档案如何建立？** | [map-sectors](skills/map-sectors/SKILL.md)<br>[compose-profile](skills/compose-profile/SKILL.md) | **标准建档与赛道归入**：`map-sectors` 将经营型机构归入既有 01–10 赛道（投资机构无 category_id，按自身 group 等分组）；`compose-profile` 维护唯一源 `data/companies/<id>.json`，抓取创业公司与金融机构的官方 Logo，并通过 `build.py` 生成交互看板。 |
| **3. 找核心人物（最重要）**<br>*(Find Key People)* | **有哪些核心人物，去哪里直接建联？** | [find-person](skills/find-person/SKILL.md) | **最核心环节与人物级建联**：锁定机构的 **Key People**（创始人/CEO/CTO、首席科学家、商业化/业务 VP、VC 创始/管理合伙人），核实其在 **LinkedIn**（个人页 `/in/`）、**X (Twitter)**、**GitHub**（核验 `account_type: "User"`）、**即刻** 上的公开主页与建联策略（详见 [核心人物建联指南](skills/find-person/references/person-outreach.md)）。目前创业公司核心人物大多为空白，是最高优先级补齐对象。 |
| **4. 找机构公开渠道**<br>*(Find Channels)* | **有哪些公开渠道可以 Approach？** | [find-channels](skills/find-channels/SKILL.md) | **最后触达入口（动态模板）**：核实机构的 6 个标准槽位——官方网站、官方招聘/投递链接（`careers_url`）、公开招聘邮箱、**BOSS 直聘** 企业主页、**猎聘** 企业主页、**LinkedIn** 企业主页（`professional_social`），由 Agent 后续核实填充动态模板，绝不猜测 URL 或邮箱。 |
| **本地管理**<br>*(Private Workspace)* | **如何管理我自己的跟进记录？** | [setup-workspace](skills/setup-workspace/SKILL.md) | **公私物理隔离**：在本地被 Git 忽略的 `workspace/` 中维护个人履历、目标偏好、LinkedIn/BOSS 沟通进展与邮件草稿，绝不外流至公共仓库。 |

---

## 快速导航（从这里开始）

| 需求 | 入口 |
| --- | --- |
| **Agent 规则与任务路由** | [AGENTS.md](AGENTS.md) |
| **第一阶段（默认起点）：圈定 Tier 1／Tier 2 金融机构 → 打 Tier、收 logo、记人物** | [find-investors](skills/find-investors/SKILL.md) · [榜单与 Tier 口径](skills/find-investors/references/tier-and-rankings.md) |
| **第一阶段（补充）：寻找新进创业公司、新 VC 与拆分项目** | [find-startups](skills/find-startups/SKILL.md) · [新进 VC 识别 SOP](skills/find-startups/references/new-vc-spinouts.md) |
| **第一阶段（补充）：寻找已有巨头、大厂实验室与业务团队** | [find-incumbents](skills/find-incumbents/SKILL.md) · [大厂项目与拆分 SOP](skills/find-incumbents/references/corporate-ventures.md) |
| **第二阶段：归入既有赛道 / 维护公司档案** | [map-sectors](skills/map-sectors/SKILL.md) · [compose-profile](skills/compose-profile/SKILL.md) · 只写 `data/companies/<id>.json`，页面与索引由 `build.py` 生成 |
| **第三阶段：核查核心人物与公开主页（最优先）** | [find-person](skills/find-person/SKILL.md) · [核心人物建联指南](skills/find-person/references/person-outreach.md) |
| **第四阶段：核查机构公开渠道（官网 / 官招 / 邮箱 / BOSS / 猎聘 / LinkedIn 企业页）** | [find-channels](skills/find-channels/SKILL.md) · [公开渠道采集 SOP](skills/find-channels/references/layer2-research.md) |
| **浏览自动生成的中国 AI 与 VC 公开资料** | [统一机器索引](data/index.json) · [阅读总目录](data/views/README.md) · [第一波新进名单](data/views/first-wave.md) · [VC 机构目录](data/views/vcs.md) |
| **筛选、搜索并展开机构档案** | [交互看板](data/views/dashboard.html) · 第一层先分 **创业公司／现有巨头／金融机构**（未归类单独放置），第二层按既有 01–10 赛道分区；再搜索、按城市／批次筛选，查看核心人物、渠道与来源 |
| **查看数据契约、查询工具与 Git 同步边界** | [数据模型说明](data/README.md) · [工具与同步说明](tools/README.md) |

---

## 数据如何组织与流转

1. **统一机构档案（Companies）与 Tier 1 分类**：所有完整公共档案统一维护在 `data/companies/*.json`。看板第一层划分 **创业公司**（经营型新进）、**现有巨头**（经营型已有）与 **金融机构**（`investment_firm`）。经营型机构归入既有 01–10 赛道，投资机构不设赛道编号。参考寻源名单在 `data/lists/vcs.json` 与 `data/lists/incumbents.json`；赛道分类在 `data/taxonomy.json`。投资机构可记录有来源的 `tier`；经营型公司可记录 `founded` 与 `investment.rounds[]`（含已披露投资方）。这些字段都是可选、按披露留空，不当官方排名或补齐率指标。`data/index.json` 和 `data/views/` 由 `python3 tools/build.py` 自动生成。
同一家公司统一维护，办公地不另建上海／苏州等地区公司副本；当地线索、来源与核查日期保留在主档案 `regional_notes[]`。真实独立机构和具备不同业务边界的项目分别核实；旧地区阅读链接兼容跳转到主公司。

2. **核心人物（Key People）优先与机构渠道（Channels）模板**：
   - 核心人物身份、职务和履历统一写入 `people[]`；LinkedIn、X、GitHub 等个人主页写入该人物的 `profiles[]`。新增人物证据标 `scope: "person"`，身份与主页独立记录来源、核验状态和核查日期。创业公司人物为当前重点补齐对象。
   - `channels[]` 保存机构 6 个标准槽位入口（官网、官招链接、公开招聘邮箱、BOSS直聘／猎聘企业主页及 LinkedIn 企业主页等），`owner.scope` 为 `organization`，证据标 `scope: "channel"`。
   - 公开人物档案采集与公开渠道维护直接更新 `data/companies/<id>.json`，不经过私人 `inbox/`，也不要求初始化私人工作区。

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
