"""Shared validation for sourced public organization records; never fetches or invents evidence."""
import json
from functools import lru_cache
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
ID_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
ENTITY_FOLDERS = {"operating_organization": "companies", "investment_firm": "companies"}
PLATFORMS = {
  "boss_zhipin": ("zhipin.com", ("/gongsi/", "/gongsir/", "/companys/")),
  "liepin": ("liepin.com", ("/company/",)),
  "maimai": ("maimai.cn", ("/ent/",)),
}
LAYER_NAMES = {"official": "Layer 1 官方", "recruitment_platform": "Layer 2 招聘平台", "professional_social": "Layer 3 专业社交"}


def normalized_organization_name(value):
  return ''.join(c for c in unicodedata.normalize('NFKC', value or '').casefold() if c.isalnum())


def today():
  return datetime.now(timezone(timedelta(hours=8))).date()


def load(path):
  return json.loads(Path(path).read_text(encoding="utf-8"))


@lru_cache(maxsize=64)
def schema_validator(name, root=ROOT):
  from jsonschema import Draft202012Validator, FormatChecker
  from referencing import Registry, Resource
  root = Path(root)
  registry = Registry()
  for path in (root / "data" / "schemas").glob("*.schema.json"):
    schema = load(path)
    Draft202012Validator.check_schema(schema)
    if "$id" in schema:
      registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
  return Draft202012Validator(load(root / "data" / "schemas" / name), registry=registry, format_checker=FormatChecker())


def reject_placeholders(value, path="record"):
  if isinstance(value, dict):
    if value.get("draft") is True:
      raise ValueError(path + ": draft material cannot enter canonical data")
    for key, child in value.items():
      reject_placeholders(child, path + "." + key)
  elif isinstance(value, list):
    for i, child in enumerate(value):
      reject_placeholders(child, path + "[%d]" % i)
  elif isinstance(value, str):
    if re.match(r"^(?:TODO\b|TBD\b|PLACEHOLDER\b|待填写)", value.strip(), re.I):
      raise ValueError(path + ": unfinished placeholder")
    if value.startswith(("https://", "http://")):
      host = (urlsplit(value).hostname or "").lower()
      if host in {"example.com", "example.org", "example.net", "localhost"} or host.endswith((".example.com", ".example.org", ".example.net", ".invalid", ".test")):
        raise ValueError(path + ": placeholder/local source URL")


def platform_url(url, platform):
  if platform not in PLATFORMS:
    raise ValueError("Unsupported recruitment platform")
  parsed = urlsplit(url)
  host = (parsed.hostname or "").lower()
  domain, paths = PLATFORMS[platform]
  if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
    raise ValueError("Use an HTTPS public company-profile URL without credentials")
  if not (host == domain or host.endswith("." + domain)) or not parsed.path.startswith(paths):
    raise ValueError("URL is not a recognized company profile on the declared platform")
  if not any(parsed.path[len(prefix):].strip("/") for prefix in paths if parsed.path.startswith(prefix)):
    raise ValueError("Company profile URL needs a specific organization ID")
  if any(part in {".", ".."} for part in unquote(parsed.path).split("/")):
    raise ValueError("Invalid company-profile path")
  # Strip tracking/session query parameters from stable public profile URLs.
  return urlunsplit(("https", host, parsed.path, "", ""))


def record_path(root, entity_type, entity_id):
  root = Path(root).resolve()
  if entity_type not in ENTITY_FOLDERS or not ID_PATTERN.fullmatch(entity_id):
    raise ValueError("Unknown organization type or invalid stable ID")
  from company_routes import redirects
  target_id = redirects(root).get(entity_id)
  if target_id:
    raise ValueError("Retired regional organization ID; use canonical company ID: " + target_id)
  folder = root / "data" / ENTITY_FOLDERS[entity_type]
  target = folder / (entity_id + ".json")
  if folder.is_symlink() or target.is_symlink() or target.resolve().parent != folder.resolve() or root not in folder.resolve().parents or folder.resolve() != folder:
    raise ValueError("Organization record path escapes the canonical data directory")
  return target


