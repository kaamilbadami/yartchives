import argparse
import json
import os
import sys
import urllib.error
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
            return data.get("workflow_runs") or []
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

    active_runs = [
        parse_iso(r["created_at"]) for r in runs
        if r.get("status") in ("in_progress", "queued", "pending") and r.get("created_at")
    ]

    if active_runs:
        latest_active = max(active_runs)
        active_duration = now - latest_active
        if active_duration <= timedelta(minutes=allowed_progress_minutes):
            return True, f"Freshness breached (age {feed_age}), but a refresh is actively in progress (started {active_duration} ago). Suppressing duplicate dispatch."

    return False, f"Feed is STALE. Published age: {feed_age} > {threshold}. No on-time active refresh is replacing it."


def dispatch_feed_refresh(repo: str, token: str | None, ref: str = "main") -> tuple[bool, str]:
    if not token:
        return False, "Cannot dispatch feed refresh: GITHUB_TOKEN is unavailable."

    url = f"https://api.github.com/repos/{repo}/actions/workflows/update-feed.yml/dispatches"
    payload = json.dumps({"ref": ref}).encode("utf-8")
    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 204:
                return True, f"Dispatched Update opportunity feed on {ref}."
            return False, f"Feed refresh dispatch returned unexpected HTTP {response.status}."
    except urllib.error.HTTPError as e:
        return False, f"Feed refresh dispatch failed with HTTP {e.code}."
    except Exception as e:
        return False, f"Feed refresh dispatch failed: {e}"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", default="data/listings.json", help="Path to listings.json")
    parser.add_argument("--threshold-hours", type=float, default=2.0)
    parser.add_argument("--allowed-progress-minutes", type=float, default=45.0)
    parser.add_argument("--alert-hours", type=float, default=3.0)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "kaamilbadami/yartchives"))
    args = parser.parse_args()

    try:
        with open(args.feed, "r", encoding="utf-8") as f:
            data = json.load(f)
        generated_at = parse_iso(data["generated_at"])
    except Exception as e:
        print(f"Failed to read feed generated_at: {e}", file=sys.stderr)
        return 1

    now = now_utc()
    feed_age = now - generated_at
    if "GITHUB_OUTPUT" in os.environ:
        alert_required = feed_age >= timedelta(hours=args.alert_hours)
        alert_tag = f"yartchives-feed-stale-{generated_at.strftime('%Y%m%dT%H%M%SZ')}"
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
            output.write(f"feed_age_seconds={int(feed_age.total_seconds())}\n")
            output.write(f"feed_generated_at={generated_at.isoformat()}\n")
            output.write(f"alert_required={'true' if alert_required else 'false'}\n")
            output.write(f"alert_tag={alert_tag}\n")

    token = os.environ.get("GITHUB_TOKEN")
    runs = get_workflow_runs(args.repo, token)

    ok, message = evaluate_freshness(
        generated_at=generated_at,
        runs=runs,
        now=now,
        threshold_hours=args.threshold_hours,
        allowed_progress_minutes=args.allowed_progress_minutes,
    )

    if ok:
        print(message)
        return 0

    dispatched, dispatch_message = dispatch_feed_refresh(args.repo, token)
    if dispatched:
        print(f"{message} {dispatch_message}")
        return 0

    print(f"{message} {dispatch_message}", file=sys.stderr)
    return 1

if __name__ == "__main__":
    sys.exit(main())
