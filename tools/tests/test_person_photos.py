"""Keep the optional person portrait field strict and inside the public asset boundary."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import validate
from person_checks import validate_person_photo
from record_checks import schema_validator

SOURCES = {
    "s01": {
        "id": "s01", "title": "Synthetic team page",
        "url": "https://synthetic-company.org/team",
        "supports": "Synthetic unit-test observation only.", "published_date": None,
        "checked_at": "2026-10-31",
    },
}
PERSON = {
    "name": "Synthetic Person", "role": "Founder", "background": None, "previous_firms": [],
    "profiles": [], "source_ids": ["s01"], "checked_at": "2026-10-31",
    "verification_status": "partial", "notes": None,
}
PHOTO = {
    "path": "assets/people/synthetic-person.jpg",
    "source_url": "https://cdn.synthetic-company.org/team/person.jpg",
    "page_url": "https://synthetic-company.org/team",
    "checked_at": "2026-10-31",
    "source_ids": ["s01"],
}


class PersonPhotoTests(unittest.TestCase):
    def person(self, photo=None):
        person = dict(PERSON)
        if photo is not None:
            person["photo"] = photo
        return person

    def errors(self, value):
        return list(schema_validator("person.schema.json").iter_errors(value))

    def test_photo_is_optional_and_relaxes_nothing_else(self):
        self.assertEqual(self.errors(self.person()), [])
        self.assertEqual(self.errors(self.person(dict(PHOTO))), [])

    def test_photo_rejects_unknown_fields_missing_keys_and_bad_paths(self):
        cases = [
            {**PHOTO, "extra": "x"},
            {key: value for key, value in PHOTO.items() if key != "page_url"},
            {**PHOTO, "path": "/etc/person.jpg"},
            {**PHOTO, "path": "assets/people/Synthetic Person.jpg"},
            {**PHOTO, "path": "assets/people/synthetic-person.gif"},
            {**PHOTO, "source_url": "http://cdn.synthetic-company.org/person.jpg"},
            {**PHOTO, "page_url": "http://synthetic-company.org/team"},
            {**PHOTO, "checked_at": "2026-13-01"},
            {**PHOTO, "source_ids": []},
            {**PHOTO, "source_ids": ["photo"]},
        ]
        for photo in cases:
            with self.subTest(photo=photo):
                self.assertNotEqual(self.errors(self.person(photo)), [])

    def test_photo_requires_attached_person_or_organization_evidence(self):
        from datetime import date
        latest = date(2026, 11, 11)
        self.assertEqual(validate_person_photo(dict(PHOTO), SOURCES, latest), {"s01"})
        for photo, sources in [
            ({**PHOTO, "source_ids": ["s99"]}, SOURCES),
            (dict(PHOTO), {"s01": {**SOURCES["s01"], "scope": "channel"}}),
            ({**PHOTO, "checked_at": "2026-11-01"}, SOURCES),
        ]:
            with self.subTest(photo=photo), self.assertRaises(ValueError):
                validate_person_photo(photo, sources, latest)

    def test_stored_photo_must_exist_under_data_views_and_stay_small(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "repo"
            (root / "data/views/assets/people").mkdir(parents=True)
            record = {"people": [self.person(dict(PHOTO))]}
            with self.assertRaises(AssertionError):
                validate.validate_person_photos([record], root)
            target = root / "data/views" / PHOTO["path"]
            target.write_bytes(b"\xff\xd8\xff" + b"0" * 1024)
            self.assertEqual(validate.validate_person_photos([record], root), 1)
            target.write_bytes(b"\xff\xd8\xff" + b"0" * (validate.PHOTO_LIMIT - 3))
            self.assertGreaterEqual(target.stat().st_size, validate.PHOTO_LIMIT)
            with self.assertRaises(AssertionError):
                validate.validate_person_photos([record], root)
            self.assertEqual(validate.validate_person_photos([{"people": [self.person()]}], root), 0)


if __name__ == "__main__":
    unittest.main()
