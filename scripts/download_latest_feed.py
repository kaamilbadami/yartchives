#!/usr/bin/env python3
"""Hydrate runtime feed files from the latest publishable GitHub Actions artifacts.

The repository copies remain rollback/local-development fallbacks. When a matching
artifact is available, this script replaces the fallback with the latest validated
runtime payload without requiring generated data commits on main.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import io
import json
import os
import sys
import urllib.error
import urllib.request
from urllib.parse import urlsplit
import zipfile
from pathlib import Path

API_ROOT = "https://api.github.com"
DEFAULT_REPO = os.environ.get("GITHUB_REPOSITORY", "kaamilbadami/yartchives")
USER_AGENT = "yartchives-runtime-artifact-loader/1.0"

ARTIFACT_SPECS = {
    "feed": ("update-feed.yml", "yartchives-listings", "listings.json"),
    "inspections": ("refresh-inspections.yml", "yartchives-inspections", "workday-inspections.json"),
    "employer_universe": ("update-feed.yml", "yartchives-employer-universe", "employer_universe.json"),
}


def _request_json(url: str, token: str | None) -> dict:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


class _SafeArtifactRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Do not forward GitHub credentials to the artifact storage redirect host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        if urlsplit(req.full_url).netloc != urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
            redirected.remove_header("X-GitHub-Api-Version")
        return redirected


def _request_bytes(url: str, token: str | None) -> bytes:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": USER_AGENT}
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    request = urllib.request.Request(url, headers=headers)
    opener = urllib.request.build_opener(_SafeArtifactRedirectHandler())
    with opener.open(request, timeout=60) as response:
        return response.read()


def latest_artifact(repo: str, workflow: str, artifact_name: str, token: str | None) -> dict | None:
    runs_url = (
        f"{API_ROOT}/repos/{repo}/actions/workflows/{workflow}/runs"
        "?branch=main&per_page=20"
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
    require_artifact: bool = False,
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

    if require_artifact:
        raise RuntimeError(f"required {kind} artifact could not be hydrated")

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
    parser.add_argument("--employer-universe", type=Path, default=Path("employer_universe.json"))
    parser.add_argument("--token", default=os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    parser.add_argument("--require-feed-artifact", action="store_true")
    parser.add_argument("--max-feed-age-hours", type=float, default=None)
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
        require_artifact=args.require_feed_artifact,
    )
    if args.max_feed_age_hours is not None:
        payload = json.loads(args.feed.read_text(encoding="utf-8"))
        generated_at = payload.get("generated_at")
        if not generated_at:
            raise RuntimeError("feed is missing generated_at")
        generated = datetime.fromisoformat(str(generated_at).replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds() / 3600
        if age_hours < 0 or age_hours > args.max_feed_age_hours:
            raise RuntimeError(
                f"feed generated_at is {age_hours:.2f} hours old; "
                f"maximum allowed is {args.max_feed_age_hours:.2f}"
            )

    inspection_source = hydrate_one(
        repo=args.repo,
        kind="inspections",
        output=args.inspections,
        token=args.token,
        pages_base=args.pages_base,
    )
    employer_universe_source = hydrate_one(
        repo=args.repo,
        kind="employer_universe",
        output=args.employer_universe,
        token=args.token,
        pages_base=None,
    )
    print(f"Hydrated feed from {feed_source}")
    print(f"Hydrated inspections from {inspection_source}")
    print(f"Hydrated employer universe from {employer_universe_source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