def validate_record(record, root=ROOT):
  kind = record.get("organization_type")
  if kind not in ENTITY_FOLDERS:
    raise ValueError("Missing or unknown organization_type")
  name = "company.schema.json" if kind == "operating_organization" else "investor.schema.json"
  errors = sorted(schema_validator(name, root).iter_errors(record), key=lambda e: str(list(e.path)))
  if errors:
    raise ValueError(record.get("id", "record") + ": " + "; ".join(str(list(e.path)) + " " + e.message for e in errors))
  reject_placeholders(record)
  latest = today()
  if date.fromisoformat(record["checked_at"]) > latest:
    raise ValueError("Business-profile verification date is in the future")
  sources = {s["id"]: s for s in record["sources"]}
  if len(sources) != len(record["sources"]):
    raise ValueError("Duplicate source IDs")
  regional_source_ids = set()
  for note in record.get("regional_notes", []):
    refs = set(note["source_ids"])
    if not refs <= sources.keys() or any(sources[s].get("scope", "organization") != "organization" for s in refs):
      raise ValueError("Regional research requires organization evidence in the same company")
    checked = date.fromisoformat(note["checked_at"])
    if checked > latest or checked > max(date.fromisoformat(sources[s]["checked_at"]) for s in refs):
      raise ValueError("Regional research date lacks matching evidence")
    regional_source_ids.update(refs)
  targeting = record["targeting"]
  if not set(targeting["source_ids"]) <= sources.keys() or date.fromisoformat(targeting["labelled_at"]) > latest:
    raise ValueError("Invalid editorial targeting evidence/date")
  if any(sources[s].get("scope", "organization") != "organization" for s in targeting["source_ids"]):
    raise ValueError("Channel-only evidence cannot establish the organization's target classification")
  for case in record.get("representative_cases", []):
    refs = set(case["evidence_source_ids"])
    if not refs <= sources.keys() or any(sources[s].get("scope", "organization") != "organization" for s in refs):
      raise ValueError("Investment cases require organization evidence, not channel-only sources")
  tier = record.get("tier")
  if tier:
    refs = set(tier["source_ids"])
    if not refs <= sources.keys() or any(sources[s].get("scope", "organization") != "organization" for s in refs):
      raise ValueError("Tier labels require organization evidence, not channel-only sources")
    if date.fromisoformat(tier["labelled_at"]) > latest:
      raise ValueError("Tier label date is in the future")
  for funding_round in record.get("investment", {}).get("rounds", []):
    refs = set(funding_round["source_ids"])
    for investor in funding_round["investors"]:
      refs.update(investor["source_ids"])
      if investor["firm_id"]:
        target = load(record_path(root, "investment_firm", investor["firm_id"]))
        if target["id"] != investor["firm_id"]:
          raise ValueError("Round investor firm_id must reference an investment-firm profile")
    if not refs <= sources.keys() or any(sources[s].get("scope", "organization") != "organization" for s in refs):
      raise ValueError("Funding rounds require organization evidence")
  context = record.get("organizational_context")
  if record.get("investment", {}).get("verification_status") == "not_applicable":
    if not context or context["form"] not in {"internal_team", "research_lab", "product_project"} or context["relationship_status"] != "confirmed":
      raise ValueError("Non-applicable equity finance requires an evidenced internal unit, lab or project")
  if context:
    refs = set(context["source_ids"])
    if not refs <= sources.keys() or any(sources[s].get("scope", "organization") != "organization" for s in refs):
      raise ValueError("Organization form and parent relationships require organization evidence")
    context_date = date.fromisoformat(context["checked_at"])
    if context_date > latest or context_date > date.fromisoformat(record["checked_at"]) or any(context_date > date.fromisoformat(sources[s]["checked_at"]) for s in refs):
      raise ValueError("Organization relationship date lacks matching business evidence")
    if context["form"] in {"corporate_spinout", "corporate_subsidiary", "internal_team", "research_lab", "product_project"} and not context["parent_platform_ids"]:
      raise ValueError("Corporate units and projects need an identified parent platform")
    platform_ids = {p["id"] for p in load(Path(root) / "data/lists/incumbents.json")["platforms"]}
    if not set(context["parent_platform_ids"]) <= platform_ids:
      raise ValueError("Unknown parent platform; add an evidenced discovery seed first")
  if targeting["wave"] == "first" and targeting["player_group"] != "new_entrant":
    raise ValueError("First wave must be an editorial new-entrant candidate")
  if targeting["player_group"] == "incumbent" and targeting["wave"] != "later":
    raise ValueError("Incumbents belong to the later register")
  if targeting["player_group"] == "unresolved" and targeting["wave"] != "watchlist":
    raise ValueError("Unresolved player groups must remain on the watchlist")
  channel_ids = set()
  channel_keys = set()
  channel_source_ids = set()
  for channel in record["channels"]:
    if channel["owner"]["scope"] != "organization":
      raise ValueError("channels stores institution channels only; use people for personal profiles")
    known_names = {normalized_organization_name(n) for n in [record['name'], *record['aliases']]}
    if channel['verification_status'] == 'confirmed' and normalized_organization_name(channel['owner']['name']) not in known_names:
      raise ValueError("Confirmed channel owner must match the target or an evidenced identity alias; related/group channels remain partial")
    if channel['verification_status'] == 'partial' and not channel.get('notes'):
      raise ValueError("Partial channels need a note explaining the ownership or access gap")
    key = (channel["platform"], channel["url"], channel["owner"]["scope"])
    if channel["id"] in channel_ids or key in channel_keys:
      raise ValueError("Duplicate public channel")
    channel_ids.add(channel["id"]); channel_keys.add(key)
    refs = set(channel["source_ids"])
    historical_refs = set(channel.get('historical_source_ids', []))
    if not (refs | historical_refs) <= sources.keys():
      raise ValueError("Channel refers to missing evidence")
    if refs & historical_refs:
      raise ValueError("Channel current and historical evidence must be separate")
    if any(sources[s].get('scope') == 'person' for s in refs | historical_refs):
      raise ValueError("Person evidence cannot establish an organization channel")
    checked = date.fromisoformat(channel["checked_at"])
    if checked > latest or any(checked > date.fromisoformat(sources[s]["checked_at"]) for s in refs):
      raise ValueError("Channel check lacks evidence at the claimed date")
    channel_source_ids.update(refs | historical_refs)
    if channel["layer"] == "recruitment_platform":
      platform_url(channel["url"], channel["platform"])
      if channel["owner"]["scope"] != "organization" or channel["purpose"] != "recruitment":
        raise ValueError("Layer 2 stores public organization recruiting profiles, not private people")
    elif channel["platform"] in PLATFORMS:
      raise ValueError("Recruitment platforms cannot be counted as official/social channels")
  from person_checks import validate_person_evidence, person_profile_url
  person_source_ids = set()
  person_names = set()
  profile_owners = {}
  for person in record.get("people", []):
    normalized_name = ''.join(person["name"].casefold().split())
    if not normalized_name or normalized_name in person_names:
      raise ValueError("Duplicate person identity; update the existing people record")
    person_names.add(normalized_name)
    person_source_ids.update(validate_person_evidence(person, sources, latest))
    for profile in person["profiles"]:
      key = (profile["platform"], person_profile_url(profile["url"], profile["platform"]))
      if key in profile_owners and profile_owners[key] != normalized_name:
        raise ValueError("A personal profile cannot belong to multiple people in one company")
      profile_owners[key] = normalized_name
  for sid, source in sources.items():
    checked = date.fromisoformat(source["checked_at"])
    if checked > latest:
      raise ValueError("Future source check")
    published = source["published_date"]
    if published:
      published_day = date.fromisoformat(published + ("-01-01" if len(published) == 4 else "-01" if len(published) == 7 else ""))
      if published_day > checked:
        raise ValueError("Publication is after the claimed source check")
    if source.get("scope", "organization") == "channel":
      if sid not in channel_source_ids:
        raise ValueError("Channel-only source is not attached to a channel")
    elif source.get("scope") == "person":
      if sid not in person_source_ids:
        raise ValueError("Person-only source is not attached to a person or profile")
    elif sid not in regional_source_ids and checked > date.fromisoformat(record["checked_at"]):
      raise ValueError("Organization source is newer than the business-profile check")
  return record


