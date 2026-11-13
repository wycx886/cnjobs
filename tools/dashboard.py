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
    {"id": "unresolved", "label": "未归类", "description": "身份待确认的机构", "method": "待核实", "default": False},
)

LABELS = {
    "player_group": {"new_entrant": "新进候选", "incumbent": "已有玩家", "unresolved": "身份待确认"},
    "groups": {
        "emerging": "新兴机构", "established": "成熟机构",
        "recent": "新兴机构", "new_generation": "新兴机构",
        "founding_unconfirmed": "成立待确认",
    },
    "cohorts": {
        "recent": "新兴机构", "new_generation": "新兴机构",
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
        "research_lab": "研究院", "product_project": "产品线", "unresolved": "待确认",
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


def _parent_platforms(root, records, by_id):
    parent_ids = {
        parent_id
        for record in records
        for parent_id in ((record.get("organizational_context") or {}).get("parent_platform_ids") or [])
    }
    listing = json.loads((Path(root) / "data/lists/incumbents.json").read_text(encoding="utf-8"))
    platforms = {}
    for platform in listing.get("platforms", []):
        parent_id = platform.get("id")
        if parent_id not in parent_ids:
            continue
        profile_id = platform.get("company_id")
        if profile_id not in by_id:
            profile_id = parent_id if parent_id in by_id else None
        platforms[parent_id] = {
            "id": parent_id,
            "name": platform.get("name") or parent_id,
            "profile_id": profile_id,
        }
    for parent_id in parent_ids - set(platforms):
        record = by_id.get(parent_id)
        platforms[parent_id] = {
            "id": parent_id,
            "name": (record or {}).get("name") or parent_id,
            "profile_id": parent_id if record else None,
        }
    return platforms


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
        "parent_platforms": _parent_platforms(root, records, by_id),
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
<meta name="theme-color" content="#0e1111">
<title>中国 AI 机会索引 · cnjobs</title>
<meta name="description" content="中国 AI 机构寻源看板：先分创业公司、现有巨头与金融机构，再按赛道展开公司档案、核心人物与公开渠道。">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Dataset","name":"中国 AI 机会索引","description":"中国 AI 创业公司、大厂创新单元与投资机构的公开研究索引。","keywords":["中国 AI","创业公司","现有巨头","投资机构","风险投资"],"isAccessibleForFree":true}
</script>
<style>
:root{
  --paper:#f7f3ea;
  --surface:#fcfaf4;
  --surface-2:#f1ebdd;
  --ink:#1d1b16;
  --ink-2:#3f3a31;
  --muted:#786f61;
  --line:#ded6c6;
  --line-soft:#eae4d7;
  --accent:#b9874f;
  --accent-2:#8c5b32;
  --jade:#7fae9a;
  --hero:#0e1111;
  --hero-2:#121614;
  --hero-ink:#f2eee4;
  --hero-muted:#98a09a;
  --hero-line:rgba(242,238,228,.16);
  --nav-h:64px;
  --serif:"Songti SC","STSong","Noto Serif SC","Source Han Serif SC",serif;
  --sans:"PingFang SC","Hiragino Sans GB","Microsoft YaHei","Noto Sans SC",system-ui,sans-serif;
  --mono:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:calc(var(--nav-h) + 18px)}
body{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:15px;line-height:1.7;-webkit-font-smoothing:antialiased;overflow-x:hidden}
a{color:inherit;text-decoration:none}
button{font:inherit;color:inherit}
.shell{max-width:1360px;margin:0 auto;padding:0 40px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
.skip{position:absolute;left:16px;top:-56px;z-index:120;background:var(--ink);color:var(--paper);padding:8px 12px;text-decoration:none}
.skip:focus{top:16px}
:focus-visible{outline:2px solid var(--accent-2);outline-offset:3px}
.site-header:not(.solid) :focus-visible,.hero :focus-visible,.p-hero :focus-visible{outline-color:var(--accent)}
.muted{color:var(--muted);font-size:11px}
.section-note{font-size:10.5px;color:var(--muted);line-height:1.7;margin:12px 0 0}

/* ---------- nav ---------- */
.site-header{position:fixed;top:0;left:0;right:0;z-index:60;color:var(--hero-ink);background:transparent;border-bottom:1px solid transparent;transition:background .45s ease,color .45s ease,border-color .45s ease,backdrop-filter .45s ease}
.site-header.solid{background:rgba(247,243,234,.95);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border-bottom-color:var(--line);color:var(--ink)}
.nav-inner{display:flex;align-items:center;gap:30px;padding-top:14px;padding-bottom:14px;min-width:0}
.wordmark{display:flex;align-items:baseline;gap:10px;flex:0 0 auto;font-family:var(--serif)}
.wordmark .mark{font-size:16px;font-weight:600;letter-spacing:.05em}
.wordmark .sub{font-size:16px;font-weight:500;letter-spacing:.16em;opacity:.72}
.site-nav-tabs{display:flex;gap:26px;flex-wrap:wrap;min-width:0}
.class-tab{appearance:none;background:none;border:0;border-bottom:1px solid transparent;padding:6px 0 5px;cursor:pointer;font-size:12.5px;letter-spacing:.1em;color:inherit;opacity:.68;display:inline-flex;align-items:baseline;gap:6px;transition:opacity .25s ease,border-color .25s ease}
.class-tab .ct-count{font-size:9.5px;letter-spacing:.02em;font-variant-numeric:tabular-nums;opacity:.7}
.class-tab:hover{opacity:1}
.class-tab[aria-pressed="true"]{opacity:1;border-bottom-color:currentColor}
.class-tab.ghost{opacity:.5}
.class-tab.ghost:hover{opacity:.85}
.class-tab.ghost[aria-pressed="true"]{opacity:1}
.nav-meta{margin-left:auto;display:flex;align-items:center;gap:16px;flex:0 0 auto;font-size:10.5px;letter-spacing:.06em;opacity:.72;white-space:nowrap}
.nav-meta a{border-bottom:1px solid currentColor;padding-bottom:1px;opacity:.9}
.nav-meta a:hover{color:var(--accent);border-color:var(--accent);opacity:1}

/* ---------- hero ---------- */
.hero{position:relative;min-height:100vh;min-height:100svh;display:flex;align-items:flex-end;isolation:isolate;overflow:hidden;color:var(--hero-ink);background:radial-gradient(125% 90% at 72% 6%,#171c1a 0%,#101413 48%,#0b0e0e 100%)}
.hero-field{position:absolute;inset:0;z-index:0}
.hero-field canvas{display:block;width:100%;height:100%}
.hero-grain{position:absolute;inset:0;width:100%;height:100%;opacity:.05;pointer-events:none;z-index:0}
.hero-inner{position:relative;z-index:1;width:100%;padding-top:calc(var(--nav-h) + 56px);padding-bottom:clamp(48px,10vh,112px);transform-origin:0 100%;transform:translateY(calc(var(--hp,0) * -34px)) scale(calc(1 - var(--hp,0) * .13));opacity:calc(1 - var(--hp,0) * 1.25)}
.hero-kicker{margin:0 0 clamp(18px,3vw,34px);font-size:10px;letter-spacing:.36em;color:var(--hero-muted);text-transform:uppercase}
.class-title{display:flex;flex-wrap:wrap;font-family:var(--serif);font-weight:500;font-size:clamp(3rem,12.4vw,10rem);line-height:.95;letter-spacing:.09em;margin:0;max-width:100%}
.class-title .ch{display:inline-block;opacity:0;transform:translateY(.42em);animation:chIn .62s cubic-bezier(.18,.72,.2,1) both}
@keyframes chIn{to{opacity:1;transform:none}}
.hero-count{margin:clamp(18px,3vw,30px) 0 0;font-size:13px;letter-spacing:.1em;color:rgba(242,238,228,.8);font-variant-numeric:tabular-nums}
.hero-dek{margin:14px 0 0;max-width:40em;font-size:12.5px;line-height:1.85;color:var(--hero-muted)}
.hero-cue{appearance:none;margin-top:clamp(26px,4vw,42px);background:none;border:1px solid var(--hero-line);border-radius:999px;padding:8px 17px;font-size:11px;letter-spacing:.18em;color:rgba(242,238,228,.82);cursor:pointer;display:inline-flex;align-items:center;gap:9px;transition:border-color .3s ease,color .3s ease,background .3s ease}
.hero-cue:hover{border-color:var(--accent);color:var(--hero-ink);background:rgba(185,135,79,.08)}
.hero-cue span{display:inline-block;animation:bob 2.8s ease-in-out infinite}
@keyframes bob{50%{transform:translateY(3px)}}

/* ---------- paper ---------- */
.paper{position:relative;background:var(--paper);z-index:1}
.paper::before{content:"";position:absolute;left:0;right:0;top:0;height:1px;background:rgba(242,238,228,.14)}
.section{padding-top:clamp(56px,7vw,92px);scroll-margin-top:calc(var(--nav-h) + 18px)}
.sec-bar{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;border-bottom:1px solid var(--ink);padding-bottom:12px;flex-wrap:wrap}
.sec-bar h2{font-family:var(--serif);font-size:clamp(21px,2.5vw,29px);font-weight:500;letter-spacing:.06em;margin:0}
.sec-hint{margin:0;font-size:11px;color:var(--muted);letter-spacing:.02em;max-width:46em}

/* reveal */
.reveal{opacity:0;transform:translateY(18px);transition:opacity .7s cubic-bezier(.2,.7,.2,1),transform .7s cubic-bezier(.2,.7,.2,1)}
.reveal.in{opacity:1;transform:none}

/* ---------- sector cards ---------- */
.sector-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(224px,1fr));gap:12px;margin-top:18px}
.sector-card{position:relative;appearance:none;text-align:left;background:var(--surface);border:1px solid var(--line);padding:16px 17px 15px;cursor:pointer;color:var(--ink);display:flex;flex-direction:column;overflow:hidden;transition:border-color .3s ease,background .3s ease,color .3s ease,transform .3s ease}
.sector-card::after{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:var(--accent);transform:scaleY(0);transform-origin:top;transition:transform .4s cubic-bezier(.2,.7,.2,1)}
.sector-card:hover{border-color:var(--ink-2);transform:translateY(-2px)}
.sector-card[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);color:var(--paper)}
.sector-card[aria-pressed="true"]::after{transform:scaleY(1)}
.sector-card[aria-pressed="true"] .sc-no,.sector-card[aria-pressed="true"] .sc-count,.sector-card[aria-pressed="true"] .sc-boundary{color:rgba(247,243,234,.64)}
.sc-icon{width:26px;height:26px;color:var(--accent-2);transition:color .3s ease}
.sector-card[aria-pressed="true"] .sc-icon{color:var(--accent)}
.sc-icon svg{display:block;width:100%;height:100%;overflow:visible}
.sc-icon svg>*{stroke-dasharray:1;stroke-dashoffset:1;animation:iconDraw .9s cubic-bezier(.2,.7,.2,1) .15s forwards}
@keyframes iconDraw{to{stroke-dashoffset:0}}
.sc-no{position:absolute;top:13px;right:15px;font-family:var(--mono);font-size:9.5px;letter-spacing:.1em;color:var(--muted)}
.sc-name{margin-top:14px;font-family:var(--serif);font-size:16.5px;line-height:1.35;letter-spacing:.02em}
.sc-count{margin-top:3px;font-size:10.5px;letter-spacing:.1em;color:var(--muted);font-variant-numeric:tabular-nums}
.sc-boundary{margin-top:9px;font-size:10.5px;line-height:1.6;color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}

/* ---------- toolbar ---------- */
.toolbar-wrap{position:sticky;top:var(--nav-h);z-index:30;margin-top:clamp(40px,5vw,62px);background:rgba(247,243,234,.95);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border-top:1px solid var(--line);border-bottom:1px solid var(--line)}
.toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:12px 22px;padding-top:11px;padding-bottom:11px}
.searchbox{flex:1 1 220px;max-width:380px;position:relative;min-width:0}
.searchbox input{width:100%;border:0;border-bottom:1px solid var(--line);background:transparent;color:var(--ink);padding:6px 26px 6px 0;font:inherit;font-size:13px}
.searchbox input:focus{outline:0;border-bottom-color:var(--ink)}
.slash{position:absolute;right:0;top:50%;transform:translateY(-50%);font-family:var(--mono);font-size:10px;color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;align-items:center;gap:10px 18px;min-width:0}
.field{display:inline-flex;align-items:baseline;gap:7px;font-size:10px;letter-spacing:.1em;color:var(--muted)}
.field select{font:inherit;font-size:12px;letter-spacing:0;color:var(--ink);background:transparent;border:0;border-bottom:1px solid var(--line);padding:3px 16px 3px 0;max-width:180px}
.field select:focus{outline:0;border-bottom-color:var(--ink)}
.toggle{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--ink-2);cursor:pointer;white-space:nowrap}
.toggle input{accent-color:var(--accent-2);margin:0;width:12px;height:12px}
.reset{appearance:none;background:none;border:0;padding:0;font-size:11px;color:var(--muted);text-decoration:underline;text-underline-offset:3px;cursor:pointer}
.reset:hover{color:var(--accent-2)}
.filters.right{margin-left:auto}

