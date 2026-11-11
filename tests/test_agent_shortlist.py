import unittest
from datetime import datetime, timedelta, timezone

from scripts.build_agent_shortlist import build_export


NOW = datetime(2026, 11, 11, 15, tzinfo=timezone.utc)


def sample_job(name="A", **overrides):
    data = {
        "id": name, "company": "Example", "title": "Software Engineering Intern",
        "url": "https://example.com/apply/" + name,
        "posted_at": "2026-11-10T14:00:00Z",
        "profiles": ["cs"], "opportunity_type": "internship",
    }
    data.update(overrides)
    return data


class AgentShortlistTests(unittest.TestCase):
    def feed(self, jobs, generated=None):
        return {"generated_at": generated or "2026-11-11T14:00:00Z", "jobs": jobs}

    def test_recent_candidate_export_and_minimal_schema(self):
        result = build_export(self.feed([sample_job()]), now=NOW)
        self.assertEqual(len(result["jobs"]), 1)
        self.assertFalse(result["selection"]["personalized"])
        self.assertEqual(result["jobs"][0]["id"], "A")
        self.assertNotIn("resume", result["jobs"][0])

    def test_reject_stale_feed(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            build_export(self.feed([sample_job()], "2026-10-02T14:00:00Z"), now=NOW)

    def test_reject_irrelevant_and_old_jobs(self):
        data = [
            sample_job("old", posted_at="2026-09-01T14:00:00Z"),
            sample_job("bad", url="javascript:alert(1)"),
            sample_job("fulltime", title="Software Engineer II", opportunity_type="fulltime"),
            sample_job("good"),
        ]
        result = build_export(self.feed(data), now=NOW)
        self.assertEqual([x["id"] for x in result["jobs"]], ["good"])

    def test_inspection_evidence_is_bounded(self):
        cache = {
            "listing_index": {"A": "canonical"},
            "entries": {"canonical": {"inspection": {
                "status": "ok",
                "posting": {"requisition_id": "REQ123", "application_status": "available"},
                "requirements": {"graduation": {"required": [{"statement": "Graduation in 2028 or 2029"}]}}
            }}}
        }
        result = build_export(self.feed([sample_job()]), now=NOW, inspections=cache)
        evidence = result["jobs"][0]["employer_evidence"]
        self.assertEqual(evidence["requisition_id"], "REQ123")
        self.assertEqual(evidence["requirements"]["graduation"][0]["level"], "required")
        self.assertNotIn("description", evidence)

    def test_filters_international_and_2026_roles(self):
        jobs = [
            sample_job("india", location="IN - Bengaluru, India"),
            sample_job("canada", location="Toronto, ON, CA"),
            sample_job("conversion", title="Intern Conversion/Systems Engineer I"),
            sample_job("lastyear", term="Fall 2026"),
            sample_job("indiana", location="Indianapolis, IN"),
        ]
        result = build_export(self.feed(jobs), now=NOW)
        self.assertEqual([x["id"] for x in result["jobs"]], ["indiana"])

    def test_known_recent_posting_precedes_ingestion_only(self):
        jobs = [
            sample_job("unknown", posted_at=None, first_seen="2026-11-11T14:00:00Z"),
            sample_job("known", posted_at="2026-11-10T14:00:00Z"),
        ]
        result = build_export(self.feed(jobs), now=NOW, limit=2)
        self.assertEqual(result["jobs"][0]["id"], "known")
        self.assertEqual(result["jobs"][0]["date_basis"], "posted_at")
        self.assertEqual(result["jobs"][1]["date_basis"], "first_seen_only")

    def test_cap_and_deduplication(self):
        jobs = [sample_job(str(i)) for i in range(5)]
        jobs.append(sample_job("0", id="duplicate"))
        result = build_export(self.feed(jobs), now=NOW, limit=3)
        self.assertEqual(len(result["jobs"]), 3)
        self.assertEqual(len({j["url"] for j in result["jobs"]}), 3)


if __name__ == "__main__":
    unittest.main()
