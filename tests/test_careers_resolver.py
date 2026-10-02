import importlib.util
from pathlib import Path
import unittest

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "careers_resolver.py"
spec = importlib.util.spec_from_file_location("careers_resolver", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class FakeResponse:
    def __init__(self, url, text="", status=200, history=None):
        self.url = url
        self.text = text
        self.status_code = status
        self.history = history or []
        self.headers = {"Content-Type": "text/html"}


class FakeSession:
    def __init__(self, routes):
        self.routes = routes
        self.requested = []

    def get(self, url, **kwargs):
        self.requested.append(url)
        return self.routes.get(url, FakeResponse(url, status=404))


class CareersResolverTests(unittest.TestCase):
    def resolve(self, routes, domain="acme.example"):
        session = FakeSession(routes)
        result = mod.resolve_employer({"name": "Acme", "domain_hints": [domain]}, session)
        return result, session

    def test_workday_link_is_resolved_without_visiting_job_details(self):
        root = "https://acme.example/"
        careers = "https://acme.example/careers"
        workday = "https://acme.wd5.myworkdayjobs.com/en-US/External"
        job = workday + "/job/Boston/Engineer_R123"
        html = f'<a href="{workday}">Careers</a><a href="{job}">Engineer</a>'
        result, session = self.resolve({root: FakeResponse(root, html), careers: FakeResponse(careers, html), workday: FakeResponse(workday, "Careers at Acme")})
        self.assertEqual(result["url"], workday)
        self.assertEqual(result["platform"], "workday")
        self.assertEqual(result["provider"]["family"], "workday")
        self.assertNotIn(job, session.requested)

    def test_bare_workday_tenant_can_discover_site_link(self):
        tenant = "https://acme.wd5.myworkdayjobs.com/"
        board = "https://acme.wd5.myworkdayjobs.com/en-US/External"
        html = f'<a href="{board}">View jobs</a>'
        session = FakeSession({
            tenant: FakeResponse(tenant, html),
            board: FakeResponse(board, "Careers at Acme"),
        })
        result = mod.resolve_employer({"name": "Acme", "url_hint": tenant}, session)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["url"], board)
        self.assertEqual(result["platform"], "workday")

    def test_oracle_redirect_and_evidence_are_preserved(self):
        careers = "https://acme.example/careers"
        oracle = "https://acme.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1"
        redirect = FakeResponse(careers, status=302)
        routes = {
            "https://acme.example/": FakeResponse("https://acme.example/", "Welcome"),
            careers: FakeResponse(oracle, "Candidate Experience Careers", history=[redirect]),
        }
        result, _ = self.resolve(routes)
        self.assertEqual(result["platform"], "oracle")
        attempt = next(item for item in result["evidence"] if item["requested_url"] == careers)
        self.assertEqual([hop["status"] for hop in attempt["redirect_chain"]], [302, 200])
        self.assertEqual(attempt["final_url"], oracle)

    def test_successfactors_company_parameter_is_kept_but_job_is_not_followed(self):
        root = "https://acme.example/"
        sf = "https://career5.successfactors.eu/career?company=acme"
        job = sf + "&career_ns=job_listing&career_job_req_id=1234"
        html = f'<a href="{sf}">Job opportunities</a><a href="{job}">One opening</a>'
        result, session = self.resolve({root: FakeResponse(root, html), sf: FakeResponse(sf, "Careers")})
        self.assertEqual(result["url"], sf)
        self.assertEqual(result["platform"], "successfactors")
        self.assertNotIn(job, session.requested)

    def test_company_branded_careers_page(self):
        careers = "https://acme.example/careers"
        result, _ = self.resolve({careers: FakeResponse(careers, "Build your career with us. View opportunities.")})
        self.assertEqual(result["url"], careers)
        self.assertEqual(result["platform"], "company-branded")
        self.assertEqual(result["provider"]["family"], "custom_unknown")

    def test_company_branded_role_link_is_not_enumerated(self):
        root = "https://acme.example/"
        role = "https://acme.example/careers/software-engineer"
        result, session = self.resolve({root: FakeResponse(root, f'<a href="{role}">Careers: Software Engineer</a>')})
        self.assertEqual(result["status"], "unresolved")
        self.assertNotIn(role, session.requested)

    def test_unrelated_external_careers_link_is_ignored(self):
        root = "https://acme.example/"
        result, session = self.resolve({root: FakeResponse(root, '<a href="https://other.example/careers">Careers</a>')})
        self.assertEqual(result["status"], "unresolved")
        self.assertNotIn("https://other.example/careers", session.requested)

    def test_seed_and_universe_payloads_are_supported(self):
        payload = {
            "schema_version": 1,
            "source": {"key": "benchmark", "kind": "coverage_benchmark"},
            "employers": [{"name": "Acme", "domain_hints": ["acme.example"]}],
        }
        entries, key = mod.registry_entries(payload)
        self.assertEqual(key, "employers")
        self.assertEqual(entries[0]["domain_hints"], ["acme.example"])

    def test_shared_provider_host_without_tenant_is_not_resolved(self):
        host = "https://job-boards.greenhouse.io/"
        result, _ = self.resolve({host: FakeResponse(host, "Find jobs")}, domain="job-boards.greenhouse.io")
        self.assertEqual(result["status"], "unresolved")
        attempt = next(item for item in result["evidence"] if item["requested_url"] == host)
        self.assertIn("lacks employer tenant identity", attempt["signals"][0])

    def test_shared_provider_root_linked_from_employer_is_not_resolved(self):
        root = "https://acme.example/"
        shared = "https://job-boards.greenhouse.io/"
        html = f'<a href="{shared}">Careers</a>'
        result, _ = self.resolve({
            root: FakeResponse(root, html),
            shared: FakeResponse(shared, "Find jobs"),
        })
        self.assertNotEqual(result.get("url"), shared)
        attempt = next(item for item in result["evidence"] if item["requested_url"] == shared)
        self.assertLess(attempt["score"], 0)
        self.assertIn("lacks employer tenant identity", attempt["signals"][0])

    def test_shared_provider_board_path_is_tenant_specific(self):
        board = "https://job-boards.greenhouse.io/acme"
        session = FakeSession({board: FakeResponse(board, "Careers at Acme")})
        result = mod.resolve_employer({"name": "Acme", "url_hint": board}, session)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["platform"], "greenhouse")

    def test_registry_is_enriched_without_losing_input_fields(self):
        careers = "https://acme.example/careers"
        session = FakeSession({careers: FakeResponse(careers, "Careers and opportunities")})
        entries = [{"id": "acme", "name": "Acme", "domain": "acme.example"}]
        enriched = mod.resolve_registry(entries, session)[0]
        self.assertEqual(enriched["id"], "acme")
        self.assertEqual(enriched["careers_url"], careers)
        self.assertEqual(enriched["careers_platform"], "company-branded")
        self.assertIn("evidence", enriched["careers_resolution"])


    def test_workday_406_is_accepted_and_ats_wins_over_branded(self):
        """HTTP 406 on a Workday domain is a valid discovery and wins over 200 branded."""
        from scripts.employer_resolution_queue import queue_entry
        from scripts.careers_resolver import resolve_employer

        # Fake responses:
        #  .com/careers -> 200 OK (company-branded)
        #  .wd5.myworkdayjobs.com/ -> 406 Not Acceptable (Workday)
        responses = {
            "https://www.testcorp.com/careers": (200, "<html>Careers page</html>", "text/html"),
            "https://testcorp.wd5.myworkdayjobs.com/": (406, "", "")
        }

        class FakeResponse:
            def __init__(self, url, status, text, content_type):
                self.url = url
                self.status_code = status
                self.text = text
                self.headers = {"Content-Type": content_type}

        class FakeSession:
            def get(self, url, **kwargs):
                if url in responses:
                    return FakeResponse(url, *responses[url])
                return FakeResponse(url, 404, "", "")

        employer = {
            "id": "testcorp",
            "name": "TestCorp",
            "aliases": [],
            "seed_sets": ["fake"],
            "seed_metadata": {
                "fake": {
                    "domain_hints": [
                        "testcorp.com",
                        "testcorp.wd5.myworkdayjobs.com"
                    ]
                }
            }
        }

        result = resolve_employer(queue_entry(employer), session=FakeSession())
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["platform"], "workday")
        self.assertEqual(result["url"], "https://testcorp.wd5.myworkdayjobs.com/")


