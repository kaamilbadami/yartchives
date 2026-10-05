import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock
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

    def test_stale_feed_is_not_masked_by_recent_successful_workflow(self):
        generated_at = self.now - timedelta(hours=3)
        runs = [
            {"status": "completed", "conclusion": "success", "updated_at": self._iso(self.now - timedelta(hours=1))}
        ]
        ok, msg = mod.evaluate_freshness(generated_at, runs, self.now, self.threshold_hours, self.allowed_progress_minutes)
        self.assertFalse(ok)
        self.assertIn("Feed is STALE", msg)

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

    def test_dispatch_requires_token(self):
        ok, msg = mod.dispatch_feed_refresh("owner/repo", None)
        self.assertFalse(ok)
        self.assertIn("GITHUB_TOKEN", msg)

    def test_stale_recovery_dispatches_fast_workflow(self):
        generated_at = self.now - timedelta(hours=3)
        with mock.patch.object(mod, "get_workflow_runs", return_value=[]), \
             mock.patch.object(mod, "dispatch_feed_refresh", return_value=(True, "ok")) as dispatch:
            ok, _ = mod.evaluate_freshness(
                generated_at, [], self.now, self.threshold_hours, self.allowed_progress_minutes
            )
            self.assertFalse(ok)
            mod.dispatch_feed_refresh(
                "owner/repo",
                "token",
                workflow="update-feed-fast.yml",
            )
        dispatch.assert_called_once_with(
            "owner/repo",
            "token",
            workflow="update-feed-fast.yml",
        )

    def test_main_exposes_three_hour_alert_state(self):
        with tempfile.NamedTemporaryFile("w+", suffix=".json") as feed, tempfile.NamedTemporaryFile("w+") as output:
            generated = self.now - timedelta(hours=3, minutes=5)
            feed.write('{"generated_at":"' + self._iso(generated) + '"}')
            feed.flush()
            with mock.patch.object(mod, "now_utc", return_value=self.now), \
                 mock.patch.object(mod, "get_workflow_runs", return_value=[{"status": "in_progress", "created_at": self._iso(self.now - timedelta(minutes=5))}]) as runs, \
                 mock.patch.dict(os.environ, {"GITHUB_OUTPUT": output.name, "GITHUB_TOKEN": "token"}, clear=False), \
                 mock.patch("sys.argv", ["watchdog_feed_freshness.py", "--feed", feed.name]):
                self.assertEqual(mod.main(), 0)
            runs.assert_called_once_with("kaamilbadami/yartchives", "token", "update-feed-fast.yml")
            output.seek(0)
            text = output.read()
            self.assertIn("alert_required=true", text)
            self.assertIn("alert_tag=yartchives-feed-stale-", text)

if __name__ == "__main__":
    unittest.main()
