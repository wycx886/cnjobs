"""Render a self-contained interactive dashboard from canonical public JSON."""
import json
import re
from collections import Counter
from pathlib import Path

from organizations import select
from targets import build_index

ROOT = Path(__file__).resolve().parents[1]
LOGO_DIR = Path("data/views/assets/logos")
LOGO_EXTENSIONS = {".apng", ".avif", ".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp"}

CITY_NAMES = (
    "上海", "苏州", "北京", "深圳", "杭州", "广州", "南京", "武汉", "成都",
    "合肥", "无锡", "昆山", "常州", "宁波", "西安", "天津", "重庆", "长沙",
    "厦门", "珠海", "东莞", "佛山", "青岛", "济南", "郑州", "香港", "澳门",
    "新加坡", "东京", "旧金山", "硅谷", "波士顿", "巴黎", "阿布扎比", "宜宾",
    "如皋", "南通", "吉隆坡", "Menlo Park", "San Jose",
)

CLASSES = (
    {"id": "startups", "label": "创业公司", "description": "新进经营型机构", "method": "find-startups", "default": True},
    {"id": "incumbents", "label": "现有巨头", "description": "成熟经营型平台与业务单元", "method": "find-incumbents", "default": False},
    {"id": "investors", "label": "金融机构", "description": "投资机构与基金管理团队", "method": "find-investors（拟定）", "default": False},
    {"id": "unresolved", "label": "未归类", "description": "身份待确认，独立于三类之外", "method": "待核实", "default": False},
)

LABELS = {
    "types": {"operating_organization": "经营型机构", "investment_firm": "投资机构"},
    "waves": {"first": "第一波候选", "watchlist": "观察候选", "later": "已有玩家／后续"},
    "wave_short": {"first": "第一波", "watchlist": "观察", "later": "后续"},
    "player_group": {"new_entrant": "新进候选", "incumbent": "已有玩家", "unresolved": "身份待确认"},
    "groups": {
        "emerging": "2020–2023 新一代机构", "established": "成熟机构",
        "recent": "2024–2026 新设机构", "new_generation": "2020–2023 新一代机构",
        "founding_unconfirmed": "成立时间待确认",
    },
    "cohorts": {
        "recent": "2024–2026 新设", "new_generation": "2020–2023 新一代",
        "established": "成熟机构", "founding_unconfirmed": "成立待确认",
    },
    "coverage_roles": {"main": "主要样本", "watchlist": "观察补充", "adjacent": "相关机构"},
    "funding": {
        "confirmed_disclosure": "已核验披露（非完整现股东表）", "partial": "部分核验",
        "not_found": "未找到可靠公开披露", "not_applicable": "内部单元，不适用独立主体股权融资",
    },
    "layers": {"official": "官方入口", "recruitment_platform": "招聘平台", "professional_social": "专业社交"},
    "platforms": {
        "boss_zhipin": "BOSS直聘", "liepin": "猎聘", "website": "官网", "careers": "官方招聘",
        "linkedin": "LinkedIn", "x": "X", "github": "GitHub", "jike": "即刻", "maimai": "脉脉",
        "scholar": "Google Scholar", "zhihu": "知乎", "personal_site": "个人主页", "other": "其他",
    },
    "purposes": {"recruitment": "招聘", "general": "官网／通用", "business": "商务", "bp": "BP", "media": "媒体", "technical": "技术", "public_profile": "公开主页"},
    "verification": {"confirmed": "已核验", "partial": "部分核验", "historical": "历史入口"},
    "profile_platforms": {
        "linkedin": "LinkedIn", "x": "X", "github": "GitHub", "scholar": "Google Scholar",
        "jike": "即刻", "zhihu": "知乎", "personal_site": "个人主页", "other": "其他主页",
    },
    "source_scope": {"organization": "机构", "channel": "渠道", "person": "人物"},
    "forms": {
        "independent_organization": "独立机构", "corporate_spinout": "拆分／衍生",
        "corporate_subsidiary": "子公司", "internal_team": "内部团队",
        "research_lab": "研究实验室", "product_project": "产品项目", "unresolved": "待确认",
    },
    "relationships": {"confirmed": "已确认", "reported": "媒体报道", "unresolved": "待核实"},
}


def _city_text(record):
    notes = " ".join(note.get("region", "") for note in record.get("regional_notes", []))
    return (record.get("locations_text") or "") + " " + notes


def _cities(records):
    counts = Counter()
    for record in records:
        text = _city_text(record)
        for city in CITY_NAMES:
            if city in text:
                counts[city] += 1
    return [{"name": city, "count": count}
            for city, count in sorted(counts.items(), key=lambda item: (-item[1], CITY_NAMES.index(item[0])))]


def _coverage(records):
    return {
        "channels": sum(1 for record in records if record.get("channels")),
        "people": sum(1 for record in records if record.get("people")),
        "regional_notes": sum(1 for record in records if record.get("regional_notes")),
        "sources": sum(len(record.get("sources", [])) for record in records),
    }


def _class_of(record):
    if record.get("organization_type") == "investment_firm":
        return "investors"
    group = (record.get("targeting") or {}).get("player_group")
    if group == "new_entrant":
        return "startups"
    if group == "incumbent":
        return "incumbents"
    return "unresolved"


def _logos(root):
    directory = Path(root) / LOGO_DIR
    mapping = {}
    if not directory.exists():
        return mapping
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in LOGO_EXTENSIONS:
            mapping[path.stem] = (Path("assets/logos") / path.name).as_posix()
    return mapping


def build_dataset(root=ROOT):
    root = Path(root)
    selected = select(root)
    records = [record for _, record in selected]
    by_id = {record["id"]: record for record in records}
    index = build_index(root, selected)
    taxonomy = json.loads((root / "data/taxonomy.json").read_text(encoding="utf-8"))
    logos = _logos(root)
    organizations = []
    class_counts = Counter()
    for entry in index["organizations"]:
        record = by_id[entry["id"]]
        org_class = _class_of(record)
        class_counts[org_class] += 1
        organizations.append({
            "index": entry,
            "record": record,
            "class": org_class,
            "logo": logos.get(record["id"]),
        })
    return {
        "meta": {
            "name": "中国 AI 机会索引",
            "generated_from": ["data/index.json", "data/companies/*.json", "data/taxonomy.json", LOGO_DIR.as_posix()],
            "latest_checked_at": index["latest_checked_at"],
            "index_schema_version": index["schema_version"],
            "default_class": "startups",
            "logo_manifest": (LOGO_DIR / "manifest.json").as_posix(),
            "schemas": {
                "index": "data/schemas/index.schema.json",
                "company": "data/schemas/company.schema.json",
                "investor": "data/schemas/investor.schema.json",
                "person": "data/schemas/person.schema.json",
                "channel": "data/schemas/channel.schema.json",
                "targeting": "data/schemas/targeting.schema.json",
            },
            "note": "看板只展示规范 JSON 中的字段。第一层按机构类别分区，第二层按既有 category_id 与 taxonomy.json 分组；城市筛选项由 locations_text 与 regional_notes[].region 文本匹配得出，仅用于定位，不新增地点事实。",
        },
        "labels": LABELS,
        "classes": [dict(item, count=class_counts[item["id"]]) for item in CLASSES],
        "counts": index["counts"],
        "statistics": index["statistics"],
        "coverage": _coverage(records),
        "taxonomy": taxonomy,
        "cities": _cities(records),
        "city_names": list(CITY_NAMES),
        "logos": logos,
        "organizations": organizations,
    }


def _script_json(value):
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def render(root=ROOT):
    root = Path(root)
    data = build_dataset(root)
    counts = data["counts"]
    coverage = data["coverage"]
    class_counts = {item["id"]: item["count"] for item in data["classes"]}
    replacements = {
        "__TOTAL__": counts["organizations"],
        "__OPERATING__": counts["operating_organizations"],
        "__INVESTORS__": counts["investment_firms"],
        "__STARTUPS__": class_counts["startups"],
        "__INCUMBENTS__": class_counts["incumbents"],
        "__FINANCIALS__": class_counts["investors"],
        "__UNRESOLVED__": class_counts["unresolved"],
        "__FIRST__": counts["first"],
        "__WATCHLIST__": counts["watchlist"],
        "__LATER__": counts["later"],
        "__CHANNELS__": coverage["channels"],
        "__PEOPLE__": coverage["people"],
        "__SOURCES__": coverage["sources"],
        "__LATEST__": data["meta"]["latest_checked_at"],
    }
    page = TEMPLATE
    for token, value in replacements.items():
        page = page.replace(token, str(value))
    missing = re.search(r"__[A-Z_]+__", page.replace("__DATASET__", ""))
    if missing:
        raise ValueError("Unresolved dashboard token: " + missing.group(0))
    page = page.replace("__DATASET__", _script_json(data))
    return {"data/views/dashboard.html": page}


TEMPLATE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>中国 AI 机会索引 · cn_ai_opp</title>
<meta name="description" content="中国 AI 机构寻源看板：先分创业公司、现有巨头与金融机构，再按赛道展开公司档案、核心人物与公开渠道。">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Dataset","name":"中国 AI 机会索引","description":"中国 AI 创业公司、大厂创新单元与投资机构的公开研究索引。","keywords":["中国 AI","创业公司","现有巨头","投资机构","风险投资"],"isAccessibleForFree":true}
</script>
<style>
:root{
  --ink:#16211d;
  --ink-2:#36453e;
  --muted:#64716a;
  --paper:#edf0e9;
  --surface:#f8f9f4;
  --surface-2:#f2f4ed;
  --line:#d1d8cf;
  --line-soft:rgba(209,216,207,.62);
  --canal:#28596a;
  --canal-dark:#1c434f;
  --celadon:#7d9c8b;
  --celadon-ink:#4b6857;
  --seal:#a4432c;
  --seal-dark:#7f2d1c;
  --amber:#8a6118;
  --radius:3px;
  --serif:"Songti SC","STSong","Noto Serif SC","Source Han Serif SC",serif;
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;
  --mono:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.65;-webkit-font-smoothing:antialiased}
