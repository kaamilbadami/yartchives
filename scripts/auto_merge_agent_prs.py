#!/usr/bin/env python3
"""Safely merge completed autonomous-agent pull requests after exact-head CI passes."""

from __future__ import annotations

import json
import os
import re
import subprocess
from fnmatch import fnmatch
from typing import Any, Callable, Iterable

QUALITY_WORKFLOW = "Quality checks"
TERMINAL_AGENT_LABELS = {"jules-review-ready", "codex-review-ready"}
REQUIRED_ISSUE_LABEL = "autonomous-backlog"
BLOCKED_PATH_PATTERNS = (
    ".github/**",
    "requirements.txt",
    "audit/samples/**",
    "scripts/dispatch_autonomous_issues.py",
    "scripts/triage_workflow_failures.py",
    "scripts/auto_merge_agent_prs.py",
)
CLOSING_ISSUE_RE = re.compile(
    r"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b"
)
JULES_REVIEW_READY_LABEL = "jules-review-ready"
GITHUB_ACTIONS_BOT = "github-actions[bot]"


def label_names(issue: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for label in issue.get("labels", []):
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and label.get("name"):
            names.add(str(label["name"]))
    return names


def linked_issue_number(body: str) -> int | None:
    match = CLOSING_ISSUE_RE.search(body or "")
    return int(match.group(1)) if match else None


def completed_jules_pr_number(
    comments: Iterable[dict[str, Any]], repo: str
) -> int | None:
    """Return the PR number from a trusted Jules completion comment."""
    pattern = re.compile(
        rf"(?m)^Pull request:\s+https://github\.com/{re.escape(repo)}/pull/(\d+)\s*$"
    )
    for comment in reversed(list(comments)):
        user = comment.get("user") or {}
        if str(user.get("login") or "") != GITHUB_ACTIONS_BOT:
            continue
        body = str(comment.get("body") or "")
        if "Jules completed session `" not in body:
            continue
        match = pattern.search(body)
        if match:
            return int(match.group(1))
    return None


def review_ready_issue_by_pr(
    issues: Iterable[dict[str, Any]],
    *,
    repo: str,
    load_comments: Callable[[int], list[dict[str, Any]]],
) -> dict[int, dict[str, Any]]:
    """Map exact Jules output PRs back to their authorized review-ready issues."""
    mapping: dict[int, dict[str, Any]] = {}
    for issue in issues:
        if "pull_request" in issue:
            continue
        labels = label_names(issue)
        if (
            str(issue.get("state") or "") != "open"
            or REQUIRED_ISSUE_LABEL not in labels
            or JULES_REVIEW_READY_LABEL not in labels
        ):
            continue
        number = int(issue.get("number") or 0)
        pr_number = completed_jules_pr_number(load_comments(number), repo)
        if pr_number is None:
            continue
        existing = mapping.get(pr_number)
        if existing is not None and int(existing.get("number") or 0) != number:
            raise RuntimeError(
                f"PR #{pr_number} is recorded as Jules output for multiple issues"
            )
        mapping[pr_number] = issue
    return mapping


def ensure_closing_link(pr: dict[str, Any], issue_number: int) -> str:
    """Return a PR body normalized with an explicit closing issue reference."""
    body = str(pr.get("body") or "").rstrip()
    if linked_issue_number(body) is not None:
        return body
    closing = f"Closes #{issue_number}"
    return f"{body}\n\n{closing}" if body else closing


def blocked_changed_paths(paths: Iterable[str]) -> list[str]:
    blocked: list[str] = []
    for path in paths:
        if any(fnmatch(path, pattern) for pattern in BLOCKED_PATH_PATTERNS):
            blocked.append(path)
    return blocked


def exact_head_quality_passed(runs: Iterable[dict[str, Any]], head_sha: str) -> bool:
    return any(
        str(run.get("name") or "") == QUALITY_WORKFLOW
        and str(run.get("head_sha") or "") == head_sha
        and str(run.get("status") or "") == "completed"
        and str(run.get("conclusion") or "") == "success"
        for run in runs
    )


def exact_head_quality_present(runs: Iterable[dict[str, Any]], head_sha: str) -> bool:
    return any(
        str(run.get("name") or "") == QUALITY_WORKFLOW
        and str(run.get("head_sha") or "") == head_sha
        for run in runs
    )


def exact_head_quality_action_required(
    runs: Iterable[dict[str, Any]], head_sha: str
) -> bool:
    return any(
        str(run.get("name") or "") == QUALITY_WORKFLOW
        and str(run.get("head_sha") or "") == head_sha
        and str(run.get("status") or "") == "completed"
        and str(run.get("conclusion") or "") == "action_required"
        for run in runs
    )


def exact_head_quality_in_flight(
    runs: Iterable[dict[str, Any]], head_sha: str
) -> bool:
    return any(
        str(run.get("name") or "") == QUALITY_WORKFLOW
        and str(run.get("head_sha") or "") == head_sha
        and str(run.get("status") or "") in {"queued", "in_progress", "pending", "requested", "waiting"}
        for run in runs
    )


def autonomous_issue_ready(issue: dict[str, Any]) -> bool:
    labels = label_names(issue)
    return (
        str(issue.get("state") or "") == "open"
        and REQUIRED_ISSUE_LABEL in labels
        and bool(labels & TERMINAL_AGENT_LABELS)
        and "blocked" not in labels
        and "needs-product-decision" not in labels
    )


def eligible_pr(
    pr: dict[str, Any],
    *,
    repo: str,
    issue: dict[str, Any],
    changed_paths: Iterable[str],
    quality_runs: Iterable[dict[str, Any]],
    require_quality: bool = True,
) -> tuple[bool, str]:
    if str(pr.get("state") or "") != "open":
        return False, "pull request is not open"
    if bool(pr.get("draft")):
        return False, "pull request is a draft"

    head = pr.get("head") or {}
    head_repo = (head.get("repo") or {}).get("full_name")
    if head_repo != repo:
        return False, "pull request branch is not in the source repository"

    issue_number = linked_issue_number(str(pr.get("body") or ""))
    if issue_number is None:
        return False, "pull request does not close an issue"
    if int(issue.get("number") or 0) != issue_number:
        return False, "linked issue does not match fetched issue"
    if not autonomous_issue_ready(issue):
        return False, "linked autonomous issue is not ready for merge"

    blocked = blocked_changed_paths(changed_paths)
    if blocked:
        return False, f"protected path changed: {blocked[0]}"

    head_sha = str(head.get("sha") or "")
    if not head_sha:
        return False, "pull request has no head commit"
    if require_quality and not exact_head_quality_passed(quality_runs, head_sha):
        return False, "exact pull request head has not passed Quality checks"

    return True, "eligible"


def quality_runs_api_path(repo: str, head_sha: str) -> str:
    return f"repos/{repo}/actions/runs?head_sha={head_sha}&per_page=100"


def gh_json(*args: str) -> Any:
    result = subprocess.run(["gh", *args], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def gh_run(*args: str) -> None:
    subprocess.run(["gh", *args], check=True)


def update_pull_request_branch(repo: str, number: int, head_sha: str) -> tuple[bool, str]:
    result = subprocess.run(
        [
            "gh",
            "api",
            "--method",
            "PUT",
            f"repos/{repo}/pulls/{number}/update-branch",
            "-f",
            f"expected_head_sha={head_sha}",
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return True, ""
    detail = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    lowered = detail.casefold()
    if "merge conflict between base and head" in lowered or (
        "http 422" in lowered and "merge conflict" in lowered
    ):
        return False, detail
    raise subprocess.CalledProcessError(
        result.returncode,
        result.args,
        output=result.stdout,
        stderr=result.stderr,
    )


def flatten_pages(pages: Any) -> list[Any]:
    if not isinstance(pages, list):
        raise TypeError("paginated response must be a list")
    rows: list[Any] = []
    for page in pages:
        if not isinstance(page, list):
            raise TypeError("each paginated page must be a list")
        rows.extend(page)
    return rows


def gh_paginated_json(*args: str) -> list[Any]:
    result = subprocess.run(
        ["gh", *args, "--paginate", "--slurp"],
        check=True,
        text=True,
        capture_output=True,
    )
    return flatten_pages(json.loads(result.stdout))


def main() -> int:
    repo = os.environ["REPOSITORY"]
    pull_requests = gh_paginated_json(
        "api",
        f"repos/{repo}/pulls?state=open&per_page=100",
    )
    pull_requests.sort(key=lambda pr: int(pr["number"]))

    review_ready_issues = gh_paginated_json(
        "api",
        f"repos/{repo}/issues?state=open&labels={JULES_REVIEW_READY_LABEL}&per_page=100",
    )
    recovered_issue_by_pr = review_ready_issue_by_pr(
        review_ready_issues,
        repo=repo,
        load_comments=lambda issue_number: gh_paginated_json(
            "api",
            f"repos/{repo}/issues/{issue_number}/comments?per_page=100",
        ),
    )

    merged_count = 0

    for pr in pull_requests:
        number = int(pr["number"])
        issue_number = linked_issue_number(str(pr.get("body") or ""))
        issue = None
        if issue_number is None:
            issue = recovered_issue_by_pr.get(number)
            if issue is None:
                continue
            issue_number = int(issue["number"])
            normalized_body = ensure_closing_link(pr, issue_number)
            gh_run(
                "api",
                "--method", "PATCH",
                f"repos/{repo}/pulls/{number}",
                "-f", f"body={normalized_body}",
            )
            pr["body"] = normalized_body
            print(
                f"Recovered Jules linkage for PR #{number} from review-ready issue "
                f"#{issue_number} and added 'Closes #{issue_number}'."
            )

        if issue is None:
            issue = gh_json("api", f"repos/{repo}/issues/{issue_number}")
        files = gh_paginated_json(
            "api",
            f"repos/{repo}/pulls/{number}/files?per_page=100",
        )
        head_sha = str((pr.get("head") or {}).get("sha") or "")
        runs = gh_json(
            "api",
            quality_runs_api_path(repo, head_sha),
        ).get("workflow_runs", [])

        changed_paths = [str(row.get("filename") or "") for row in files]
        pre_ci_eligible, reason = eligible_pr(
            pr,
            repo=repo,
            issue=issue,
            changed_paths=changed_paths,
            quality_runs=runs,
            require_quality=False,
        )
        if not pre_ci_eligible:
            print(f"Skipping PR #{number}: {reason}.")
            continue

        head_ref = str((pr.get("head") or {}).get("ref") or "")
        if not exact_head_quality_passed(runs, head_sha):
            if exact_head_quality_in_flight(runs, head_sha):
                print(f"PR #{number} already has exact-head Quality checks in flight.")
                continue
            should_redispatch = (
                exact_head_quality_action_required(runs, head_sha)
                or not exact_head_quality_present(runs, head_sha)
            )
            if should_redispatch and head_ref:
                gh_run(
                    "workflow", "run", "quality.yml",
                    "--repo", repo,
                    "--ref", head_ref,
                )
                print(
                    f"Dispatched Quality checks manually for PR #{number} because the "
                    "exact-head run was missing or required manual approval."
                )
                continue

        eligible, reason = eligible_pr(
            pr,
            repo=repo,
            issue=issue,
            changed_paths=changed_paths,
            quality_runs=runs,
        )
        if not eligible:
            print(f"Skipping PR #{number}: {reason}.")
            continue

        base_ref = str((pr.get("base") or {}).get("ref") or "main")
        comparison = gh_json("api", f"repos/{repo}/compare/{base_ref}...{head_sha}")
        if int(comparison.get("behind_by") or 0) > 0:
            updated, detail = update_pull_request_branch(repo, number, head_sha)
            if not updated:
                print(
                    f"Skipping PR #{number}: branch cannot be updated automatically because "
                    "it conflicts with current base. Continuing with later pull requests."
                )
                if detail:
                    print(detail)
                continue
            if not head_ref:
                raise RuntimeError(f"PR #{number} has no head branch for fresh CI")
            gh_run(
                "workflow", "run", "quality.yml",
                "--repo", repo,
                "--ref", head_ref,
            )
            print(
                f"Updated PR #{number} onto current {base_ref} and dispatched fresh "
                "Quality checks on the updated branch."
            )
            continue

        fresh = gh_json("api", f"repos/{repo}/pulls/{number}")
        if fresh.get("mergeable") is not True or str(fresh.get("mergeable_state") or "") not in {
            "clean",
            "has_hooks",
            "unstable",
        }:
            print(
                f"Skipping PR #{number}: GitHub does not currently report it as safely mergeable."
            )
            continue

        gh_run(
            "api",
            "--method", "PUT",
            f"repos/{repo}/pulls/{number}/merge",
            "-f", "merge_method=squash",
            "-f", f"sha={head_sha}",
        )
        print(f"Squash-merged eligible autonomous PR #{number}.")
        merged_count += 1

    if merged_count:
        print(f"Squash-merged {merged_count} eligible autonomous pull request(s).")
    else:
        print("No autonomous pull request is currently eligible for automatic merge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
