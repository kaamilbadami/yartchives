import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def parse_iso(dt_str: str) -> datetime:
    if dt_str.endswith("Z"):
        dt_str = dt_str[:-1] + "+00:00"
    return datetime.fromisoformat(dt_str)

def get_workflow_runs(repo: str, token: str | None) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repo}/actions/workflows/update-feed.yml/runs?per_page=10"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("workflow_runs", [])
    except Exception as e:
        print(f"Warning: Failed to fetch workflow runs: {e}", file=sys.stderr)
        return []

def evaluate_freshness(
    generated_at: datetime,
    runs: list[dict[str, Any]],
    now: datetime,
    threshold_hours: float = 2.0,
    allowed_progress_minutes: float = 45.0,
) -> tuple[bool, str]:
    feed_age = now - generated_at
    threshold = timedelta(hours=threshold_hours)

    if feed_age <= threshold:
        return True, f"Feed is fresh. Published age: {feed_age} <= {threshold}"

    success_runs = [
        parse_iso(r["updated_at"]) for r in runs
        if r.get("status") == "completed" and r.get("conclusion") == "success"
    ]

    if success_runs:
        latest_success = max(success_runs)
        success_age = now - latest_success
        if success_age <= threshold:
            return True, f"Feed is fresh (unchanged content). Published age > {threshold}, but latest successful verification was {success_age} ago."

    active_runs = [
        parse_iso(r["created_at"]) for r in runs
        if r.get("status") in ("in_progress", "queued", "pending")
    ]

    if active_runs:
        latest_active = max(active_runs)
        active_duration = now - latest_active
        if active_duration <= timedelta(minutes=allowed_progress_minutes):
            return True, f"Freshness breached (age {feed_age}), but an on-time refresh is actively in progress (started {active_duration} ago). Suppressing alert."

    return False, f"Feed is STALE. Published age: {feed_age} > {threshold}. No recent successful runs or on-time active refreshes."

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", default="data/listings.json", help="Path to listings.json")
    parser.add_argument("--threshold-hours", type=float, default=2.0)
    parser.add_argument("--allowed-progress-minutes", type=float, default=45.0)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "kaamilbadami/yartchives"))
    args = parser.parse_args()

    try:
        with open(args.feed, "r", encoding="utf-8") as f:
            data = json.load(f)
        generated_at = parse_iso(data["generated_at"])
    except Exception as e:
        print(f"Failed to read feed generated_at: {e}", file=sys.stderr)
        return 1

    runs = get_workflow_runs(args.repo, os.environ.get("GITHUB_TOKEN"))

    ok, message = evaluate_freshness(
        generated_at=generated_at,
        runs=runs,
        now=now_utc(),
        threshold_hours=args.threshold_hours,
        allowed_progress_minutes=args.allowed_progress_minutes,
    )

    if ok:
        print(message)
        return 0
    else:
        print(message, file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
