"""Keep company consolidation source-dated, unambiguous and compatible with old links."""
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build
from company_routes import canonical_id, redirects, render
from record_checks import record_path, validate_record


class CompanyRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "data/companies").mkdir(parents=True)
        (self.root / "data/lists").mkdir()
        self.company = {"id": "company", "name": "合成公司"}
        ((self.root / "data/companies/company.json").resolve()).write_text(json.dumps(self.company))

    def route(self, routes):
        (self.root / "data/lists/company-redirects.json").write_text(
            json.dumps({"schema_version": 1, "redirects": routes}))

    def test_old_reader_link_and_query_resolve_to_one_canonical_company(self):
        routes = redirects(ROOT)
        self.assertEqual(routes["bytedance-shanghai"], "bytedance")
        output = build.outputs()
        entries = json.loads(output["data/index.json"])["organizations"]
        ids = {entry["id"] for entry in entries}
        self.assertTrue(set(routes).isdisjoint(ids))
        for old, target in routes.items():
            self.assertIn(target, ids)
            self.assertIn("](" + target + ".md)", output["data/views/companies/" + old + ".md"])
            self.assertFalse((ROOT / "data/companies" / (old + ".json")).exists())
        result = subprocess.check_output([sys.executable, str(ROOT / "tools/query.py"),
                                          "--id", "bytedance-shanghai", "--json"])
        self.assertEqual([r["id"] for r in json.loads(result)], ["bytedance"])

    def test_retired_ids_cannot_silently_recreate_or_write_regional_companies(self):
        self.route({"company-shanghai": "company"})
        self.assertEqual(canonical_id(self.root, "company-shanghai"), "company")
        with self.assertRaisesRegex(ValueError, "canonical company ID: company"):
            record_path(self.root, "operating_organization", "company-shanghai")
        self.assertEqual(record_path(self.root, "operating_organization", "company"),
                         (self.root / "data/companies/company.json").resolve())

    def test_missing_target_duplicate_record_chain_and_cycle_are_rejected(self):
        for routes in ({"old": "missing"}, {"old": "next", "next": "company"},
                       {"old": "next", "next": "old"}, {"company": "company"}):
            with self.subTest(routes=routes):
                self.route(routes)
                with self.assertRaises(ValueError):
                    redirects(self.root)
        self.route({"old": "company"})
        (self.root / "data/companies/old.json").write_text("{}")
        with self.assertRaises(ValueError):
            render(self.root)

    def test_independent_institutions_and_named_entities_keep_their_identity(self):
        entries = {r["id"]: r for r in json.loads(build.outputs()["data/index.json"])["organizations"]}
        for identity in ("shanghai-ai-lab", "shanghai-electric", "shanghai-fanuc", "anew-labs", "qisda", "wistron-kunshan"):
            self.assertIn(identity, entries)
            self.assertNotIn(identity, redirects(ROOT))


class RegionalResearchTests(unittest.TestCase):
    def record(self):
        return json.loads((ROOT / "data/companies/hypershell.json").read_text())

    def add_regional_source(self, record):
        later = min(date.fromisoformat(record["checked_at"]) + timedelta(days=1), date.today()).isoformat()
        record["sources"].append({"id": "s999", "title": "合成地区资料", "url": "https://www.hypershell.tech/regional-research",
                                  "supports": "Synthetic local research, not a fresh company-wide check.",
                                  "published_date": None, "checked_at": later})
        record["regional_notes"] = [{"region": "上海", "summary": "地区研究范围有限。",
                                     "source_ids": ["s999"], "checked_at": later}]

    def test_local_evidence_has_its_own_date_without_refreshing_company_facts(self):
        record = copy.deepcopy(self.record())
        original_date = (date.today() - timedelta(days=8)).isoformat()
        record["checked_at"] = original_date
        record["people"] = []
        record["sources"] = [s for s in record["sources"] if s.get("scope", "organization") != "person"]
        for source in record["sources"]:
            if source.get("checked_at") and source["checked_at"] > original_date:
                source["checked_at"] = original_date
        self.add_regional_source(record)
        validate_record(record, ROOT)
        self.assertEqual(record["checked_at"], original_date)
        record.pop("regional_notes")
        with self.assertRaisesRegex(ValueError, "newer than the business-profile check"):
            validate_record(record, ROOT)

    def test_regional_notes_require_real_organization_refs_and_supported_dates(self):
        original = self.record()
        self.add_regional_source(original)
        source_date = original["sources"][-1]["checked_at"]
        note_newer = (date.fromisoformat(source_date) + timedelta(days=1)).isoformat()
        invalid_cases = [("source_ids", ["s998"]), ("checked_at", "2099-01-01"), ("checked_at", note_newer)]
        for field, value in invalid_cases:
            record = copy.deepcopy(original)
            record["regional_notes"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                validate_record(record, ROOT)
        record = copy.deepcopy(original)
        record["sources"][-1]["scope"] = "channel"
        with self.assertRaisesRegex(ValueError, "Regional research requires organization evidence"):
            validate_record(record, ROOT)


if __name__ == "__main__":
    unittest.main()
