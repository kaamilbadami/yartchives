import importlib.util
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

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
