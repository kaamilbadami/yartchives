#!/usr/bin/env python3
"""Prevent completed Jules issues from being blindly redispatched.

A completed Jules session can leave an issue open when its PR is closed without
merge. If the review-ready label is later removed, the normal dispatcher would
otherwise treat the original issue as fresh work and start a new session from
the original prompt. This guard restores the review-ready state from durable
issue history before dispatch selection.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Iterable

AUTONOMOUS_MARKER = "<!-- autonomous-task -->"
JULES_ACTIVE_LABEL = "jules-session"
JULES_REVIEW_READY_LABEL = "jules-review-ready"
JULES_FAILED_LABEL = "jules-failed"
JULES_FEEDBACK_LABEL = "jules-needs-feedback"

COMPLETED_RE = re.compile(
    r"Jules completed session\s+`?([^\s`]+)`?.*?Pull request:\s*(https://github\.com/[^\s]+/pull/\d+)",
    re.IGNORECASE | re.DOTALL,
)


def label_names(issue: dict[str, Any]) -> frozenset[str]:
    labels: set[str] = set()
    for label in issue.get("labels", []):
        if isinstance(label, str):
            labels.add(label)
        elif isinstance(label, dict) and label.get("name"):
            labels.add(str(label["name"]))
    return frozenset(labels)


def completed_attempt(comments: Iterable[dict[str, Any]]) -> tuple[str, str] | None:
    """Return the newest completed Jules session and PR recorded on the issue."""
    for comment in reversed(list(comments)):
        match = COMPLETED_RE.search(str(comment.get("body") or ""))
        if match:
            return match.group(1), match.group(2).rstrip(").,")
    return None


def should_restore_review_ready(
    issue: dict[str, Any],
    comments: Iterable[dict[str, Any]],
) -> tuple[str, str] | None:
    """Return prior attempt metadata when an issue would otherwise redispatch."""
    if str(issue.get("state") or "open") != "open":
        return None
    if AUTONOMOUS_MARKER not in str(issue.get("body") or ""):
        return None

    labels = label_names(issue)
    if labels & {
        JULES_ACTIVE_LABEL,
        JULES_REVIEW_READY_LABEL,
        JULES_FAILED_LABEL,
        JULES_FEEDBACK_LABEL,
        "blocked",
        "needs-product-decision",
    }:
        return None
    return completed_attempt(comments)


def gh_json(*args: str) -> Any:
    result = subprocess.run(["gh", *args], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def gh_run(*args: str) -> None:
    subprocess.run(["gh", *args], check=True)


def fetch_open_issues(repo: str) -> list[dict[str, Any]]:
    issues = gh_json("api", "--paginate", f"repos/{repo}/issues?state=open&per_page=100")
    if issues and isinstance(issues[0], list):
        flattened = [item for page in issues for item in page]
    else:
        flattened = issues
    return [issue for issue in flattened if "pull_request" not in issue]


def fetch_comments(repo: str, number: int) -> list[dict[str, Any]]:
    comments = gh_json(
        "api",
        "--paginate",
        f"repos/{repo}/issues/{number}/comments?per_page=100",
    )
    if comments and isinstance(comments[0], list):
        return [item for page in comments for item in page]
    return comments


def main() -> int:
    repo = os.environ["REPOSITORY"]
    for issue in fetch_open_issues(repo):
        number = int(issue["number"])
        attempt = should_restore_review_ready(issue, fetch_comments(repo, number))
        if attempt is None:
            continue

        session_id, pr_url = attempt
        gh_run(
            "issue",
            "edit",
            str(number),
            "--repo",
            repo,
            "--add-label",
            JULES_REVIEW_READY_LABEL,
        )
        gh_run(
            "issue",
            "comment",
            str(number),
            "--repo",
            repo,
            "--body",
            (
                f"Restored `{JULES_REVIEW_READY_LABEL}` because this issue already had "
                f"a completed Jules attempt (`{session_id}`) with PR {pr_url}.\n\n"
                "Automatic redispatch is blocked so a closed/rejected attempt is not "
                "silently rerun from the original issue instructions. Narrow or update "
                "the task with the rejection reason before explicitly scheduling another attempt."
            ),
        )
        print(f"Blocked blind redispatch of #{number}; prior completed PR: {pr_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
