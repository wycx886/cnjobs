# 数据字段、第一波标记与公开渠道

公共记录是有来源的研究资料；个人偏好、简历、联系人聊天和投递状态保存在配置的私人工作区，见 [本地工作流](../skills/setup-workspace/references/workflow.md)。

## 正式记录与生成内容

`data/companies/`、`data/lists/` 和 `data/taxonomy.json` 保存正式、可维护的 JSON；`data/views/` 是由这些 JSON 生成的人类阅读版和 CSV。同一条记录不在两处分别维护。

例如修改 `data/companies/hypershell.json` 后运行 `python3 tools/build.py`，生成 `data/views/companies/hypershell.md`、汇总 CSV 与索引。生成的机构数量、分类和名单以当前 JSON 计算，README 不重复维护一份数字清单。

| 位置 | 职责 |
| --- | --- |
| `data/companies/*.json` | 所有完整公司／机构档案，包括经营型机构、投资机构及单列的研究单元 |
| `data/taxonomy.json` | 经营型机构赛道的编辑分类定义 |
| `data/lists/vcs.json` | 用于发现新机构与投资线索的参考名单；引用 `companies/` 的稳定 ID 与来源，不复制完整档案 |
| `data/lists/incumbents.json` | 当前中国 AI 的已有玩家／母平台寻源底表、行业标签与主题证据；不计入正式机构目标 |
| `data/index.json` | 唯一自动生成的机器索引，schema version 4；`organizations` 同时收录经营型机构和投资机构 |
| `data/views/first-wave.md` | 自动生成的第一波与观察候选阅读版 |
| `data/views/incumbents.md` | 自动生成的母平台排查清单；官网身份核对不等于项目核验 |
| `data/views/corporate-ventures.md` | 已有 `organizational_context` 标注的经营型记录阅读版 |
| `data/views/later.md` | 已有玩家的现有资料登记；保留研究批次，不禁止后续研究 |
| 其他 `data/views/` 与统一机器索引 | 自动生成的明细、分类、CSV 和检索入口 |

仓库更名保留既有 schema URN 标识，兼容旧读取器；文件入口采用新名称。经营型／投资机构采用 schema version 3；契约见 [company.schema.json](schemas/company.schema.json) 和 [investor.schema.json](schemas/investor.schema.json)。分类文件保留自己的版本约定，见 [taxonomy.schema.json](schemas/taxonomy.schema.json)。


机器索引只维护 `data/index.json`。`organizations` 中的每项用 `organization_type` 区分类型，并提供稳定 ID、名称／别名、业务、标记、实际核查日期、原始 JSON 路径与阅读版路径；保留各类型的赛道、融资状态、团队、案例归因等摘要。`counts.companies` 与 `counts.organizations` 都是全部档案数，`operating_organizations`／`investment_firms` 才是类型分项；`statistics` 同样按这两种类型汇总。索引与阅读版均由 `tools/build.py` 生成，不手改，也不替代带完整来源的单条记录。

## 名单与完整档案

`data/lists/` 放可被不同 Skill 共用的发现入口；Skill 只说明查找方法与读取路径。`vcs.json` 的每个条目包含 `company_id`、`source_ids` 和 `discovery_use`，通过 `company_id` 读取 `data/companies/<id>.json` 的名称、官网、来源和真实核查日期。作为寻源入口与作为研究目标是不同用途，同一家 VC 只维护一份完整档案。条目来源必须是所引用公司的业务证据，不能只凭招聘渠道入表。

`incumbents.json` 保留已有玩家底表的 `platforms` 数组及其 ID、别名、访问范围与主题证据；这些种子不自动成为完整目标。如果需要完整研究或 Layer 2／3，为对应机构建立 `companies/` 档案，并复用可确认的稳定身份。

原来 `data/investors/<id>.json` 的完整资料现统一位于 `data/companies/<id>.json`；原 `data/platforms.json` 改为 `data/lists/incumbents.json`。Agent 先读当前 `data/index.json` 获取路径，勿拼接旧目录。索引 v4 的 `counts.companies` 从经营型数量改为全部公司数量，类型分项与 `statistics` 改用 `operating_organizations`／`investment_firms`；分项日期相应为 `latest_operating_check`／`latest_investment_firm_check`。

