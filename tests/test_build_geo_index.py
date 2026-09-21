import json
import unittest

from scripts.build_geo_index import build_geo_artifact


class GeoIndexArtifactTests(unittest.TestCase):
    def test_builds_zip_and_deduplicated_city_indexes(self):
        rows = [
            {"zip_code": "20740", "city": "College Park", "state": "MD", "latitude": "38.99", "longitude": "-76.93"},
            {"zip_code": "20742", "city": "College Park", "state": "MD", "latitude": "38.98", "longitude": "-76.94"},
            {"zip_code": "06897", "city": "Wilton", "state": "CT", "latitude": "41.19", "longitude": "-73.44"},
        ]
        artifact = build_geo_artifact(rows)
        self.assertEqual(artifact["version"], 1)
        self.assertEqual(len(artifact["zips"]), 3)
        self.assertEqual(len(artifact["cities"]), 2)
        college_park = next(row for row in artifact["cities"] if row[:2] == ["MD", "college park"])
        self.assertEqual(college_park[2:], [38.985, -76.935])

    def test_compact_shape_avoids_source_only_columns(self):
        rows = [{
            "zip_code": "20740",
            "city": "College Park",
            "state": "MD",
            "latitude": "38.99",
            "longitude": "-76.93",
            "county": "Prince George's",
            "timezone": "America/New_York",
            "population": "99999",
            "median_household_income": "99999",
        }]
        encoded = json.dumps(build_geo_artifact(rows))
        self.assertNotIn("county", encoded)
        self.assertNotIn("timezone", encoded)
        self.assertNotIn("population", encoded)
        self.assertNotIn("median_household_income", encoded)


if __name__ == "__main__":
    unittest.main()