/* ---------- directory ---------- */
.dir-head{display:flex;align-items:baseline;justify-content:space-between;gap:24px;border-bottom:1px solid var(--ink);padding-bottom:12px;flex-wrap:wrap}
.dir-head h2{font-family:var(--serif);font-size:clamp(24px,3vw,32px);font-weight:500;letter-spacing:.06em;margin:0}
.dir-sub{font-size:11px;color:var(--muted);letter-spacing:.06em;margin:4px 0 0;font-variant-numeric:tabular-nums}
.sort-note{font-size:10.5px;color:var(--muted);margin:0}
.org-cols{display:grid;grid-template-columns:minmax(220px,1.15fr) minmax(0,1.9fr) 150px 130px;gap:24px;padding:14px 30px 10px 10px;border-bottom:1px solid var(--line);font-size:10px;letter-spacing:.16em;color:var(--muted)}
.org-cols.no-meta{grid-template-columns:minmax(220px,1.15fr) minmax(0,1.9fr) 150px}
.sector-group{margin-top:34px}
.parent-group{margin-top:42px}
.sector-head{display:flex;align-items:baseline;gap:11px;border-bottom:1px solid var(--line);padding:0 10px 9px}
.parent-head{border-bottom-color:var(--ink-2)}
.parent-head .sector-no{letter-spacing:.16em;color:var(--accent-2)}
.parent-head .sector-count{margin-left:auto}
.sh-icon{width:16px;height:16px;flex:0 0 auto;color:var(--accent-2);align-self:center}
.sh-icon svg{display:block;width:100%;height:100%}
.sector-no{font-family:var(--mono);font-size:10px;color:var(--muted)}
.sector-head h3{font-family:var(--serif);font-size:17.5px;font-weight:500;letter-spacing:.04em;margin:0;white-space:nowrap}
.sector-link{appearance:none;background:none;border:0;padding:0;cursor:pointer;font:inherit;color:inherit}
.sector-link:hover{color:var(--accent-2)}
.sector-boundary{font-size:10.5px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1 1 auto;min-width:0;margin-left:4px}
.sector-count{font-size:10px;color:var(--muted);letter-spacing:.1em;white-space:nowrap}
.subhead{display:flex;align-items:baseline;justify-content:space-between;gap:14px;padding:15px 10px 7px;border-bottom:1px solid var(--line-soft)}
.subhead h4{font-family:var(--sans);font-size:10.5px;font-weight:500;letter-spacing:.18em;margin:0;color:var(--ink-2)}
.subhead .sub-count{font-size:9.5px;letter-spacing:.1em;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}
.org-row{position:relative;appearance:none;display:grid;grid-template-columns:minmax(220px,1.15fr) minmax(0,1.9fr) 150px 130px;gap:24px;align-items:center;width:100%;text-align:left;background:none;border:0;border-bottom:1px solid var(--line);padding:15px 30px 15px 10px;cursor:pointer;color:var(--ink);overflow:hidden}
.org-row.no-meta{grid-template-columns:minmax(220px,1.15fr) minmax(0,1.9fr) 150px}
.org-row::before{content:"";position:absolute;inset:0;z-index:0;background:var(--surface-2);transform:scaleX(0);transform-origin:left;transition:transform .38s cubic-bezier(.2,.7,.2,1)}
.org-row:hover::before,.org-row:focus-visible::before{transform:scaleX(1)}
.org-row:hover,.org-row:focus-visible{outline:0;box-shadow:inset 2px 0 0 var(--accent)}
.org-row>*{z-index:1}
.cell-name{display:flex;align-items:center;gap:12px;min-width:0}
.org-name{font-family:var(--serif);font-size:18.5px;font-weight:500;letter-spacing:.02em;line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.org-listed{flex:0 0 auto;margin-left:-5px;border:1px solid rgba(127,174,154,.55);background:rgba(127,174,154,.09);border-radius:2px;padding:0 5px;font-size:9px;line-height:1.75;letter-spacing:.12em;color:#4d7565;white-space:nowrap;cursor:help}
.org-origin{flex:0 0 auto;margin-left:-4px;border:1px solid rgba(185,135,79,.34);background:rgba(185,135,79,.06);border-radius:2px;padding:0 5px;font-size:8.5px;line-height:1.8;letter-spacing:.08em;color:var(--accent-2);white-space:nowrap;cursor:help}
.org-desc{font-size:12.5px;color:var(--ink-2);line-height:1.55;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0}
.cell-loc{font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.cell-meta{font-size:10.5px;color:var(--muted);letter-spacing:.02em;white-space:nowrap;font-variant-numeric:tabular-nums}
.row-arrow{position:absolute;right:10px;top:50%;transform:translate(-6px,-50%);opacity:0;color:var(--accent-2);font-size:14px;line-height:1;transition:opacity .3s ease,transform .3s ease}
.org-row:hover .row-arrow,.org-row:focus-visible .row-arrow{opacity:1;transform:translate(0,-50%)}
.org-row:hover .logo-frame{transform:translateX(3px)}
.org-row:hover .org-name{color:var(--accent-2)}

/* logos */
.logo-frame{--logo-base:34px;--logo-ar:1;width:calc(var(--logo-base) * max(1, min(var(--logo-ar), 2.2)));height:34px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);display:grid;place-items:center;overflow:hidden;transition:transform .35s cubic-bezier(.2,.7,.2,1),width .2s ease}
.logo-frame img{width:100%;height:100%;object-fit:contain;padding:4px;background:#fff;display:block}
.logo-frame .monogram{font-family:var(--serif);font-size:15px;color:var(--accent-2);line-height:1}
.logo-frame.xl{--logo-base:76px;height:76px}
.logo-frame.xl img{padding:10px}
.logo-frame.xl .monogram{font-size:34px}

/* empty state */
.empty{padding:72px 0 80px;border-bottom:1px solid var(--line);max-width:640px}
.empty h3{font-family:var(--serif);font-size:26px;font-weight:500;margin:0 0 8px}
.empty p{color:var(--ink-2);font-size:13px;margin:0 0 18px}
.btn{display:inline-block;border:1px solid var(--ink);background:var(--ink);color:var(--paper);padding:8px 14px;font-size:11px;letter-spacing:.08em;cursor:pointer;text-decoration:none}
.btn:hover{background:var(--accent-2);border-color:var(--accent-2);color:var(--paper)}
.btn.ghost{background:none;color:var(--ink)}
.btn.ghost:hover{background:var(--ink);color:var(--paper)}

/* ---------- profile ---------- */
.profile-view{display:none}
body.profile-open .profile-view{display:block}
body.profile-open .site-header,body.profile-open .home-view{display:none}
@keyframes viewIn{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:none}}
.view-enter{animation:viewIn .3s cubic-bezier(.2,.7,.2,1) both}
.profile-bar{position:sticky;top:0;z-index:40;background:rgba(247,243,234,.95);-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px);border-bottom:1px solid var(--line)}
.profile-bar-inner{display:flex;align-items:center;gap:16px;padding-top:13px;padding-bottom:13px;font-size:11px;letter-spacing:.06em;min-width:0}
.back-link{appearance:none;background:none;border:0;padding:0;cursor:pointer;font-size:11px;letter-spacing:.08em;color:var(--ink);display:inline-flex;align-items:center;gap:6px;white-space:nowrap}
.back-link:hover{color:var(--accent-2)}
.profile-crumb{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.profile-crumb b{color:var(--ink);font-weight:500}
.p-hero{position:relative;isolation:isolate;overflow:hidden;color:var(--hero-ink);background:radial-gradient(120% 100% at 70% 0%,#171c1a 0%,#101413 55%,#0b0e0e 100%)}
.p-field{position:absolute;inset:0;opacity:.45;z-index:0}
.p-hero.is-incumbent .p-field,.p-hero.is-investor .p-field{opacity:.62}
.p-field canvas{display:block;width:100%;height:100%}
.p-hero-inner{position:relative;z-index:1;padding-top:clamp(48px,7vw,84px);padding-bottom:clamp(44px,6vw,76px)}
.p-brand{display:flex;align-items:flex-start;gap:22px;min-width:0}
.p-id{min-width:0}
.p-name{font-family:var(--serif);font-size:clamp(2.6rem,5.2vw,4.4rem);font-weight:500;line-height:1.03;letter-spacing:.02em;margin:0;outline:none;overflow-wrap:anywhere}
.p-alias{font-size:11px;color:var(--hero-muted);letter-spacing:.06em;margin:10px 0 0;overflow-wrap:anywhere}
.p-parent{margin:16px 0 0;font-size:11px;letter-spacing:.08em;color:var(--hero-muted)}
.p-focus{max-width:46em;margin:26px 0 0}
.p-focus p{font-size:16.5px;line-height:1.78;color:rgba(242,238,228,.82);margin:0 0 10px}
.p-focus p:last-child{margin-bottom:0}
.p-hero .muted{color:var(--hero-muted)}
.p-links{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-top:26px}
.pill{display:inline-flex;align-items:center;gap:6px;border:1px solid var(--line);border-radius:999px;background:var(--surface);padding:4px 12px;font-size:11px;color:var(--ink-2);transition:border-color .25s ease,color .25s ease}
a.pill:hover{border-color:var(--ink);color:var(--ink)}
.pill.cta{background:var(--ink);border-color:var(--ink);color:var(--paper);padding:8px 16px;font-size:11px;letter-spacing:.08em}
.pill.cta:hover{background:var(--accent-2);border-color:var(--accent-2)}
.p-hero .pill{border-color:rgba(242,238,228,.28);background:transparent;color:rgba(242,238,228,.86)}
.p-hero a.pill:hover{border-color:var(--accent);color:#fff}
.p-hero .pill.cta{background:var(--hero-ink);border-color:var(--hero-ink);color:var(--ink)}
.p-hero .pill.cta:hover{background:var(--accent);border-color:var(--accent);color:#14110d}
.p-hero .logo-frame{border-color:rgba(242,238,228,.24);background:rgba(255,255,255,.06)}
.p-chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:18px}
.p-chip{display:inline-flex;align-items:baseline;gap:6px;border:1px solid var(--line);border-radius:999px;padding:3px 11px;font-size:10.5px;letter-spacing:.04em;color:var(--muted)}
.p-chip b{font-weight:500;color:var(--ink);white-space:nowrap}
.p-hero .p-chip{border-color:rgba(242,238,228,.22);color:rgba(242,238,228,.68)}
.p-hero .p-chip b{color:var(--hero-ink)}
.p-hero .p-chip.is-quiet{border-style:dashed;color:rgba(242,238,228,.5)}
.p-kicker{display:flex;flex-wrap:wrap;align-items:center;gap:10px;margin:0 0 16px;font-size:10px;letter-spacing:.26em;color:var(--hero-muted)}
.p-kicker .pk-class{color:var(--accent)}
.p-kicker .pk-sep{display:inline-block;width:20px;height:1px;background:rgba(242,238,228,.32)}
.p-listed{display:inline-flex;align-items:baseline;gap:6px;border:1px solid rgba(127,174,154,.5);border-radius:2px;padding:1px 7px;font-size:9.5px;letter-spacing:.16em;color:var(--jade);cursor:help}
.p-listed span{font-size:8.5px;letter-spacing:.06em;color:var(--hero-muted)}
.p-focus .p-lead{margin:0;max-width:44em;font-size:15.5px;line-height:1.82;color:rgba(242,238,228,.86)}
.p-focus .p-aside{margin:10px 0 0;max-width:46em;font-size:11.5px;line-height:1.75;color:var(--hero-muted)}
.p-hero.is-incumbent .p-name{font-size:clamp(2.2rem,4.4vw,3.7rem);letter-spacing:.05em}
.p-hero.is-incumbent .p-kicker::before{content:"";display:inline-block;width:28px;height:1px;background:var(--accent);opacity:.8}
.p-meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(168px,1fr));gap:14px 30px;margin:24px 0 0;padding-top:18px;border-top:1px solid var(--hero-line);max-width:62em}
.p-meta div{min-width:0}
.p-meta dt{font-size:9.5px;letter-spacing:.18em;color:var(--hero-muted);margin:0 0 3px;font-weight:400}
.p-meta dd{margin:0;font-size:12.5px;line-height:1.65;color:rgba(242,238,228,.86);overflow-wrap:anywhere}
.p-meta dd.is-quiet{color:var(--hero-muted)}
.p-facts{display:flex;flex-wrap:wrap;align-items:baseline;gap:5px 0;margin:24px 0 0;padding-top:16px;border-top:1px solid var(--hero-line);font-size:12px;color:rgba(242,238,228,.82);max-width:62em}
.p-facts .p-fact{white-space:nowrap}
.p-facts .p-fact+.p-fact::before{content:"/";margin:0 12px;color:rgba(242,238,228,.26)}
.p-cases{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:15px 0 0}
.p-cases .p-case-label{font-size:9.5px;letter-spacing:.16em;color:var(--hero-muted);margin-right:2px}
.p-case{border:1px solid rgba(242,238,228,.2);border-left:2px solid var(--accent);padding:2px 9px;font-size:11px;color:rgba(242,238,228,.86)}
.p-investors{margin:22px 0 0;padding-top:16px;border-top:1px solid var(--hero-line);max-width:62em}
.pi-head{font-size:9.5px;letter-spacing:.18em;color:var(--hero-muted);margin:0 0 10px}
.pi-list{list-style:none;margin:0;padding:0;display:flex;flex-wrap:wrap;gap:8px 22px}
.pi-item{display:flex;flex-wrap:wrap;align-items:baseline;gap:8px;min-width:0;font-size:12.5px;line-height:1.6;color:rgba(242,238,228,.88)}
.pi-name{overflow-wrap:anywhere}
.pi-link{font:inherit;color:rgba(242,238,228,.88);background:none;border:0;border-bottom:1px solid rgba(242,238,228,.28);padding:0 0 1px;cursor:pointer;text-align:left;overflow-wrap:anywhere}
.pi-link:hover{color:#fff;border-bottom-color:var(--accent)}
.pi-link:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.pi-rounds{display:inline-flex;flex-wrap:wrap;gap:4px 8px}
.pi-round{font-size:10px;letter-spacing:.04em;color:var(--hero-muted)}
.pi-round.is-lead{color:var(--jade);font-weight:600}
.pi-note{margin:8px 0 0;font-size:9.5px;letter-spacing:.04em;color:rgba(242,238,228,.45)}
.p-hero.is-investor .p-focus p{font-size:14.5px}
.p-hero.is-investor .p-links{margin-top:20px}
.p-sub{margin-top:26px;border-top:1px solid var(--line-soft);padding-top:14px}
.p-sub h3{font-size:10px;letter-spacing:.18em;font-weight:500;color:var(--muted);margin:0 0 8px}
.body-prose{margin-top:20px;max-width:52em}
.body-prose p{font-size:14px;line-height:1.85;color:var(--ink-2);margin:0 0 10px}
.body-prose p:last-child{margin-bottom:0}
.case-list{list-style:none;margin:0;padding:0}
.case-list li{padding:10px 0;border-top:1px solid var(--line-soft)}
.case-list li:first-child{border-top:0;padding-top:0}
.case-top{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap}
.case-top strong{font-size:13px;font-weight:600}
.case-meta{font-size:10.5px;color:var(--muted);letter-spacing:.03em}
.case-note{font-size:12px;color:var(--ink-2);margin:2px 0 0;line-height:1.65}
.case-src{margin:4px 0 0}
.p-section .section-note{margin-top:12px}
.profile-shell{padding-top:clamp(44px,6vw,64px);padding-bottom:96px}
.p-section{padding:52px 0 0}
.p-section:first-child{padding-top:0}
.sec-head{display:flex;align-items:baseline;justify-content:space-between;gap:24px;border-bottom:1px solid var(--ink);padding-bottom:12px;flex-wrap:wrap}
.sec-kicker{font-size:10px;letter-spacing:.24em;color:var(--muted);margin:0 0 6px}
.sec-head h2{font-family:var(--serif);font-size:clamp(24px,3vw,32px);font-weight:500;letter-spacing:.06em;margin:0}
.sec-note{font-size:10.5px;color:var(--muted);margin:0;letter-spacing:.02em}

/* people */
.people-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(268px,1fr));gap:14px;margin-top:22px}
.person-card{border:1px solid var(--line);background:var(--surface);padding:22px;display:flex;flex-direction:column;gap:12px;min-width:0}
.person-top{display:flex;align-items:center;gap:14px;min-width:0}
.person-mono{position:relative;width:54px;height:54px;flex:0 0 auto;border:1px solid var(--line);background:var(--paper);display:grid;place-items:center;overflow:hidden;font-family:var(--serif);font-size:22px;color:var(--accent-2)}
.person-mono.photo img{width:100%;height:100%;object-fit:cover;display:block;filter:grayscale(1);transition:filter .25s ease}
.person-card:hover .person-mono.photo img,.person-card:focus-within .person-mono.photo img{filter:grayscale(0)}
.person-photo-src{position:absolute;left:0;right:0;bottom:0;padding:1px 0 2px;background:rgba(247,243,234,.88);font-size:8.5px;line-height:1.2;letter-spacing:.06em;text-align:center;color:var(--ink-2)}
.person-photo-src:hover{color:var(--accent-2)}
.person-id{min-width:0}
.person-name{font-family:var(--serif);font-size:19px;font-weight:500;margin:0;line-height:1.2;overflow-wrap:anywhere}
.person-role{font-size:10px;letter-spacing:.1em;color:var(--accent-2);margin:3px 0 0}
.person-bg{font-size:12.5px;color:var(--ink-2);line-height:1.65;margin:0}
.person-prev{font-size:10.5px;color:var(--muted);margin:0}
.person-links{display:flex;flex-wrap:wrap;gap:6px}
.person-links a{border:1px solid var(--line);border-radius:999px;padding:2px 9px;font-size:10px;color:var(--ink-2)}
.person-links a:hover{border-color:var(--ink)}
.person-verify{font-size:10px;color:var(--muted);margin:0;line-height:1.6}
.people-empty{padding-bottom:8px}
.pe-head{display:flex;align-items:flex-start;gap:16px;margin-top:22px}
.pe-mark{width:54px;height:54px;flex:0 0 auto;border:1px solid var(--line);background:var(--surface);display:grid;place-items:center;font-family:var(--serif);font-size:22px;color:var(--muted)}
.pe-head h3{font-family:var(--serif);font-size:22px;font-weight:500;margin:0 0 4px}
.pe-head p{font-size:12px;color:var(--ink-2);margin:0;max-width:44em}
.people-grid.reserved{margin-top:18px}
.person-card.reserved{border-style:dashed;background:transparent;gap:8px}
.reserved-no{font-family:var(--mono);font-size:10px;color:var(--muted)}
.reserved-label{font-size:11px;color:var(--ink-2);margin:0}
.reserved-value{font-size:11px;color:var(--muted);letter-spacing:.06em}

/* opportunities */
.opp-list{list-style:none;margin:0;padding:0;border-top:1px solid var(--line)}
.opp-row{display:grid;grid-template-columns:180px minmax(0,1fr) auto;gap:20px;align-items:baseline;padding:14px 4px;border-bottom:1px solid var(--line)}
.opp-label{font-size:11px;letter-spacing:.08em;color:var(--muted)}
.opp-dest{font-size:13px;color:var(--ink);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.opp-action{font-size:11px;letter-spacing:.06em;white-space:nowrap;color:var(--muted)}
.opp-action a{color:var(--ink);border-bottom:1px solid var(--line);padding-bottom:1px}
.opp-action a:hover{color:var(--accent-2);border-color:var(--accent-2)}
.slot-empty{color:var(--muted);font-size:11px;letter-spacing:.08em}
.opp-extra{margin-top:26px}
.opp-extra h3{font-size:10px;letter-spacing:.18em;color:var(--muted);font-weight:500;margin:0 0 4px}

/* appendix */
.appendix{padding-top:60px}
.appendix-head{display:flex;align-items:baseline;gap:14px;border-bottom:1px solid var(--line);padding-bottom:10px}
.appendix-head h2{font-family:var(--serif);font-size:22px;font-weight:500;letter-spacing:.1em;color:var(--ink-2);margin:0}
.appendix-head span{font-size:10px;letter-spacing:.2em;color:var(--muted)}
.a-section{padding:22px 0;border-bottom:1px solid var(--line-soft)}
.a-section h3{font-size:11px;letter-spacing:.16em;font-weight:500;color:var(--muted);margin:0 0 8px}
.a-section p{font-size:12.5px;color:var(--ink-2);margin:0 0 7px;line-height:1.7}
.a-section .lead{font-size:13px;color:var(--ink)}
.kv{font-size:12.5px;color:var(--ink-2)}
.kv>span{display:inline-block;min-width:4.2em;color:var(--muted);margin-right:8px;font-size:10.5px}
.section-tag{margin-left:auto;font-family:var(--mono);font-size:9px;font-weight:400;color:var(--muted);border:1px solid var(--line);padding:0 4px}
.source-line{font-size:10px;color:var(--muted);margin-top:8px!important}
.src-chip{display:inline-block;font-family:var(--mono);font-size:9.5px;line-height:1.5;color:var(--accent-2);text-decoration:none;border:1px solid var(--line);padding:0 4px;margin-right:3px;background:var(--surface)}
.src-chip:hover{background:var(--accent-2);color:var(--paper);border-color:var(--accent-2)}
.linklike{border:0;background:none;padding:0;color:var(--accent-2);font:inherit;font-size:10.5px;text-decoration:underline;text-underline-offset:2px;cursor:pointer}
.regional{padding:8px 0;border-top:1px solid var(--line-soft)}
.regional:first-of-type{border-top:0}
.regional summary{display:flex;align-items:baseline;justify-content:space-between;gap:12px;cursor:pointer;font-size:12.5px;font-weight:600}
.regional summary span:last-child{font-size:9.5px;color:var(--muted);font-weight:400}
.regional[open] summary{margin-bottom:7px}
.case-group ul{margin:0;padding:0;list-style:none}
.case-group li{font-size:11.5px;color:var(--ink-2);padding:6px 0;border-top:1px solid var(--line-soft)}
.case-group li strong{color:var(--ink)}
.case-group h4{font-size:10px;letter-spacing:.14em;font-weight:500;color:var(--muted);margin:10px 0 4px}
.source-list{list-style:none;margin:0;padding:0}
.source-item{padding:8px 0;border-top:1px solid var(--line-soft)}
.source-item:first-child{border-top:0;padding-top:0}
.source-top{display:flex;align-items:baseline;gap:7px}
.source-id{font-family:var(--mono);font-size:9.5px;color:var(--muted);flex:0 0 auto}
.source-title{font-size:12px;font-weight:600}
.source-supports{font-size:11.5px;color:var(--ink-2);margin:2px 0!important}
.source-meta{font-size:9.5px;color:var(--muted);margin:0!important}
.detail-actions{display:flex;flex-wrap:wrap;align-items:center;gap:8px;padding:28px 0 0}
.detail-path{flex:1 0 100%;font-size:9.5px;color:var(--muted);margin:6px 0 0;overflow-wrap:anywhere}
.detail-path code{font-family:var(--mono)}

/* agent appendix + footer */
.agent-wrap{padding-top:76px;padding-bottom:24px}
.agents{border-top:1px solid var(--line);padding:26px 0 8px}
.agent-head{display:grid;grid-template-columns:minmax(0,.8fr) minmax(0,1.2fr);gap:40px;align-items:start}
.agents h2{font-family:var(--serif);font-size:22px;font-weight:500;letter-spacing:.08em;margin:0;color:var(--ink-2)}
.agent-head p{margin:0;color:var(--muted);font-size:12px;line-height:1.75}
.agent-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:40px;margin-top:20px}
.agents h3{font-size:10px;letter-spacing:.18em;color:var(--muted);font-weight:500;margin:0 0 8px}
.path-list{list-style:none;margin:0;padding:0}
.path-list li{padding:8px 0;border-top:1px solid var(--line)}
.path-list a{font-family:var(--mono);font-size:11px}
.path-list a:hover{color:var(--accent-2)}
.path-list span{display:block;font-size:10.5px;color:var(--muted)}
.agents p{font-size:11.5px;color:var(--muted);line-height:1.75}
.agents pre{background:var(--surface);color:var(--ink-2);border:1px solid var(--line);padding:14px;overflow:auto;font-family:var(--mono);font-size:10px;line-height:1.6;margin:10px 0}
.agents code{font-family:var(--mono);font-size:.94em}
footer{border-top:1px solid var(--line);margin-top:40px;padding:18px 0 34px;font-size:10.5px;color:var(--muted)}
footer .shell{display:flex;justify-content:space-between;gap:24px;flex-wrap:wrap}
footer p{margin:0}
footer a{margin-left:14px}
footer a:hover{color:var(--accent-2)}
.toast{position:fixed;left:50%;bottom:24px;z-index:90;transform:translate(-50%,10px);opacity:0;pointer-events:none;background:var(--ink);color:var(--paper);padding:8px 13px;font-size:11px;letter-spacing:.04em;transition:opacity .16s ease,transform .16s ease}
.toast.show{opacity:1;transform:translate(-50%,0)}

@media (max-width:1180px){
  .org-cols{grid-template-columns:minmax(190px,1fr) minmax(0,1.8fr) 120px 110px;gap:16px}
  .org-row{grid-template-columns:minmax(190px,1fr) minmax(0,1.8fr) 120px 110px;gap:16px}
  .org-cols.no-meta,.org-row.no-meta{grid-template-columns:minmax(190px,1fr) minmax(0,1.8fr) 120px}
}
@media (max-width:1080px){
  .org-cols{display:none}
  .org-row{grid-template-columns:minmax(0,1fr) auto;gap:4px 14px;padding:14px 26px 14px 8px}
  .org-row.no-meta{grid-template-columns:minmax(0,1fr) auto}
  .cell-name{grid-column:1;grid-row:1}
  .cell-meta{grid-column:2;grid-row:1;justify-self:end;text-align:right}
  .org-desc{grid-column:1 / -1;grid-row:2}
  .cell-loc{grid-column:1 / -1;grid-row:3}
  .sector-boundary{display:none}
  .sector-head{padding-right:0}
}
@media (max-width:960px){
  .nav-meta{display:none}
  .agent-head,.agent-grid{grid-template-columns:1fr;gap:18px}
}
@media (max-width:760px){
  .shell{padding-left:20px;padding-right:20px}
  .nav-inner{gap:14px;padding-top:12px;padding-bottom:11px;align-items:center}
  .wordmark .mark,.wordmark .sub{font-size:14px}
  .site-nav-tabs{gap:16px;flex-wrap:nowrap;overflow-x:auto;scrollbar-width:none;min-width:0;flex:1 1 auto}
  .site-nav-tabs::-webkit-scrollbar{display:none}
  .class-tab{font-size:11.5px;letter-spacing:.02em;white-space:nowrap;padding:5px 0 4px}
  .class-tab .ct-count{font-size:9px}
  .hero-inner{padding-bottom:clamp(40px,9vh,72px)}
  .class-title{font-size:clamp(3.1rem,15vw,4.6rem);letter-spacing:.06em}
  .hero-dek{font-size:11.5px}
  .hero-cue{padding:7px 14px;font-size:10.5px;letter-spacing:.14em}
  .sector-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}
  .sector-card{padding:13px 13px 12px}
  .sc-name{font-size:14.5px;margin-top:11px}
  .sc-boundary{-webkit-line-clamp:2;font-size:10px}
  .sc-icon{width:22px;height:22px}
  .toolbar-wrap{margin-top:34px}
  .toolbar{gap:9px 16px;padding-top:10px;padding-bottom:10px}
  .filters{gap:8px 14px}
  .filters.right{margin-left:0}
  .dir-head{display:block}
  .sort-note{margin-top:6px}
  .p-brand{gap:14px}
  .logo-frame.xl{--logo-base:56px;height:56px}
  .logo-frame.xl img{padding:7px}
  .logo-frame.xl .monogram{font-size:25px}
  .p-name{font-size:clamp(2rem,8.6vw,2.8rem)}
  .p-focus p{font-size:15px}
  .p-focus .p-lead{font-size:14.5px}
  .p-meta{grid-template-columns:1fr;gap:11px;margin-top:20px}
  .p-facts{font-size:11.5px}
  .p-facts .p-fact{white-space:normal}
  .p-facts .p-fact+.p-fact::before{display:none}
  .p-facts{display:grid;gap:4px}
  .pi-list{display:grid;gap:7px}
  .pi-item{font-size:12px}
  .profile-shell{padding-top:32px}
  .opp-row{grid-template-columns:112px minmax(0,1fr) auto;gap:12px}
  .people-grid{grid-template-columns:minmax(0,1fr)}
  .appendix{padding-top:44px}
  .agents h2{font-size:20px}
  footer .shell{display:block}
  footer a{display:inline-block;margin:6px 14px 0 0}
}
@media (prefers-reduced-motion:reduce){
  html{scroll-behavior:auto}
  *,*::before,*::after{transition-duration:.01ms!important;animation-duration:.01ms!important}
  .reveal{opacity:1;transform:none}
  .class-title .ch{opacity:1;transform:none}
  .hero-cue span{animation:none}
  .hero-inner{transform:none;opacity:1}
}
</style>
</head>
<body>
<a class="skip" href="#main" data-scroll="main">跳到机构索引</a>
<header class="site-header" id="site-header">
  <div class="shell nav-inner">
    <a class="wordmark" href="#main" data-scroll="main"><span class="mark">中国 AI</span><span class="sub">机会索引</span></a>
    <nav class="site-nav-tabs" id="classbar" aria-label="机构类别">
      <button class="class-tab" type="button" data-class="startups" aria-pressed="true">创业公司<span class="ct-count">__STARTUPS__</span></button>
      <button class="class-tab" type="button" data-class="incumbents" aria-pressed="false">现有巨头<span class="ct-count">__INCUMBENTS__</span></button>
      <button class="class-tab" type="button" data-class="investors" aria-pressed="false">金融机构<span class="ct-count">__FINANCIALS__</span></button>
      <button class="class-tab ghost" type="button" data-class="unresolved" aria-pressed="false">未归类<span class="ct-count">__UNRESOLVED__</span></button>
    </nav>
    <div class="nav-meta">
      <span>数据截至 <time datetime="__LATEST__">__LATEST__</time></span>
      <a href="../index.json">机器索引</a>
      <a href="#agents" data-scroll="agents">供 Agent 读取</a>
    </div>
  </div>
</header>

<main id="main">
  <div class="home-view" id="home-view">
    <section class="hero" id="hero" aria-labelledby="class-title">
      <div class="hero-field" aria-hidden="true"><canvas id="hero-canvas"></canvas></div>
      <svg class="hero-grain" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">
        <filter id="grain-noise"><feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch"></feTurbulence><feColorMatrix type="saturate" values="0"></feColorMatrix></filter>
        <rect width="100%" height="100%" filter="url(#grain-noise)"></rect>
      </svg>
      <div class="shell hero-inner">
        <p class="hero-kicker">机构索引</p>
        <h1 class="class-title" id="class-title">创业公司</h1>
        <p class="hero-count" id="hero-count">__STARTUPS__ 家新进经营型机构</p>
        <p class="hero-dek">先分创业公司、现有巨头与金融机构，再按赛道展开公司档案、核心人物与公开渠道。每条判断都能回到来源。</p>
        <button type="button" class="hero-cue" data-scroll="sectors">向下浏览 <span aria-hidden="true">↓</span></button>
      </div>
    </section>

    <div class="paper">
      <section class="shell section sectors reveal" id="sectors" aria-labelledby="sectors-title">
        <div class="sec-bar">
          <h2 id="sectors-title">按赛道浏览</h2>
          <p class="sec-hint" id="sectors-hint">点选赛道卡片筛选下方公司，再次点击取消；卡片内数字为当前类别的机构数。</p>
        </div>
        <div class="sector-grid" id="sector-grid"></div>
      </section>

      <div class="toolbar-wrap">
        <div class="shell toolbar">
          <div class="searchbox">
            <label class="sr-only" for="q">在当前类别内搜索机构名、别名或方向</label>
            <input id="q" type="search" placeholder="搜索机构名、别名或方向" autocomplete="off" spellcheck="false">
            <span class="slash" aria-hidden="true">/</span>
          </div>
          <div class="filters">
            <label class="field"><span id="category-label">赛道</span><select id="f-category"></select></label>
            <label class="field"><span>城市</span><select id="f-city"></select></label>
            <label class="toggle"><input id="f-channels" type="checkbox"><span>有公开渠道</span></label>
            <label class="toggle"><input id="f-people" type="checkbox"><span>有公开人物</span></label>
            <label class="field"><span>排序</span><select id="f-sort"></select></label>
          </div>
          <div class="filters right"><button class="reset" id="reset" type="button">清除</button></div>
        </div>
      </div>

      <section class="shell section directory reveal" id="directory" data-class="startups" aria-labelledby="dir-title">
        <div class="dir-head">
          <div>
            <h2 id="dir-title">全部公司</h2>
            <p class="dir-sub" id="result-count" aria-live="polite">共 __STARTUPS__ 家</p>
          </div>
          <p class="sort-note" id="sort-note">排序：按赛道分组，组内按名称字母序（中文按拼音）。这是本页的排序顺序。</p>
        </div>
        <div class="org-cols" id="org-cols" aria-hidden="true"><span>名称</span><span>简介</span><span>地点</span><span>人物 · 渠道</span></div>
        <div id="org-list" class="org-list" aria-label="机构列表" role="region"></div>
      </section>

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
                <li><a href="../index.json">data/index.json</a><span>__TOTAL__ 个机构的机器索引，含 ID、类型、赛道与路径</span></li>
                <li><a href="../companies/">data/companies/&lt;id&gt;.json</a><span>完整档案：身份、业务、渠道、人物、地区、来源与核查日期</span></li>
                <li><a href="../schemas/">data/schemas/</a><span>company / investor / person / channel / targeting / index 契约</span></li>
                <li><a href="../taxonomy.json">data/taxonomy.json</a><span>既有 01–10 赛道定义、边界与参考框架</span></li>
                <li><a href="assets/logos/manifest.json">data/views/assets/logos/manifest.json</a><span>机构 logo 的官方来源、抓取日期或跳过原因</span></li>
              </ul>
            </div>
            <div>
              <h3>内嵌数据</h3>
              <p>页面包含 <code>&lt;script type="application/json" id="cnjobs-data"&gt;</code>，可直接取用。共 __TOTAL__ 个机构：__OPERATING__ 个经营型机构、__INVESTORS__ 个投资机构；__CHANNELS__ 家已有公开渠道，__PEOPLE__ 家已有公开人物，__SOURCES__ 条来源记录。</p>
              <pre><code>{
  "meta": { "default_class": "startups", "generated_from": [...] },
  "labels": {...},
  "classes": [{ "id": "startups", "count": __STARTUPS__ }, ...],
  "taxonomy": {...},
  "logos": { "unitree": "assets/logos/unitree.svg" },
  "organizations": [
    { "class": "startups", "logo": "...", "index": {...}, "record": {...} }
  ]
}</code></pre>
              <p class="note">每条记录的 <code>index.json_path</code> 指向原始 JSON；公司档案页提供“复制 JSON”“复制看板链接”与原始 JSON／阅读版入口。Logo 只是派生视图资产，缺失时使用文字占位。</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  </div>

  <div class="profile-view" id="profile-view">
    <div class="profile-bar">
      <div class="shell profile-bar-inner">
        <button type="button" class="back-link" id="profile-back" data-back>← 返回索引</button>
        <span class="profile-crumb" id="profile-crumb"></span>
      </div>
    </div>
    <section class="p-hero" id="profile-hero" data-class="startups" aria-labelledby="profile-title">
      <div class="p-field" aria-hidden="true"><canvas id="profile-canvas"></canvas></div>
      <div class="shell p-hero-inner"><div id="profile-intro"></div></div>
    </section>
    <div class="shell profile-shell">
      <div id="profile-body"></div>
    </div>
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

<script type="application/json" id="cnjobs-data">__DATASET__</script>
<script>
(function () {
  "use strict";
  var DATA = JSON.parse(document.getElementById("cnjobs-data").textContent);
  var ORGS = DATA.organizations || [];
  var BY_ID = new Map(ORGS.map(function (org) { return [org.record.id, org]; }));
  var CATEGORIES = (DATA.taxonomy && DATA.taxonomy.categories) || [];
  var CAT_BY_ID = new Map(CATEGORIES.map(function (cat) { return [cat.id, cat]; }));
  var CLASSES = DATA.classes || [];
  var CLASS_BY_ID = new Map(CLASSES.map(function (item) { return [item.id, item]; }));
  var LOGOS = DATA.logos || {};
  var COLLATOR = new Intl.Collator("zh-Hans-CN", { numeric: true, sensitivity: "base" });
  var L = DATA.labels;
  var MATURITY_ORDER = ["established", "emerging", "founding_unconfirmed"];
  var MATURITY_LABELS = { established: "成熟机构", emerging: "新兴机构", founding_unconfirmed: "成立待确认" };
  var MATURITY_MARKS = { established: "熟", emerging: "新", founding_unconfirmed: "待" };
  var MATURITY_BOUNDARY = {
    established: "组织成熟度分组：成熟机构，不是官方排名。",
    emerging: "组织成熟度分组：新兴机构，不是官方排名。",
    founding_unconfirmed: "公开档案成立年份待补齐，暂列此区。"
  };
  var CLASS_MOTIFS = { startups: "stars", incumbents: "lattice", investors: "ledgers", unresolved: "stars" };
  var SORTS = ["category", "name", "checked"];
  var SORT_OPTIONS = { category: "官方顺序", name: "名称", checked: "最近核查" };
  var CHANNEL_SLOTS = [
    { key: "website", label: "官网", action: "打开" },
    { key: "careers", label: "官网投递", action: "投递" },
    { key: "email", label: "职业邮箱", action: "发信" },
    { key: "boss", label: "BOSS 直聘企业主页", action: "打开" },
    { key: "liepin", label: "猎聘企业主页", action: "打开" },
    { key: "linkedin", label: "LinkedIn 公司主页", action: "打开" },
    { key: "other_email", label: "其他公开邮箱", action: "发信" }
  ];
  var CHANNEL_BY_KEY = new Map(CHANNEL_SLOTS.map(function (item) { return [item.key, item]; }));

  var CLASS_HOOKS = {
    startups: "is-startup", incumbents: "is-incumbent",
    investors: "is-investor", unresolved: "is-unresolved"
  };

  var CLASS_CHROME = {
    startups: {
      dir: "全部公司",
      cols: ["名称", "简介", "地点", "人物 · 渠道"],
      sectors: "点选赛道卡片筛选下方公司，再次点击取消；卡片内数字为当前类别的机构数。"
    },
    incumbents: {
      dir: "全部平台",
      cols: ["名称", "业务一句话", "地点", "赛道"],
      sectors: "点选赛道卡片筛选下方平台，再次点击取消；卡片内数字为当前类别的平台数。"
    },
    investors: {
      dir: "全部机构",
      cols: ["名称", "投资方向", "阶段 · 成立"],
      sectors: "点选类型卡片筛选下方机构，再次点击取消；卡片内数字为当前类别的机构数。"
    },
    unresolved: {
      dir: "待核实机构",
      cols: ["名称", "简介", "地点", "身份"],
      sectors: "点选赛道卡片筛选下方机构，再次点击取消；卡片内数字为当前类别的机构数。"
    }
  };

  var PEOPLE_COPY = {
    startups: {
      kicker: "find-person · 创始 / 团队", title: "核心人物",
      note: "人物身份与公开主页分别核验",
      emptyTitle: "核心人物待补充",
      emptyBody: "这家公司尚未收录公开人物档案。后续由 find-person 核实创始人、业务或研究负责人，并记录可核对的身份来源与公开主页。"
    },
    incumbents: {
      kicker: "find-person · 业务 / 研究负责人", title: "核心人物",
      note: "平台口径：业务或研究负责人，不写成创业公司故事",
      emptyTitle: "核心人物待补充",
      emptyBody: "这家平台尚未收录公开人物档案。后续由 find-person 核实业务或研究负责人；平台档案不写成创业公司故事。"
    },
    investors: {
      kicker: "find-person · 投资团队", title: "团队",
      note: "合伙人或投资团队成员，不以机构品牌代替团队",
      emptyTitle: "团队待补充",
      emptyBody: "这家机构尚未收录公开团队档案。后续由 find-person 核实合伙人、投资团队成员及公开主页；不以机构品牌代替具体团队。"
    }
  };

  var OPP_COPY = {
    startups: {
      kicker: "公开招聘与投递入口", title: "机会",
      note: "这些是公开入口，不表示岗位仍在招聘。",
      order: ["website", "careers", "email", "boss", "liepin", "linkedin", "other_email"]
    },
    incumbents: {
      kicker: "平台级招聘与业务入口", title: "机会",
      note: "平台级入口，不表示具体业务团队或岗位仍在招聘。",
      order: ["website", "careers", "email", "boss", "liepin", "linkedin", "other_email"]
    },
    investors: {
      kicker: "BP / 招聘 / 官网", title: "公开入口",
      note: "BP 与招聘邮箱为公开入口，不表示承诺回复或受理。",
      order: ["other_email", "careers", "email", "website", "boss", "liepin", "linkedin"]
    }
  };

  var state = {
    cls: "startups", q: "", category: "all", city: "all",
    channels: false, people: false, sort: "category", org: null
  };

  var qEl = document.getElementById("q");
  var categoryEl = document.getElementById("f-category");
  var categoryLabel = document.getElementById("category-label");
  var cityEl = document.getElementById("f-city");
  var channelsEl = document.getElementById("f-channels");
  var peopleEl = document.getElementById("f-people");
  var sortEl = document.getElementById("f-sort");
  var listEl = document.getElementById("org-list");
  var resultEl = document.getElementById("result-count");
  var sortNoteEl = document.getElementById("sort-note");
  var homeView = document.getElementById("home-view");
  var profileView = document.getElementById("profile-view");
  var profileIntro = document.getElementById("profile-intro");
  var profileBody = document.getElementById("profile-body");
  var profileCrumb = document.getElementById("profile-crumb");
  var profileHero = document.getElementById("profile-hero");
  var sectorGrid = document.getElementById("sector-grid");
  var sectorsHintEl = document.getElementById("sectors-hint");
  var directoryEl = document.getElementById("directory");
  var orgColsEl = document.getElementById("org-cols");
  var dirTitleEl = document.getElementById("dir-title");
  var toastEl = document.getElementById("toast");
  var liveEl = document.getElementById("live-status");
  var headerEl = document.getElementById("site-header");
  var heroEl = document.getElementById("hero");
  var heroInner = document.querySelector(".hero-inner");
  var toastTimer = null;
  var homeScroll = 0;
  var heroField = null;
  var profileField = null;

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

  function label(map, key) { return (map && map[key]) || key || ""; }
  function classMeta(id) { return CLASS_BY_ID.get(id) || CLASSES[0]; }

  function cityText(record) {
    var notes = (record.regional_notes || []).map(function (note) { return note.region || ""; }).join(" ");
    return (record.locations_text || "") + " " + notes;
  }

  function classOrgs(id) {
    return ORGS.filter(function (org) { return org.class === id; });
  }

  function maturityKey(record) {
    var group = record.group;
    if (group === "established") return "established";
    if (group === "emerging" || group === "recent" || group === "new_generation") return "emerging";
    return "founding_unconfirmed";
  }

  function categoryRank(record) {
    var id = record.category_id || "zz";
    var index = CATEGORIES.findIndex(function (cat) { return cat.id === id; });
    return index === -1 ? CATEGORIES.length : index;
  }

  function groupKey(record) {
    if (state.cls === "investors") return maturityKey(record);
    return record.category_id || "zz";
  }

  function matches(org, query) {
    if (!query) return true;
    var record = org.record;
    var haystack = [record.name, (record.aliases || []).join(" "), record.focus || "", categoryName(record.category_id)].join(" ").toLocaleLowerCase();
    return haystack.indexOf(query) !== -1;
  }

  function compareRows(a, b) {
    var recA = a.record, recB = b.record;
    if (state.sort === "name") return COLLATOR.compare(recA.name, recB.name);
    if (state.sort === "checked") return recB.checked_at.localeCompare(recA.checked_at) || COLLATOR.compare(recA.name, recB.name);
    if (state.cls === "investors") {
      var maturity = MATURITY_ORDER.indexOf(maturityKey(recA)) - MATURITY_ORDER.indexOf(maturityKey(recB));
      if (maturity) return maturity;
      return COLLATOR.compare(recA.name, recB.name);
    }
    var rank = categoryRank(recA) - categoryRank(recB);
    if (rank) return rank;
    return COLLATOR.compare(recA.name, recB.name);
  }

  function visibleOrgs() {
    var query = state.q.trim().toLocaleLowerCase();
    return classOrgs(state.cls).filter(function (org) {
      var record = org.record;
      if (state.category !== "all" && groupKey(record) !== state.category) return false;
      if (state.city !== "all" && cityText(record).indexOf(state.city) === -1) return false;
      if (state.channels && !(record.channels || []).length) return false;
      if (state.people && !(record.people || []).length) return false;
      return matches(org, query);
    }).sort(compareRows);
  }

  function groupInfo(record) {
    var cat = CAT_BY_ID.get(record.category_id);
    return cat ? { id: cat.id, no: cat.id, name: cat.name, boundary: cat.boundary } : { id: "zz", no: "—", name: "未分类", boundary: "暂无主赛道记录。" };
  }

  function parentInfo(id) {
    return ((DATA.parent_platforms || {})[id]) || { id: id, name: id, profile_id: null };
  }

  function parentOf(record) {
    var ids = ((record.organizational_context || {}).parent_platform_ids) || [];
    return ids.length ? ids[0] : null;
  }

  function sectorSections(rows) {
    var groups = new Map();
    rows.forEach(function (org) {
      var info = groupInfo(org.record);
      if (!groups.has(info.id)) groups.set(info.id, { info: info, rows: [] });
      groups.get(info.id).rows.push(org);
    });
    return Array.from(groups.values()).sort(function (a, b) {
      return categoryRank(a.rows[0].record) - categoryRank(b.rows[0].record);
    });
  }

  function incumbentSections(rows) {
    var groups = new Map();
    rows.forEach(function (org) {
      var pid = parentOf(org.record);
      if (!pid) return;
      if (!groups.has(pid)) groups.set(pid, []);
      groups.get(pid).push(org);
    });
    var profileIds = new Set();
    groups.forEach(function (_, pid) {
      var profileId = parentInfo(pid).profile_id;
      if (profileId && BY_ID.has(profileId)) profileIds.add(profileId);
    });
    var parents = Array.from(groups.keys()).map(function (pid) {
      var info = parentInfo(pid);
      var profile = info.profile_id && BY_ID.get(info.profile_id);
      if (profile && profile.class !== "incumbents") profile = null;
      return {
        kind: "parent",
        info: info,
        profile: profile || null,
        rows: groups.get(pid).filter(function (org) {
          return !profile || org.record.id !== profile.record.id;
        }).sort(compareRows)
      };
    }).sort(function (a, b) {
      return (b.rows.length - a.rows.length) || COLLATOR.compare(a.info.name, b.info.name);
    });
    var rest = rows.filter(function (org) {
      var record = org.record;
      if (parentOf(record)) return false;
      return !profileIds.has(record.id);
    });
    return parents.concat(sectorSections(rest).map(function (section) {
      section.kind = "sector";
      return section;
    }));
  }

  function maturitySections(rows) {
    var groups = new Map();
    rows.forEach(function (org) {
      var key = maturityKey(org.record);
      if (!groups.has(key)) {
        groups.set(key, {
          info: { id: key, no: MATURITY_MARKS[key] || "—", name: MATURITY_LABELS[key], boundary: MATURITY_BOUNDARY[key] || "" },
          rows: []
        });
      }
      groups.get(key).rows.push(org);
    });
    return MATURITY_ORDER.filter(function (key) { return groups.has(key); }).map(function (key) {
      return groups.get(key);
    });
  }

  function listSections(rows) {
    if (state.sort !== "category") return [{ info: null, rows: rows }];
    if (state.cls === "investors") return maturitySections(rows);
    if (state.cls === "incumbents") return incumbentSections(rows);
    return sectorSections(rows);
  }

  function sortNoteText() {
    if (state.sort === "name") return "当前按名称字母序排列（中文按拼音），不是官方顺序。";
    if (state.sort === "checked") return "当前按最近核查日期排列，不是官方顺序。";
    if (state.cls === "investors") {
      var note = "排序：先成熟机构，再新兴机构，组内按名称字母序（中文按拼音）。";
      if (classOrgs("investors").some(function (org) { return maturityKey(org.record) === "founding_unconfirmed"; })) {
        note += "成立待确认列在最后。";
      }
      return note + "这是本页的排序顺序。";
    }
    return "排序：按赛道分组，组内按名称字母序（中文按拼音）。这是本页的排序顺序。";
  }

  function logoHtml(org, size) {
    var src = org.logo || LOGOS[org.record.id];
    var cls = "logo-frame" + (size ? " " + size : "");
    var name = String(org.record.name || "").trim();
    var mark = name ? name.slice(0, 1) : "?";
    if (src) {
      return '<span class="' + cls + '"><img src="' + esc(src) + '" alt="" loading="lazy" decoding="async" data-mark="' + esc(mark) + '"></span>';
    }
    return '<span class="' + cls + '" aria-hidden="true"><span class="monogram">' + esc(mark) + "</span></span>";
  }

  function markLogoAspect(img) {
    if (!img || img.tagName !== "IMG" || !img.parentNode) return;
    var frame = img.parentNode;
    if (!frame.classList || !frame.classList.contains("logo-frame")) return;
    var w = img.naturalWidth;
    var h = img.naturalHeight;
    if (!w || !h) return;
    var ratio = w / h;
    if (isFinite(ratio) && ratio > 0) frame.style.setProperty("--logo-ar", ratio.toFixed(3));
  }

  function syncLogoAspects(scope) {
    if (!scope || !scope.querySelectorAll) return;
    Array.prototype.forEach.call(scope.querySelectorAll(".logo-frame img"), markLogoAspect);
  }

  document.addEventListener("load", function (event) {
    markLogoAspect(event.target);
  }, true);

  document.addEventListener("error", function (event) {
    var img = event.target;
    if (!img || img.tagName !== "IMG" || !img.parentNode) return;
    var frame = img.parentNode;
    if (!frame.classList) return;
    var mark = esc(img.getAttribute("data-mark") || "?");
    if (frame.classList.contains("logo-frame")) {
      frame.innerHTML = '<span class="monogram">' + mark + "</span>";
      return;
    }
    if (frame.classList.contains("person-mono") && frame.classList.contains("photo")) {
      frame.className = "person-mono";
      frame.setAttribute("aria-hidden", "true");
      frame.innerHTML = mark;
    }
  }, true);

  var SPROUT = '<path pathLength="1" d="M12 20.2v-6.1"/><path pathLength="1" d="M12 14.1c-4.1 0-6.2-2.6-6.2-6.1 4.1 0 6.2 2.6 6.2 6.1z"/><path pathLength="1" d="M12 14.1c4.1 0 6.2-2.6 6.2-6.1-4.1 0-6.2 2.6-6.2 6.1z"/>';
  var SECTOR_ICONS = {
    all: '<rect pathLength="1" x="3.6" y="3.6" width="7" height="7" rx="1.2"/><rect pathLength="1" x="13.4" y="3.6" width="7" height="7" rx="1.2"/><rect pathLength="1" x="3.6" y="13.4" width="7" height="7" rx="1.2"/><rect pathLength="1" x="13.4" y="13.4" width="7" height="7" rx="1.2"/>',
    "01": '<circle pathLength="1" cx="6" cy="6" r="2"/><circle pathLength="1" cx="6" cy="18" r="2"/><circle pathLength="1" cx="18" cy="12" r="2.4"/><path pathLength="1" d="M8 6.6 15.6 11M8 17.4 15.6 13M8 8v8"/>',
    "02": '<rect pathLength="1" x="7" y="7" width="10" height="10" rx="1.6"/><rect pathLength="1" x="10.4" y="10.4" width="3.2" height="3.2" rx=".6"/><path pathLength="1" d="M10 7V4.2M14 7V4.2M10 20v-2.8M14 20v-2.8M7 10H4.2M7 14H4.2M20 10h-2.8M20 14h-2.8"/>',
    "03": '<path pathLength="1" d="M9 8.2 5 12l4 3.8M15 8.2 19 12l-4 3.8"/><path pathLength="1" d="M13.2 6 10.8 18"/>',
    "04": '<path pathLength="1" d="M6 4.6 18 9.6l-5.1 1.7-1.7 5.1z"/><path pathLength="1" d="M12.4 12.6 17 17.2"/><path pathLength="1" d="M18.6 3.6v3.2M17 5.2h3.2"/>',
    "05": '<rect pathLength="1" x="3.4" y="5.2" width="12.6" height="13.6" rx="1.6"/><path pathLength="1" d="M3.4 15.6 7 12l3 3"/><circle pathLength="1" cx="12.2" cy="9" r="1.2"/><path pathLength="1" d="M19.4 3.4v3.4M17.7 5.1h3.4M19.4 16.4v3.2M17.8 18h3.2"/>',
    "06": '<path pathLength="1" d="M4 20.4V4.2h6.4v16.2"/><path pathLength="1" d="M10.4 9.4h9.2v11h-9.2"/><path pathLength="1" d="M6.2 7.2h2M6.2 10.6h2M6.2 14h2M13 12.4h3.4M13 16h3.4"/>',
    "07": '<path pathLength="1" d="M3.9 12.3 12 4.2h7.9v7.9L11.8 20.2z"/><circle pathLength="1" cx="15.6" cy="8.5" r="1.3"/><path pathLength="1" d="M8.6 10.4 13 14.8"/>',
    "08": '<rect pathLength="1" x="3.4" y="16.4" width="6.2" height="4.2" rx="1"/><path pathLength="1" d="M6.5 16.4V11"/><circle pathLength="1" cx="6.5" cy="9.4" r="1.6"/><path pathLength="1" d="M8.1 9.4h5.8"/><circle pathLength="1" cx="15.5" cy="9.4" r="1.6"/><path pathLength="1" d="M15.5 11v3.4M14 16.4v-2h3v2"/>',
    "09": '<rect pathLength="1" x="7.6" y="7.6" width="8.8" height="8.8" rx="2.4"/><path pathLength="1" d="M10 7.6V4.4h4v3.2M10 16.4v3.2h4v-3.2"/><path pathLength="1" d="M12 10.6v2.8"/>',
    "10": '<circle pathLength="1" cx="12" cy="4.4" r="1.7"/><circle pathLength="1" cx="5.4" cy="16.2" r="1.7"/><circle pathLength="1" cx="18.6" cy="16.2" r="1.7"/><circle pathLength="1" cx="12" cy="11.4" r="1.6"/><path pathLength="1" d="M12 6.1v3.7M10.8 12.6 6.6 15M13.2 12.6l4.2 2.4"/>',
    emerging: SPROUT,
    new_generation: SPROUT,
    recent: SPROUT,
    established: '<path pathLength="1" d="M3.6 20.4h16.8"/><path pathLength="1" d="M6.2 20.4V8.6h11.6v11.8"/><path pathLength="1" d="M9.2 11.6h2M13 11.6h2M9.2 15.4h2M13 15.4h2"/><path pathLength="1" d="M12 8.6V4.4l3.6 1.8-3.6 1.8"/>',
    founding_unconfirmed: '<circle pathLength="1" cx="12" cy="12" r="8.2"/><path pathLength="1" d="M9.6 9.6a2.5 2.5 0 1 1 3.7 2.2c-.8.5-1.3 1-1.3 1.9"/><path pathLength="1" d="M12 16.8h.01"/>'
  };

  function iconSvg(id) {
    var body = SECTOR_ICONS[id] || SECTOR_ICONS.all;
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + body + "</svg>";
  }

  /* ---------- generative field ---------- */
  function initField(canvas, options) {
    if (!canvas || !canvas.getContext) return null;
    var ctx = canvas.getContext("2d");
    if (!ctx) return null;
    var opts = options || {};
    var accent = opts.accent || "185,135,79";
    var maxPoints = opts.max || 110;
    var motif = opts.motif || "stars";
    var reduced = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false;
    var field = { w: 0, h: 0, pts: [], grid: [], rules: [], t: 0.18, raf: 0, visible: false };

    function buildStars() {
      var count = Math.round((field.w * field.h) / 16000);
      count = Math.max(24, Math.min(maxPoints, count));
      field.pts = [];
      for (var i = 0; i < count; i += 1) {
        field.pts.push({
          x: Math.random() * field.w,
          y: Math.random() * field.h,
          vx: (Math.random() - 0.5) * 0.15,
          vy: (Math.random() - 0.5) * 0.15,
          r: 0.7 + Math.random() * 1.2,
          warm: Math.random() < 0.16
        });
      }
    }

    function buildLattice() {
      var grid = [];
      var gap = Math.max(64, Math.round(field.w / 15));
      var x = gap * 0.55;
      var i = 0;
      while (x < field.w) {
        if (i % 5 !== 2) grid.push({ kind: "v", x: x, depth: 0.3 + (i % 4) * 0.16, phase: i * 0.62, sway: 3.2 + (i % 4) * 1.7 });
        x += gap * (0.72 + ((i * 37) % 11) / 22);
        i += 1;
      }
      var floorGap = Math.max(58, Math.round(field.h / 8));
      var y = floorGap * 0.5;
      var j = 0;
      while (y < field.h) {
        if (j % 4 !== 3) grid.push({ kind: "h", y: y, phase: j * 0.48, drift: 1.6 + (j % 3) * 1.1 });
        y += floorGap * (0.8 + ((j * 17) % 7) / 24);
        j += 1;
      }
      grid.push({ kind: "brace", x: field.w * 0.18, y: field.h * 0.66, w: Math.min(190, field.w * 0.17), h: Math.min(104, field.h * 0.15), phase: 1.7 });
      grid.push({ kind: "brace", x: field.w * 0.7, y: field.h * 0.3, w: Math.min(150, field.w * 0.13), h: Math.min(86, field.h * 0.12), phase: 3.1 });
      field.grid = grid;
    }

    function buildLedgers() {
      var rules = [];
      var count = Math.max(6, Math.min(13, Math.round(field.h / 92)));
      var top = field.h * 0.2;
      var step = (field.h * 0.6) / Math.max(1, count - 1);
      var cols = Math.max(5, Math.min(10, Math.round(field.w / 160)));
      for (var r = 0; r < count; r += 1) {
        var y = top + r * step;
        var ticks = [];
        for (var c = 0; c < cols; c += 1) {
          if ((r + c * 3) % 6 === 0) continue;
          ticks.push({
            x: field.w * 0.1 + c * (field.w * 0.8 / Math.max(1, cols - 1)),
            len: 6 + ((r * 7 + c * 11) % 9) * 1.6,
            phase: r * 0.8 + c * 0.62,
            jade: (r + c) % 3 === 0,
            warm: (r * cols + c) % 19 === 0
          });
        }
        rules.push({ y: y, phase: r * 0.55, ticks: ticks });
      }
      field.rules = rules;
    }

    function build() {
      if (motif === "lattice") { buildLattice(); return; }
      if (motif === "ledgers") { buildLedgers(); return; }
      buildStars();
    }

    function size() {
      var rect = canvas.getBoundingClientRect();
      var w = Math.round(rect.width);
      var h = Math.round(rect.height);
      if (w < 2 || h < 2) return false;
      var dpr = Math.min(window.devicePixelRatio || 1, 2);
      field.w = w;
      field.h = h;
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      build();
      return true;
    }

    function drawStars(move) {
      var w = field.w, h = field.h, pts = field.pts;
      if (!pts.length) return;
      ctx.clearRect(0, 0, w, h);
      var i, j, p;
      if (move) {
        for (i = 0; i < pts.length; i += 1) {
          p = pts[i];
          p.x += p.vx;
          p.y += p.vy;
          if (p.x < -24) p.x = w + 24; else if (p.x > w + 24) p.x = -24;
          if (p.y < -24) p.y = h + 24; else if (p.y > h + 24) p.y = -24;
        }
      }
      var reach = Math.max(96, Math.min(168, Math.sqrt(w * h) * 0.085));
      var reach2 = reach * reach;
      var warm = [];
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (i = 0; i < pts.length; i += 1) {
        var a = pts[i];
        for (j = i + 1; j < pts.length; j += 1) {
          var b = pts[j];
          var dx = a.x - b.x, dy = a.y - b.y;
          var d2 = dx * dx + dy * dy;
          if (d2 > reach2) continue;
          if (a.warm && b.warm) { warm.push(a.x, a.y, b.x, b.y); continue; }
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
        }
      }
      ctx.strokeStyle = "rgba(228,234,228,0.10)";
      ctx.stroke();
      if (warm.length) {
        ctx.beginPath();
        for (i = 0; i < warm.length; i += 4) {
          ctx.moveTo(warm[i], warm[i + 1]);
          ctx.lineTo(warm[i + 2], warm[i + 3]);
        }
        ctx.strokeStyle = "rgba(" + accent + ",0.22)";
        ctx.stroke();
      }
      ctx.beginPath();
      for (i = 0; i < pts.length; i += 1) {
        p = pts[i];
        if (p.warm) continue;
        ctx.moveTo(p.x + p.r, p.y);
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      }
      ctx.fillStyle = "rgba(236,240,234,0.42)";
      ctx.fill();
      ctx.beginPath();
      for (i = 0; i < pts.length; i += 1) {
        p = pts[i];
        if (!p.warm) continue;
        ctx.moveTo(p.x + p.r, p.y);
        ctx.arc(p.x, p.y, p.r + 0.3, 0, Math.PI * 2);
      }
      ctx.fillStyle = "rgba(" + accent + ",0.78)";
      ctx.fill();
    }

    function drawLattice(move) {
      var w = field.w, h = field.h, grid = field.grid;
      if (!grid.length) return;
      ctx.clearRect(0, 0, w, h);
      if (move) field.t += 0.012;
      var t = field.t;
      var sweep = (t % 1) * w;
      var band = Math.max(96, w * 0.14);
      var i, item;

      var glow = ctx.createLinearGradient(sweep - band, 0, sweep + band, 0);
      glow.addColorStop(0, "rgba(" + accent + ",0)");
      glow.addColorStop(0.5, "rgba(" + accent + ",0.075)");
      glow.addColorStop(1, "rgba(" + accent + ",0)");
      ctx.fillStyle = glow;
      ctx.fillRect(sweep - band, 0, band * 2, h);

      ctx.lineWidth = 1;
      for (i = 0; i < grid.length; i += 1) {
        item = grid[i];
        if (item.kind === "v") {
          var drift = Math.sin(t * 3.2 + item.phase) * item.sway;
          var vx = item.x + drift;
          var near = Math.max(0, 1 - Math.abs(vx - sweep) / band);
          ctx.strokeStyle = "rgba(228,234,228," + (0.06 + item.depth * 0.05 + near * 0.16).toFixed(3) + ")";
          ctx.beginPath();
          ctx.moveTo(vx, 0);
          ctx.lineTo(vx, h);
          ctx.stroke();
          if (near > 0.4) {
            var top = h * 0.16 + Math.sin(t * 2.4 + item.phase) * 3;
            ctx.strokeStyle = "rgba(" + accent + "," + (0.08 + near * 0.26).toFixed(3) + ")";
            ctx.beginPath();
            ctx.moveTo(vx, top);
            ctx.lineTo(vx, top + Math.min(220, h * 0.34));
            ctx.stroke();
          }
        } else if (item.kind === "h") {
          var fy = item.y + Math.sin(t * 2.4 + item.phase) * item.drift;
          ctx.strokeStyle = "rgba(228,234,228,0.075)";
          ctx.beginPath();
          ctx.moveTo(0, fy);
          ctx.lineTo(w, fy);
          ctx.stroke();
          var reach = 74;
          if (sweep > -reach && sweep < w + reach) {
            var floorGlow = ctx.createLinearGradient(sweep - reach, 0, sweep + reach, 0);
            floorGlow.addColorStop(0, "rgba(" + accent + ",0)");
            floorGlow.addColorStop(0.5, "rgba(" + accent + ",0.30)");
            floorGlow.addColorStop(1, "rgba(" + accent + ",0)");
            ctx.strokeStyle = floorGlow;
            ctx.beginPath();
            ctx.moveTo(sweep - reach, fy);
            ctx.lineTo(sweep + reach, fy);
            ctx.stroke();
          }
        } else {
          var by = item.y + Math.sin(t * 2.1 + item.phase) * 2.2;
          ctx.strokeStyle = "rgba(" + accent + "," + (0.13 + 0.06 * (0.5 + 0.5 * Math.sin(t * 1.7 + item.phase))).toFixed(3) + ")";
          ctx.beginPath();
          ctx.moveTo(item.x, by);
          ctx.lineTo(item.x + item.w, by);
          ctx.lineTo(item.x + item.w, by - item.h);
          ctx.stroke();
        }
      }
      ctx.fillStyle = "rgba(236,240,234,0.24)";
      for (var n = 0; n < grid.length; n += 7) {
        var node = grid[n];
        if (node.kind !== "v") continue;
        var nx = node.x + Math.sin(t * 3.2 + node.phase) * node.sway;
        var ny = h * 0.82 + Math.sin(t * 2.8 + node.phase) * 2.4;
        ctx.fillRect(nx - 1, ny, 2, 2);
      }
    }

    function drawLedgers(move) {
      var w = field.w, h = field.h, rules = field.rules;
      if (!rules.length) return;
      ctx.clearRect(0, 0, w, h);
      if (move) field.t += 0.013;
      var t = field.t;
      var scan = t % 1;
      var cursor = w * (0.055 + scan * 0.89);
      var band = Math.max(52, w * 0.055);
      var drift = Math.sin(t * 2.6) * Math.max(3, w * 0.006);
      var top = rules[0].y - 16;
      var bottom = rules[rules.length - 1].y + 16;

      var sheet = ctx.createLinearGradient(cursor - band, 0, cursor + band, 0);
      sheet.addColorStop(0, "rgba(" + accent + ",0)");
      sheet.addColorStop(0.5, "rgba(" + accent + ",0.05)");
      sheet.addColorStop(1, "rgba(" + accent + ",0)");
      ctx.fillStyle = sheet;
      ctx.fillRect(cursor - band, top, band * 2, bottom - top);

      ctx.lineWidth = 1;
      for (var i = 0; i < rules.length; i += 1) {
        var rule = rules[i];
        var ry = rule.y + Math.sin(t * 2 + rule.phase) * 2.6;
        ctx.strokeStyle = "rgba(228,234,228," + (0.065 + 0.02 * (0.5 + 0.5 * Math.sin(t * 1.9 + rule.phase))).toFixed(3) + ")";
        ctx.beginPath();
        ctx.moveTo(w * 0.06, ry);
        ctx.lineTo(w * 0.94, ry);
        ctx.stroke();
        for (var j = 0; j < rule.ticks.length; j += 1) {
          var tick = rule.ticks[j];
          var tx = tick.x + drift + Math.sin(t * 2.4 + tick.phase) * 1.8;
          var near = Math.max(0, 1 - Math.abs(tx - cursor) / band);
          var pulse = 0.5 + 0.5 * Math.sin(t * 3.6 + tick.phase);
          var len = tick.len * (0.7 + pulse * 0.22 + near * 0.5);
          var alpha = 0.13 + pulse * 0.12 + near * 0.42 + (tx < cursor ? 0.03 : 0);
          ctx.strokeStyle = tick.warm ?
            "rgba(" + accent + "," + (alpha + 0.2).toFixed(3) + ")" :
            tick.jade ? "rgba(127,174,154," + alpha.toFixed(3) + ")" :
            "rgba(228,234,228," + (alpha * 0.8).toFixed(3) + ")";
          ctx.beginPath();
          ctx.moveTo(tx, ry);
          ctx.lineTo(tx, ry - len);
          ctx.stroke();
        }
      }

      var cursorFade = ctx.createLinearGradient(0, top, 0, bottom);
      cursorFade.addColorStop(0, "rgba(" + accent + ",0)");
      cursorFade.addColorStop(0.2, "rgba(" + accent + ",0.30)");
      cursorFade.addColorStop(0.8, "rgba(" + accent + ",0.30)");
      cursorFade.addColorStop(1, "rgba(" + accent + ",0)");
      ctx.fillStyle = cursorFade;
      ctx.fillRect(cursor - 0.6, top, 1.2, bottom - top);
    }

    function draw(move) {
      if (!field.w || !field.h) return;
      if (motif === "lattice") drawLattice(move);
      else if (motif === "ledgers") drawLedgers(move);
      else drawStars(move);
    }

    canvas.setAttribute("data-motif", motif);
    field.setMotif = function (name) {
      if (!name || name === motif) return;
      motif = name;
      canvas.setAttribute("data-motif", name);
      field.t = 0.18;
      if (field.w > 1) build();
      if (reduced) { draw(false); return; }
      if (field.visible) { stop(); start(); }
    };

    function loop() {
      field.raf = 0;
      if (!field.visible || document.hidden) return;
      draw(true);
      field.raf = window.requestAnimationFrame(loop);
    }

    function start() {
      if (reduced) { draw(false); return; }
      if (field.raf) return;
      field.raf = window.requestAnimationFrame(loop);
    }

    function stop() {
      if (field.raf) { window.cancelAnimationFrame(field.raf); field.raf = 0; }
    }

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) stop(); else if (field.visible) start();
    });

    var resizeTimer = 0;
    window.addEventListener("resize", function () {
      if (resizeTimer) return;
      resizeTimer = window.setTimeout(function () {
        resizeTimer = 0;
        if (size() && reduced) draw(false);
      }, 180);
    });

    if (!("IntersectionObserver" in window)) {
      if (size()) { field.visible = true; start(); }
      return field;
    }
    new IntersectionObserver(function (entries) {
      field.visible = entries[0].isIntersecting;
      if (field.visible) {
        if (field.w < 2) size();
        start();
      } else {
        stop();
      }
    }, { threshold: 0.02 }).observe(canvas);
    return field;
  }

  function setFieldMotif(field, cls) {
    if (field && field.setMotif) field.setMotif(CLASS_MOTIFS[cls] || "stars");
  }


  /* ---------- rendering ---------- */
  function renderClassNav() {
    document.querySelectorAll(".class-tab[data-class]").forEach(function (button) {
      var item = classMeta(button.dataset.class);
      button.setAttribute("aria-pressed", String(button.dataset.class === state.cls));
      button.setAttribute("aria-label", item.label + "，" + item.count + " 家，" + item.description);
    });
  }

  function renderHeroTitle(text) {
    var el = document.getElementById("class-title");
    var out = "";
    for (var i = 0; i < text.length; i += 1) {
      out += '<span class="ch" style="animation-delay:' + (40 + i * 70) + 'ms">' + esc(text.charAt(i)) + "</span>";
    }
    el.innerHTML = out;
    el.setAttribute("aria-label", text);
  }

  function renderHero() {
    var meta = classMeta(state.cls);
    var rows = classOrgs(state.cls);
    var seen = {};
    rows.forEach(function (org) { seen[groupKey(org.record)] = true; });
    var unit = state.cls === "investors" ? "个类型" : "个赛道";
    renderHeroTitle(meta.label);
    document.getElementById("hero-count").textContent = rows.length + " 家" + meta.description + " · " + Object.keys(seen).length + " " + unit;
    setFieldMotif(heroField, state.cls);
    renderClassNav();
  }

  function sectorItems() {
    var counts = {};
    classOrgs(state.cls).forEach(function (org) {
      var key = groupKey(org.record);
      counts[key] = (counts[key] || 0) + 1;
    });
    var items = [];
    if (state.cls === "investors") {
      MATURITY_ORDER.forEach(function (id) {
        if (!counts[id]) return;
        items.push({ id: id, no: MATURITY_MARKS[id] || "—", name: MATURITY_LABELS[id], count: counts[id], boundary: MATURITY_BOUNDARY[id] || "" });
      });
      return items;
    }
    CATEGORIES.forEach(function (cat) {
      if (!counts[cat.id]) return;
      items.push({ id: cat.id, no: cat.id, name: cat.name, count: counts[cat.id], boundary: cat.boundary });
    });
    return items;
  }

  function renderSectors() {
    var items = sectorItems();
    var total = classOrgs(state.cls).length;
    var allLabel = state.cls === "investors" ? "全部机构" : "全部赛道";
    var allHint = state.cls === "investors" ? "清空类型筛选，显示当前类别的全部投资机构。" : "清空赛道筛选，显示当前类别的全部机构。";
    var html = '<button type="button" class="sector-card" data-category="all" aria-pressed="' + (state.category === "all") + '">' +
      '<span class="sc-icon">' + iconSvg("all") + "</span>" +
      '<span class="sc-no">全部</span>' +
      '<span class="sc-name">' + esc(allLabel) + "</span>" +
      '<span class="sc-count">' + total + " 家</span>" +
      '<span class="sc-boundary">' + esc(allHint) + "</span></button>";
    html += items.map(function (item) {
      return '<button type="button" class="sector-card" data-category="' + esc(item.id) + '" aria-pressed="' + (state.category === item.id) + '">' +
        '<span class="sc-icon">' + iconSvg(item.id) + "</span>" +
        '<span class="sc-no">' + esc(item.no) + "</span>" +
        '<span class="sc-name">' + esc(item.name) + "</span>" +
        '<span class="sc-count">' + item.count + " 家</span>" +
        '<span class="sc-boundary">' + esc(item.boundary || "") + "</span></button>";
    }).join("");
    sectorGrid.innerHTML = html;
  }

  function renderOptions() {
    if (state.cls === "investors") {
      categoryLabel.textContent = "类型";
      var typeCounts = {};
      classOrgs(state.cls).forEach(function (org) {
        var id = groupKey(org.record);
        typeCounts[id] = (typeCounts[id] || 0) + 1;
      });
      categoryEl.innerHTML = '<option value="all">全部机构</option>' + MATURITY_ORDER.filter(function (id) {
        return typeCounts[id];
      }).map(function (id) {
        return '<option value="' + esc(id) + '">' + esc(MATURITY_LABELS[id]) + "（" + typeCounts[id] + "）</option>";
      }).join("");
    } else {
      categoryLabel.textContent = "赛道";
      var categoryCounts = {};
      classOrgs(state.cls).forEach(function (org) {
        var id = org.record.category_id;
        if (id) categoryCounts[id] = (categoryCounts[id] || 0) + 1;
      });
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
    categoryEl.value = state.category;
    if (categoryEl.value !== state.category) categoryEl.value = "all";
    cityEl.value = state.city;
    if (cityEl.value !== state.city) cityEl.value = "all";
    channelsEl.checked = state.channels;
    peopleEl.checked = state.people;
    sortEl.value = state.sort;
    document.querySelectorAll(".sector-card[data-category]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.category === state.category));
    });
    sortNoteEl.textContent = sortNoteText();
    renderClassNav();
  }

  function orgTypeMeta(record) {
    var cat = CAT_BY_ID.get(record.category_id);
    if (cat) return cat.name;
    var context = record.organizational_context;
    return context ? label(L.forms, context.form) : "—";
  }

  function listedInfo(record) {
    var rounds = (record.investment && record.investment.rounds) || [];
    for (var i = 0; i < rounds.length; i += 1) {
      var round = rounds[i];
      if (!round || round.round !== "已上市") continue;
      var bits = [];
      if (round.announced_on) bits.push(round.announced_on + " 上市");
      if (round.notes) bits.push(round.notes);
      return { date: round.announced_on || "", title: bits.join(" · ") || "已上市" };
    }
    return null;
  }

  function listedMark(org, variant) {
    if (!org || org.class !== "startups") return "";
    var info = listedInfo(org.record);
    if (!info) return "";
    var cls = variant === "kicker" ? "p-listed" : "org-listed";
    var date = variant === "kicker" && info.date ? "<span>" + esc(info.date) + "</span>" : "";
    return '<span class="' + cls + '" title="' + esc(info.title) + '">已上市' + date + "</span>";
  }

  function originInfo(record) {
    var firms = [];
    (record.people || []).forEach(function (person) {
      (person.previous_firms || []).forEach(function (firm) {
        if (firm && firms.indexOf(firm) === -1) firms.push(firm);
      });
    });
    if (!firms.length) return null;
    return { firms: firms, first: firms[0], title: "出身：" + firms.join("、") };
  }

  function originMark(org) {
    if (!org || org.class !== "startups") return "";
    var info = originInfo(org.record);
    if (!info) return "";
    return '<span class="org-origin" title="' + esc(info.title) + '">出身 ' + esc(shorten(info.first, 18)) + "</span>";
  }

  function rowHtml(org) {
    var record = org.record;
    var desc;
    var third;
    var fourth;
    var descTitle;
    var isInvestors = state.cls === "investors";
    if (isInvestors) {
      desc = record.focus || "—";
      descTitle = record.focus || "";
      third = record.stage ? stageText(record.stage) : (record.founded && record.founded.year != null ? record.founded.year + " 年成立" : "—");
      fourth = null;
    } else if (state.cls === "incumbents") {
      desc = record.products ? shorten(record.products, 46) : (record.focus || "—");
      descTitle = record.products || record.focus || "";
      third = record.locations_text ? shorten(record.locations_text, 24) : "—";
      fourth = orgTypeMeta(record);
    } else {
      desc = record.focus || "—";
      descTitle = record.focus || "";
      third = record.locations_text ? shorten(record.locations_text, 24) : "—";
      fourth = "人物 " + (record.people || []).length + " · 渠道 " + (record.channels || []).length;
    }
    var metaCell = fourth == null ? "" : '<span class="cell-meta">' + esc(fourth) + "</span>";
    return '<button type="button" class="org-row' + (isInvestors ? " no-meta" : "") + '" data-open="' + esc(record.id) + '">' +
      '<span class="cell-name">' + logoHtml(org) + '<span class="org-name">' + esc(record.name) + "</span>" + listedMark(org) + originMark(org) + "</span>" +
      '<span class="org-desc" title="' + esc(descTitle) + '">' + esc(desc) + "</span>" +
      '<span class="cell-loc">' + esc(third) + "</span>" +
      metaCell +
      '<span class="row-arrow" aria-hidden="true">→</span>' +
      "</button>";
  }

  function sectorHead(info, count) {
    var clickable = info.id !== "zz";
    var title = clickable ?
      '<button type="button" class="sector-link" data-category-set="' + esc(info.id) + '">' + esc(info.name) + "</button>" :
      esc(info.name);
    return '<div class="sector-head">' +
      '<span class="sh-icon" aria-hidden="true">' + iconSvg(info.id) + "</span>" +
      '<span class="sector-no">' + esc(info.no) + "</span>" +
      "<h3>" + title + "</h3>" +
      '<span class="sector-boundary">' + esc(info.boundary || "") + "</span>" +
      '<span class="sector-count">' + count + " 家</span></div>";
  }

  function parentHead(info, count) {
    var profile = info.profile_id && BY_ID.get(info.profile_id);
    var title = profile && profile.class === "incumbents" ?
      '<button type="button" class="sector-link" data-open="' + esc(profile.record.id) + '">' + esc(info.name) + "</button>" :
      esc(info.name);
    return '<div class="sector-head parent-head">' +
      '<span class="sh-icon" aria-hidden="true">' + iconSvg("all") + "</span>" +
      '<span class="sector-no">母公司</span>' +
      "<h3>" + title + "</h3>" +
      '<span class="sector-count">' + count + " 个业务单元</span></div>";
  }

  function renderChrome() {
    var chrome = CLASS_CHROME[state.cls] || CLASS_CHROME.startups;
    dirTitleEl.textContent = chrome.dir;
    sectorsHintEl.textContent = chrome.sectors;
    directoryEl.dataset.class = state.cls;
    orgColsEl.classList.toggle("no-meta", state.cls === "investors");
    orgColsEl.innerHTML = chrome.cols.map(function (text) { return "<span>" + esc(text) + "</span>"; }).join("");
  }

  function resultLine(rows) {
    if (state.cls === "investors") {
      var withCases = rows.filter(function (org) {
        return (org.record.representative_cases || []).length;
      }).length;
      var withEntry = rows.filter(function (org) { return (org.record.channels || []).length; }).length;
      return "共 " + rows.length + " 家机构 · 已记录案例 " + withCases + " · 有公开入口 " + withEntry;
    }
    if (state.cls === "incumbents") {
      var withProducts = rows.filter(function (org) { return org.record.products; }).length;
      var withChannels = rows.filter(function (org) { return (org.record.channels || []).length; }).length;
      return "共 " + rows.length + " 家平台 · 有业务描述 " + withProducts + " · 有公开入口 " + withChannels;
    }
    var channels = rows.filter(function (org) { return (org.record.channels || []).length; }).length;
    var people = rows.filter(function (org) { return (org.record.people || []).length; }).length;
    return "共 " + rows.length + " 家 · 有渠道 " + channels + " · 有人物 " + people;
  }

  function renderList() {
    var rows = visibleOrgs();
    resultEl.textContent = resultLine(rows);
    if (!rows.length) {
      listEl.innerHTML = '<div class="empty"><h3>没有匹配的机构</h3><p>试试减少城市、赛道或“有公开渠道／人物”的条件，或者清空搜索词。</p><button type="button" class="btn" data-clear="1">清除筛选</button></div>';
      return;
    }
    listEl.innerHTML = listSections(rows).map(function (section) {
      if (section.kind === "parent") {
        var parentBody = (section.profile ? rowHtml(section.profile) : "") + section.rows.map(rowHtml).join("");
        return '<section class="sector-group parent-group" aria-label="' + esc(section.info.name) + '">' +
          parentHead(section.info, section.rows.length) + parentBody + "</section>";
      }
      var body = section.rows.map(rowHtml).join("");
      if (!section.info) {
        return '<section class="sector-group" aria-label="机构列表">' + body + "</section>";
      }
      return '<section class="sector-group' + (state.cls === "investors" ? " maturity-group" : "") + '" aria-label="' + esc(section.info.name) + '">' +
        sectorHead(section.info, section.rows.length) + body + "</section>";
    }).join("");
    syncLogoAspects(listEl);
  }

  function renderClass() {
    renderHero();
    renderSectors();
    renderOptions();
  }

  function renderHome() {
    renderChrome();
    syncControls();
    renderList();
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

  function contactSlot(record, url, labelText) {
    if (!url) return null;
    return { url: url, status: "archive", checked_at: record.checked_at, contact: labelText };
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

  function slotStatus(slot) {
    if (!slot) return "";
    if (slot.status === "archive") return "档案字段，核查 " + slot.checked_at;
    return label(L.verification, slot.status) + "，核查 " + slot.checked_at;
  }

  function slotDestination(slot) {
    if (!slot) return null;
    if (slot.mailto) return slot.mailto;
    var safe = safeUrl(slot.url);
    return safe ? hostOf(safe) : null;
  }

  function slotHref(slot) {
    if (!slot) return null;
    if (slot.mailto) return "mailto:" + slot.mailto;
    return safeUrl(slot.url);
  }

  function oppRow(labelText, slot, actionText) {
    var href = slotHref(slot);
    var dest = slotDestination(slot);
    if (!href || !dest) {
      return '<li class="opp-row is-empty"><span class="opp-label">' + esc(labelText) + '</span><span class="opp-dest slot-empty">待补充</span><span class="opp-action">—</span></li>';
    }
    return '<li class="opp-row"><span class="opp-label">' + esc(labelText) + "</span>" +
      '<span class="opp-dest" title="' + esc(dest) + '">' + esc(dest) + "</span>" +
      '<span class="opp-action"><a href="' + esc(href) + '" target="_blank" rel="noopener noreferrer" title="' + esc(slotStatus(slot)) + '">' + esc(actionText) + ' <span aria-hidden="true">↗</span></a></span></li>';
  }

  function websiteUrl(record) {
    if (record.contacts && record.contacts.website) return record.contacts.website;
    var channel = slotFromChannel(record, "website");
    return channel ? channel.url : null;
  }

  function socialLinks(record) {
    var social = ["linkedin", "x", "github", "jike", "zhihu", "maimai"];
    var seen = {};
    var out = [];
    (record.channels || []).forEach(function (channel) {
      if (channel.layer !== "professional_social" && social.indexOf(channel.platform) === -1) return;
      if (seen[channel.platform]) return;
      seen[channel.platform] = true;
      out.push(link(channel.url, label(L.platforms, channel.platform) || channel.platform, "pill"));
    });
    return out.join("");
  }

  function roleLabel(role) {
    return { lead: "领投", participant: "参与", undisclosed: "角色未披露" }[role] || "角色未披露";
  }

  function roundLabel(value) {
    var text = String(value || "").trim();
    if (!text) return "";
    if (/轮|上市|融资|IPO|首轮/.test(text)) return text;
    return text + "轮";
  }

  function investorsBlock(org) {
    if (org.class !== "startups" && org.class !== "incumbents") return "";
    var record = org.record;
    var rounds = (record.investment || {}).rounds || [];
    var order = [];
    var byFirm = {};
    var byName = {};

    function entryFor(name, firm) {
      if (firm && byFirm[firm]) return byFirm[firm];
      if (byName[name]) {
        var known = byName[name];
        if (!known.firm && firm) {
          known.firm = firm;
          byFirm[firm] = known;
        }
        return known;
      }
      var entry = { name: name, firm: firm || null, seen: {}, rounds: [] };
      if (firm) byFirm[firm] = entry;
      byName[name] = entry;
      order.push(entry);
      return entry;
    }

    rounds.forEach(function (round) {
      if (!round) return;
      var label = roundLabel(round.round);
      (round.investors || []).forEach(function (investor) {
        var name = String((investor && investor.name) || "").trim();
        if (!name) return;
        var entry = entryFor(name, investor.firm_id || null);
        var role = investor.role || "undisclosed";
        var key = label + "|" + role;
        if (entry.seen[key]) return;
        entry.seen[key] = true;
        entry.rounds.push({ label: label, role: role });
      });
    });
    if (!order.length) return "";
    var items = order.map(function (item) {
      var nameHtml = item.firm && BY_ID.has(item.firm)
        ? '<button type="button" class="pi-link" data-open="' + esc(item.firm) + '">' + esc(item.name) + "</button>"
        : '<span class="pi-name">' + esc(item.name) + "</span>";
      var roles = item.rounds.map(function (part) {
        var text = part.label + (part.role === "undisclosed" ? "" : " " + roleLabel(part.role));
        return '<span class="pi-round' + (part.role === "lead" ? " is-lead" : "") + '">' + esc(text) + "</span>";
      }).join("");
      return '<li class="pi-item">' + nameHtml + '<span class="pi-rounds">' + roles + "</span></li>";
    }).join("");
    return '<div class="p-investors" role="group" aria-label="投资方">' +
      '<p class="pi-head">投资方</p><ul class="pi-list">' + items + "</ul>" +
      '<p class="pi-note">按首次披露轮次排序；参与不等于主导。</p></div>';
  }

  function stageText(value) {
    if (!value) return "";
    return shorten(String(value).replace(/\s+/g, " ").replace(/。$/, "").trim(), 24);
  }

  function firstSentence(value, max) {
    var text = String(value == null ? "" : value).replace(/\s+/g, " ").trim();
    var stop = text.search(/[。；]/);
    if (stop > 0) text = text.slice(0, stop + 1);
    return shorten(text, max || 64);
  }

  function fundingText(record) {
    var investment = record.investment;
    if (!investment) return null;
    if (investment.verification_status === "not_applicable") {
      return { text: "内部单元，不适用独立股权融资", title: label(L.funding, investment.verification_status) };
    }
    var rounds = investment.rounds || [];
    if (rounds.length) {
      var sorted = rounds.slice().sort(function (a, b) {
        return String(b.announced_on || "").localeCompare(String(a.announced_on || ""));
      });
      var round = sorted[0];
      var bits = [];
      if (round.round) bits.push(round.round);
      if (round.announced_on) bits.push(round.announced_on);
      if (round.amount_text) bits.push(round.amount_text);
      return {
        text: bits.join(" · "),
        title: label(L.funding, investment.verification_status)
      };
    }
    if (investment.summary) {
      return {
        text: firstSentence(investment.summary, 64),
        title: label(L.funding, investment.verification_status) + "；" + shorten(investment.summary, 140)
      };
    }
    return { text: "融资未公开披露", quiet: true };
  }

  function startupChips(record) {
    var chips = [];
    if (record.locations_text) {
      chips.push('<span class="p-chip" title="' + esc(record.locations_text) + '"><b>地点</b>' + esc(shorten(record.locations_text, 32)) + "</span>");
    } else {
      chips.push('<span class="p-chip is-quiet">地点待补充</span>');
    }
    if (record.founded && record.founded.year != null) {
      chips.push('<span class="p-chip"><b>成立</b>' + esc(record.founded.year) + "</span>");
    } else {
      chips.push('<span class="p-chip is-quiet">成立年份待补充</span>');
    }
    var funding = fundingText(record);
    if (funding) {
      chips.push('<span class="p-chip' + (funding.quiet ? " is-quiet" : "") + '"' +
        (funding.title ? ' title="' + esc(funding.title) + '"' : "") + "><b>融资</b>" + esc(funding.text) + "</span>");
    } else {
      chips.push('<span class="p-chip is-quiet">融资未公开披露</span>');
    }
    chips.push('<span class="p-chip"><b>核查</b>' + esc(record.checked_at) + "</span>");
    return '<div class="p-chips">' + chips.join("") + "</div>";
  }

  function incumbentMeta(record) {
    var items = [];
    items.push({
      label: "地点",
      value: record.locations_text ? shorten(record.locations_text, 58) : "地点待补充",
      quiet: !record.locations_text,
      title: record.locations_text || ""
    });
    var context = record.organizational_context;
    if (context) {
      var bits = [];
      if (context.form) bits.push("形态 " + label(L.forms, context.form));
      if (context.relationship_status) bits.push("关系 " + label(L.relationships, context.relationship_status));
      var parents = (context.parent_platform_ids || []).join("、");
      if (parents) bits.push("母平台 " + parents);
      items.push({
        label: "组织形态",
        value: bits.join(" · ") || "已记录",
        quiet: false,
        title: context.summary ? shorten(context.summary, 140) : ""
      });
    } else {
      items.push({
        label: "组织边界",
        value: "待核",
        quiet: true,
        title: "档案尚未记录 organizational_context；缺省不表示已确认独立或已拆分。"
      });
    }
    items.push({ label: "核查", value: record.checked_at });
    return '<dl class="p-meta">' + items.map(function (item) {
      return '<div><dt>' + esc(item.label) + "</dt><dd" + (item.quiet ? ' class="is-quiet"' : "") +
        (item.title ? ' title="' + esc(item.title) + '"' : "") + ">" + esc(item.value) + "</dd></div>";
    }).join("") + "</dl>";
  }

  function investorCaseNames(record) {
    var cases = record.representative_cases || [];
    var current = [];
    var prior = [];
    var seen = {};
    cases.forEach(function (item) {
      if (!item || !item.company || seen[item.company]) return;
      seen[item.company] = true;
      if (item.attribution === "prior_firm") prior.push(item.company);
      else current.push(item.company);
    });
    var names = current.concat(prior).slice(0, 3);
    return { names: names, label: "代表案例", title: "仅为档案已记录案例，不是完整投资组合" };
  }

  function investorFacts(record) {
    var facts = [];
    if (record.founded && record.founded.year != null) facts.push(record.founded.year + " 年成立");
    if (record.stage) facts.push(stageText(record.stage));
    if (record.coverage && record.coverage.role) facts.push("研究位置 · " + label(L.coverage_roles, record.coverage.role));
    var out = facts.length ? '<div class="p-facts">' + facts.map(function (text) {
      return '<span class="p-fact">' + esc(text) + "</span>";
    }).join("") + "</div>" : '<div class="p-facts"><span class="p-fact">机构资料待补充</span></div>';
    var cases = investorCaseNames(record);
    if (cases.names.length) {
      out += '<div class="p-cases" title="' + esc(cases.title) + '"><span class="p-case-label">' + esc(cases.label) + "</span>" +
        cases.names.map(function (name) { return '<span class="p-case">' + esc(name) + "</span>"; }).join("") + "</div>";
    }
    return out;
  }

  function profileMeta(org) {
    if (org.class === "incumbents") return incumbentMeta(org.record);
    if (org.class === "investors") return investorFacts(org.record);
    return startupChips(org.record);
  }

  function profileKicker(org) {
    var record = org.record;
    var parts = ['<span class="pk-class">' + esc(classMeta(org.class).label) + "</span>"];
    var listed = listedMark(org, "kicker");
    if (listed) parts.push(listed);
    if (org.class !== "investors" && record.category_id) {
      parts.push('<span class="pk-sep" aria-hidden="true"></span>', '<span class="sr-only">，</span>',
        "<span>" + esc(categoryName(record.category_id)) + "</span>");
    }
    return '<p class="p-kicker">' + parts.join("") + "</p>";
  }

  function profileLead(org) {
    var record = org.record;
    if (org.class === "incumbents") {
      var lead = record.products ? shorten(String(record.products).replace(/\s+/g, " ").trim(), 96) : "";
      if (!lead) lead = record.focus ? shorten(record.focus, 96) : "";
      var out = '<div class="p-focus"><p class="p-lead">' + esc(lead || "档案尚未补充业务简介。") + "</p>";
      if (record.focus && record.focus !== lead) out += '<p class="p-aside">研究切面 · ' + esc(record.focus) + "</p>";
      return out + "</div>";
    }
    if (org.class === "investors") {
      return '<div class="p-focus">' + (paragraphs(record.focus) || '<p class="muted">投资方向待补充。</p>') + "</div>";
    }
    return '<div class="p-focus">' + (paragraphs(record.focus) || '<p class="muted">档案尚未补充简介。</p>') + "</div>";
  }

  function unitContext(org) {
    if (org.class !== "incumbents") return "";
    var context = org.record.organizational_context;
    var ids = (context && context.parent_platform_ids) || [];
    if (!ids.length) return "";
    var names = ids.map(function (id) { return parentInfo(id).name; });
    var form = context.form ? label(L.forms, context.form) : "";
    return '<p class="p-parent">所属：' + esc(names.join("、")) + (form ? " · " + esc(form) : "") + "</p>";
  }

  function profileLinks(org) {
    var record = org.record;
    var website = websiteUrl(record);
    var links = [];
    if (org.class === "investors") {
      var contacts = record.contacts || {};
      if (contacts.other_email) {
        var purpose = contacts.other_email_purpose || "";
        var mailLabel = /BP|商业计划/i.test(purpose) ? "BP 邮箱" : "公开邮箱";
        links.push('<a class="pill" href="mailto:' + esc(contacts.other_email) + '" title="' + esc(purpose || "公开邮箱") + '">' +
          esc(mailLabel) + ' <span aria-hidden="true">↗</span></a>');
      }
      if (contacts.recruitment_email) {
        links.push('<a class="pill" href="mailto:' + esc(contacts.recruitment_email) + '">招聘邮箱</a>');
      } else if (contacts.careers_url) {
        links.push(link(contacts.careers_url, "招聘入口", "pill"));
      }
      var investorSocials = socialLinks(record);
      if (investorSocials) links.push(investorSocials);
      if (website) {
        links.push('<a class="pill cta" href="' + esc(safeUrl(website)) + '" target="_blank" rel="noopener noreferrer">访问官网 <span aria-hidden="true">↗</span></a>');
      }
      return '<div class="p-links">' + links.join("") + "</div>";
    }
    var socials = socialLinks(record);
    if (socials) links.push(socials);
    if (website) {
      links.push('<a class="pill cta" href="' + esc(safeUrl(website)) + '" target="_blank" rel="noopener noreferrer">访问官网 <span aria-hidden="true">↗</span></a>');
    }
    return '<div class="p-links">' + links.join("") + "</div>";
  }

  function personPortrait(person) {
    var mark = String(person.name || "").trim().slice(0, 1) || "人";
    var photo = person.photo;
    if (photo && photo.path) {
      return '<span class="person-mono photo"><img src="' + esc(photo.path) + '" alt="" loading="lazy" decoding="async" data-mark="' + esc(mark) + '">' +
        (photo.page_url ? '<a class="person-photo-src" href="' + esc(photo.page_url) + '" target="_blank" rel="noopener noreferrer">图源</a>' : "") + "</span>";
    }
    return '<span class="person-mono" aria-hidden="true">' + esc(mark) + "</span>";
  }

  function secHead(kicker, title, note, titleId) {
    return '<div class="sec-head"><div><p class="sec-kicker">' + esc(kicker) + '</p><h2 id="' + esc(titleId) + '">' + esc(title) + "</h2></div>" +
      '<p class="sec-note">' + esc(note) + "</p></div>";
  }

  function peopleSection(record, variant) {
    var copy = PEOPLE_COPY[variant] || PEOPLE_COPY.startups;
    var people = record.people || [];
    var out = '<section class="p-section" id="d-people" aria-labelledby="people-title">';
    out += secHead(copy.kicker, copy.title, copy.note, "people-title");
    if (!people.length) {
      out += '<div class="people-empty"><div class="pe-head"><span class="pe-mark" aria-hidden="true">待</span><div><h3>' + esc(copy.emptyTitle) + "</h3>" +
        "<p>" + esc(copy.emptyBody) + "</p></div></div>";
      out += '<div class="people-grid reserved">' + [
        ["01", "姓名与职务"], ["02", "公开履历"], ["03", "公开主页"]
      ].map(function (item) {
        return '<article class="person-card reserved"><span class="reserved-no">' + esc(item[0]) + '</span><span class="reserved-label">' + esc(item[1]) + '</span><span class="reserved-value">待补充</span></article>';
      }).join("") + "</div>";
      out += '<p class="section-note">待 find-person 补充；缺失不表示机构没有关键人物。</p></div>';
      out += "</section>";
      return out;
    }
    out += '<div class="people-grid">';
    people.forEach(function (person) {
      out += '<article class="person-card"><div class="person-top">' + personPortrait(person) + '<div class="person-id">' +
        '<h3 class="person-name">' + esc(person.name) + "</h3>" +
        (person.role ? '<p class="person-role">' + esc(person.role) + "</p>" : "") + "</div></div>";
      if (person.background) out += '<p class="person-bg">' + esc(person.background) + "</p>";
      if ((person.previous_firms || []).length) {
        var previous = variant === "startups" ? "出身：" : "原平台 ";
        out += '<p class="person-prev">' + previous + esc(person.previous_firms.join("、")) + "</p>";
      }
      var profiles = (person.profiles || []).map(function (profile) {
        return link(profile.url, label(L.profile_platforms, profile.platform) || profile.platform, "");
      });
      out += '<div class="person-links">' + (profiles.length ? profiles.join("") : '<span class="muted">未记录公开个人主页</span>') + "</div>";
      out += '<p class="person-verify">' + esc(label(L.verification, person.verification_status)) + " · 核查 " + esc(person.checked_at) + " · 来源 " + sourceLinks(record, person.source_ids) + "</p>";
      if (person.notes) out += '<p class="person-verify">' + esc(person.notes) + "</p>";
      out += "</article>";
    });
    out += "</div>";
    out += '<p class="section-note">人物身份与主页分别核验；迁移资料不自动等于当前职务已重新核实。</p>';
    out += "</section>";
    return out;
  }

  function opportunitiesSection(record, variant) {
    var copy = OPP_COPY[variant] || OPP_COPY.startups;
    var resolved = resolveSlots(record);
    var slots = resolved.slots;
    var out = '<section class="p-section" id="d-opportunities" aria-labelledby="opp-title">';
    out += secHead(copy.kicker, copy.title, copy.note, "opp-title");
    var items = copy.order.map(function (key) { return CHANNEL_BY_KEY.get(key); }).filter(function (item) {
      if (!item) return false;
      if (item.key === "other_email" && !slots.other_email) return variant === "investors";
      return true;
    });
    out += '<ol class="opp-list">' + items.map(function (item) {
      var labelText = item.label;
      if (variant === "investors" && item.key === "other_email") labelText = "BP / 商务邮箱";
      return oppRow(labelText, slots[item.key], item.action);
    }).join("") + "</ol>";
    var extras = (record.channels || []).filter(function (channel) { return !resolved.used[channel.id]; });
    if (extras.length) {
      out += '<div class="opp-extra"><h3>其他公开入口</h3><ol class="opp-list">';
      extras.forEach(function (channel) {
        var headline = label(L.platforms, channel.platform) + " · " + label(L.purposes, channel.purpose);
        out += oppRow(headline, { url: channel.url, status: channel.verification_status, checked_at: channel.checked_at }, "打开");
      });
      out += "</ol></div>";
    }
    out += "</section>";
    return out;
  }

  function orgContextBlock(record) {
    var context = record.organizational_context;
    if (!context) {
      return '<div class="p-sub"><h3>组织边界</h3><p class="section-note">组织边界待核：档案尚未记录 organizational_context；缺省不表示已确认独立或已拆分。</p></div>';
    }
    var parents = (context.parent_platform_ids || []).join("、");
    return '<div class="p-sub"><h3>组织边界</h3>' +
      '<p class="kv"><span>形态</span>' + esc(label(L.forms, context.form)) + "</p>" +
      '<p class="kv"><span>关系</span>' + esc(label(L.relationships, context.relationship_status)) + "</p>" +
      '<p class="kv"><span>母平台</span>' + esc(parents || "未记录") + "</p>" +
      paragraphs(context.summary) +
      '<p class="source-line">核查 ' + esc(context.checked_at) + "；依据 " + sourceLinks(record, context.source_ids) + "</p></div>";
  }

  function businessSection(record) {
    var out = '<section class="p-section" id="d-business" aria-labelledby="business-title">';
    out += secHead("业务与产品 · find-incumbents", "业务与产品", "平台 / 业务单元口径，不是创业公司简介", "business-title");
    out += '<div class="body-prose">' + (paragraphs(record.products) || paragraphs(record.focus) || '<p class="muted">业务描述待补充。</p>') + "</div>";
    out += orgContextBlock(record);
    out += '<p class="section-note">业务事实来源 ' + allSourcesButton(record) + "</p>";
    out += "</section>";
    return out;
  }

  function casesBlock(record, title) {
    var cases = record.representative_cases || [];
    if (!cases.length) {
      return '<div class="p-sub"><h3>' + esc(title) + '</h3><p class="section-note">本轮未收录足够证据支持的案例；不表示确定没有投资。</p></div>';
    }
    var current = cases.filter(function (item) { return item.attribution !== "prior_firm"; });
    var prior = cases.filter(function (item) { return item.attribution === "prior_firm"; });
    var ordered = current.concat(prior);
    return '<div class="p-sub"><h3>' + esc(title) + "（" + ordered.length + "）</h3><ul class=\"case-list\">" +
      ordered.map(function (item) {
        var meta = [item.investor_or_team, item.attribution === "prior_firm" ? "原平台" : ""].filter(Boolean).join(" · ");
        return '<li><div class="case-top"><strong>' + esc(item.company) + '</strong><span class="case-meta">' + esc(meta) + "</span></div>" +
          (item.outcome ? '<p class="case-note">' + esc(item.outcome) + "</p>" : "") +
          '<p class="case-src">' + sourceLinks(record, item.evidence_source_ids) + "</p></li>";
      }).join("") + "</ul></div>";
  }

  function investmentSection(record) {
    var out = '<section class="p-section" id="d-investment" aria-labelledby="investment-title">';
    out += secHead("find-investors", "投资方向与阶段", "案例仅为有出处的历史披露；参与不等于主导", "investment-title");
    out += '<div class="body-prose">' + (paragraphs(record.focus) || '<p class="muted">投资方向待补充。</p>') + "</div>";
    out += '<p class="kv"><span>阶段</span>' + esc(record.stage || "未记录") + "</p>";
    var coverage = record.coverage || {};
    out += '<p class="kv"><span>研究位置</span>' + esc(label(L.coverage_roles, coverage.role) || "未记录") +
      "；" + esc(coverage.reason || "范围未记录") + "</p>";
    out += casesBlock(record, "代表案例");
    if (record.recent_activity) out += '<p class="kv"><span>近期活动</span>' + esc(record.recent_activity) + "</p>";
    out += '<p class="section-note">代表案例为档案已记录条目，不是完整投资组合；上市案例不据此推断已退出或回报。</p>';
    out += "</section>";
    return out;
  }

  function aSection(title, body) {
    return '<section class="a-section"><h3>' + esc(title) + "</h3>" + body + "</section>";
  }

  function regionalSection(record) {
    var notes = record.regional_notes || [];
    if (!notes.length) return "";
    var body = "";
    notes.forEach(function (note) {
      body += '<details class="regional"><summary><span>' + esc(note.region) + "</span><span>核查 " + esc(note.checked_at) + "</span></summary>" +
        paragraphs(note.summary) +
        '<p class="source-line">依据 ' + sourceLinks(record, note.source_ids) + "</p></details>";
    });
    body += '<p class="section-note">地区资料独立标注日期，不自动刷新公司整体业务事实。</p>';
    return aSection("地区研究与历史线索", body);
  }

  function sourcesSection(record) {
    var sources = record.sources || [];
    var body = '<p class="section-note">来源按档案维护；公开日期未知时保留“未标明”，整理不会刷新核查日期。</p><ol class="source-list">';
    body += sources.map(function (source) {
      var safe = safeUrl(source.url);
      var title = safe ? link(safe, source.title || source.url, "source-title") : '<span class="source-title">' + esc(source.title || source.url) + "</span>";
      return '<li class="source-item"><div class="source-top"><span class="source-id">' + esc(source.id) + "</span>" + title + "</div>" +
        '<p class="source-supports">' + esc(source.supports) + "</p>" +
        '<p class="source-meta">公开日期 ' + esc(source.published_date || "未标明") + "，核查 " + esc(source.checked_at) + "，范围 " + esc(label(L.source_scope, source.scope || "organization")) + "</p></li>";
    }).join("");
    body += "</ol>";
    return aSection("证据与来源", body);
  }

  function relFromViews(path) {
    if (!path) return "#";
    return path.replace(/^data\/views\//, "").replace(/^data\//, "../");
  }

  function comparisonSection(record) {
    if (!record.comparison) return "";
    return aSection("同类区别", paragraphs(record.comparison.summary) +
      '<p class="kv"><span>比较对象</span>' + esc((record.comparison.peer_names || []).join("、") || "未记录") + "</p>" +
      '<p class="source-line">产品定位分析，非性能排名。' + allSourcesButton(record) + "</p>");
  }

  function investmentBackground(record, title) {
    if (!record.investment) return "";
    return aSection(title || "投资背景", paragraphs(record.investment.summary) +
      '<p class="kv"><span>披露状态</span>' + esc(label(L.funding, record.investment.verification_status)) + "</p>" +
      '<p class="source-line">历史披露不表示完整现股东名册。' + allSourcesButton(record) + "</p>");
  }

  function orgBoundarySection(record) {
    var context = record.organizational_context;
    if (!context) return "";
    return aSection("组织边界",
      '<p class="kv"><span>形态</span>' + esc(label(L.forms, context.form)) + "</p>" +
      '<p class="kv"><span>关系</span>' + esc(label(L.relationships, context.relationship_status)) + "</p>" +
      '<p class="kv"><span>母平台</span>' + esc((context.parent_platform_ids || []).join("、") || "未记录") + "</p>" +
      paragraphs(context.summary) +
      '<p class="source-line">核查 ' + esc(context.checked_at) + "；依据 " + sourceLinks(record, context.source_ids) + "</p>");
  }

  function appendixHtml(org) {
    var record = org.record;
    var cls = org.class;
    var out = '<section class="appendix" id="d-appendix" aria-labelledby="appendix-title">' +
      '<div class="appendix-head"><span>档案附录</span><h2 id="appendix-title">附录</h2></div>';
    if (cls === "investors") {
      out += aSection("研究判断", paragraphs(record.why_follow) + paragraphs(record.difference));
    } else if (cls === "incumbents") {
      out += comparisonSection(record);
    } else {
      out += aSection("业务与产品", paragraphs(record.products) + '<p class="source-line">业务事实来源 ' + allSourcesButton(record) + "</p>");
      out += comparisonSection(record);
      out += orgBoundarySection(record);
      out += investmentBackground(record, "投资背景");
    }
    out += regionalSection(record);
    if (cls === "incumbents") out += investmentBackground(record, "资本背景");
    if (record.notes) out += aSection("核查备注", paragraphs(record.notes));
    out += sourcesSection(record);
    out += '<div class="detail-actions">' +
      '<button type="button" class="btn ghost" data-copy-json="' + esc(record.id) + '">复制 JSON</button>' +
      '<a class="btn ghost" href="' + esc(relFromViews(org.index.json_path)) + '" target="_blank" rel="noopener noreferrer">原始 JSON</a>' +
      '<a class="btn ghost" href="' + esc(relFromViews(org.index.markdown_path)) + '" target="_blank" rel="noopener noreferrer">阅读版</a>' +
      '<button type="button" class="btn ghost" data-copy-link="1">复制看板链接</button>' +
      '<p class="detail-path"><code>' + esc(org.index.json_path) + "</code></p>" +
      "</div>";
    out += "</section>";
    return out;
  }

  function profileIntroHtml(org) {
    var record = org.record;
    var aliases = (record.aliases || []).filter(Boolean);
    var out = profileKicker(org);
    out += '<div class="p-brand">' + logoHtml(org, "xl") +
      '<div class="p-id"><h1 class="p-name" id="profile-title" tabindex="-1">' + esc(record.name) + "</h1>" +
      '<p class="p-alias">' + (aliases.length ? "别名 " + esc(aliases.join("、")) : "ID " + esc(record.id)) + "</p></div></div>";
    out += unitContext(org);
    out += profileLead(org);
    out += profileLinks(org);
    out += profileMeta(org);
    out += investorsBlock(org);
    return out;
  }

  function profileBodyHtml(org) {
    var record = org.record;
    if (org.class === "investors") {
      return investmentSection(record) + peopleSection(record, "investors") + opportunitiesSection(record, "investors") + appendixHtml(org);
    }
    if (org.class === "incumbents") {
      return businessSection(record) + peopleSection(record, "incumbents") + opportunitiesSection(record, "incumbents") + appendixHtml(org);
    }
    return peopleSection(record, "startups") + opportunitiesSection(record, "startups") + appendixHtml(org);
  }

  function writeHash() {
    var params = new URLSearchParams();
    if (state.q) params.set("q", state.q);
    if (state.cls !== "startups") params.set("class", state.cls);
    if (state.category !== "all") params.set("cat", state.category);
    if (state.city !== "all") params.set("city", state.city);
    if (state.channels) params.set("ch", "1");
    if (state.people) params.set("ppl", "1");
    if (state.sort !== "category") params.set("sort", state.sort);
    if (state.org) params.set("org", state.org);
    var hash = params.toString();
    var base = location.href.split("#")[0];
    try { history.replaceState(null, "", base + (hash ? "#" + hash : "")); }
    catch (error) { if (hash) location.hash = hash; }
  }

  function readHash() {
    var params = new URLSearchParams(location.hash.replace(/^#/, ""));
    var cls = params.get("class");
    var category = params.get("cat");
    var city = params.get("city");
    var sort = params.get("sort");
    var org = params.get("org");
    state.q = params.get("q") || "";
    state.cls = CLASS_BY_ID.has(cls) ? cls : "startups";
    if (org && BY_ID.has(org)) state.cls = BY_ID.get(org).class;
    var known = state.cls === "investors" ? MATURITY_ORDER.indexOf(category) !== -1 : CAT_BY_ID.has(category);
    state.category = known ? category : "all";
    state.city = (DATA.city_names || []).indexOf(city) !== -1 ? city : "all";
    state.channels = params.get("ch") === "1";
    state.people = params.get("ppl") === "1";
    state.sort = SORTS.indexOf(sort) !== -1 ? sort : "category";
    state.org = BY_ID.has(org) ? org : null;
  }

  function jumpTo(y) {
    try { window.scrollTo({ top: y || 0, left: 0, behavior: "instant" }); }
    catch (error) { window.scrollTo(0, y || 0); }
  }

  function restart(el) {
    if (!el) return;
    el.classList.remove("view-enter");
    void el.offsetWidth;
    el.classList.add("view-enter");
  }

  function openProfile(id, options) {
    var org = BY_ID.get(id);
    if (!org) return null;
    if (!state.org) homeScroll = window.scrollY || 0;
    state.org = id;
    profileHero.className = "p-hero " + (CLASS_HOOKS[org.class] || "is-unresolved");
    profileHero.setAttribute("data-class", org.class);
    setFieldMotif(profileField, org.class);
    profileCrumb.innerHTML = "<b>" + esc(org.record.name) + "</b> · " + esc(classMeta(org.class).label);
    profileIntro.innerHTML = profileIntroHtml(org);
    profileBody.innerHTML = profileBodyHtml(org);
    syncLogoAspects(profileIntro);
    document.body.classList.add("profile-open");
    homeView.setAttribute("aria-hidden", "true");
    if (!(options && options.write === false)) writeHash();
    jumpTo(0);
    restart(profileView);
    if (options && options.focus) {
      var title = document.getElementById("profile-title");
      if (title) title.focus({ preventScroll: true });
    }
    liveEl.textContent = "已打开 " + org.record.name + " 的档案";
    return org;
  }

  function showHome(focusPrev) {
    var previous = typeof focusPrev === "string" ? focusPrev : null;
    document.body.classList.remove("profile-open");
    homeView.removeAttribute("aria-hidden");
    profileHero.className = "p-hero";
    profileHero.setAttribute("data-class", "");
    profileIntro.innerHTML = "";
    profileBody.innerHTML = "";
    profileCrumb.textContent = "";
    jumpTo(homeScroll || 0);
    restart(homeView);
    if (previous) {
      var row = document.querySelector('.org-row[data-open="' + previous + '"]');
      if (row) row.focus({ preventScroll: true });
    }
  }

  function closeProfile() {
    var previous = state.org;
    state.org = null;
    writeHash();
    showHome(previous);
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
    state.sort = "category";
    writeHash();
    renderClass();
    renderHome();
  }

  function resetFilters() {
    state.q = "";
    state.category = "all";
    state.city = "all";
    state.channels = false;
    state.people = false;
    state.sort = "category";
    writeHash();
    renderHome();
  }

  function pickCategory(value) {
    state.category = value;
    writeHash();
    renderHome();
  }

  qEl.addEventListener("input", function () {
    state.q = qEl.value;
    writeHash();
    renderHome();
  });

  [categoryEl, cityEl, sortEl].forEach(function (element) {
    element.addEventListener("change", function () {
      state.category = categoryEl.value;
      state.city = cityEl.value;
      state.sort = sortEl.value;
      writeHash();
      renderHome();
    });
  });

  channelsEl.addEventListener("change", function () {
    state.channels = channelsEl.checked;
    writeHash();
    renderHome();
  });

  peopleEl.addEventListener("change", function () {
    state.people = peopleEl.checked;
    writeHash();
    renderHome();
  });

  document.getElementById("reset").addEventListener("click", resetFilters);

  document.addEventListener("click", function (event) {
    var target = event.target;

    var back = target.closest("[data-back]");
    if (back) { closeProfile(); return; }

    var classButton = target.closest(".class-tab[data-class]");
    if (classButton) {
      setClass(classButton.dataset.class, { force: true });
      return;
    }

    var card = target.closest(".sector-card[data-category]");
    if (card) {
      pickCategory(state.category === card.dataset.category ? "all" : card.dataset.category);
      return;
    }

    var sector = target.closest("[data-category-set]");
    if (sector) {
      pickCategory(sector.dataset.categorySet);
      return;
    }

    var clear = target.closest("[data-clear]");
    if (clear) { resetFilters(); return; }

    var open = target.closest("[data-open]");
    if (open) {
      openProfile(open.dataset.open, { focus: event.detail === 0 });
      return;
    }

    var copyJson = target.closest("[data-copy-json]");
    if (copyJson) {
      var org = BY_ID.get(copyJson.dataset.copyJson);
      if (org) copyText(JSON.stringify(org.record, null, 2), "已复制 " + org.record.id + ".json");
      return;
    }

    var copyLink = target.closest("[data-copy-link]");
    if (copyLink) { copyText(location.href, "已复制当前看板链接"); return; }

    var jumpSources = target.closest("[data-scroll-sources]");
    if (jumpSources) {
      var sources = document.getElementById("d-sources");
      if (sources) sources.scrollIntoView({ block: "start" });
      return;
    }

    var jump = target.closest("[data-scroll]");
    if (jump) {
      event.preventDefault();
      var section = document.getElementById(jump.dataset.scroll);
      if (section) {
        section.scrollIntoView({ block: "start" });
        section.setAttribute("tabindex", "-1");
        section.focus({ preventScroll: true });
      }
    }
  });

  window.addEventListener("hashchange", function () {
    readHash();
    renderClass();
    renderHome();
    if (state.org) openProfile(state.org, { write: false });
    else showHome(null);
  });

  document.addEventListener("keydown", function (event) {
    var target = event.target;
    var typing = /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName) || target.isContentEditable;
    if (event.key === "/" && !typing && !event.metaKey && !event.ctrlKey && !event.altKey) {
      event.preventDefault();
      qEl.focus();
    }
    if (event.key === "Escape") {
      if (state.org) closeProfile();
      else if (document.activeElement === qEl) qEl.blur();
    }
  });

  /* ---------- scroll choreography ---------- */
  function setupChrome() {
    if (!headerEl) return;
    var syncNavHeight = function () {
      var h = headerEl.offsetHeight;
      if (h > 0) document.documentElement.style.setProperty("--nav-h", h + "px");
    };
    syncNavHeight();
    window.addEventListener("resize", syncNavHeight);
    if (!("IntersectionObserver" in window) || !heroEl) return;
    new IntersectionObserver(function (entries) {
      headerEl.classList.toggle("solid", !entries[0].isIntersecting);
    }, { rootMargin: "-72px 0px 0px 0px", threshold: 0 }).observe(heroEl);
  }

  function setupHeroScroll() {
    if (!heroEl || !heroInner) return;
    var reduced = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)").matches : false;
    if (reduced || !("IntersectionObserver" in window)) return;
    var heroHeight = heroEl.offsetHeight || 1;
    var queued = false;
    var measure = function () { heroHeight = heroEl.offsetHeight || 1; };
    window.addEventListener("resize", measure);
    var apply = function () {
      queued = false;
      var y = window.scrollY || window.pageYOffset || 0;
      var p = Math.min(1, Math.max(0, y / (heroHeight * 0.78)));
      document.documentElement.style.setProperty("--hp", p.toFixed(3));
    };
    var onScroll = function () {
      if (queued) return;
      queued = true;
      window.requestAnimationFrame(apply);
    };
    new IntersectionObserver(function (entries) {
      if (entries[0].isIntersecting) {
        measure();
        window.addEventListener("scroll", onScroll, { passive: true });
        onScroll();
      } else {
        window.removeEventListener("scroll", onScroll);
      }
    }, { threshold: 0 }).observe(heroEl);
  }

  function setupReveals() {
    var items = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) {
      items.forEach(function (el) { el.classList.add("in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("in");
        io.unobserve(entry.target);
      });
    }, { threshold: 0, rootMargin: "0px 0px -8% 0px" });
    items.forEach(function (el) { io.observe(el); });
  }

  heroField = initField(document.getElementById("hero-canvas"), { accent: "185,135,79", max: 110, motif: "stars" });
  profileField = initField(document.getElementById("profile-canvas"), { accent: "127,174,154", max: 80, motif: "stars" });
  setupChrome();
  setupHeroScroll();
  setupReveals();

  readHash();
  renderClass();
  renderHome();
  if (state.org) openProfile(state.org, { write: false });
})();
</script>
</body>
</html>
'''