## 公司主体与地区信息

同一公司统一保存一个主档案，上海／苏州等办公地、当地岗位线索与渠道适用范围收进主档案，不按城市复制公司。真实法人名称中的地名保留；有不同主体或业务／项目边界的机构不能仅因品牌相同而合并。

`regional_notes[]` 按 `region`、`summary`、`source_ids`、`checked_at` 保留地区研究、原地区名称与 ID、组织边界、历史判断、导入出处和未核实范围。来源仍位于同一公司的 `sources[]`，不得把地区结论扩张为集团全部业务事实。地区资料有独立日期，其引用的业务来源可晚于主档案业务 `checked_at`；合并不刷新该主档案日期，也不提升渠道核验状态。地区来源不能凭日期较新就当作集团全部事实重新核验。

旧地区 ID 在 `lists/company-redirects.json` 单向映射到现存主公司 ID，不允许循环、链式跳转或旧 ID 继续建公司 JSON。生成的旧 Markdown 页只兼容历史阅读链接，不进入机构索引或公司计数。`tools/query.py --id <旧ID>` 返回主档案；写入工具要求使用当前主公司 ID，避免把地区别名静默当作法人归属依据。

## 第一波与机构类型

看板第一层为 Tier 1 机构分类：
1. **创业公司**：经营型新进玩家（`organization_type: "operating_organization"`，`player_group: "new_entrant"`），寻源入口为 [find-startups](../skills/find-startups/SKILL.md)。
2. **现有巨头**：经营型已有玩家（`organization_type: "operating_organization"`，`player_group: "incumbent"`），寻源入口为 [find-incumbents](../skills/find-incumbents/SKILL.md)。
3. **金融机构**：投资机构（`organization_type: "investment_firm"`）。在看板中独立展示于“金融机构”顶层分区，不混入创业公司或现有巨头；**没有 `category_id`**（01–10 赛道仅适用于经营型机构），按自身既有字段（`group`、`coverage`、`stage`）组织。寻源入口为 [find-investors](../skills/find-investors/SKILL.md)：先圈定 Tier 1／Tier 2 的 VC、PE 等机构，打 Tier 并收 logo；公司的融资轮次与已披露投资方记录在各公司档案的 `investment.rounds[].investors[]`；前两个 Skill 保留为补充寻源。

新进不是固定年份阈值，也不由上市状态或 VC 融资单独判断；成熟机构品牌变化不自动成为新进机构。

有明确边界的大厂内部新团队、实验室、孵化项目、子公司或正式拆分机构可以是新进候选，其母平台仍是已有玩家。离职团队创业也可研究，但不能仅凭履历认定它是母平台孵化或拆分。成熟平台和现有业务由 [find-incumbents](../skills/find-incumbents/SKILL.md) 研究；真正的新进单元交给 [find-startups](../skills/find-startups/SKILL.md)。实际边界按 [大厂项目 SOP](../skills/find-incumbents/references/corporate-ventures.md) 留存证据，两个 Skill 不复制机构记录。完成寻源后，按规范交接 `map-sectors` / `compose-profile`、`find-person` 与 `find-channels`。

`targeting` 的字段如下：

| 字段 | 含义 |
| --- | --- |
| `kind` | 固定 `editorial_assessment`，说明这是编辑性研究判断 |
| `player_group` | `new_entrant`、`incumbent`，或证据不足的 `unresolved` |
| `wave` | `first` 第一波研究候选、`watchlist` 待核实、`later` 既有玩家资料批次；不是禁止研究或优劣排序 |
| `rationale` | 纳入、观察或留待后续的具体理由，不写个人岗位偏好 |
| `source_ids` | 本条记录内支撑判断的来源 ID |
| `labelled_at` | 实际做分类标记的日期，不表示业务事实重新核查 |

第一波不是机构质量、基金收益、法律独立性或个人适配的评分。`coverage.role` 继续表示 VC 研究范围与证据口径，不能直接替代第一波标记；例如新 GP 没有成熟退出，不因此失去寻源价值。新 VC 的判断流程见 [专门 SOP](../skills/find-startups/references/new-vc-spinouts.md)。

## 机构事实与来源