if __name__ == "__main__":
    unittest.main()

    def test_respects_provider_identity_lost_in_redirect_to_company_branded(self):
        entry = {
            "id": "airbnb",
            "name": "Airbnb",
            "domain_hints": ["job-boards.greenhouse.io/airbnb", "airbnb.com"],
            "aliases": []
        }

        intermediate = FakeResponse("https://job-boards.greenhouse.io/airbnb", status=302)
        final = FakeResponse("https://careers.airbnb.com/positions/", text="<html><body>Careers</body></html>", status=200, history=[intermediate])

        # When hitting the hint, it redirects to a company-branded URL
        session = FakeSession({
            "https://job-boards.greenhouse.io/airbnb": final,
            "https://airbnb.com/": FakeResponse("https://airbnb.com/", text="Home"),
            "https://airbnb.com/careers": FakeResponse("https://airbnb.com/careers", status=404),
            "https://airbnb.com/jobs": FakeResponse("https://airbnb.com/jobs", status=404),
        })

        result, _ = self.resolve(entry, session)
        self.assertEqual(result["status"], "resolved")
        self.assertEqual(result["platform"], "greenhouse")
        self.assertEqual(result["provider"]["family"], "greenhouse")
        self.assertEqual(result["url"], "https://careers.airbnb.com/positions/")
