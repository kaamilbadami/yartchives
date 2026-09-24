#!/usr/bin/env python3
"""Hydrate runtime feed files from the latest successful GitHub Actions artifacts.

The repository copies remain rollback/local-development fallbacks. When a matching
artifact is available, this script replaces the fallback with the latest validated
runtime payload without requiring generated data commits on main.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

API_ROOT = "https://api.github.com"
DEFAULT_REPO = os.environ.get("GITHUB_REPOSITORY", "kaamilbadami/yartchives")
USER_AGENT = "yartchives-runtime-artifact-loader/1.0"

ARTIFACT_SPECS = {
    "feed": ("update-feed.yml", "yartchives-listings", "listings.json"),
    "inspections": ("refresh-inspections.yml", "yartchives-inspections", "workday-inspections.json"),
}


def _request_json(url: str, token: str | None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def _request_bytes(url: str, token: str | None) -> bytes:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def latest_artifact(repo: str, workflow: str, artifact_name: str, token: str | None) -> dict | None:
    runs_url = (
        f"{API_ROOT}/repos/{repo}/actions/workflows/{workflow}/runs"
        "?branch=main&status=success&per_page=20"
    )
    payload = _request_json(runs_url, token)
    for run in payload.get("workflow_runs", []):
        run_id = run.get("id")
        if not run_id:
            continue
        artifacts = _request_json(
            f"{API_ROOT}/repos/{repo}/actions/runs/{run_id}/artifacts?per_page=100",
            token,
        )
        for artifact in artifacts.get("artifacts", []):
            if artifact.get("name") == artifact_name and not artifact.get("expired", False):
                return artifact
    return None


def hydrate_one(
    *,
    repo: str,
    kind: str,
    output: Path,
    token: str | None,
    pages_base: str | None,
) -> str:
    workflow, artifact_name, member_name = ARTIFACT_SPECS[kind]
    if token:
        try:
            artifact = latest_artifact(repo, workflow, artifact_name, token)
            if artifact:
                raw = _request_bytes(artifact["archive_download_url"], token)
                with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                    candidates = [
                        name for name in archive.namelist()
                        if Path(name).name == member_name
                    ]
                    if not candidates:
                        raise RuntimeError(
                            f"artifact {artifact_name} did not contain {member_name}"
                        )
                    output.parent.mkdir(parents=True, exist_ok=True)
                    output.write_bytes(archive.read(candidates[0]))
                    return f"artifact:{artifact.get('id')}"
        except (OSError, KeyError, RuntimeError, urllib.error.URLError, zipfile.BadZipFile) as exc:
            print(f"warning: could not hydrate {kind} from GitHub artifact: {exc}", file=sys.stderr)

    if pages_base:
        try:
            url = f"{pages_base.rstrip('/')}/data/{member_name}"
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(_request_bytes(url, None))
            return f"pages:{url}"
        except (OSError, urllib.error.URLError) as exc:
            print(f"warning: could not hydrate {kind} from Pages: {exc}", file=sys.stderr)

    if output.exists():
        return f"fallback:{output}"
    raise RuntimeError(f"no usable {kind} runtime data is available")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--feed", type=Path, default=Path("data/listings.json"))
    parser.add_argument("--inspections", type=Path, default=Path("data/workday-inspections.json"))
    parser.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    parser.add_argument(
        "--pages-base",
        default=None,
        help="Optional public Pages base URL used only after artifact retrieval fails.",
    )
    args = parser.parse_args()

    feed_source = hydrate_one(
        repo=args.repo,
        kind="feed",
        output=args.feed,
        token=args.token,
        pages_base=args.pages_base,
    )
    inspection_source = hydrate_one(
        repo=args.repo,
        kind="inspections",
        output=args.inspections,
        token=args.token,
        pages_base=args.pages_base,
    )
    print(f"Hydrated feed from {feed_source}")
    print(f"Hydrated inspections from {inspection_source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
