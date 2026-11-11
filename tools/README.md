# 资料库工具与 Git 同步

本目录集中维护共用查询、草稿、构建、校验和发布程序；测试在 `tools/tests/`。各 Skill 专用脚本随 Skill 保存，私人工作区初始化与解析由 [setup-workspace](../skills/setup-workspace/SKILL.md) 负责。

所有命令从仓库根目录执行。

## 查询与草稿

```bash
python3 tools/query.py --entity organizations --wave first
python3 tools/query.py --player-group incumbent
python3 tools/query.py --entity investors --id monolith --json
python3 tools/query_lists.py --list incumbents --sector hardware
python3 tools/query_lists.py --list vcs
python3 tools/query_lists.py --list incumbents --topic AI
python3 tools/audit_entities.py --summary
python3 skills/find-person/scripts/audit_people.py --wave all --summary
python3 tools/scaffold_entity.py --entity company --id candidate-org --name "待核实机构" --category 04
```

`query.py` 读取 `data/companies/` 中的全部正式档案；`--entity companies` 包含金融公司，`--entity operating`／`investors` 仅按类型筛选，不对应独立目录。`query_lists.py` 读取发现底表；主题证据缺失不表示没有相关业务。脚手架默认只输出未核实草稿，显式 `--save-draft` 才写到已配置私人工作区，不直接创建公共记录。字段和适用范围见 [data/README.md](../data/README.md)。

合并的地区旧 ID 见 `data/lists/company-redirects.json`，`query.py --id` 可解析旧 ID；写入时须使用主公司 ID，旧 ID 会明确报错。生成的旧地区 Markdown 只作链接跳转，不计入公司数。

按照方法论（**找公司 → 公司档案 → 找核心人物 → 找渠道**），核心人物最优先且只维护在公司档案的 `people[]`（使用 [find-person](../skills/find-person/SKILL.md)）；机构公开渠道模板维护在 `channels[]`（使用 [find-channels](../skills/find-channels/SKILL.md)）。人物写入工具为 `skills/find-person/scripts/update_people.py`，输入契约见 [人物批次](../data/schemas/person-batch.schema.json)。两个写入工具共用 `record_writes.py` 的并发检查、临时文件清理与条件回滚，人物平台校验在 `person_checks.py`。

分别检查 BOSS／猎聘的覆盖情况，不把任一平台已有渠道当作两边均已完成：

```bash
python3 skills/find-channels/scripts/audit_channels.py --entity companies --wave later --summary
```

输出包含逐平台 `confirmed`／`partial`／`historical`／`missing` 档案数及 `both_boss_and_liepin_confirmed`。未收录不等于没有招聘；平台主页确认也不表示岗位开放。

## 构建与检查

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r tools/requirements-dev.txt
.venv/bin/python tools/validate.py
python3 tools/build.py
.venv/bin/python tools/validate.py --check-generated
.venv/bin/python -m unittest discover -s tools/tests -v
.venv/bin/python tools/check_public.py
```

`build.py` 从正式 JSON 生成唯一的 `data/index.json` 和 `data/views/`，不修改业务事实。`validate.py` 检查格式、引用、日期及本地链接，`--check-generated` 同时检查生成内容。检查不代替实际网页核验。

机构 Logo 是从官网抓取的派生视图资产，不写入机构研究 JSON：

```bash
python3 tools/fetch_logos.py --id unitree
python3 tools/fetch_logos.py --id hongshan
python3 tools/fetch_logos.py --workers 8
```

工具默认读取**创业公司**（`operating_organization` 且 `player_group == "new_entrant"`）和**所有有官网的 `investment_firm`**；传入 `--id` 时投资机构不再被跳过。它从 `contacts.website` 或官方 `channels` 找 apple-touch-icon、favicon、og:image 或明确 logo；幂等跳过已有文件，限制超时与文件大小，并把来源、抓取日期或跳过原因写入 `data/views/assets/logos/manifest.json`。不接入 Clearbit 等第三方 logo CDN；缺失时看板使用文字占位，不阻断构建。

## 提交与推送

本仓库有自己的 `.git/`。保存是本地修改，提交记录修改，推送才上传到配置的 GitHub 远端。先审阅实际差异、来源、日期与共享范围：

```bash
git status --short
git diff
git remote -v
.venv/bin/python tools/publish.py --message "更新公共资料"
```

发布工具生成阅读版、校验、运行测试并检查共享边界，仅暂存共享文件后提交和普通推送；失败即停止，不强制推送或自动解决远端冲突。只检查可运行 `.venv/bin/python tools/publish.py --check-only`。Fork 使用者应使用自己的远端；克隆原仓库不自动获得写入权限。

## 共享边界

| 内容 | 保存位置 | 上传 GitHub |
| --- | --- | --- |
| 方法、专用资源和空白模板 | `skills/` | 是 |
| 公开事实、字段约束、统一索引及阅读版 | `data/` | 是 |
| 共用工具、依赖与测试 | `tools/`、`.github/` | 是 |
| 个人事实、简历、草稿、聊天与投递 | 本地 `workspace/` 或绑定的外部工作区 | 否 |
| 个人投递／沟通与原始依据 | 私人 `applications/<公司>/log.md`、`records/`；路由见 `applications/index.md` | 否 |
| 尚未核实的新机构草稿 | 私人 `drafts/research/` | 否 |
| 私人工作区路径 | `workspace.local.json` | 否 |

公开 Layer 2 采集直接更新所属公司的 `data/companies/<id>.json`，可用渠道 Skill 的 `update_layer2.py --apply` 从标准输入写入，无需私人工作区或 inbox；私人对话及联系进展继续留私人工作区。共享目录只保留 `skills/`、`data/`、`tools/`、`.github/` 及根入口文件；历史旧目录仅在历史审计中兼容，具体名单以 `check_public.py` 为准。

内部 `workspace/` 和路径配置被 Git 忽略；外部工作区在 Git 根目录之外。旧个人目录的忽略规则继续保留，不用强制添加绕过。检查可拦住私人目录、常见凭据和电脑路径，但不能识别所有姓名和聊天，仍需审阅内容。忽略不清除历史；发现历史私人内容时停止推送，评估后再清理，不擅自改写历史。

不要在私人父目录初始化或整体推送 Git。子仓库缺失而误用父仓库时，根目录检查应停止。被忽略的个人资料需使用本人可访问的私有持久存储备份。
