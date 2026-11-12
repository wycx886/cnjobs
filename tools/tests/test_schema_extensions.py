"""Optional investor/platform fields must stay backward compatible and source-backed."""
import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from record_checks import load, validate_record


class OptionalInvestorFieldTests(unittest.TestCase):
    def setUp(self):
        self.investor = load(ROOT / "data/companies/hongshan.json")
        self.company = load(ROOT / "data/companies/dify.json")

    def test_existing_records_validate_without_new_fields(self):
        validate_record(self.investor)
        validate_record(self.company)

    def test_investor_tier_is_optional_and_source_backed(self):
        record = copy.deepcopy(self.investor)
        record["tier"] = {
            "level": "tier2",
            "basis": "测试夹具：仅验证可选字段结构，不代表真实榜单判断。",
            "source_ids": ["s01", "s02"],
            "labelled_at": record["checked_at"],
        }
        validate_record(record)

    def test_investor_portfolio_field_is_not_accepted(self):
        record = copy.deepcopy(self.investor)
        record["portfolio"] = [{
            "company_name": "Dify",
            "company_id": "dify",
            "round": "Pre-A",
            "announced_on": "2026-03",
            "role": "participant",
            "attribution": "current_firm",
            "source_ids": ["s03"],
            "notes": "测试夹具，不代表真实投资关系。",
        }]
        with self.assertRaises(ValueError):
            validate_record(record)

    def test_company_founded_and_rounds_are_optional(self):
        record = copy.deepcopy(self.company)
        record["founded"] = {
            "year": None,
            "basis": "测试夹具：仅验证可选字段结构，不声明真实成立年份。",
        }
        record["investment"]["rounds"] = [{
            "round": "Pre-A",
            "announced_on": "2026-03-10",
            "amount_text": "3000万美元",
            "investors": [{
                "name": "HSG",
                "firm_id": "hongshan",
                "role": "lead",
                "source_ids": ["s01"],
            }],
            "source_ids": ["s01"],
            "notes": "测试夹具，不代表真实披露。",
        }]
        validate_record(record)

    def test_nested_tier_and_rounds_reject_unknown_fields(self):
        record = copy.deepcopy(self.investor)
        record["tier"] = {
            "level": "tier1",
            "basis": "测试夹具。",
            "source_ids": ["s01"],
            "labelled_at": record["checked_at"],
            "ranking": "unexpected",
        }
        with self.assertRaises(ValueError):
            validate_record(record)

        company = copy.deepcopy(self.company)
        company["investment"]["rounds"] = [{
            "round": "A",
            "announced_on": None,
            "amount_text": None,
            "investors": [],
            "source_ids": ["s01"],
            "notes": None,
            "valuation": "unexpected",
        }]
        with self.assertRaises(ValueError):
            validate_record(company)


if __name__ == "__main__":
    unittest.main()
