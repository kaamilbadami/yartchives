import unittest
from scripts.employer_resolution_queue import _hint_identity_status
from scripts.careers_resolver import has_provider_tenant_identity

class TestAshbyTenantIdentity(unittest.TestCase):
    def test_ashby_hint_identity_status(self):
        self.assertEqual(_hint_identity_status("https://jobs.ashbyhq.com"), "tenant")
        self.assertEqual(_hint_identity_status("https://ashbyhq.com"), "tenant")
        self.assertEqual(_hint_identity_status("https://jobs.lever.co"), "tenant")
        self.assertEqual(_hint_identity_status("https://boards.greenhouse.io"), "tenant")
        self.assertEqual(_hint_identity_status("https://jobs.ashbyhq.com/company"), "tenant")

    def test_has_provider_tenant_identity_ashby(self):
        self.assertTrue(has_provider_tenant_identity("https://jobs.ashbyhq.com/company", "ashby"))
        self.assertFalse(has_provider_tenant_identity("https://jobs.ashbyhq.com/jobs", "ashby"))
        self.assertFalse(has_provider_tenant_identity("https://jobs.ashbyhq.com/careers", "ashby"))
        self.assertFalse(has_provider_tenant_identity("https://ashbyhq.com/jobs", "ashby"))

if __name__ == '__main__':
    unittest.main()
