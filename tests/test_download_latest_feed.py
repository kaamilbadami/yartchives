import importlib.util
import io
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
import zipfile
from pathlib import Path
from urllib.request import Request
from unittest.mock import patch
import sys

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "download_latest_feed.py"
spec = importlib.util.spec_from_file_location("download_latest_feed", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def zip_bytes(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


class DownloadLatestFeedTests(unittest.TestCase):
    def test_latest_artifact_accepts_validated_artifact_from_later_failed_run(self):
        responses = [
            {"workflow_runs": [{"id": 9, "conclusion": "failure"}]},
            {"artifacts": [{"id": 99, "name": "yartchives-listings", "expired": False}]},
        ]
        with patch.object(mod, "_request_json", side_effect=responses) as request_json:
            artifact = mod.latest_artifact(
                "owner/repo",
                "update-feed.yml",
                "yartchives-listings",
                "token",
            )
        self.assertEqual(artifact["id"], 99)
        self.assertNotIn("status=success", request_json.call_args_list[0].args[0])


    def test_artifact_redirect_drops_github_auth_on_cross_host(self):
        handler = mod._SafeArtifactRedirectHandler()
        request = Request(
            "https://api.github.com/repos/owner/repo/actions/artifacts/123/zip",
            headers={
                "Authorization": "Bearer secret",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://pipelines.actions.githubusercontent.com/example/archive.zip",
        )
        self.assertIsNotNone(redirected)
        self.assertIsNone(redirected.get_header("Authorization"))
        self.assertIsNone(redirected.get_header("X-GitHub-Api-Version"))


    def test_workflow_has_active_run_recognizes_running_and_queued_states(self):
        with patch.object(mod, "_request_json", return_value={
            "workflow_runs": [
                {"status": "completed"},
                {"status": "in_progress"},
            ]
        }):
            self.assertTrue(mod.workflow_has_active_run(
                "owner/repo", "update-feed.yml", "token"
            ))
        with patch.object(mod, "_request_json", return_value={
            "workflow_runs": [{"status": "completed"}]
        }):
            self.assertFalse(mod.workflow_has_active_run(
                "owner/repo", "update-feed.yml", "token"
            ))

    def test_main_defers_stale_feed_only_when_refresh_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "listings.json"
            inspections = Path(tmp) / "inspections.json"
            universe = Path(tmp) / "universe.json"
            github_output = Path(tmp) / "github-output.txt"
            stale = datetime.now(timezone.utc) - timedelta(hours=4)
            feed.write_text(
                '{"generated_at":"' + stale.isoformat().replace("+00:00", "Z") + '","jobs":[]}',
                encoding="utf-8",
            )

            def fake_hydrate(**kwargs):
                return "artifact:test"

            argv = [
                "download_latest_feed.py",
                "--repo", "owner/repo",
                "--feed", str(feed),
                "--inspections", str(inspections),
                "--employer-universe", str(universe),
                "--max-feed-age-hours", "3",
                "--defer-stale-feed-if-workflow-active", "update-feed.yml",
                "--github-output", str(github_output),
            ]
            with patch.object(sys, "argv", argv), \
                 patch.object(mod, "hydrate_one", side_effect=fake_hydrate), \
                 patch.object(mod, "workflow_has_active_run", return_value=True):
                self.assertEqual(mod.main(), 0)

            output = github_output.read_text(encoding="utf-8")
            self.assertIn("deploy_ready=false", output)
            self.assertIn("defer_reason=stale_feed_refresh_active", output)

    def test_main_still_fails_stale_feed_when_no_refresh_is_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed = Path(tmp) / "listings.json"
            stale = datetime.now(timezone.utc) - timedelta(hours=4)
            feed.write_text(
                '{"generated_at":"' + stale.isoformat().replace("+00:00", "Z") + '","jobs":[]}',
                encoding="utf-8",
            )
            argv = [
                "download_latest_feed.py",
                "--repo", "owner/repo",
                "--feed", str(feed),
                "--max-feed-age-hours", "3",
                "--defer-stale-feed-if-workflow-active", "update-feed.yml",
                "--github-output", str(Path(tmp) / "github-output.txt"),
            ]
            with patch.object(sys, "argv", argv), \
                 patch.object(mod, "hydrate_one", return_value="artifact:test"), \
                 patch.object(mod, "workflow_has_active_run", return_value=False):
                with self.assertRaisesRegex(RuntimeError, "maximum allowed"):
                    mod.main()

    def test_required_artifact_never_falls_back_to_checked_in_feed(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "listings.json"
            output.write_text('{"generated_at":"2026-09-23T23:43:36Z","jobs":[]}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "required feed artifact"):
                mod.hydrate_one(
                    repo="owner/repo",
                    kind="feed",
                    output=output,
                    token=None,
                    pages_base=None,
                    require_artifact=True,
                )

    def test_existing_file_is_last_known_good_fallback_without_remote_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "listings.json"
            output.write_text('{"jobs": [{"id": "old"}]}', encoding="utf-8")
            source = mod.hydrate_one(
                repo="owner/repo",
                kind="feed",
                output=output,
                token=None,
                pages_base=None,
            )
            self.assertEqual(source, f"fallback:{output}")
            self.assertIn('"old"', output.read_text(encoding="utf-8"))

    def test_latest_artifact_replaces_fallback_atomically_at_file_level(self):
        payload = zip_bytes("nested/listings.json", b'{"jobs": [{"id": "new"}]}')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "listings.json"
            output.write_text('{"jobs": [{"id": "old"}]}', encoding="utf-8")
            with patch.object(
                mod,
                "latest_artifact",
                return_value={"id": 123, "archive_download_url": "https://example.invalid/archive"},
            ), patch.object(mod, "_request_bytes", return_value=payload):
                source = mod.hydrate_one(
                    repo="owner/repo",
                    kind="feed",
                    output=output,
                    token="token",
                    pages_base=None,
                )
            self.assertEqual(source, "artifact:123")
            self.assertIn('"new"', output.read_text(encoding="utf-8"))

    def test_missing_artifact_does_not_destroy_last_known_good_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "workday-inspections.json"
            output.write_text('{"inspections": [{"id": "kept"}]}', encoding="utf-8")
            with patch.object(mod, "latest_artifact", return_value=None):
                source = mod.hydrate_one(
                    repo="owner/repo",
                    kind="inspections",
                    output=output,
                    token="token",
                    pages_base=None,
                )
            self.assertEqual(source, f"fallback:{output}")
            self.assertIn('"kept"', output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