| 字段 | 含义 |
| --- | --- |
| `id` | 稳定小写 ASCII ID，与 JSON 文件名一致；改品牌时保留 ID |
| `name`／`aliases` | 当前整理名称、别名及历史名称，不单凭旧名称确认运营主体 |
| `category_id`、`focus`、`products` | 经营型机构的主赛道、业务和交付方式 |
| `locations_text` | 公开城市记录，保留总部、团队或招聘地等限定 |
| `regional_notes` | 主公司内的地区研究、历史线索、限定范围及独立来源／日期，不形成地区公司副本 |
| `comparison` | 编辑分析和比较对象，不表示性能排名或完整竞争清单 |
| `investment` | 经营型机构的历史投资披露与核验状态；可选 `rounds[]` 逐轮记录 |
| `organizational_context` | 经营型记录可选的组织形式、母平台关系及核验信息；缺失不表示独立 |
| `founded` | 机构成立口径：`year` 与 `basis`；经营型公司可选，投资机构沿用既有必填口径 |
| `tier` | 投资机构可选 Tier 编辑判断：`tier1` / `tier2` / `unlisted`，含依据、来源与打标日期；不是官方或收益排名 |
| `people` | 所有机构的公开人物身份、职务、背景、原平台、身份来源与日期及 `profiles`；原 VC `team` 已迁入此处 |
| `representative_cases` | 投资机构案例；`prior_firm` 与 `current_firm` 归因分开 |
| `contacts` | 既有公开入口，保留用途与备注，兼容旧消费者 |
| `channels` | 有明确归属、用途、来源和独立核查日期的结构化公开渠道 |
| `notes` | 主体冲突、历史用途、证据缺口和口径限制 |
| `checked_at` | 业务事实实际核查日期；编辑标记、导入和格式迁移不刷新它 |
| `sources` | 来源 ID、URL、标题、支持内容、公开日期、实际核查日期；渠道专用来源可标 `scope: "channel"` |
| `provenance` | 原始图谱名称等导入信息，不等同现行分类或已核事实 |

来源的 `published_date` 可为年、年月或年月日；未知用 `null`，不能用抓取或合并日期代替。业务来源和渠道来源的核查日期分别保留，不自动为未访问的网页刷新日期。

`sources[].scope` 为 `organization`、`channel` 或 `person`；兼容旧来源时，省略表示 `organization`。机构渠道新增证据写 `channel`，人物身份与主页新增证据写 `person`。后两种来源都不能支撑机构分类、投资案例或刷新业务事实日期；每条专用来源必须被相应渠道或人物引用。

融资披露状态：

| 状态 | 含义 |
| --- | --- |
| `confirmed_disclosure` | 当前融资摘要有公开披露支持；不表示完整现股东名册或仍持有 |
| `partial` | 有部分支持，仍有冲突、范围限制或未确认关系 |
| `not_found` | 已开展研究但未找到可靠披露；不是未研究，也不表示零融资 |
| `not_applicable` | 有证据确认的内部团队、实验室或产品项目不适用独立机构股权融资字段；不表示没有内部经费 |

自筹、众筹、创始人支持、产业收购、国资或战略融资等限定逐条保留，不能统一标成 VC-backed。投资机构的完整字段与案例边界见 [VC 方法](../skills/find-startups/references/investment-cases.md)。

## Tier、融资轮次与 Logo

### 投资机构 Tier

`tier` 是可选对象，表达**有来源的编辑判断**，不是官方排名、基金收益排名或个人推荐分数。`group`（`emerging` / `established`）表示组织成熟度，与 Tier 不是同一轴，二者都保留。

| 字段 | 含义 |
| --- | --- |
| `level` | `tier1`：近年多份权威股权投资榜单中稳定靠前，或被交叉引用的综合性主力机构；`tier2`：榜单中经常出现、有清晰策略与可核公开活动，但交叉引用不如第一档稳定（含公开存在的专业或新锐基金）；`unlisted`：已建档但榜单依据不足，不强行打档 |
| `basis` | 判断依据，写明参考的榜单名称、年份或期次、URL，以及该机构被如何提及 |
| `source_ids` | 本记录 `sources[]` 中支撑 Tier 的机构级来源，至少 1 个 |
| `labelled_at` | 实际打 Tier 的日期，不表示业务事实重新核查 |

