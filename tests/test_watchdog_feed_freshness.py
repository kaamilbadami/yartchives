import unittest
from datetime import datetime, timedelta, timezone
import scripts.watchdog_feed_freshness as mod

class TestWatchdogFeedFreshness(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2023, 10, 10, 12, 0, 0, tzinfo=timezone.utc)
        self.threshold_hours = 2.0
        self.allowed_progress_minutes = 45.0

    def _iso(self, dt: datetime) -> str:
        s = dt.isoformat()
        if s.endswith("+00:00"):
            return s[:-6] + "Z"
        return s

    def test_fresh_feed(self):
        generated_at = self.now - timedelta(hours=1)
        runs = []
        ok, msg = mod.evaluate_freshness(generated_at, runs, self.now, self.threshold_hours, self.allowed_progress_minutes)
        self.assertTrue(ok)
        self.assertIn("Feed is fresh", msg)

    def test_stale_feed(self):
        generated_at = self.now - timedelta(hours=3)
        runs = []
        ok, msg = mod.evaluate_freshness(generated_at, runs, self.now, self.threshold_hours, self.allowed_progress_minutes)
        self.assertFalse(ok)
        self.assertIn("Feed is STALE", msg)

    def test_stale_but_recent_success(self):
        generated_at = self.now - timedelta(hours=3)
        runs = [
            {"status": "completed", "conclusion": "success", "updated_at": self._iso(self.now - timedelta(hours=1))}
        ]
        ok, msg = mod.evaluate_freshness(generated_at, runs, self.now, self.threshold_hours, self.allowed_progress_minutes)
        self.assertTrue(ok)
        self.assertIn("Feed is fresh (unchanged content)", msg)

    def test_stale_but_recent_active_run(self):
        generated_at = self.now - timedelta(hours=3)
        runs = [
            {"status": "in_progress", "created_at": self._iso(self.now - timedelta(minutes=30))}
        ]
        ok, msg = mod.evaluate_freshness(generated_at, runs, self.now, self.threshold_hours, self.allowed_progress_minutes)
        self.assertTrue(ok)
        self.assertIn("actively in progress", msg)

    def test_stale_and_old_active_run(self):
        generated_at = self.now - timedelta(hours=3)
        runs = [
            {"status": "in_progress", "created_at": self._iso(self.now - timedelta(minutes=60))}
        ]
        ok, msg = mod.evaluate_freshness(generated_at, runs, self.now, self.threshold_hours, self.allowed_progress_minutes)
        self.assertFalse(ok)
        self.assertIn("Feed is STALE", msg)

if __name__ == "__main__":
    unittest.main()
