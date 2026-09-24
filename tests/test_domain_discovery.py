import unittest

from scripts.domain_discovery import _domain_is_plausible, normalize_company


class DomainDiscoveryTests(unittest.TestCase):
    def test_normalize_company_compacts_significant_tokens(self):
        self.assertEqual(normalize_company("Automatic Data Processing, Inc."), "automaticdata")

    def test_rejects_obvious_false_positive_domains(self):
        self.assertFalse(_domain_is_plausible("camminodellappia.it", ["appian"]))
        self.assertFalse(_domain_is_plausible("citadel.edu", ["citadel"]))
        self.assertFalse(_domain_is_plausible("alphabetdeal.com", ["alphabet"]))

    def test_accepts_plausible_corporate_domains(self):
        self.assertTrue(_domain_is_plausible("appian.com", ["appian"]))
        self.assertTrue(_domain_is_plausible("citadel.com", ["citadel"]))
        self.assertTrue(_domain_is_plausible("amd.com", ["advancedmicrodevices", "amd"]))


if __name__ == "__main__":
    unittest.main()