Tier 1 至少需要两份近年公开榜单交叉支持，或一份榜单加机构官网／权威报道；单份榜单不能单独定 Tier 1。优先实际访问清科中国股权投资年度排名、投中（ChinaVenture）年榜及其他可公开访问的年度机构榜，行业媒体盘点只作辅证；访问失败就保留未打档。禁止把整份受版权保护的榜单正文抄进仓库，只记录本库用到的机构、出现榜单与链接。方法见 [find-investors](../skills/find-investors/SKILL.md)。

### 公司融资轮次与投资方

经营型公司可选 `investment.rounds[]`，公司与投资方的关系只记录在公司侧，不在投资机构档案另建投资组合清单。`rounds[].investors[].firm_id` 对应投资机构稳定 ID，仅在本仓库已有该机构档案时填写；参与不等于领投，IPO 不等于已退出。

`investment.rounds[]` 每条记录 `round`、`announced_on`、`amount_text`、`investors[]`、`source_ids`、`notes`。`amount_text` 只在来源明确披露金额时保留原文（如「3000万美元」），不拆成自行换算的数字字段；`investors[]` 的 `name` 为披露名称，`firm_id` 仅在本仓库已有投资机构档案时填写，`role` 与 `source_ids` 同样按披露记录。没有可靠披露就不建 `rounds`，也不补造轮次、金额或投资方。

经营型公司的 `founded` 为可选 `{ "year": int|null, "basis": string }`，用于记录成立时间口径；不要用融资、品牌启用或登记日期替代成立年份。

### 官方 Logo

`tools/fetch_logos.py` 为创业公司（`operating_organization` + `player_group: "new_entrant"`）和所有有官网的 `investment_firm` 从机构官网或官方页面抓取 logo，写入 `data/views/assets/logos/<id>.<ext>`，并把来源、抓取日期或跳过原因写入 `data/views/assets/logos/manifest.json`。只用官方图像；找不到就跳过并由看板显示文字占位，不生成假 logo，也不使用 Clearbit 等第三方 logo CDN。

自动抓取只按页面标记猜图，可能命中客户案例图、二维码、伙伴 logo 墙或产品截图，所以抓完必须逐张目检；发现抓错时，人工在官网确认真正的图标或页头字标后，用 `python3 tools/import_logo.py --id <id> --url <官方直链>` 覆盖，并按看板的形变规则统一规范化。`manifest.json` 里有 `method: "manual_verified"` 与 `note` 的条目即为人工核对的覆盖记录。

## 大厂关联项目与母平台底表

`organizational_context` 是经营型记录上的可选对象。现有记录没有这个字段时，只表示未完成该项标注，不能推断为独立机构。`form` 与第一波标记分别维护，不按母公司的 `incumbent` 身份自动决定项目归类。

| 字段 | 含义 |
| --- | --- |
| `form` | `independent_organization`、`corporate_spinout`、`corporate_subsidiary`、`internal_team`、`research_lab`、`product_project` 或 `unresolved` |
| `parent_platform_ids` | 关联 `data/lists/incumbents.json` 的有证据的当前或历史母平台 ID；仅曾雇佣创始人不构成母平台关系，具体口径由摘要说明 |
| `relationship_status` | `confirmed`、`reported` 或 `unresolved`；媒体报道不升级为官方确认 |
| `summary` | 说明组织边界、当前／历史关系及证据限制；不补造独立性或持股比例 |
| `source_ids` | 本机构记录内支撑关系判断的业务来源 ID，不能用渠道专用证据替代 |
| `checked_at` | 该项关系实际核查日期，不自动刷新其他旧业务事实 |

内部项目和实验室不以外部 VC 融资为纳入前提。融资未披露、主体不清或关系有争议时说明已核查范围；不能据此把内部预算写成融资，也不能把 `corporate_spinout` 标签当成完全脱离母公司控制的证明。

`investment.verification_status: "not_applicable"` 仅用于 `organizational_context.form` 为 `internal_team`、`research_lab` 或 `product_project`，且 `relationship_status: "confirmed"` 并有来源支持的记录。未确认的内部归属、子公司、独立机构或报道中的拆分机构不能据此跳过融资研究；原记录状态不会因整理或新增字段而批量改变。