a{color:var(--canal);text-decoration-thickness:1px;text-underline-offset:2px}
a:hover{color:var(--canal-dark)}
button{font:inherit;color:inherit}
.shell{max-width:1500px;margin:0 auto;padding:0 28px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.skip{position:absolute;left:16px;top:-48px;z-index:100;background:var(--ink);color:#fff;padding:8px 12px;border-radius:var(--radius);text-decoration:none}
.skip:focus{top:16px}
:focus-visible{outline:2px solid var(--canal);outline-offset:2px}
.masthead{padding:32px 0 0;border-bottom:1px solid var(--line)}
.mast-grid{display:flex;align-items:flex-start;justify-content:space-between;gap:36px}
.brand{display:flex;align-items:flex-start;gap:20px;min-width:0}
.seal{flex:0 0 58px;width:58px;height:58px;background:var(--seal);color:#fdfbf5;display:grid;place-items:center;font-family:var(--serif);font-size:31px;line-height:1;border:1px solid var(--seal-dark);box-shadow:inset 0 0 0 3px var(--seal),inset 0 0 0 4px rgba(253,251,245,.66)}
h1{font-family:var(--serif);font-weight:600;font-size:clamp(2.1rem,4.4vw,3.7rem);line-height:1.04;letter-spacing:.01em;margin:0 0 10px}
.dek{max-width:44em;margin:0;color:var(--ink-2);font-size:15px}
.mast-meta{flex:0 0 auto;text-align:right;font-size:12px;color:var(--muted);padding-top:8px}
.mast-meta p{margin:0 0 6px}
.mast-meta .meta-label{color:var(--ink-2)}
.mast-meta a{margin-left:14px}
.classbar{display:grid;grid-template-columns:repeat(3,minmax(0,1fr)) minmax(120px,.62fr);align-items:end;gap:0;margin-top:26px;border-top:1px solid var(--line)}
.class-tab{position:relative;appearance:none;background:none;border:0;border-bottom:3px solid transparent;padding:16px 20px 14px 0;text-align:left;cursor:pointer;min-width:0}
.class-tab+.class-tab{padding-left:22px;border-left:1px solid var(--line-soft)}
.class-tab strong{display:block;font-family:var(--serif);font-size:clamp(1.45rem,2.5vw,2rem);font-weight:600;line-height:1.15}
.class-tab .ct-count{font-family:var(--serif);font-size:15px;color:var(--muted);margin-left:8px;font-variant-numeric:tabular-nums}
.class-tab span{display:block;font-size:11px;color:var(--muted);margin-top:3px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.class-tab:hover strong{color:var(--canal)}
.class-tab[aria-pressed="true"]{border-bottom-color:var(--seal)}
.class-tab[aria-pressed="true"] strong,.class-tab[aria-pressed="true"] .ct-count{color:var(--seal)}
.class-tab.ghost strong{font-size:clamp(1.05rem,1.8vw,1.4rem)}
.class-tab.ghost[aria-pressed="true"] strong{color:var(--amber)}
.class-tab.ghost[aria-pressed="true"]{border-bottom-color:var(--amber)}
.class-note{display:flex;justify-content:space-between;gap:18px;align-items:baseline;padding:10px 0 12px;font-size:11px;color:var(--muted)}
.class-note p{margin:0}
.class-note b{color:var(--ink-2);font-weight:600}
.coverage{display:flex;align-items:stretch;border-top:1px solid var(--line)}
.cov{appearance:none;background:none;border:0;padding:13px 18px 12px 0;min-width:120px;text-align:left;cursor:pointer;display:flex;flex-direction:column;gap:1px}
.cov strong{font-family:var(--serif);font-size:28px;font-weight:600;line-height:1;font-variant-numeric:tabular-nums}
.cov span{font-size:12px;color:var(--muted)}
.cov:hover strong{color:var(--canal)}
.cov[aria-pressed="true"] strong{color:var(--seal)}
.cov-line{position:relative;flex:0 0 48px;align-self:center;height:1px;background:var(--line)}
.cov-line::after{content:"";position:absolute;right:-2px;top:-2px;width:5px;height:5px;border-radius:50%;background:var(--celadon)}
.cov.stat{cursor:default;margin-left:auto;text-align:right;align-items:flex-end;padding-right:0}
.overview{display:grid;grid-template-columns:minmax(260px,.72fr) minmax(0,1.28fr);gap:0;border-bottom:1px solid var(--line);padding:20px 0 22px}
.ov-brief{padding-right:34px;min-width:0}
.ov-brief h2{font-family:var(--serif);font-size:32px;font-weight:600;line-height:1.1;margin:0 0 6px}
.ov-brief .ov-sub{font-size:13px;color:var(--ink-2);margin:0 0 14px}
.ov-brief .ov-method{font-size:11px;color:var(--muted);margin:0 0 14px}
.ov-stats{display:flex;flex-wrap:wrap;gap:0 24px;border-top:1px solid var(--line);padding-top:12px}
.ov-stat{min-width:74px}
.ov-stat b{display:block;font-family:var(--serif);font-size:24px;font-weight:600;line-height:1;font-variant-numeric:tabular-nums}
.ov-stat span{font-size:11px;color:var(--muted)}
.ov-sector{padding-left:34px;border-left:1px solid var(--line);min-width:0}
.ov-head{display:flex;align-items:baseline;justify-content:space-between;gap:16px}
.ov-head h2{font-family:var(--sans);font-size:13px;font-weight:600;color:var(--ink-2);margin:0 0 12px}
.ov-head p{font-size:11px;color:var(--muted);margin:0 0 12px}
.cat-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:1px 26px}
.cat{display:grid;grid-template-columns:minmax(0,1fr) 54px 28px;align-items:center;gap:10px;border:0;border-bottom:1px solid var(--line-soft);background:none;padding:5px 0;text-align:left;cursor:pointer}
.cat-name{font-size:13px;color:var(--ink-2);overflow:hidden;white-space:nowrap;text-overflow:ellipsis}
.cat-bar{display:block;height:3px;background:#e0e5de;overflow:hidden}
.cat-bar i{display:block;height:100%;background:var(--celadon);width:var(--w)}
.cat b{font-family:var(--serif);font-size:17px;font-weight:600;text-align:right;font-variant-numeric:tabular-nums}
.cat:hover .cat-name{color:var(--canal)}
.cat[aria-pressed="true"] .cat-name{color:var(--seal)}
.cat[aria-pressed="true"] .cat-bar i{background:var(--seal)}
.toolbar-wrap{position:sticky;top:0;z-index:20;background:rgba(237,240,233,.96);backdrop-filter:blur(8px);border-bottom:1px solid var(--line)}
.toolbar{display:grid;grid-template-columns:minmax(250px,390px) minmax(0,1fr);align-items:center;gap:7px 18px;padding:10px 0}
.searchbox{position:relative;width:100%;min-width:0}
.searchbox input{width:100%;border:1px solid var(--line);background:var(--surface);color:var(--ink);padding:9px 38px 9px 12px;border-radius:var(--radius);font:inherit;font-size:14px}
.searchbox input:focus{outline:2px solid var(--canal);outline-offset:1px;border-color:transparent}
.slash{position:absolute;right:10px;top:50%;transform:translateY(-50%);font-family:var(--mono);font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:3px;padding:0 4px;background:var(--paper)}
.filters{display:flex;flex-wrap:wrap;align-items:center;gap:8px;min-width:0}
.filters.primary{justify-content:flex-end}
.filters.secondary{grid-column:1/-1}
.field{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
.field select{font:inherit;font-size:13px;color:var(--ink);background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:6px 8px;max-width:200px}
.toggle{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--ink-2);white-space:nowrap;cursor:pointer}
.toggle input{accent-color:var(--canal);margin:0}
.reset{border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);padding:6px 9px;font-size:12px;color:var(--muted);cursor:pointer}
.reset:hover{border-color:var(--canal);color:var(--canal)}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) minmax(400px,500px);align-items:start;padding-top:22px}
.list-pane{min-width:0;padding-right:30px;border-right:1px solid var(--line)}
.detail-pane{position:sticky;top:112px;max-height:calc(100vh - 128px);overflow:auto;padding-left:30px;scrollbar-gutter:stable}
.list-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.list-head h2{font-family:var(--serif);font-size:26px;font-weight:600;margin:0}
#result-count{font-size:12px;color:var(--muted);margin:4px 0 0;font-variant-numeric:tabular-nums}
.sort-note{font-size:11px;color:var(--muted);margin:0 0 4px;text-align:right}
.org-list{display:flex;flex-direction:column}
.sector-section{margin-top:20px}
.sector-head{position:relative;display:grid;grid-template-columns:52px minmax(0,1fr) auto;align-items:baseline;gap:10px;padding:0 0 8px;border-bottom:2px solid var(--ink)}
.sector-no{font-family:var(--serif);font-size:30px;font-weight:600;line-height:1;color:var(--celadon-ink);font-variant-numeric:tabular-nums}
.sector-title{min-width:0}
.sector-title h3{font-family:var(--serif);font-size:20px;font-weight:600;line-height:1.2;margin:0}
.sector-title h3 .linklike{font:inherit;color:inherit;text-decoration:none}
.sector-title h3 .linklike:hover{color:var(--canal);text-decoration:underline;text-underline-offset:3px}
.sector-title p{font-size:11px;color:var(--muted);margin:2px 0 0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.sector-count{font-size:11px;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.sector-head[data-sector] .sector-title h3{cursor:pointer}
.sector-head[data-sector] .sector-title h3:hover{color:var(--canal)}
.org-row{position:relative;display:grid;grid-template-columns:46px minmax(0,1fr);gap:14px;width:100%;border:0;border-bottom:1px solid var(--line);background:none;padding:15px 12px 15px 0;text-align:left;cursor:pointer}
.org-row:hover{background:rgba(125,156,139,.09)}
.org-row[aria-current="true"]{background:rgba(40,89,106,.07)}
.org-row[aria-current="true"]::before{content:"";position:absolute;left:-1px;top:0;bottom:0;width:3px;background:var(--canal)}
.logo-frame{width:46px;height:46px;border:1px solid var(--line);background:var(--surface);display:grid;place-items:center;overflow:hidden;align-self:start;flex:0 0 auto}
.logo-frame img{width:100%;height:100%;object-fit:contain;padding:5px;display:block;background:#fff}
.logo-frame .monogram{font-family:var(--serif);font-size:19px;font-weight:600;color:var(--celadon-ink);line-height:1}
.logo-frame.lg{width:64px;height:64px}
.logo-frame.lg .monogram{font-size:27px}
.row-main{min-width:0}
.row-top{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap}
.org-name{font-family:var(--serif);font-size:19px;font-weight:600;line-height:1.25}
.org-type{font-size:10px;color:var(--muted);border:1px solid var(--line);border-radius:2px;padding:1px 5px;white-space:nowrap}
.wave-tag{font-size:10px;color:var(--celadon-ink);border:1px solid currentColor;border-radius:2px;padding:0 4px;white-space:nowrap}
.wave-tag.first{color:var(--seal)}
.wave-tag.watchlist{color:var(--amber)}
.row-meta{display:block;font-size:12px;color:var(--muted);margin-top:2px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row-why{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:13px;color:var(--ink-2);line-height:1.55;margin-top:6px}
.row-foot{display:flex;flex-wrap:wrap;gap:12px;margin-top:7px;font-size:11px;color:var(--muted);font-variant-numeric:tabular-nums}
.empty{padding:48px 0;border-bottom:1px solid var(--line)}
.empty h3{font-family:var(--serif);font-size:24px;font-weight:600;margin:0 0 8px}
.empty p{max-width:36em;color:var(--ink-2);margin:0 0 14px}
.detail-body{font-size:14px;outline:none}
.detail-empty{padding:28px 0 60px;border-top:3px solid var(--ink)}
.empty-mark{width:44px;height:44px;border:1px solid var(--line);display:grid;place-items:center;font-family:var(--serif);font-size:20px;color:var(--celadon);margin:0 0 16px}
.detail-empty h2{font-family:var(--serif);font-size:28px;font-weight:600;line-height:1.2;margin:0 0 10px}
.detail-empty p{max-width:34em;color:var(--ink-2);margin:0 0 18px}
.legend{margin:0 0 18px;padding:0;border-top:1px solid var(--line)}
.legend div{display:flex;align-items:baseline;gap:14px;padding:7px 0;border-bottom:1px solid var(--line-soft)}
.legend dt{display:flex;align-items:center;gap:6px;font-size:12px;white-space:nowrap}
.legend dd{margin:0;font-size:12px;color:var(--muted)}
.dot{width:7px;height:7px;border-radius:50%;display:inline-block}
.dot.first{background:var(--seal)}
.dot.watchlist{background:var(--amber)}
.dot.later{background:var(--celadon)}
.empty-hint{font-size:12px;color:var(--muted)}
.detail-head{position:relative;padding:0 0 18px;border-bottom:1px solid var(--line)}
.detail-close{position:absolute;right:0;top:0;border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);padding:3px 8px;font-size:11px;color:var(--muted);cursor:pointer;z-index:2}
.detail-close:hover{border-color:var(--canal);color:var(--canal)}
.dossier-top{display:flex;align-items:flex-start;gap:15px;padding-right:52px}
.dossier-id{min-width:0;flex:1}
.detail-head h2{font-family:var(--serif);font-size:29px;font-weight:600;line-height:1.15;margin:0 0 4px}
.detail-alias{font-size:11px;color:var(--muted);margin:0 0 9px;overflow-wrap:anywhere}
.detail-meta{display:flex;align-items:center;flex-wrap:wrap;gap:7px;font-size:11px;color:var(--muted)}
.detail-meta .wave-tag{font-size:10px}
.dossier-intro{font-size:14px;color:var(--ink-2);margin:13px 0 0;max-width:44em}
.dossier-locations{font-size:11px;color:var(--muted);margin:6px 0 0}
.d-section{padding:18px 0;border-bottom:1px solid var(--line)}
.d-section h3{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;margin:0 0 10px}
.d-section h3::before{content:"";width:3px;height:14px;background:var(--celadon);display:inline-block}
.section-tag{margin-left:auto;font-family:var(--mono);font-size:9px;font-weight:400;color:var(--muted);border:1px solid var(--line);border-radius:2px;padding:0 4px}
.d-section h4{font-size:12px;font-weight:600;color:var(--ink-2);margin:12px 0 5px}
.d-section p{margin:0 0 8px}
.d-section .lead{font-size:15px;color:var(--ink)}
.kv{font-size:13px;color:var(--ink-2)}
.kv>span{display:inline-block;min-width:4.2em;color:var(--muted);margin-right:8px;font-size:11px}
.section-note,.note{font-size:11px;color:var(--muted)}
.source-line{font-size:11px;color:var(--muted);margin-top:8px!important}
.src-chip{display:inline-block;font-family:var(--mono);font-size:10px;line-height:1.5;color:var(--canal);text-decoration:none;border:1px solid var(--line);border-radius:2px;padding:0 4px;margin-right:3px;background:var(--surface)}
.src-chip:hover{background:var(--canal);color:#fff;border-color:var(--canal)}
.linklike{border:0;background:none;padding:0;color:var(--canal);font:inherit;font-size:11px;text-decoration:underline;text-underline-offset:2px;cursor:pointer}
.people-empty{border:1px solid var(--line);background:var(--surface);padding:16px 16px 14px;position:relative;overflow:hidden}
.people-empty::after{content:"待";position:absolute;right:8px;bottom:-18px;font-family:var(--serif);font-size:88px;line-height:1;color:rgba(164,67,44,.07);pointer-events:none}
.people-empty h4{font-family:var(--serif);font-size:21px;font-weight:600;line-height:1.2;margin:0 0 5px}
.people-empty p{max-width:36em;font-size:12px;color:var(--ink-2);margin:0 0 10px}
.reserved-fields{list-style:none;margin:0;padding:0;border-top:1px solid var(--line);max-width:28em}
.reserved-fields li{display:flex;align-items:baseline;justify-content:space-between;gap:16px;padding:4px 0;border-bottom:1px solid var(--line-soft);font-size:11px;color:var(--muted)}
.reserved-fields b{font-family:var(--mono);font-size:9px;font-weight:400;color:var(--celadon-ink)}
.person{padding:12px 0;border-top:1px solid var(--line-soft)}
.person:first-of-type{border-top:0;padding-top:0}
.person-head{display:flex;align-items:baseline;flex-wrap:wrap;gap:8px}
.person-head h4{font-family:var(--serif);font-size:18px;font-weight:600;margin:0;color:var(--ink)}
.person-role{font-size:11px;color:var(--canal)}
.profile-links{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 0;font-size:11px}
.profile-links a{border:1px solid var(--line);border-radius:2px;padding:1px 6px;text-decoration:none;background:var(--surface)}
.profile-links a:hover{border-color:var(--canal)}
.muted{color:var(--muted);font-size:11px}
.channel-slots{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.channel-slot{display:grid;grid-template-columns:8.6em minmax(0,1fr) auto;gap:10px;align-items:baseline;padding:8px 0;border-bottom:1px solid var(--line-soft)}
.channel-slot .slot-label{font-size:11px;color:var(--muted)}
.slot-value{min-width:0;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.slot-value a{font-weight:600}
.slot-empty{color:var(--celadon-ink);font-size:12px}
.slot-status{font-size:10px;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.slot-status.historical{color:var(--amber)}
.channel-extra{margin-top:12px}
.channel-group{margin:0 0 12px}
.channel-group h4{font-size:11px;color:var(--muted);font-weight:600;margin:0 0 4px}
.channel-list{list-style:none;margin:0;padding:0}
.channel-list li{padding:8px 0;border-top:1px solid var(--line-soft)}
.channel-link{font-size:13px;font-weight:600;text-decoration:none}
.channel-meta,.channel-owner{font-size:11px;color:var(--muted);margin:1px 0!important}
.regional{padding:7px 0;border-top:1px solid var(--line-soft)}
.regional:first-of-type{border-top:0}
.regional summary{display:flex;align-items:baseline;justify-content:space-between;gap:12px;cursor:pointer;font-size:13px;font-weight:600}
.regional summary span:last-child{font-size:10px;color:var(--muted);font-weight:400}
.regional[open] summary{margin-bottom:7px}
.case-group ul{margin:0;padding:0;list-style:none}
.case-group li{font-size:12px;color:var(--ink-2);padding:6px 0;border-top:1px solid var(--line-soft)}
.case-group li strong{color:var(--ink)}
.source-list{list-style:none;margin:0;padding:0}
.source-item{padding:8px 0;border-top:1px solid var(--line-soft)}
.source-item:first-child{border-top:0;padding-top:0}
.source-top{display:flex;align-items:baseline;gap:7px}
.source-id{font-family:var(--mono);font-size:10px;color:var(--muted);flex:0 0 auto}
.source-title{font-size:13px;font-weight:600}
.source-supports{font-size:12px;color:var(--ink-2);margin:2px 0!important}
.source-meta{font-size:10px;color:var(--muted);margin:0!important}
.detail-actions{display:flex;flex-wrap:wrap;align-items:center;gap:7px;padding:18px 0 36px}
.btn{display:inline-block;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface);color:var(--ink);padding:7px 10px;font-size:12px;text-decoration:none;cursor:pointer}
.btn:hover{border-color:var(--canal);color:var(--canal)}
.btn.primary{background:var(--ink);border-color:var(--ink);color:#fff}
.btn.primary:hover{background:var(--canal-dark);border-color:var(--canal-dark);color:#fff}
.detail-path{flex:1 0 100%;font-size:10px;color:var(--muted);margin:0;overflow-wrap:anywhere}
.detail-path code{font-family:var(--mono)}
.detail-scrim{display:none}
.agent-wrap{padding-top:38px}
.agents{border-top:3px solid var(--ink);padding:22px 0 10px}
.agent-head{display:grid;grid-template-columns:minmax(0,.9fr) minmax(0,1.1fr);gap:36px;align-items:start}
.agents h2{font-family:var(--serif);font-size:30px;font-weight:600;margin:0}
.agent-head p{margin:0;color:var(--ink-2);font-size:14px}
.agent-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:36px;margin-top:22px}
.agents h3{font-size:13px;font-weight:600;margin:0 0 10px;color:var(--ink-2)}
.path-list{list-style:none;margin:0;padding:0}
.path-list li{padding:8px 0;border-top:1px solid var(--line)}
.path-list a{font-family:var(--mono);font-size:12px}
.path-list span{display:block;font-size:11px;color:var(--muted)}
.agents p{font-size:13px;color:var(--ink-2)}
.agents pre{background:var(--ink);color:#e8ede7;border-radius:var(--radius);padding:13px;overflow:auto;font-family:var(--mono);font-size:11px;line-height:1.55;margin:10px 0}
.agents code{font-family:var(--mono);font-size:.94em}
footer{border-top:1px solid var(--line);margin-top:34px;padding:18px 0 34px;font-size:11px;color:var(--muted)}
footer .shell{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap}
footer p{margin:0}
footer a{margin-left:14px}
.toast{position:fixed;left:50%;bottom:24px;z-index:90;transform:translate(-50%,10px);opacity:0;pointer-events:none;background:var(--ink);color:#fff;padding:8px 13px;border-radius:var(--radius);font-size:12px;transition:opacity .16s ease,transform .16s ease}
.toast.show{opacity:1;transform:translate(-50%,0)}
@media (max-width:1180px){
  .overview{grid-template-columns:minmax(220px,.62fr) minmax(0,1.38fr)}
  .cat-grid{grid-template-columns:minmax(0,1fr)}
}
@media (max-width:1000px){
  .workspace{grid-template-columns:minmax(0,1fr)}
  .list-pane{padding-right:0;border-right:0}
  .detail-pane{position:fixed;top:0;right:0;bottom:0;z-index:60;width:min(590px,100%);max-height:none;overflow:auto;padding:22px 24px 50px;background:var(--surface);border-left:1px solid var(--line);box-shadow:-20px 0 50px rgba(22,33,29,.22);transform:translateX(102%);transition:transform .2s ease}
  .detail-pane.open{transform:none}
  .detail-scrim{display:block;position:fixed;inset:0;z-index:55;background:rgba(22,33,29,.34);opacity:0;pointer-events:none;transition:opacity .2s ease}
  body.detail-open{overflow:hidden}
  body.detail-open .detail-scrim{opacity:1;pointer-events:auto}
}
@media (max-width:860px){
  .mast-grid{display:block}
  .mast-meta{text-align:left;padding-top:16px}
  .mast-meta a{margin-left:0;margin-right:16px}
  .classbar{grid-template-columns:repeat(2,minmax(0,1fr))}
  .class-tab+.class-tab{padding-left:16px}
  .class-tab:nth-child(3){border-left:0}
  .class-note{display:block}
  .coverage{flex-wrap:wrap}
  .cov{min-width:100px}
  .cov-line{display:none}
  .cov.stat{margin-left:0;text-align:left;align-items:flex-start;padding-left:18px}
  .overview{grid-template-columns:1fr}
  .ov-brief{padding:0 0 16px}
  .ov-sector{padding:16px 0 0;border-left:0;border-top:1px solid var(--line)}
  .cat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .toolbar{grid-template-columns:minmax(0,1fr);align-items:start;gap:9px}
  .filters,.filters.primary,.filters.secondary{grid-column:1;width:100%;justify-content:flex-start}
  .agent-head,.agent-grid{grid-template-columns:1fr;gap:18px}
}
@media (max-width:640px){
  .shell{padding:0 16px}
  .masthead{padding-top:18px}
  .brand{gap:14px}
  .seal{flex-basis:46px;width:46px;height:46px;font-size:25px}
  h1{font-size:clamp(1.7rem,8.5vw,2.05rem)}
  .dek{font-size:13px;line-height:1.55}
  .mast-meta{padding-top:10px}
  .classbar{margin-top:16px}
  .class-tab{padding:11px 12px 10px 0}
  .class-tab+.class-tab{padding-left:12px}
  .class-tab strong{font-size:1.25rem}
  .coverage{margin-top:10px}
  .cov{padding:9px 9px 9px 0;min-width:70px}
  .cov strong{font-size:22px}
  .cov span{font-size:10px}
  .cov.stat{padding:9px 0}
  .overview{padding:12px 0}
  .ov-brief h2{font-size:25px}
  .cat-grid{grid-template-columns:minmax(0,1fr)}
  .toolbar{padding:10px 0}
  .field select{max-width:170px}
  .sort-field>span{display:none}
  .list-head{align-items:flex-start;flex-direction:column;gap:2px}
  .sort-note{text-align:left;margin:0}
  .sector-head{grid-template-columns:42px minmax(0,1fr) auto;gap:7px}
  .sector-no{font-size:24px}
  .sector-title h3{font-size:18px}
  .org-row{grid-template-columns:42px minmax(0,1fr);gap:11px;padding:14px 6px 14px 0}
  .logo-frame{width:42px;height:42px}
  .org-name{font-size:18px}
  .detail-pane{padding:18px 16px 42px}
  .detail-head h2{font-size:26px}
  .dossier-top{gap:11px;padding-right:46px}
  .logo-frame.lg{width:52px;height:52px}
  .channel-slot{grid-template-columns:6.8em minmax(0,1fr)}
  .slot-status{grid-column:2;font-size:10px}
  .agents h2{font-size:26px}
  footer .shell{display:block}
  footer a{display:inline-block;margin:6px 14px 0 0}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{transition-duration:.01ms!important;animation-duration:.01ms!important}
}
</style>
</head>
<body>
<a class="skip" href="#main" data-scroll="main">跳到机构索引</a>
<header class="masthead">
  <div class="shell">
    <div class="mast-grid">
      <div class="brand">
        <div class="seal" aria-hidden="true"><span>寻</span></div>
        <div>
          <h1>中国 AI 机会索引</h1>
          <p class="dek">先分机构类别，再按赛道展开公司档案、核心人物与公开渠道；每一条判断都能回到来源。</p>
        </div>
      </div>
      <div class="mast-meta">
        <p><span class="meta-label">数据截至</span> <time datetime="__LATEST__">__LATEST__</time></p>
        <p><a href="../index.json">机器索引 JSON</a><a href="#agents" data-scroll="agents">供 Agent 读取</a></p>
      </div>
    </div>
    <nav class="classbar" id="classbar" aria-label="机构类别">
      <button class="class-tab" type="button" data-class="startups" aria-pressed="true"><strong>创业公司<span class="ct-count">__STARTUPS__</span></strong><span>新进经营型机构 · find-startups</span></button>
      <button class="class-tab" type="button" data-class="incumbents" aria-pressed="false"><strong>现有巨头<span class="ct-count">__INCUMBENTS__</span></strong><span>成熟平台与业务单元 · find-incumbents</span></button>
      <button class="class-tab" type="button" data-class="investors" aria-pressed="false"><strong>金融机构<span class="ct-count">__FINANCIALS__</span></strong><span>投资机构与基金团队</span></button>
      <button class="class-tab ghost" type="button" data-class="unresolved" aria-pressed="false"><strong>未归类<span class="ct-count">__UNRESOLVED__</span></strong><span>身份待确认，不并入三类</span></button>
    </nav>
    <div class="class-note">
      <p id="class-note">当前类别：<b>创业公司</b>；按既有主赛道分组，空赛道自动隐藏。</p>
      <p>筛选与打开的档案会写入 URL，可直接分享。</p>
    </div>
    <div class="coverage" aria-label="资料覆盖与快捷筛选">
      <button class="cov" type="button" data-cov="all"><strong>__TOTAL__</strong><span>机构档案</span></button>
      <span class="cov-line" aria-hidden="true"></span>
      <button class="cov" type="button" data-cov="channels" aria-pressed="false" aria-controls="org-list"><strong>__CHANNELS__</strong><span>有公开渠道</span></button>
      <span class="cov-line" aria-hidden="true"></span>
      <button class="cov" type="button" data-cov="people" aria-pressed="false" aria-controls="org-list"><strong>__PEOPLE__</strong><span>有公开人物</span></button>
      <div class="cov stat"><strong>__SOURCES__</strong><span>条来源记录</span></div>
    </div>
  </div>
</header>

<main id="main">
  <div class="shell">
    <section class="overview" aria-label="当前类别总览">
      <div class="ov-brief">
        <h2 id="ov-class-title">创业公司</h2>
        <p class="ov-sub" id="ov-class-desc">新进经营型机构</p>
        <p class="ov-method" id="ov-class-method">寻源方法：find-startups</p>
        <div class="ov-stats" id="ov-class-stats"></div>
      </div>
      <div class="ov-sector">
        <div class="ov-head"><h2 id="ov-sector-title">赛道分布</h2><p>点击筛选</p></div>
        <div class="cat-grid" id="ov-cats"></div>
      </div>
    </section>
  </div>

  <div class="toolbar-wrap">
    <div class="shell toolbar">
      <div class="searchbox">
        <label class="sr-only" for="q">在当前类别内搜索机构名、别名或方向</label>
        <input id="q" type="search" placeholder="在当前类别内搜索机构名、别名或方向" autocomplete="off" spellcheck="false">
        <span class="slash" aria-hidden="true">/</span>
      </div>
      <div class="filters primary">
        <label class="field"><span>批次</span><select id="f-wave"></select></label>
        <label class="field" id="category-field"><span>赛道</span><select id="f-category"></select></label>
        <label class="field sort-field"><span>排序</span><select id="f-sort"></select></label>
      </div>
      <div class="filters secondary">
        <label class="field"><span>城市</span><select id="f-city"></select></label>
        <label class="toggle"><input id="f-channels" type="checkbox"><span>有公开渠道</span></label>
        <label class="toggle"><input id="f-people" type="checkbox"><span>有公开人物</span></label>
        <button class="reset" id="reset" type="button">清除筛选</button>
      </div>
    </div>
  </div>

  <div class="shell workspace">
    <section class="list-pane" aria-labelledby="list-title">
      <div class="list-head">
        <div>
          <h2 id="list-title">创业公司</h2>
          <p id="result-count" aria-live="polite">共 __STARTUPS__ 家</p>
        </div>
        <p class="sort-note" id="sort-note">按研究批次、名称排序</p>
      </div>
      <div id="org-list" class="org-list" aria-label="机构列表" role="region"></div>
    </section>

    <aside class="detail-pane" id="detail-pane" aria-label="机构档案">
      <div class="detail-body" id="detail-body" tabindex="-1">
        <div class="detail-empty">
          <p class="empty-mark" aria-hidden="true">档</p>
          <h2 id="detail-title">选一家机构，展开完整档案</h2>
          <p>点左侧任意一行，查看公司档案、核心人物、公开渠道、地区线索与来源。核心人物是档案的主角，人物资料暂缺时也保留明确位置。</p>
          <dl class="legend">
            <div><dt><span class="dot first"></span>第一波</dt><dd>优先研究候选</dd></div>
            <div><dt><span class="dot watchlist"></span>观察</dt><dd>身份或边界待核实</dd></div>
            <div><dt><span class="dot later"></span>后续</dt><dd>已有玩家资料批次</dd></div>
          </dl>
          <p class="empty-hint">筛选、搜索与打开的机构都会写入 URL，可直接分享。</p>
        </div>
      </div>
    </aside>
  </div>

  <div class="detail-scrim" data-close aria-hidden="true"></div>

  <div class="shell agent-wrap">
    <section class="agents" id="agents" aria-labelledby="agents-title">
      <div class="agent-head">
        <h2 id="agents-title">供 Agent 读取</h2>
        <p>看板是规范 JSON 的派生视图。Agent 应读取原始文件，而不是解析页面文字；页面里的每个数字和链接都来自 <code>data/</code>。档案格式以 <code>compose-profile</code> 为准，赛道归入以 <code>map-sectors</code> 为准。</p>
      </div>
      <div class="agent-grid">
        <div>
          <h3>数据入口</h3>
          <ul class="path-list">
            <li><a href="../index.json">data/index.json</a><span>__TOTAL__ 个机构的机器索引，含 ID、类型、批次、路径</span></li>
            <li><a href="../companies/">data/companies/&lt;id&gt;.json</a><span>完整档案：身份、业务、渠道、人物、地区、来源与核查日期</span></li>
            <li><a href="../schemas/">data/schemas/</a><span>company / investor / person / channel / targeting / index 契约</span></li>
            <li><a href="../taxonomy.json">data/taxonomy.json</a><span>既有 01–10 赛道定义、边界与参考框架</span></li>
            <li><a href="assets/logos/manifest.json">data/views/assets/logos/manifest.json</a><span>创业公司 logo 的官方来源、抓取日期或跳过原因</span></li>
          </ul>
        </div>
        <div>
          <h3>内嵌数据</h3>
          <p>页面包含 <code>&lt;script type="application/json" id="cn-ai-opp-data"&gt;</code>，可直接取用。</p>
          <pre><code>{
  "meta": { "default_class": "startups", "generated_from": [...] },
  "labels": {...},
  "classes": [{ "id": "startups", "count": 102 }, ...],
  "taxonomy": {...},
  "logos": { "unitree": "assets/logos/unitree.png" },
  "organizations": [
    { "class": "startups", "logo": "...", "index": {...}, "record": {...} }
  ]
}</code></pre>
          <p class="note">每条记录的 <code>index.json_path</code> 指向原始 JSON；详情面板提供“复制 JSON”和“原始 JSON”链接。Logo 只是派生视图资产，缺失时使用文字占位。</p>
        </div>
      </div>
    </section>
  </div>
</main>

<footer>
  <div class="shell">
    <p>公开研究快照，不保证职位仍开放。投资与案例仅为有出处的历史披露，不构成排名或收益证明。</p>
    <p><a href="../../AGENTS.md">Agent 规则</a><a href="../README.md">字段说明</a><a href="README.md">阅读目录</a></p>
  </div>
</footer>

<div class="toast" id="toast" role="status" aria-live="polite"></div>
<div class="sr-only" id="live-status" aria-live="polite"></div>

<script type="application/json" id="cn-ai-opp-data">__DATASET__</script>
<script>
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("cn-ai-opp-data").textContent);
  var ORGS = DATA.organizations || [];
  var BY_ID = new Map(ORGS.map(function (org) { return [org.record.id, org]; }));
  var CATEGORIES = (DATA.taxonomy && DATA.taxonomy.categories) || [];
  var CAT_BY_ID = new Map(CATEGORIES.map(function (cat) { return [cat.id, cat]; }));
  var CLASSES = DATA.classes || [];
  var CLASS_BY_ID = new Map(CLASSES.map(function (item) { return [item.id, item]; }));
  var LOGOS = DATA.logos || {};
  var COLLATOR = new Intl.Collator("zh-Hans-CN", { numeric: true, sensitivity: "base" });
  var L = DATA.labels;
  var WAVE_ORDER = { first: 0, watchlist: 1, later: 2 };
  var GROUP_ORDER = ["emerging", "established", "recent", "new_generation", "founding_unconfirmed"];
  var SORTS = ["wave", "name", "checked", "category"];
  var SORT_LABELS = {
    wave: "按研究批次、名称排序",
    name: "按机构名称排序",
    checked: "按最近核查日期排序",
    category: "按赛道、名称排序"
  };
  var SORT_OPTIONS = {
    wave: "批次优先", name: "名称", checked: "最近核查", category: "赛道"
  };
  var CHANNEL_SLOTS = [
    { key: "website", label: "官网" },
    { key: "careers", label: "官网投递" },
    { key: "email", label: "职业邮箱" },
    { key: "boss", label: "BOSS 直聘企业主页" },
    { key: "liepin", label: "猎聘企业主页" },
    { key: "linkedin", label: "LinkedIn 公司主页" },
    { key: "other_email", label: "其他公开邮箱" }
  ];

  var state = {
    cls: "startups", q: "", wave: "all", category: "all", city: "all",
    channels: false, people: false, sort: "wave", org: null
  };

  var qEl = document.getElementById("q");
  var waveEl = document.getElementById("f-wave");
  var categoryEl = document.getElementById("f-category");
  var categoryField = document.getElementById("category-field");
  var cityEl = document.getElementById("f-city");
  var channelsEl = document.getElementById("f-channels");
  var peopleEl = document.getElementById("f-people");
  var sortEl = document.getElementById("f-sort");
  var listEl = document.getElementById("org-list");
  var listTitleEl = document.getElementById("list-title");
  var resultEl = document.getElementById("result-count");
  var sortNoteEl = document.getElementById("sort-note");
  var classNoteEl = document.getElementById("class-note");
  var detailPane = document.getElementById("detail-pane");
  var detailBody = document.getElementById("detail-body");
  var emptyDetailHtml = detailBody.innerHTML;
  var toastEl = document.getElementById("toast");
  var liveEl = document.getElementById("live-status");
  var toastTimer = null;

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function safeUrl(value) {
    if (typeof value !== "string") return null;
    var text = value.trim();
    return /^(https?:\/\/|mailto:)/i.test(text) ? text : null;
  }

  function link(url, text, cls) {
    var safe = safeUrl(url);
    if (!safe) return esc(text);
    return '<a class="' + esc(cls || "") + '" href="' + esc(safe) + '" target="_blank" rel="noopener noreferrer">' + esc(text) + "</a>";
  }

  function hostOf(url) {
    try { return new URL(url).host.replace(/^www\./, ""); }
    catch (error) { return url; }
  }

  function paragraphs(value) {
    if (value == null || value === "") return "";
    return String(value).split(/\n{2,}/).map(function (part) {
      return "<p>" + esc(part).replace(/\n/g, "<br>") + "</p>";
    }).join("");
  }

  function shorten(value, length) {
    var text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
    return text.length > length ? text.slice(0, length) + "…" : text;
  }

  function toast(message) {
    toastEl.textContent = message;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toastEl.classList.remove("show"); }, 2200);
  }

  function copyText(text, message) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(function () { toast(message); }, function () { fallbackCopy(text, message); });
    } else {
      fallbackCopy(text, message);
    }
  }

  function fallbackCopy(text, message) {
    var area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    try { document.execCommand("copy"); toast(message); }
    catch (error) { toast("复制失败，请打开原始 JSON"); }
    area.remove();
  }

  function sourceLinks(record, ids) {
    var sources = record.sources || [];
    var byId = new Map(sources.map(function (source) { return [source.id, source]; }));
    return (ids || []).map(function (id) {
      var source = byId.get(id);
      if (!source) return '<span class="src-chip">' + esc(id) + "</span>";
      var safe = safeUrl(source.url);
      if (!safe) return '<span class="src-chip">' + esc(id) + "</span>";
      return '<a class="src-chip" href="' + esc(safe) + '" target="_blank" rel="noopener noreferrer" title="' + esc(source.title || id) + '">' + esc(id) + "</a>";
    }).join("");
  }

  function allSourcesButton(record) {
    var count = (record.sources || []).length;
    if (!count) return "";
    return '<button type="button" class="linklike" data-scroll-sources="1">查看本档案 ' + count + " 条来源</button>";
  }

  function categoryName(id) {
    var cat = CAT_BY_ID.get(id);
    return cat ? cat.id + " " + cat.name : "";
  }

  function waveClass(wave) { return wave || "later"; }
  function waveShort(wave) { return L.wave_short[wave] || wave; }
  function waveLong(wave) { return L.waves[wave] || wave; }
  function typeLabel(type) { return L.types[type] || type; }
  function label(map, key) { return (map && map[key]) || key || ""; }
  function classMeta(id) { return CLASS_BY_ID.get(id) || CLASSES[0]; }

  function cityText(record) {
    var notes = (record.regional_notes || []).map(function (note) { return note.region || ""; }).join(" ");
    return (record.locations_text || "") + " " + notes;
  }

  function classOrgs(id) {
    return ORGS.filter(function (org) { return org.class === id; });
  }

  function matches(org, query) {
    if (!query) return true;
    var record = org.record;
    var haystack = [record.name, (record.aliases || []).join(" "), record.focus || "", categoryName(record.category_id)].join(" ").toLocaleLowerCase();
    return haystack.indexOf(query) !== -1;
  }

  function visibleOrgs() {
    var query = state.q.trim().toLocaleLowerCase();
    return classOrgs(state.cls).filter(function (org) {
      var record = org.record;
      if (state.wave !== "all" && record.targeting.wave !== state.wave) return false;
      if (state.category !== "all" && record.category_id !== state.category) return false;
      if (state.city !== "all" && cityText(record).indexOf(state.city) === -1) return false;
      if (state.channels && !(record.channels || []).length) return false;
      if (state.people && !(record.people || []).length) return false;
      return matches(org, query);
    }).sort(function (a, b) {
      var recA = a.record, recB = b.record;
      if (state.sort === "name") return COLLATOR.compare(recA.name, recB.name);
      if (state.sort === "checked") return recB.checked_at.localeCompare(recA.checked_at) || COLLATOR.compare(recA.name, recB.name);
      if (state.sort === "category") {
        return String(recA.category_id || "zz").localeCompare(String(recB.category_id || "zz")) ||
          COLLATOR.compare(recA.name, recB.name);
      }
      return (WAVE_ORDER[recA.targeting.wave] - WAVE_ORDER[recB.targeting.wave]) ||
        COLLATOR.compare(recA.name, recB.name);
    });
  }

  function groupKey(record) {
    if (state.cls === "investors") return record.group || "founding_unconfirmed";
    return record.category_id || "zz";
  }

  function groupInfo(record) {
    if (state.cls === "investors") {
      return { id: record.group || "founding_unconfirmed", no: "代", name: label(L.groups, record.group || "founding_unconfirmed"), boundary: "按成立代际分组，不改变机构类型与投资记录。" };
    }
    var cat = CAT_BY_ID.get(record.category_id);
    return cat ? { id: cat.id, no: cat.id, name: cat.name, boundary: cat.boundary } : { id: "zz", no: "—", name: "未分类", boundary: "暂无主赛道记录。" };
  }

  function groupRows(rows) {
    var groups = new Map();
    rows.forEach(function (org) {
      var info = groupInfo(org.record);
      if (!groups.has(info.id)) groups.set(info.id, { info: info, rows: [] });
      groups.get(info.id).rows.push(org);
    });
    var list = Array.from(groups.values());
    if (state.cls === "investors") {
      list.sort(function (a, b) { return GROUP_ORDER.indexOf(a.info.id) - GROUP_ORDER.indexOf(b.info.id); });
    } else {
      list.sort(function (a, b) { return String(a.info.id).localeCompare(String(b.info.id)); });
    }
    return list;
  }

  function logoHtml(org, large) {
    var src = org.logo || LOGOS[org.record.id];
    var size = large ? " lg" : "";
    if (src) {
      return '<span class="logo-frame' + size + '"><img src="' + esc(src) + '" alt="" loading="lazy" decoding="async"></span>';
    }
    var name = String(org.record.name || "").trim();
    var mark = name ? name.slice(0, 1) : "?";
    return '<span class="logo-frame' + size + '" aria-hidden="true"><span class="monogram">' + esc(mark) + "</span></span>";
  }

  function renderClassNav() {
    document.querySelectorAll("[data-class]").forEach(function (button) {
      var item = classMeta(button.dataset.class);
      button.setAttribute("aria-pressed", String(button.dataset.class === state.cls));
      button.setAttribute("aria-label", item.label + "，" + item.count + " 家，" + item.description);
    });
  }

  function renderClassBrief() {
    var meta = classMeta(state.cls);
    var rows = classOrgs(state.cls);
    var channels = rows.filter(function (org) { return (org.record.channels || []).length; }).length;
    var people = rows.filter(function (org) { return (org.record.people || []).length; }).length;
    var sources = rows.reduce(function (sum, org) { return sum + (org.record.sources || []).length; }, 0);
    document.getElementById("ov-class-title").textContent = meta.label;
    document.getElementById("ov-class-desc").textContent = meta.description;
    document.getElementById("ov-class-method").textContent = "寻源方法：" + meta.method;
    document.getElementById("ov-class-stats").innerHTML = [
      [rows.length, "家机构"], [channels, "有渠道"], [people, "有人物"], [sources, "条来源"]
    ].map(function (pair) {
      return '<div class="ov-stat"><b>' + pair[0] + "</b><span>" + pair[1] + "</span></div>";
    }).join("");
    listTitleEl.textContent = meta.label;
    classNoteEl.innerHTML = "当前类别：<b>" + esc(meta.label) + "</b>；" +
      (state.cls === "investors" ? "按成立代际分组。" : "按既有主赛道分组，空赛道自动隐藏。") +
      (state.cls === "unresolved" ? " 未归类机构独立于创业公司、现有巨头与金融机构。" : "") +
      " 档案口径见 <a href=\"../../skills/compose-profile/SKILL.md\">compose-profile</a>。";
  }

  function renderOverview() {
    var rows = classOrgs(state.cls);
    var counts = {};
    rows.forEach(function (org) {
      var key = groupKey(org.record);
      counts[key] = (counts[key] || 0) + 1;
    });
    var sectors;
    if (state.cls === "investors") {
      sectors = GROUP_ORDER.map(function (id) { return { id: id, no: "代", name: label(L.groups, id) }; });
      document.getElementById("ov-sector-title").textContent = "机构代际";
    } else {
      sectors = CATEGORIES;
      document.getElementById("ov-sector-title").textContent = "赛道分布";
    }
    var max = Math.max.apply(null, sectors.map(function (item) { return counts[item.id] || 0; }).concat([1]));
    document.getElementById("ov-cats").innerHTML = sectors.map(function (item) {
      var count = counts[item.id] || 0;
      var name = state.cls === "investors" ? item.name : item.id + " " + item.name;
      var active = state.cls !== "investors" && state.category === item.id;
      return '<button type="button" class="cat" data-category="' + esc(item.id) + '" aria-pressed="' + active + '"' + (state.cls === "investors" ? " disabled" : "") + '><span class="cat-name">' + esc(name) + '</span><span class="cat-bar"><i style="--w:' + Math.round(count / max * 100) + '%"></i></span><b>' + count + "</b></button>";
    }).join("");
  }

  function renderOptions() {
    var waveCounts = { first: 0, watchlist: 0, later: 0 };
    classOrgs(state.cls).forEach(function (org) {
      var wave = org.record.targeting.wave;
      if (waveCounts[wave] != null) waveCounts[wave] += 1;
    });
    waveEl.innerHTML = '<option value="all">全部批次</option>' +
      '<option value="first">第一波 ' + waveCounts.first + "</option>" +
      '<option value="watchlist">观察 ' + waveCounts.watchlist + "</option>" +
      '<option value="later">后续 ' + waveCounts.later + "</option>";

    var categoryCounts = {};
    classOrgs(state.cls).forEach(function (org) {
      var id = org.record.category_id;
      if (id) categoryCounts[id] = (categoryCounts[id] || 0) + 1;
    });
    if (state.cls === "investors") {
      categoryField.hidden = true;
      categoryEl.innerHTML = '<option value="all">全部赛道</option>';
    } else {
      categoryField.hidden = false;
      categoryEl.innerHTML = '<option value="all">全部赛道</option>' + CATEGORIES.map(function (cat) {
        return '<option value="' + esc(cat.id) + '">' + esc(cat.id + " " + cat.name) + "（" + (categoryCounts[cat.id] || 0) + "）</option>";
      }).join("");
    }

    var cityCounts = {};
    classOrgs(state.cls).forEach(function (org) {
      var text = cityText(org.record);
      (DATA.city_names || []).forEach(function (city) {
        if (text.indexOf(city) !== -1) cityCounts[city] = (cityCounts[city] || 0) + 1;
      });
    });
    var cityNames = Object.keys(cityCounts).sort(function (a, b) {
      return (cityCounts[b] - cityCounts[a]) || (DATA.city_names || []).indexOf(a) - (DATA.city_names || []).indexOf(b);
    });
    cityEl.innerHTML = '<option value="all">全部城市线索</option>' + cityNames.map(function (city) {
      return '<option value="' + esc(city) + '">' + esc(city) + "（" + cityCounts[city] + "）</option>";
    }).join("");

    sortEl.innerHTML = SORTS.map(function (key) {
      return '<option value="' + key + '">' + esc(SORT_OPTIONS[key]) + "</option>";
    }).join("");
  }

  function syncControls() {
    qEl.value = state.q;
    waveEl.value = state.wave;
    categoryEl.value = state.category;
    cityEl.value = state.city;
    channelsEl.checked = state.channels;
    peopleEl.checked = state.people;
    sortEl.value = state.sort;
    document.querySelectorAll("[data-category]").forEach(function (button) {
      if (button.disabled) { button.setAttribute("aria-pressed", "false"); return; }
      button.setAttribute("aria-pressed", String(button.dataset.category === state.category));
    });
    document.querySelectorAll("[data-cov]").forEach(function (button) {
      if (button.dataset.cov === "channels") button.setAttribute("aria-pressed", String(state.channels));
      if (button.dataset.cov === "people") button.setAttribute("aria-pressed", String(state.people));
    });
    sortNoteEl.textContent = SORT_LABELS[state.sort] || SORT_LABELS.wave;
    renderClassNav();
  }

  function rowHtml(org) {
    var record = org.record;
    var category = record.category_id ? categoryName(record.category_id) : label(L.cohorts, org.index.cohort);
    var meta = category + "，" + shorten(record.locations_text || "地点未记录", 46);
    var channels = (record.channels || []).length;
    var people = (record.people || []).length;
    var sources = (record.sources || []).length;
    var selected = state.org === record.id;
    return '<button type="button" class="org-row" data-open="' + esc(record.id) + '" aria-current="' + selected + '">' +
      logoHtml(org, false) +
      '<span class="row-main">' +
        '<span class="row-top"><span class="org-name">' + esc(record.name) + '</span><span class="org-type">' + esc(typeLabel(record.organization_type)) + '</span><span class="wave-tag ' + esc(waveClass(record.targeting.wave)) + '">' + esc(waveShort(record.targeting.wave)) + "</span></span>" +
        '<span class="row-meta">' + esc(meta) + "</span>" +
        '<span class="row-why">' + esc(record.targeting.rationale) + "</span>" +
        '<span class="row-foot"><span>渠道 ' + channels + "</span><span>人物 " + people + "</span><span>来源 " + sources + "</span><span>核查 " + esc(record.checked_at) + "</span></span>" +
      "</span></button>";
  }

  function sectorHead(info, count) {
    var clickable = state.cls !== "investors";
    var title = clickable ?
      '<h3><button type="button" class="linklike" data-category="' + esc(info.id) + '">' + esc(info.name) + "</button></h3>" :
      "<h3>" + esc(info.name) + "</h3>";
    return '<div class="sector-head"' + (clickable ? ' data-sector="' + esc(info.id) + '"' : "") + ">" +
      '<span class="sector-no">' + esc(info.no) + "</span>" +
      '<div class="sector-title">' + title + '<p>' + esc(info.boundary || "") + "</p></div>" +
      '<span class="sector-count">' + count + " 家</span></div>";
  }

  function renderList() {
    var rows = visibleOrgs();
    var channels = rows.filter(function (org) { return (org.record.channels || []).length; }).length;
    var people = rows.filter(function (org) { return (org.record.people || []).length; }).length;
    resultEl.textContent = "共 " + rows.length + " 家（有渠道 " + channels + "，有人物 " + people + "）";
    if (!rows.length) {
      listEl.innerHTML = '<div class="empty"><h3>没有匹配的机构</h3><p>试试减少城市、赛道或“有公开渠道／人物”的条件，或者清空搜索词。</p><button type="button" class="btn" data-clear="1">清除全部筛选</button></div>';
      return;
    }
    listEl.innerHTML = groupRows(rows).map(function (group) {
      return '<section class="sector-section" aria-label="' + esc(group.info.name) + '">' +
        sectorHead(group.info, group.rows.length) +
        group.rows.map(rowHtml).join("") + "</section>";
    }).join("");
  }

  function syncSelection() {
    document.querySelectorAll(".org-row").forEach(function (row) {
      row.setAttribute("aria-current", String(row.dataset.open === state.org));
    });
  }

  function slotFromChannel(record, platform, layer) {
    var channels = record.channels || [];
    for (var i = 0; i < channels.length; i += 1) {
      var channel = channels[i];
      if (channel.platform !== platform) continue;
      if (layer && channel.layer !== layer) continue;
      return { url: channel.url, status: channel.verification_status, checked_at: channel.checked_at, channel: channel };
    }
    return null;
  }

  function contactSlot(record, url, label) {
    if (!url) return null;
    return { url: url, status: "archive", checked_at: record.checked_at, contact: label };
  }

  function resolveSlots(record) {
    var contacts = record.contacts || {};
    var used = {};
    var websiteChannel = slotFromChannel(record, "website");
    var careersChannel = slotFromChannel(record, "careers");
    var boss = slotFromChannel(record, "boss_zhipin", "recruitment_platform");
    var liepin = slotFromChannel(record, "liepin", "recruitment_platform");
    var linkedin = slotFromChannel(record, "linkedin", "professional_social");
    if (boss && boss.channel) used[boss.channel.id] = true;
    if (liepin && liepin.channel) used[liepin.channel.id] = true;
    if (linkedin && linkedin.channel) used[linkedin.channel.id] = true;
    if (websiteChannel && websiteChannel.channel) used[websiteChannel.channel.id] = true;
    if (careersChannel && careersChannel.channel) used[careersChannel.channel.id] = true;
    return {
      used: used,
      slots: {
        website: contactSlot(record, contacts.website, "官网") || websiteChannel,
        careers: contactSlot(record, contacts.careers_url, "官网投递") || careersChannel,
        email: contacts.recruitment_email ? { mailto: contacts.recruitment_email, status: "archive", checked_at: record.checked_at } : null,
        boss: boss,
        liepin: liepin,
        linkedin: linkedin,
        other_email: contacts.other_email ? { mailto: contacts.other_email, status: "archive", checked_at: record.checked_at, purpose: contacts.other_email_purpose } : null
      }
    };
  }

  function statusText(slot) {
    if (!slot) return "";
    if (slot.status === "archive") return "档案字段，核查 " + esc(slot.checked_at);
    return esc(label(L.verification, slot.status)) + "，核查 " + esc(slot.checked_at);
  }

  function slotValue(slot, fallback) {
    if (!slot) return '<span class="slot-empty">待补充</span>';
    if (slot.mailto) {
      return '<a href="mailto:' + esc(slot.mailto) + '">' + esc(slot.mailto) + "</a>" +
        (slot.purpose ? ' <span class="muted">（' + esc(slot.purpose) + "）</span>" : "");
    }
    var safe = safeUrl(slot.url);
    if (!safe) return '<span class="slot-empty">待补充</span>';
    return link(safe, hostOf(safe) + (slot.url.length > 40 ? "…" : ""));
  }

  function statusClass(slot) {
    var cls = "slot-status";
    if (slot && slot.status === "historical") cls += " historical";
    return cls;
  }

  function channelsSection(record) {
    var resolved = resolveSlots(record);
    var slots = resolved.slots;
    var out = '<section class="d-section" id="d-channels"><h3>公开渠道<span class="section-tag">find-channels</span></h3>';
    out += '<ol class="channel-slots">' + CHANNEL_SLOTS.filter(function (item) {
      return item.key !== "other_email" || slots.other_email;
    }).map(function (item) {
      var slot = slots[item.key];
      return '<li class="channel-slot"><span class="slot-label">' + esc(item.label) + "</span>" +
        '<span class="slot-value">' + slotValue(slot) + "</span>" +
        '<span class="' + statusClass(slot) + '">' + (slot ? statusText(slot) : "") + "</span></li>";
    }).join("") + "</ol>";
    var extras = (record.channels || []).filter(function (channel) { return !resolved.used[channel.id]; });
    if (extras.length) {
      out += '<div class="channel-extra"><h4>其他公开入口</h4><ul class="channel-list">';
      extras.forEach(function (channel) {
        var headline = label(L.platforms, channel.platform) + "，" + label(L.purposes, channel.purpose);
        var safe = safeUrl(channel.url);
        out += "<li>" + (safe ? link(safe, headline, "channel-link") : '<span class="channel-link">' + esc(headline) + "</span>") +
          '<p class="channel-meta">' + esc(label(L.verification, channel.verification_status)) + "，核查 " + esc(channel.checked_at) + "</p>" +
          (channel.owner && channel.owner.name ? '<p class="channel-owner">主体：' + esc(channel.owner.name) + "</p>" : "") +
          (channel.notes ? '<p class="note">' + esc(channel.notes) + "</p>" : "") +
          '<p class="source-line">来源 ' + sourceLinks(record, channel.source_ids) + "</p></li>";
      });
      out += "</ul></div>";
    }
    out += '<p class="section-note">固定槽位便于后续 find-channels 逐项补齐；空槽显示“待补充”，不猜测 URL。渠道只证明公开入口归属，不表示岗位仍在招聘；联系方式无字段级来源映射，依据见档案来源。' + allSourcesButton(record) + "</p></section>";
    return out;
  }

  function peopleSection(record) {
    var people = record.people || [];
    var out = '<section class="d-section people-section" id="d-people"><h3>核心人物<span class="section-tag">find-person</span></h3>';
    if (!people.length) {
      out += '<div class="people-empty"><h4>核心人物待补充</h4>' +
        '<p>这家公司尚未收录公开人物档案。后续由 find-person 核实创始人、业务或研究负责人，并记录可核对的身份来源与公开主页。</p>' +
        '<ul class="reserved-fields"><li><span>人物姓名与当前职务</span><b>待补充</b></li><li><span>公开背景与履历摘要</span><b>待补充</b></li><li><span>LinkedIn / X / GitHub / 即刻</span><b>待补充</b></li></ul>' +
        '<p class="section-note">待 find-person 补充；缺失不表示机构没有关键人物。</p></div>';
    } else {
      people.forEach(function (person) {
        out += '<article class="person"><div class="person-head"><h4>' + esc(person.name) + "</h4>" + (person.role ? '<span class="person-role">' + esc(person.role) + "</span>" : "") + "</div>";
        if (person.background) out += paragraphs(person.background);
        if ((person.previous_firms || []).length) out += '<p class="kv"><span>原平台</span>' + esc(person.previous_firms.join("、")) + "</p>";
        var profiles = (person.profiles || []).map(function (profile) {
          var name = label(L.profile_platforms, profile.platform);
          var safe = safeUrl(profile.url);
          return safe ? link(safe, name, "") : esc(name);
        });
        out += '<div class="profile-links">' + (profiles.length ? profiles.join(" ") : '<span class="muted">未记录公开个人主页</span>') + "</div>";
        out += '<p class="source-line">' + esc(label(L.verification, person.verification_status)) + "，核查 " + esc(person.checked_at) + "；来源 " + sourceLinks(record, person.source_ids) + "</p>";
        if (person.notes) out += '<p class="note">' + esc(person.notes) + "</p>";
        out += "</article>";
      });
      out += '<p class="section-note">人物身份与主页分别核验；迁移资料不自动等于当前职务已重新核实。</p>';
    }
    out += "</section>";
    return out;
  }

  function regionalSection(record) {
    var notes = record.regional_notes || [];
    if (!notes.length) return "";
    var out = '<section class="d-section"><h3>地区研究与历史线索</h3>';
    notes.forEach(function (note) {
      out += '<details class="regional"><summary><span>' + esc(note.region) + "</span><span>核查 " + esc(note.checked_at) + "</span></summary>" +
        paragraphs(note.summary) +
        '<p class="source-line">依据 ' + sourceLinks(record, note.source_ids) + "</p></details>";
    });
    out += '<p class="section-note">地区资料独立标注日期，不自动刷新公司整体业务事实。</p></section>';
    return out;
  }

  function casesSection(record) {
    var cases = record.representative_cases || [];
    var out = '<section class="d-section"><h3>案例与归因</h3><p class="section-note">原平台与当前机构分开；参与不等于主导，IPO 不等于已退出。</p>';
    [["prior_firm", "原平台案例"], ["current_firm", "本机构案例"]].forEach(function (pair) {
      var group = cases.filter(function (item) { return item.attribution === pair[0]; });
      out += '<div class="case-group"><h4>' + esc(pair[1]) + "（" + group.length + "）</h4>";
      if (!group.length) {
        out += '<p class="note">本轮未收录足够证据支持的案例；不表示确定没有投资。</p>';
      } else {
        out += "<ul>" + group.map(function (item) {
          return "<li><strong>" + esc(item.company) + "</strong>　" + esc(item.investor_or_team) + "。" + esc(item.outcome) + " " + sourceLinks(record, item.evidence_source_ids) + "</li>";
        }).join("") + "</ul>";
      }
      out += "</div>";
    });
    out += "</section>";
    return out;
  }

  function sourcesSection(record) {
    var sources = record.sources || [];
    var out = '<section class="d-section" id="d-sources"><h3>证据与来源</h3><p class="section-note">来源按档案维护；公开日期未知时保留“未标明”，整理不会刷新核查日期。</p><ol class="source-list">';
    out += sources.map(function (source) {
      var safe = safeUrl(source.url);
      var title = safe ? link(safe, source.title || source.url, "source-title") : '<span class="source-title">' + esc(source.title || source.url) + "</span>";
      return '<li class="source-item"><div class="source-top"><span class="source-id">' + esc(source.id) + "</span>" + title + "</div>" +
        '<p class="source-supports">' + esc(source.supports) + "</p>" +
        '<p class="source-meta">公开日期 ' + esc(source.published_date || "未标明") + "，核查 " + esc(source.checked_at) + "，范围 " + esc(label(L.source_scope, source.scope || "organization")) + "</p></li>";
    }).join("");
    out += "</ol></section>";
    return out;
  }

  function relFromViews(path) {
    if (!path) return "#";
    return path.replace(/^data\/views\//, "").replace(/^data\//, "../");
  }

  function detailHtml(org) {
    var record = org.record;
    var index = org.index;
    var isInvestor = record.organization_type === "investment_firm";
    var aliases = (record.aliases || []).filter(Boolean);
    var metaBits = [
      '<span class="wave-tag ' + esc(waveClass(record.targeting.wave)) + '">' + esc(waveShort(record.targeting.wave)) + "</span>",
      "<span>" + esc(label(L.player_group, record.targeting.player_group)) + "</span>",
      "<span>" + esc(record.category_id ? categoryName(record.category_id) : label(L.cohorts, index.cohort)) + "</span>",
      "<span>核查 " + esc(record.checked_at) + "</span>"
    ];
    var out = '<div class="detail-head"><button type="button" class="detail-close" data-close aria-label="关闭档案">关闭</button>' +
      '<div class="dossier-top">' + logoHtml(org, true) +
      '<div class="dossier-id"><h2 id="detail-title" tabindex="-1">' + esc(record.name) + "</h2>" +
      '<p class="detail-alias">' + (aliases.length ? "别名：" + esc(aliases.join("、")) : "ID：" + esc(record.id)) + "</p>" +
      '<div class="detail-meta">' + metaBits.join("") + "</div></div></div>" +
      '<p class="dossier-intro">' + esc(record.focus) + "</p>" +
      '<p class="dossier-locations">' + esc(record.locations_text || "地点未记录") + "</p></div>";

    out += peopleSection(record);

    if (!isInvestor) {
      out += '<section class="d-section"><h3>业务与产品</h3>' + paragraphs(record.products) +
        '<p class="source-line">业务事实来源 ' + allSourcesButton(record) + "</p></section>";

      if (record.comparison) {
        out += '<section class="d-section"><h3>同类区别</h3>' + paragraphs(record.comparison.summary) +
          '<p class="kv"><span>比较对象</span>' + esc((record.comparison.peer_names || []).join("、") || "未记录") + "</p>" +
          '<p class="source-line">产品定位分析，非性能排名。' + allSourcesButton(record) + "</p></section>";
      }

      if (record.organizational_context) {
        var context = record.organizational_context;
        out += '<section class="d-section"><h3>组织边界</h3>' +
          '<p class="kv"><span>形态</span>' + esc(label(L.forms, context.form)) + "</p>" +
          '<p class="kv"><span>关系</span>' + esc(label(L.relationships, context.relationship_status)) + "</p>" +
          '<p class="kv"><span>母平台</span>' + esc((context.parent_platform_ids || []).join("、") || "未记录") + "</p>" +
          paragraphs(context.summary) +
          '<p class="source-line">核查 ' + esc(context.checked_at) + "；依据 " + sourceLinks(record, context.source_ids) + "</p></section>";
      }

      if (record.investment) {
        out += '<section class="d-section"><h3>投资背景</h3>' + paragraphs(record.investment.summary) +
          '<p class="kv"><span>披露状态</span>' + esc(label(L.funding, record.investment.verification_status)) + "</p>" +
          '<p class="source-line">历史披露不表示完整现股东名册。' + allSourcesButton(record) + "</p></section>";
      }
    } else {
      out += '<section class="d-section"><h3>投资方向与阶段</h3>' +
        '<p class="kv"><span>阶段</span>' + esc(record.stage || "未记录") + "</p>" +
        '<p class="kv"><span>成立</span>' + esc(record.founded && record.founded.year != null ? record.founded.year : "未确认") + "；" + esc(record.founded && record.founded.basis || "口径未记录") + "</p>" +
        '<p class="kv"><span>研究位置</span>' + esc(label(L.coverage_roles, record.coverage && record.coverage.role)) + "；" + esc(record.coverage && record.coverage.reason || "范围未记录") + "</p></section>";
      out += '<section class="d-section"><h3>研究判断</h3>' + paragraphs(record.why_follow) + paragraphs(record.difference) +
        '<p class="kv"><span>近期活动</span>' + esc(record.recent_activity || "未记录") + "</p></section>";
      out += casesSection(record);
    }

    out += channelsSection(record);
    out += regionalSection(record);
    if (record.notes) out += '<section class="d-section"><h3>核查备注</h3>' + paragraphs(record.notes) + "</section>";
    out += sourcesSection(record);

    out += '<div class="detail-actions">' +
      '<button type="button" class="btn primary" data-copy-json="' + esc(record.id) + '">复制 JSON</button>' +
      '<a class="btn" href="' + esc(relFromViews(index.json_path)) + '" target="_blank" rel="noopener noreferrer">原始 JSON</a>' +
      '<a class="btn" href="' + esc(relFromViews(index.markdown_path)) + '" target="_blank" rel="noopener noreferrer">阅读版</a>' +
      '<button type="button" class="btn" data-copy-link="1">复制看板链接</button>' +
      '<p class="detail-path"><code>' + esc(index.json_path) + "</code></p>" +
      "</div>";
    return out;
  }

  function showDetail(id, options) {
    var org = BY_ID.get(id);
    if (!org) return;
    state.org = id;
    writeHash();
    detailBody.innerHTML = detailHtml(org);
    detailPane.scrollTop = 0;
    detailPane.classList.add("open");
    document.body.classList.add("detail-open");
    syncSelection();
    liveEl.textContent = "已打开 " + org.record.name + " 的档案";
    if (options && options.focus) detailBody.focus({ preventScroll: true });
  }

  function showEmpty() {
    detailBody.innerHTML = emptyDetailHtml;
    detailPane.classList.remove("open");
    document.body.classList.remove("detail-open");
    syncSelection();
  }

  function closeDetail() {
    var previous = state.org;
    state.org = null;
    writeHash();
    showEmpty();
    if (previous) {
      var row = document.querySelector('.org-row[data-open="' + previous + '"]');
      if (row) row.focus();
    }
  }

  function setClass(id, options) {
    if (!CLASS_BY_ID.has(id)) id = "startups";
    if (state.cls === id && !(options && options.force)) return;
    state.cls = id;
    state.category = "all";
    state.city = "all";
    state.channels = false;
    state.people = false;
    state.org = null;
    state.sort = "wave";
    writeHash();
    renderClassBrief();
    renderOverview();
    renderOptions();
    syncControls();
    renderList();
    showEmpty();
  }

  function resetFilters() {
    state.q = "";
    state.wave = "all";
    state.category = "all";
    state.city = "all";
    state.channels = false;
    state.people = false;
    state.sort = "wave";
    writeHash();
    syncControls();
    renderList();
  }

  function readHash() {
    var params = new URLSearchParams(location.hash.replace(/^#/, ""));
    var cls = params.get("class");
    var wave = params.get("wave");
    var category = params.get("cat");
    var city = params.get("city");
    var sort = params.get("sort");
    var org = params.get("org");
    state.q = params.get("q") || "";
    state.cls = CLASS_BY_ID.has(cls) ? cls : "startups";
    if (org && BY_ID.has(org)) state.cls = BY_ID.get(org).class;
    state.wave = ["first", "watchlist", "later"].indexOf(wave) !== -1 ? wave : "all";
    state.category = CAT_BY_ID.has(category) ? category : "all";
    state.city = (DATA.city_names || []).indexOf(city) !== -1 ? city : "all";
    state.channels = params.get("ch") === "1";
    state.people = params.get("ppl") === "1";
    state.sort = SORTS.indexOf(sort) !== -1 ? sort : "wave";
    state.org = BY_ID.has(org) ? org : null;
  }

  function writeHash() {
    var params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.cls !== "startups") params.set("class", state.cls);
    if (state.wave !== "all") params.set("wave", state.wave);
    if (state.category !== "all") params.set("cat", state.category);
    if (state.city !== "all") params.set("city", state.city);
    if (state.channels) params.set("ch", "1");
    if (state.people) params.set("ppl", "1");
    if (state.sort !== "wave") params.set("sort", state.sort);
    if (state.org) params.set("org", state.org);
    var hash = params.toString();
    var base = location.href.split("#")[0];
    try { history.replaceState(null, "", base + (hash ? "#" + hash : "")); }
    catch (error) { if (hash) location.hash = hash; }
  }

  qEl.addEventListener("input", function () {
    state.q = qEl.value;
    writeHash();
    renderList();
  });

  [waveEl, categoryEl, cityEl, sortEl].forEach(function (element) {
    element.addEventListener("change", function () {
      state.wave = waveEl.value;
      state.category = categoryEl.value;
      state.city = cityEl.value;
      state.sort = sortEl.value;
      writeHash();
      syncControls();
      renderList();
    });
  });

  channelsEl.addEventListener("change", function () {
    state.channels = channelsEl.checked;
    writeHash();
    syncControls();
    renderList();
  });

  peopleEl.addEventListener("change", function () {
    state.people = peopleEl.checked;
    writeHash();
    syncControls();
    renderList();
  });

  document.getElementById("reset").addEventListener("click", resetFilters);

  document.querySelectorAll("[data-cov]").forEach(function (button) {
    button.addEventListener("click", function () {
      var kind = button.dataset.cov;
      if (kind === "all") resetFilters();
      if (kind === "channels") {
        state.channels = !state.channels;
        writeHash();
        syncControls();
        renderList();
      }
      if (kind === "people") {
        state.people = !state.people;
        writeHash();
        syncControls();
        renderList();
      }
    });
  });

  document.addEventListener("click", function (event) {
    var classButton = event.target.closest("[data-class]");
    if (classButton) {
      setClass(classButton.dataset.class, { force: true });
      return;
    }
    var button = event.target.closest("[data-category]");
    if (!button || button.disabled) return;
    state.category = state.category === button.dataset.category ? "all" : button.dataset.category;
    writeHash();
    syncControls();
    renderList();
  });

  listEl.addEventListener("click", function (event) {
    var clear = event.target.closest("[data-clear]");
    if (clear) { resetFilters(); return; }
    var row = event.target.closest("[data-open]");
    if (!row) return;
    showDetail(row.dataset.open, { focus: event.detail === 0 });
  });

  detailBody.addEventListener("click", function (event) {
    var close = event.target.closest("[data-close]");
    if (close) { closeDetail(); return; }
    var copyJson = event.target.closest("[data-copy-json]");
    if (copyJson) {
      var org = BY_ID.get(copyJson.dataset.copyJson);
      if (org) copyText(JSON.stringify(org.record, null, 2), "已复制 " + org.record.id + ".json");
      return;
    }
    var copyLink = event.target.closest("[data-copy-link]");
    if (copyLink) { copyText(location.href, "已复制当前看板链接"); return; }
    var jump = event.target.closest("[data-scroll-sources]");
    if (jump) {
      var sources = document.getElementById("d-sources");
      if (sources) sources.scrollIntoView({ block: "start" });
    }
  });

  document.querySelector(".detail-scrim").addEventListener("click", closeDetail);

  document.addEventListener("click", function (event) {
    var jump = event.target.closest("[data-scroll]");
    if (!jump) return;
    event.preventDefault();
    var target = document.getElementById(jump.dataset.scroll);
    if (target) {
      target.scrollIntoView({ block: "start" });
      target.setAttribute("tabindex", "-1");
      target.focus({ preventScroll: true });
    }
  });

  window.addEventListener("hashchange", function () {
    readHash();
    renderClassBrief();
    renderOverview();
    renderOptions();
    syncControls();
    renderList();
    if (state.org) showDetail(state.org);
    else showEmpty();
  });

  document.addEventListener("keydown", function (event) {
    var target = event.target;
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable;
    if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      qEl.focus();
    }
    if (event.key === "Escape") {
      if (state.org) closeDetail();
      else if (document.activeElement === qEl) qEl.blur();
    }
  });

  readHash();
  renderClassBrief();
  renderOverview();
  renderOptions();
  syncControls();
  renderList();
  if (state.org) showDetail(state.org);
})();
</script>
</body>
</html>
'''
