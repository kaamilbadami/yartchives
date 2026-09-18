import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "provider_links.py"
spec = importlib.util.spec_from_file_location("provider_links", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ProviderLinksTests(unittest.TestCase):
    def test_parse_workday_slug(self):
        self.assertEqual(
            mod.parse_workday_slug("https://zapply.jobs/l/d/workday-nvidia-nvidiaexternalcareersite-JR2023856?s=x"),
            ("nvidia", "nvidiaexternalcareersite", "JR2023856"),
        )
        self.assertEqual(
            mod.parse_workday_slug("https://zapply.jobs/l/d/workday-brunswick-search-JR-051290"),
            ("brunswick", "search", "JR-051290"),
        )
        self.assertEqual(
            mod.parse_workday_slug("https://zapply.jobs/l/d/workday-globalhr-rec-rtx-ext-gateway-01872508"),
            ("globalhr", "rec-rtx-ext-gateway", "01872508"),
        )

    def test_workday_config_from_direct_url(self):
        self.assertEqual(
            mod.workday_config_from_url(
                "https://nvidia.wd5.myworkdayjobs.com/en-US/NVIDIAExternalCareerSite/job/US-CA/Test_JR2023856"
            ),
            ("nvidia", "nvidia.wd5.myworkdayjobs.com", "NVIDIAExternalCareerSite"),
        )

    def test_workday_match_requires_requisition_in_external_path(self):
        row = {"externalPath": "/job/US-CA/Foo_JR2023856"}
        self.assertTrue(mod.workday_posting_match(row, "JR2023856"))
        self.assertFalse(mod.workday_posting_match(row, "JR2023999"))

    def test_jobright_named_apply_url_is_accepted(self):
        html = '<script type="application/json">{"applyUrl":"https://example.com/careers/jobs/123"}</script>'
        self.assertEqual(mod.jobright_candidates_from_html(html), ["https://example.com/careers/jobs/123"])

    def test_jobright_ambiguous_apply_urls_are_rejected(self):
        html = (
            '<script type="application/json">{"applyUrl":"https://one.example.com/jobs/1",'
            '"applicationUrl":"https://two.example.com/jobs/2"}</script>'
        )
        self.assertEqual(mod.jobright_candidates_from_html(html), [])

    def test_jobright_does_not_accept_aggregator_as_direct(self):
        html = '<script type="application/json">{"applyUrl":"https://jobright.ai/jobs/info/abc"}</script>'
        self.assertEqual(mod.jobright_candidates_from_html(html), [])

    def test_recover_stale_workday_direct_uses_same_requisition(self):
        stale = (
            "https://amgen.wd1.myworkdayjobs.com/Careers/job/"
            "United-States---Remote/Undergrad-Intern-Software-Engineer_R-255719"
        )
        recovered = (
            "https://amgen.wd1.myworkdayjobs.com/en-US/Careers/job/"
            "United-States---Remote/Undergrad-Intern-Software-Engineer_R-255719"
        )

        self.assertEqual(mod.workday_req_id_from_url(stale), "R-255719")
        with patch.object(mod, "query_workday", return_value=recovered) as query:
            self.assertEqual(mod.recover_stale_workday_direct(stale), recovered)

        query.assert_called_once_with("amgen.wd1.myworkdayjobs.com", "amgen", "Careers", "R-255719")

    def test_amgen_r255719_recovers_exact_current_apply_route(self):
        stale = (
            "https://amgen.wd1.myworkdayjobs.com/Careers/job/United-States---Remote/"
            "Undergrad-Intern-Software-Engineer-Technology-AI-Data-Summer-2027_R-255719"
        )
        external_path = (
            "/job/United-States---Remote/"
            "Undergrad-Intern---Software-Engineer---Amgen-s-Technology---Medical-Organizations--Summer-2027-_R-255719"
        )
        expected = (
            "https://amgen.wd1.myworkdayjobs.com/Careers"
            + external_path
            + "/apply"
        )

        class Response:
            status_code = 200

            def json(self):
                return {"jobPostings": [{"externalPath": external_path}]}

        with (
            patch.object(mod.requests, "post", return_value=Response()),
            patch.object(mod.links, "validate_candidate_once", side_effect=lambda value: value),
        ):
            recovered = mod.query_workday(
                "amgen.wd1.myworkdayjobs.com",
                "amgen",
                "Careers",
                "R-255719",
            )

        self.assertEqual(recovered, expected)


    def test_source_job_with_dead_workday_url_is_recovery_target(self):
        job = {
            "company": "Amgen",
            "title": "Undergrad Intern - Software Engineer",
            "link_kind": "source",
            "url": "",
            "dead_url": (
                "https://amgen.wd1.myworkdayjobs.com/Careers/job/"
                "United-States---Remote/Undergrad-Intern-Software-Engineer_R-255719"
            ),
        }
        recovered = (
            "https://amgen.wd1.myworkdayjobs.com/en-US/Careers/job/"
            "United-States---Remote/Undergrad-Intern-Software-Engineer_R-255719"
        )
        with patch.object(mod, "recover_stale_workday_direct", return_value=recovered):
            self.assertEqual(
                mod.resolve_one(job, {}),
                (recovered, "stale-workday-requisition"),
            )


if __name__ == "__main__":
    unittest.main()