def people_markdown(record):
  people = record.get("people", [])
  if not people:
    return ""
  def md(text):
    return str(text).replace("|", "\\|").replace("\n", " ")
  out = "## 核心人物与公开主页\n\n人物身份、职务和履历独立标记核验状态；迁移不代表重新核查现职。\n\n| 姓名 | 角色／职务 | 背景概要／原平台 | 身份核验／来源 | 公开主页 | 说明 |\n| --- | --- | --- | --- | --- | --- |\n"
  for p in people:
    links = " · ".join(
      f"[{prof['platform']}]({prof['url']}) ({prof['verification_status']}, {','.join(prof['source_ids'])})"
      for prof in p.get("profiles", [])
    ) or "暂未收录公开主页"
    out += "| %s | %s | %s | %s | %s | %s |\n" % (
      md(p["name"]), md(p.get("role") or "未标明"),
      md((p.get("background") or "未标明") + ("；原平台：" + "、".join(p.get("previous_firms", [])) if p.get("previous_firms") else "")),
      md(p["verification_status"] + " / " + p["checked_at"] + " / " + ','.join(p["source_ids"])),
      links, md(p.get("notes") or ""),
    )
  return out + "\n"


def channel_markdown(record):
  channels = record.get("channels", [])
  if not channels:
    base = "## 结构化公开渠道\n\n当前档案尚无结构化机构渠道；上方旧入口及来源引用不等于入口归属已核实。未收录不表示没有相关渠道，按任务继续核查。\n\n"
    return base + people_markdown(record)
  def md(text):
    return str(text).replace("|", "\\|").replace("\n", " ")
  out = "## 结构化公开渠道\n\n| 类别 | 平台与用途 | 公开链接 | 归属 | 核查日期 | 状态／来源 |\n| --- | --- | --- | --- | --- | --- |\n"
  for c in channels:
    owner = (c['owner']['name'] or c['owner']['scope']) + ('；' + c['owner']['role'] if c['owner'].get('role') else '')
    status = c['verification_status'] + ' / ' + ','.join(c['source_ids']) + ('；' + c['notes'] if c.get('notes') else '')
    if c.get('historical_source_ids'):
      status += '；历史依据（不作当前归属证明）：' + ','.join(c['historical_source_ids'])
    out += "| %s | %s / %s | [入口](%s) | %s | %s | %s |\n" % tuple(map(md, [LAYER_NAMES[c['layer']],c['platform'],c['purpose'],c['url'],owner,c['checked_at'],status]))
  return out + "\n核验的是公开入口与主体归属，不表示岗位仍开放，也不授权发送或投递。\n\n" + people_markdown(record)
