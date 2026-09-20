import importlib.util
import threading
import time
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "parallel_ats_collect.py"
spec = importlib.util.spec_from_file_location("parallel_ats_collect", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ParallelAtsCollectTests(unittest.TestCase):
    def test_collectors_run_concurrently(self):
        lock = threading.Lock()
        active = 0
        max_active = 0

        def task(name):
            def run():
                nonlocal active, max_active
                with lock:
                    active += 1
                    max_active = max(max_active, active)
                time.sleep(0.03)
                with lock:
                    active -= 1
                return {"jobs": [{"id": name}], "sources": {}}
            return run

        result = mod.run_parallel({
            "workday": task("workday"),
            "icims": task("icims"),
            "greenhouse": task("greenhouse"),
            "oracle": task("oracle"),
        })

        self.assertGreater(max_active, 1)
        self.assertEqual(set(result), {"workday", "icims", "greenhouse", "oracle"})

    def test_merge_is_provider_ordered_and_preserves_authoritative_branding(self):
        base = {
            "jobs": [{
                "id": "same",
                "company": "Sage49",
                "title": "Software Engineer Intern",
                "location": "Remote",
                "url": "https://job-boards.greenhouse.io/sage/jobs/123",
                "source_keys": ["aggregator"],
                "source_names": ["Aggregator"],
                "source_urls": ["https://example.com"],
                "profiles": ["cs"],
                "states": ["Remote"],
            }],
            "sources": {"aggregator": {"status": "healthy"}},
        }
        workday = {
            "jobs": [dict(base["jobs"][0])],
            "sources": dict(base["sources"]),
        }
        greenhouse_job = dict(base["jobs"][0])
        greenhouse_job.update({
            "company": "Sage",
            "direct_employer": True,
            "source_keys": ["aggregator", "direct-greenhouse-sage"],
            "source_names": ["Aggregator", "Sage"],
            "source_urls": ["https://example.com", "https://job-boards.greenhouse.io/sage"],
        })
        greenhouse = {
            "jobs": [greenhouse_job],
            "sources": {
                **base["sources"],
                "direct-greenhouse-sage": {"status": "healthy", "direct": True},
            },
        }

        merged = mod.merge_provider_documents(
            base,
            {
                "workday": workday,
                "greenhouse": greenhouse,
                "icims": {"jobs": list(base["jobs"]), "sources": dict(base["sources"])},
                "oracle": {"jobs": list(base["jobs"]), "sources": dict(base["sources"])},
            },
        )

        self.assertEqual(len(merged["jobs"]), 1)
        self.assertEqual(merged["jobs"][0]["company"], "Sage")
        self.assertTrue(merged["jobs"][0]["direct_employer"])
        self.assertIn("direct-greenhouse-sage", merged["jobs"][0]["source_keys"])
        self.assertIn("direct-greenhouse-sage", merged["sources"])

    def test_merge_unions_distinct_provider_jobs(self):
        base = {"jobs": [], "sources": {}}
        provider_docs = {}
        for name in mod.PROVIDER_ORDER:
            provider_docs[name] = {
                "jobs": [{
                    "id": name,
                    "company": name.title(),
                    "title": "Software Engineer Intern",
                    "location": "Remote",
                    "url": f"https://{name}.example/jobs/1",
                    "source_keys": [name],
                    "source_names": [name],
                    "source_urls": [f"https://{name}.example"],
                    "profiles": ["cs"],
                    "states": ["Remote"],
                    "direct_employer": True,
                }],
                "sources": {name: {"status": "healthy", "direct": True}},
            }

        merged = mod.merge_provider_documents(base, provider_docs)

        self.assertEqual({job["id"] for job in merged["jobs"]}, set(mod.PROVIDER_ORDER))
        self.assertEqual(set(merged["sources"]), set(mod.PROVIDER_ORDER))


if __name__ == "__main__":
    unittest.main()
