from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import migrate_cached_requirements as migration
from posting_requirements import EXTRACTOR_VERSION


class CachedRequirementRenormalizationTests(unittest.TestCase):
    def inspected_entry(self, description):
        return {
            "provider": "workday",
            "inspection": {
                "provider": "workday",
                "status": "inspected",
                "retrieval_confidence": "high",
                "error": None,
                "posting": {
                    "application_status": "available",
                    "description": description,
                },
                "requirements": {},
                "provenance": {"inspected_at": "2026-09-16T20:00:00Z"},
            },
            "last_attempted_at": "2026-09-16T20:00:00Z",
            "last_success_at": "2026-09-16T20:00:00Z",
            "last_error": None,
        }

    def test_cached_description_is_renormalized_with_current_extractor(self):
        entry = self.inspected_entry(
            "Qualifications:\n"
            "Academic or project experience with React, C#/.NET, and SQL.\n"
            "Familiarity or interest in AI agent frameworks and LLMs."
        )
        cache = {"entries": {"https://example.test/job": entry}}

        updated, stats = migration.migrate_cache(cache)

        self.assertEqual(stats["migrated"], 1)
        migrated = updated["entries"]["https://example.test/job"]
        self.assertEqual(migrated["requirements_extractor_version"], EXTRACTOR_VERSION)
        skills = migrated["inspection"]["requirements"]["skills"]
        self.assertEqual(skills["classification"], "unspecified")
        self.assertEqual(
            skills["unspecified"][0]["technologies"],
            ["C#", "React", ".NET", "SQL"],
        )

    def test_entry_without_reprocessable_description_is_invalidated_for_refresh(self):
        entry = self.inspected_entry(None)
        entry["inspection"]["requirements"] = {
            "skills": {"classification": "required", "required": [{"statement": "Old stale fact"}]}
        }
        cache = {"entries": {"https://example.test/job": entry}}

        updated, stats = migration.migrate_cache(cache)

        self.assertEqual(stats["invalidated"], 1)
        migrated = updated["entries"]["https://example.test/job"]
        self.assertEqual(migrated["inspection"]["status"], "stale_requirements")
        self.assertIsNone(migrated["last_success_at"])
        self.assertIsNone(migrated["last_attempted_at"])
        self.assertIn("extractor", migrated["last_error"].lower())

    def test_current_version_is_idempotent(self):
        entry = self.inspected_entry("Qualifications:\nJava experience required.")
        entry["requirements_extractor_version"] = EXTRACTOR_VERSION
        entry["inspection"]["requirements"] = {"sentinel": True}
        cache = {"entries": {"https://example.test/job": entry}}

        updated, stats = migration.migrate_cache(cache)

        self.assertEqual(stats["current"], 1)
        self.assertEqual(updated["entries"]["https://example.test/job"]["inspection"]["requirements"], {"sentinel": True})


if __name__ == "__main__":
    unittest.main()
