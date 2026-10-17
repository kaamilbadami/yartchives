import unittest
from scripts.pay_normalization import (
    parse_pay_from_text,
    normalize_compensation,
    merge_salary_fields,
)

class TestPayNormalization(unittest.TestCase):

    def test_parse_pay_from_text_hourly_range(self):
        res = parse_pay_from_text("Pay: $30.00 - $45.00 / hr")
        self.assertIsNotNone(res)
        self.assertEqual(res["salary_min"], 30.0)
        self.assertEqual(res["salary_max"], 45.0)
        self.assertEqual(res["salary_period"], "hour")
        self.assertEqual(res["salary_currency"], "USD")

    def test_parse_pay_from_text_hourly_single(self):
        res = parse_pay_from_text("Compensation is $35/hr for Summer 2027")
        self.assertIsNotNone(res)
        self.assertEqual(res["salary_min"], 35.0)
        self.assertEqual(res["salary_max"], 35.0)
        self.assertEqual(res["salary_period"], "hour")

    def test_parse_pay_from_text_annual_range_k(self):
        res = parse_pay_from_text("$70k - $90k / year")
        self.assertIsNotNone(res)
        self.assertEqual(res["salary_min"], 70000.0)
        self.assertEqual(res["salary_max"], 90000.0)
        self.assertEqual(res["salary_period"], "year")

    def test_parse_pay_from_text_weekly(self):
        res = parse_pay_from_text("$1,500/wk stipend / salary")
        self.assertIsNotNone(res)
        self.assertEqual(res["salary_min"], 1500.0)
        self.assertEqual(res["salary_period"], "week")

    def test_parse_pay_from_text_stipend(self):
        res = parse_pay_from_text("Housing stipend of $5,000 stipend")
        self.assertIsNotNone(res)
        self.assertEqual(res["salary_min"], 5000.0)
        self.assertEqual(res["salary_period"], "stipend")

    def test_parse_pay_from_text_no_match(self):
        res = parse_pay_from_text("Great team culture, flexible work hours!")
        self.assertIsNone(res)

    def test_normalize_compensation_dict(self):
        raw = {
            "min": 40.0,
            "max": 50.0,
            "period": "HOURLY",
            "currency": "USD"
        }
        res = normalize_compensation(raw, provenance="structured_ats")
        self.assertEqual(res["salary_min"], 40.0)
        self.assertEqual(res["salary_max"], 50.0)
        self.assertEqual(res["salary_period"], "hour")
        self.assertEqual(res["salary_provenance"], "structured_ats")

    def test_merge_salary_fields(self):
        target = {
            "title": "Software Intern",
            "salary_min": 30.0,
            "salary_max": 30.0,
            "salary_period": "hour",
            "salary_provenance": "text_extraction"
        }
        incoming = {
            "salary_min": 30.0,
            "salary_max": 40.0,
            "salary_period": "hour",
            "salary_provenance": "structured_ats"
        }
        merge_salary_fields(target, incoming)
        self.assertEqual(target["salary_max"], 40.0)
        self.assertEqual(target["salary_provenance"], "structured_ats")

if __name__ == "__main__":
    unittest.main()
