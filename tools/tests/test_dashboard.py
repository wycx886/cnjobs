"""Keep the self-contained dashboard generated, complete and inside the public boundary."""
import json
import re
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build

PRIVATE_MARKERS = (
    "/Users/", "/home/", "workspace.local.json", "applications/inbox",
    "applications/index.md", "profile.md", "resume/", "resumes/", "data/workspace/", "/workspace/",
)
CHANNEL_LABELS = (
    "官网", "官网投递", "职业邮箱", "BOSS 直聘企业主页", "猎聘企业主页", "LinkedIn 公司主页",
)
LISTED_IDS = {
    "biren", "deepexi", "enflame", "iluvatar-corex", "innovusion",
    "insilico", "metax", "microport-medbot", "minimax", "moore-threads",
    "unitree", "xtalpi", "zhipu",
}


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.output = build.outputs()
        cls.html = cls.output["data/views/dashboard.html"]
        match = re.search(
            r'<script type="application/json" id="cn-ai-opp-data">(.*?)</script>',
            cls.html, re.S)
        if not match:
            raise AssertionError("Dashboard has no embedded dataset")
        cls.dataset = json.loads(match.group(1))

    def test_dashboard_is_generated_with_every_organization_id(self):
        self.assertIn("data/views/dashboard.html", self.output)
        index = json.loads(self.output["data/index.json"])
        expected = {entry["id"] for entry in index["organizations"]}
        embedded = {item["record"]["id"] for item in self.dataset["organizations"]}
        self.assertEqual(embedded, expected)
        for item in self.dataset["organizations"]:
            self.assertEqual(item["index"]["json_path"], f"data/companies/{item['record']['id']}.json")
        self.assertIn("data/index.json", self.html)
        self.assertIn("data/schemas/", self.html)
        self.assertIn("assets/logos/manifest.json", self.html)

    def test_default_view_is_startups_and_classes_partition(self):
        self.assertEqual(self.dataset["meta"]["default_class"], "startups")
        groups = Counter(item["class"] for item in self.dataset["organizations"])
        expected_startups = sum(
            1 for item in self.dataset["organizations"]
            if item["record"]["organization_type"] == "operating_organization"
            and item["record"]["targeting"]["player_group"] == "new_entrant")
        expected_incumbents = sum(
            1 for item in self.dataset["organizations"]
            if item["record"]["organization_type"] == "operating_organization"
            and item["record"]["targeting"]["player_group"] == "incumbent")
        expected_unresolved = sum(
            1 for item in self.dataset["organizations"]
            if item["record"]["organization_type"] == "operating_organization"
            and item["record"]["targeting"]["player_group"] == "unresolved")
        expected_investors = sum(
            1 for item in self.dataset["organizations"]
            if item["record"]["organization_type"] == "investment_firm")
        self.assertEqual(groups["startups"], expected_startups)
        self.assertEqual(groups["incumbents"], expected_incumbents)
        self.assertEqual(groups["unresolved"], expected_unresolved)
        self.assertEqual(groups["investors"], expected_investors)
        self.assertEqual(sum(groups.values()), len(self.dataset["organizations"]))
        classes = {item["id"]: item["count"] for item in self.dataset["classes"]}
        self.assertEqual(classes["startups"], expected_startups)
        self.assertEqual(sum(classes.values()), len(self.dataset["organizations"]))
        for item in self.dataset["organizations"]:
            if item["class"] == "startups":
                self.assertEqual(item["record"]["organization_type"], "operating_organization")
                self.assertEqual(item["record"]["targeting"]["player_group"], "new_entrant")
        self.assertIn('data-class="startups"', self.html)
        self.assertIn('data-class="incumbents"', self.html)
        self.assertIn('data-class="investors"', self.html)
        self.assertIn('data-class="unresolved"', self.html)

    def test_dashboard_keeps_public_sources_and_no_private_paths(self):
        self.assertIn('id="cn-ai-opp-data"', self.html)
        # Public source URLs may legitimately contain path segments like /home/about;
        # strip URLs before looking for local filesystem markers.
        haystack = re.sub(r'https?://[^\s"\'<>]+', " ", self.html)
        for marker in PRIVATE_MARKERS:
            self.assertNotIn(marker, haystack)
        for item in self.dataset["organizations"]:
            self.assertIn("sources", item["record"])
            self.assertTrue(item["record"]["sources"])

    def test_profile_template_renders_people_and_channel_slots_even_when_empty(self):
        self.assertIn("待 find-person 补充", self.html)
        self.assertIn("核心人物待补充", self.html)
        slots = self.html.split("var CHANNEL_SLOTS = [", 1)[1].split("];", 1)[0]
        positions = [slots.index(label) for label in CHANNEL_LABELS]
        self.assertEqual(positions, sorted(positions))
        for label in CHANNEL_LABELS:
            self.assertIn(label, slots)
        self.assertIn(">待补充</span>", self.html)
        self.assertIn("LinkedIn 公司主页", self.html)

    def test_logos_reference_only_generated_assets_or_placeholders(self):
        lowered = self.html.lower()
        self.assertNotIn("clearbit", lowered)
        self.assertNotIn("logo.dev", lowered)
        logos = self.dataset.get("logos") or {}
        for company_id, path in logos.items():
            self.assertTrue(path.startswith("assets/logos/"), company_id)
            self.assertTrue((ROOT / "data/views" / path).exists(), path)
        for item in self.dataset["organizations"]:
            if item.get("logo"):
                self.assertEqual(item["logo"], logos[item["record"]["id"]])
            else:
                self.assertNotIn(item["record"]["id"], logos)

    def _source(self, start, end):
        return self.html.split("function " + start, 1)[1].split("function " + end, 1)[0]

    def test_profile_cover_has_three_class_hooks_and_kickers(self):
        self.assertIn('class="p-hero" id="profile-hero" data-class="startups"', self.html)
        for hook in ('is-startup', 'is-incumbent', 'is-investor'):
            self.assertIn(hook, self.html)
        self.assertIn('profileHero.className = "p-hero " + (CLASS_HOOKS[org.class]', self.html)
        intro = self._source("profileIntroHtml", "profileBodyHtml")
        self.assertIn("profileKicker(org)", intro)
        self.assertIn("profileLead(org)", intro)
        self.assertIn("profileMeta(org)", intro)
        kicker = self._source("profileKicker", "profileLead")
        self.assertIn('class="pk-class"', kicker)
        self.assertIn("tierLabel(record)", kicker)
        self.assertIn("编辑判断，不是官方排名", kicker)
        self.assertIn("categoryName(record.category_id)", kicker)
        # The long tier basis stays in the appendix, not on the cover.
        self.assertNotIn("tier.basis", intro)

    def test_cover_meta_is_class_specific_and_does_not_invent_funding(self):
        startup = self._source("startupChips", "incumbentMeta")
        self.assertIn("成立年份待补充", startup)
        self.assertIn("融资未公开披露", startup)
        self.assertIn("investment.rounds", self._source("fundingText", "startupChips"))
        self.assertIn("amount_text", self._source("fundingText", "startupChips"))
        incumbent = self._source("incumbentMeta", "investorCaseNames")
        self.assertIn("组织边界", incumbent)
        self.assertIn("organizational_context", incumbent)
        self.assertNotIn("investment", incumbent)
        investor = self._source("investorFacts", "profileMeta")
        self.assertIn("founded.year", investor)
        self.assertIn("record.stage", investor)
        self.assertIn("coverage_roles", investor)
        cases = self._source("investorCaseNames", "investorFacts")
        self.assertIn("representative_cases", cases)
        self.assertIn("prior_firm", cases)
        self.assertIn("portfolio", cases)
        self.assertIn("slice(0, 3)", cases)

    def test_profile_body_order_differs_by_class(self):
        body = self._source("profileBodyHtml", "writeHash")
        self.assertRegex(
            body,
            r'org\.class === "investors"[\s\S]*?investmentSection\(record\)[\s\S]*?'
            r'peopleSection\(record, "investors"\)[\s\S]*?opportunitiesSection\(record, "investors"\)[\s\S]*?appendixHtml')
        self.assertRegex(
            body,
            r'org\.class === "incumbents"[\s\S]*?businessSection\(record\)[\s\S]*?'
            r'peopleSection\(record, "incumbents"\)[\s\S]*?opportunitiesSection\(record, "incumbents"\)[\s\S]*?appendixHtml')
        self.assertRegex(
            body,
            r'return peopleSection\(record, "startups"\)[\s\S]*?opportunitiesSection\(record, "startups"\)[\s\S]*?appendixHtml')
        self.assertIn("业务与产品", self._source("businessSection", "casesBlock"))
        self.assertIn("投资方向与阶段", self.html)
        self.assertIn('title: "公开入口"', self.html)
        self.assertIn("BP / 商务邮箱", self._source("opportunitiesSection", "orgContextBlock"))
        people_copy = self.html.split("var PEOPLE_COPY", 1)[1].split("var OPP_COPY", 1)[0]
        self.assertNotIn("创始团队", people_copy)
        self.assertIn("投资团队", people_copy)
        self.assertIn('"档位口径"', self.html)

    def test_portfolio_links_only_when_resolvable_and_never_invents_amounts(self):
        portfolio = self._source("portfolioBlock", "investmentSection")
        self.assertIn("BY_ID.get(item.company_id)", portfolio)
        self.assertIn("item.company_name", portfolio)
        self.assertIn("item.round", portfolio)
        self.assertIn("item.announced_on", portfolio)
        self.assertIn("roleLabel(item.role)", portfolio)
        self.assertNotIn("amount", portfolio)

    def test_directory_chrome_and_rows_follow_class(self):
        chrome = self.html.split("var CLASS_CHROME", 1)[1].split("var PEOPLE_COPY", 1)[0]
        for text in ("全部平台", "全部机构", "业务一句话", "投资方向", "编辑档位"):
            self.assertIn(text, chrome)
        self.assertNotIn("精选", chrome)
        self.assertNotIn("重点平台", chrome)
        self.assertNotIn("featured", chrome)
        self.assertNotIn("代际", chrome)
        self.assertNotIn("全部公司 / 精选公司", chrome)
        row = self._source("rowHtml", "sectorHead")
        self.assertIn('state.cls === "investors"', row)
        self.assertIn('state.cls === "incumbents"', row)
        self.assertIn("tierLabel(record)", row)
        self.assertIn("stageText(record.stage)", row)
        self.assertIn("shorten(record.products, 46)", row)
        self.assertIn("function renderChrome", self.html)
        self.assertIn("directoryEl.dataset.class = state.cls", self.html)
        self.assertIn("resultLine(rows)", self.html)
        self.assertIn("已记录案例", self.html)
        self.assertIn("有业务描述", self.html)

    def test_investor_tier_language_is_editorial(self):
        self.assertIn('if (level === "tier1") return "Tier 1"', self.html)
        self.assertIn('if (level === "tier2") return "Tier 2"', self.html)
        self.assertIn('if (level === "unlisted") return "未列入"', self.html)
        tier = self._source("tierBasisSection", "appendixHtml")
        self.assertIn("编辑判断，不是官方排名", tier)
        self.assertIn("record.tier.basis", tier)
        self.assertIn("record.tier.source_ids", tier)

    def test_listed_startups_stay_in_startups_and_get_a_quiet_mark(self):
        listed = {}
        for item in self.dataset["organizations"]:
            rounds = (item["record"].get("investment") or {}).get("rounds") or []
            if any((round or {}).get("round") == "已上市" for round in rounds):
                listed[item["record"]["id"]] = item
        # These verified listing rounds stay in startups and are the only ones
        # that can trigger the mark.
        self.assertEqual(set(listed), LISTED_IDS)
        for org_id, item in listed.items():
            self.assertEqual(item["class"], "startups", org_id)
            self.assertEqual(item["record"]["targeting"]["player_group"], "new_entrant", org_id)
            round = next(r for r in item["record"]["investment"]["rounds"] if r.get("round") == "已上市")
            self.assertEqual(round["round"], "已上市")
            self.assertTrue(round.get("announced_on") or round.get("notes"), org_id)
        for item in self.dataset["organizations"]:
            if item["class"] != "startups":
                rounds = (item["record"].get("investment") or {}).get("rounds") or []
                self.assertFalse(
                    any((round or {}).get("round") == "已上市" for round in rounds),
                    item["record"]["id"])

        info = self._source("listedInfo", "listedMark")
        self.assertIn('round.round !== "已上市"', info)
        self.assertIn("announced_on", info)
        self.assertIn("notes", info)
        self.assertNotIn("summary", info)

        mark = self._source("listedMark", "rowHtml")
        self.assertIn('org.class !== "startups"', mark)
        self.assertIn("if (!info) return", mark)
        self.assertIn('variant === "kicker"', mark)
        self.assertIn('"p-listed"', mark)
        self.assertIn('"org-listed"', mark)

        row = self._source("rowHtml", "sectorHead")
        self.assertIn("listedMark(org)", row)
        kicker = self._source("profileKicker", "profileLead")
        self.assertIn('listedMark(org, "kicker")', kicker)

        # Restrained styling rides the existing paper/ink/copper-jade system.
        self.assertIn(".org-listed{", self.html)
        self.assertIn(".p-listed{", self.html)
        self.assertIn(".p-listed span{", self.html)
        self.assertNotIn("ipo-banner", self.html)
        self.assertNotIn('class="ipo', self.html)
        # The existing funding chip still reports the latest round as-is.
        funding = self._source("fundingText", "startupChips")
        self.assertIn("round.round", funding)

    def test_featured_strips_are_gone(self):
        for text in (
            "精选公司", "精选机构", "重点平台", "重点核实",
            'id="featured"', "featured-grid", "renderFeatured", "featuredNote",
        ):
            self.assertNotIn(text, self.html)
        self.assertNotIn("featured", self.html.lower())

    def test_official_sort_copy_and_investor_grouping(self):
        self.assertIn("这是本页的排序顺序", self.html)
        self.assertIn("排序：按赛道分组，组内按名称字母序（中文按拼音）", self.html)
        self.assertIn("排序：先成熟机构，再新兴机构，组内按名称字母序（中文按拼音）", self.html)
        self.assertIn("成立待确认列在最后", self.html)
        self.assertNotIn("先 Tier 1，再 Tier 2", self.html)
        self.assertNotIn("档内先新兴机构、后成熟机构", self.html)
        self.assertIn('category: "官方顺序"', self.html)
        self.assertIn('sort: "category"', self.html)
        self.assertIn('var TIER_ORDER = ["tier1", "tier2", "unlisted"]', self.html)
        self.assertIn('var MATURITY_ORDER = ["established", "emerging", "founding_unconfirmed"]', self.html)
        self.assertIn(
            'MATURITY_LABELS = { established: "成熟机构", emerging: "新兴机构", founding_unconfirmed: "成立待确认" }',
            self.html)
        self.assertIn('MATURITY_MARKS = { established: "熟", emerging: "新", founding_unconfirmed: "待" }', self.html)
        self.assertNotIn("新生代", self.html)
        self.assertNotIn("新一代机构", self.html)
        self.assertNotIn("2020–2023", self.html)
        self.assertNotIn("全部档位", self.html)
        self.assertNotIn('categoryLabel.textContent = "档位"', self.html)
        investor_sectors = self._source("sectorItems", "renderSectors")
        self.assertIn("MATURITY_ORDER", investor_sectors)
        self.assertIn("MATURITY_LABELS", investor_sectors)
        self.assertNotIn("TIER_ORDER", investor_sectors)
        groups = self._source("maturitySections", "listSections")
        self.assertIn("MATURITY_ORDER", groups)
        self.assertNotIn("TIER_ORDER", groups)
        self.assertNotIn("subgroups", groups)
        listed = self._source("listSections", "sortNoteText")
        self.assertIn('state.sort !== "category"', listed)
        self.assertIn("maturitySections(rows)", listed)
        self.assertIn("sectorSections(rows)", listed)
        # Filter chrome and URL state follow maturity, not tier, groups.
        options = self.html.split("function renderOptions", 1)[1].split("var cityCounts", 1)[0]
        self.assertIn('categoryLabel.textContent = "类型"', options)
        self.assertIn("全部机构", options)
        self.assertIn("MATURITY_ORDER", options)
        self.assertNotIn("TIER_ORDER", options)
        self.assertIn('MATURITY_ORDER.indexOf(category) !== -1', self.html)
        # Tier stays as a quiet cover badge and appendix judgment.
        self.assertIn('class="pk-class"', self.html)
        self.assertIn("档位口径", self.html)

    def test_three_distinct_class_field_motifs(self):
        self.assertIn(
            'var CLASS_MOTIFS = { startups: "stars", incumbents: "lattice", investors: "ledgers"',
            self.html)
        for name in ("buildStars", "buildLattice", "buildLedgers",
                     "drawStars", "drawLattice", "drawLedgers"):
            self.assertIn("function " + name, self.html)
        self.assertIn("function setFieldMotif", self.html)
        self.assertIn("setFieldMotif(heroField, state.cls)", self.html)
        self.assertIn("setFieldMotif(profileField, org.class)", self.html)
        self.assertIn('canvas.setAttribute("data-motif"', self.html)
        self.assertIn("prefers-reduced-motion: reduce", self.html)
        self.assertIn("devicePixelRatio", self.html)
        self.assertIn("IntersectionObserver", self.html)
        stars = self._source("drawStars", "drawLattice")
        self.assertIn("arc(", stars)
        self.assertIn("pts", stars)
        lattice = self._source("drawLattice", "drawLedgers")
        self.assertNotIn("arc(", lattice)
        self.assertNotIn("pts", lattice)
        self.assertIn("item.kind", lattice)
        self.assertIn("field.t += 0.012", lattice)
        self.assertIn("Math.sin(t * 3.2", lattice)
        self.assertIn("createLinearGradient", lattice)
        ledgers = self.html.split("function drawLedgers", 1)[1].split("function draw(", 1)[0]
        self.assertNotIn("arc(", ledgers)
        self.assertNotIn("pts", ledgers)
        self.assertIn("rule.ticks", ledgers)
        self.assertIn("field.t += 0.013", ledgers)
        self.assertIn("cursor", ledgers)
        self.assertIn("near", ledgers)
        self.assertNotIn('kind === "v"', ledgers)
        self.assertNotIn('kind === "h"', ledgers)
        self.assertNotIn("cursor", lattice)
        self.assertNotIn("grid", ledgers)


if __name__ == "__main__":
    unittest.main()
