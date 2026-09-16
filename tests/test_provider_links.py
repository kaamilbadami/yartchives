import importlib.util
from pathlib import Path
import unittest

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


if __name__ == "__main__":
    unittest.main()