`data/lists/incumbents.json` 保存当前中国 AI 场景的编辑性排查范围。`group` 为 `internet_platform`、`cloud_ict_adjacent`、`software_and_ai`、`hardware_and_semiconductors` 或 `industry_incumbents`；这是寻源分组，不是统一市场排名，也不将它们全部称为 hyperscaler。可选 `sectors` 为筛选标签，不替代正式档案的业务分类。

官网身份入口只支持识别候选。可选 `topic_evidence` 逐条保存 `topic`、`role`、`title`、`url`、`supports`、`published_date`、`checked_at`，说明在某个主题中的具体角色及来源；发布日期未知用 `null`，核查日期按实际访问记录。存在一项主题证据不表示已确认行业领先、母子公司关系或全部业务。没有该数组表示尚未记录主题证据，不表示确定没有相关业务。

`python3 tools/query_lists.py --list incumbents` 可用 `--sector`、`--topic`、`--group`、`--id` 筛选底表。平台进入底表不会自动进入 `data/index.json`；确定需研究的机构或具体单元后，按正式记录核验、建档和圈选。生成的 [平台清单](views/incumbents.md) 与 [大厂关联项目](views/corporate-ventures.md) 分别承担这些用途。

`python3 tools/query_lists.py --list vcs` 将 VC 名单与完整档案关联后输出；名单增删不会自动新增或删除完整公司档案，VC 名单可以为空。`views/exports/companies.csv`／`sources.csv` 为经营型资料筛选表，`investors.csv`／`investor-sources.csv` 为投资机构筛选表；它们都是统一档案的自动生成视图。

## 通用 Skill 与当前公共契约

`find-startups` 和 `find-incumbents` 的主题、地域和行业由具体任务确定；本仓库现有公共分类与 schema 则继续服务当前中国 AI 资料。通用方法不等于当前数据契约已经扩展到所有行业。超出既有分类的结果先存私人工作区 `research/`，或在明确扩展 taxonomy、schema 和生成规则后发布，不能借用一个不相符的 AI 类目来通过校验。研究流程和第三方参考见 [研究方法](../skills/find-incumbents/references/research-methods.md)。

## 三类公开渠道与六槽位模板

公开渠道作为 Agent 后续核实填充的**动态模板**，涵盖标准 6 槽位：官方网站（`official`）、官招/投递链接（`official`）、招聘邮箱（`official` / `contacts`）、BOSS直聘企业主页（`recruitment_platform`）、猎聘企业主页（`recruitment_platform`）与 LinkedIn 企业主页（`professional_social`）。绝不猜测 URL 或邮箱。

三类是入口类别，不表示渠道之间有高低优先级，也不预设个人职能方向。

| `layer` | 典型信息 |
| --- | --- |
| `official` | 官网、官方招聘或业务页面等，经核实的机构正式入口 |
| `recruitment_platform` | 机构在 BOSS 直聘、猎聘、脉脉上的公开企业主页 |
| `professional_social` | 机构 LinkedIn 公司主页、官方社媒账号（个人主页属于 `people[].profiles`） |

每条 `channels` 记录包含：

| 字段 | 含义 |
| --- | --- |
| `id` | 本机构内稳定渠道 ID |
| `layer`／`platform` | 渠道类别及具体平台 |
| `url`／`purpose` | 公开入口及用途；招聘、BP、商务等目的分开 |
| `owner.scope`、`owner.name`、`owner.role` | `scope` 固定 `organization`；人物主页使用 `people[].profiles` |
| `verification_status` | `confirmed`、`partial` 或 `historical`；不是招聘开放状态 |
| `checked_at` | 实际核对该页面和归属的日期 |
| `source_ids` | 本机构内对应证据来源 ID |
| `notes` | 适用范围、历史性或其他公开事实限定 |

`contacts.careers_url` 可能是官方页、招聘平台或历史帖子，不能一律计为 Layer 1。`sources` 中引用了 GitHub、X 或领英网址，也不能由域名推断它就是该机构或负责人的渠道。结构化覆盖率按已核实的 `channels` 计算，既有未结构化信息另作提示。

