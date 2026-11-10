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
        for marker in PRIVATE_MARKERS:
            self.assertNotIn(marker, self.html)
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


if __name__ == "__main__":
    unittest.main()