`owner.name` 为网页实际观察到的主体名称，不能统一替换为档案标签。`confirmed` 必须匹配目标名称或有来源确认的同一主体别名；母集团、其他城市法人、关联销售公司的入口保留为 `partial`，用 `owner.role` 和 `notes` 说明范围与待核实关系。`partial` 不计入已确认渠道覆盖率，阅读版同时展示这些说明。地区业务集合不自动成为独立公司；注册地址、历史基地、当前办公地与具体岗位地点分别判断，地域不确定时直接在 `locations_text` 标明待核实和依据。

已有玩家底表的可选 `company_id` 只路由到同层级完整机构档案，稳定底表 ID 不必与档案 ID 相同（例如 `trip-com` → `ctrip`）。未绑定时省略，不用上海／苏州团队替代集团档案；完整研究仍只维护在 `data/companies/`。

渠道复核替换当前主体／证据时，原观察的来源、支持内容和日期保留在 `sources`，通过该渠道的 `historical_source_ids` 引用。历史依据不参与当前归属和核查日期判断；当前依据仍放 `source_ids`。写入工具新增观察，不覆盖旧观察来伪装成一次重新核查。

## 人物资料与公开主页

核心人物是机构机会研究的最关键信息。当前公共数据中，原 VC 团队已迁入 `people[]`，而经营型创业公司（`operating_organization` + `new_entrant`）的 `people[]` 目前大多为空；**创业公司的核心人物（创始人/高管/首席科学家/业务负责人）是最高优先级补齐对象**。

人物统一放 `people[]`，契约见 [person.schema.json](schemas/person.schema.json)。`name`、`role`、`background`、`previous_firms` 是身份事实；`source_ids`、`checked_at`、`verification_status`、`notes` 记录其核验依据和限制。`profiles[]` 独立记录平台、URL、核验状态、来源与日期；替换身份依据时，旧依据用 `historical_source_ids` 保留，不参与当前核查日期判断；不在 `channels[]` 或 VC 的 `team[]` 复制人物。

原有 42 条 VC 团队人物已迁入 `people[]`：姓名、职务、履历和原平台完整保留，使用原机构核查日期与既有来源包，标 `partial` 并注明尚未逐人重新核查、来源范围待细化。没有新增或猜测个人主页，也不把迁移日期当作新核查日期。公司 JSON schema 升至 v3；索引的 `team_names` 仅作为兼容摘要字段，由 `people[]` 生成，不是第二份人物维护源。

`confirmed` 身份与主页需有至少两处不同 URL 的真实交叉依据，包括个人主页与支持身份／现职的公开资料。URL 数量和校验通过不等于已核实内容；采集者须实际读页确认。同名、改任或历史履历应保留限定。GitHub 个人主页另需 `account_type: "User"` 及对应 `api.github.com/users/<handle>` 的真实公开观察，机构账号留在 `channels[]`。

人物工具输入契约见 [person-batch.schema.json](schemas/person-batch.schema.json)。`update_people.py` 支持标准输入及默认预览；`--apply` 将全部输入校验后写入公司档案，拒绝旧日期覆盖较新身份、主页或来源，失败时条件回滚并保留其他写入者的新改动。相关方法见 [find-person](../skills/find-person/SKILL.md)。

## 从候选到正式记录

新机构草稿先输出到标准输出，或显式保存到私人 `drafts/research/`；缺失事实和日期保留 `null`，不创建虚假的来源。核实后才写入正式 `data/`，发布检查拒绝占位内容和示例网址。

Layer 2 按 [渠道方法](../skills/find-channels/SKILL.md) 核对公开企业主页，采集 Agent 将已核实结果直接更新到 `data/companies/<id>.json` 的 `channels` 与 `sources`。可直接编辑后校验，也可将观察结果经标准输入交给 `update_layer2.py --apply`；不要求先落盘批次、私人工作区或 inbox，也不要求另一个 Agent 批准。未找到、访问受限或主体存疑在本次研究报告说明，不补造已确认记录。`applications/inbox/` 只处理个人投递、聊天和进展；原始聊天、私人联系方式、个人期望薪酬及投递状态不得进入公共资料。

每次正式变更先校验，再生成阅读版，最后检查同步与差异：

```bash
.venv/bin/python tools/validate.py
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
```

结构与日期校验不能代替实际网页核验，也不能证明岗位仍开放、邮箱仍有效或披露完整。
