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
LIFECYCLE_PRIORITY_PATTERNS = (
    ".github/workflows/auto-merge-agent-prs.yml",
    ".github/workflows/autonomous-dispatch.yml",
    ".github/workflows/triage-workflow-failures.yml",
    "scripts/auto_merge_agent_prs.py",
    "scripts/dispatch_autonomous_issues.py",
    "scripts/triage_workflow_failures.py",
)
CI_PRIORITY_PATTERNS = (".github/workflows/**",)
CLOSING_ISSUE_RE = re.compile(
    r"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b"
)
JULES_REVIEW_READY_LABEL = "jules-review-ready"
GITHUB_ACTIONS_BOT = "github-actions[bot]"
OWNER_AUTHORIZED_AUTOMERGE_MARKER = "<!-- owner-authorized-automerge -->"
SAFE_MERGEABLE_STATES = {"clean", "has_hooks", "unstable", "behind"}
MAINTENANCE_TEST_BY_PATH = {
    "scripts/dispatch_autonomous_issues.py": "tests/test_dispatch_autonomous_issues.py",
    "scripts/triage_workflow_failures.py": "tests/test_triage_workflow_failures.py",
}
MAINTENANCE_ALLOWED_PATHS = frozenset(
    {*MAINTENANCE_TEST_BY_PATH, *MAINTENANCE_TEST_BY_PATH.values()}
)
MAINTENANCE_MAX_FILES = 4
MAINTENANCE_MAX_CHANGES = 250
GENERATED_ARTIFACT_PATTERNS = (
    "__pycache__/**",
    "**/__pycache__/**",
    "*.pyc",
    "**/*.pyc",
    ".pytest_cache/**",
    "**/.pytest_cache/**",
)
CONTROL_PLANE_STATIC_ALLOWED_PATHS = frozenset({
    "scripts/queue_coverage_gap.py",
    "tests/deploy-assets.test.cjs",
    "tests/test_queue_coverage_gap.py",
})
CONTROL_PLANE_LEGACY_REQUIRED_TEST = "tests/deploy-assets.test.cjs"
CONTROL_PLANE_REMOVABLE_SCRATCH_PATTERNS = ("patch_*.py",)
CONTROL_PLANE_MAX_FILES = 8
CONTROL_PLANE_MAX_CHANGES = 500
SUPERSEDE_PROTECTED_MAX_FILES = 12
SUPERSEDE_PROTECTED_MAX_CHANGES = 1000
SUPERSEDE_MARKER_TEMPLATE = "<!-- supersedes-stale-pr: {pr_number} -->"


def label_names(issue: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for label in issue.get("labels", []):
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and label.get("name"):
            names.add(str(label["name"]))
    return names


def owner_authorized_pr(
    pr: dict[str, Any],
    repo: str,
    comments: Iterable[dict[str, Any]] = (),
) -> bool:
    """Return whether the repository owner explicitly pre-authorized this PR to merge when green."""
    if str(pr.get("state") or "") != "open" or bool(pr.get("draft")):
        return False
    owner = repo.split("/", 1)[0]
    if str((pr.get("user") or {}).get("login") or "") != owner:
        return False
    head = pr.get("head") or {}
    if str((head.get("repo") or {}).get("full_name") or "") != repo:
        return False
    if OWNER_AUTHORIZED_AUTOMERGE_MARKER in str(pr.get("body") or ""):
        return True
    for comment in reversed(list(comments)):
        user = comment.get("user") or {}
        if str(user.get("login") or "") != owner:
            continue
        if OWNER_AUTHORIZED_AUTOMERGE_MARKER in str(comment.get("body") or ""):
            return True
    return False


def linked_issue_number(body: str) -> int | None:
    match = CLOSING_ISSUE_RE.search(body or "")
    return int(match.group(1)) if match else None


def completed_jules_output(
    comments: Iterable[dict[str, Any]],
) -> tuple[int, str, int, str] | None:
    """Return durable (issue, session, PR, head) identity from a trusted bot comment."""
    pattern = re.compile(
        r"<!--\s*jules-output:\s*issue=(\d+)\s+session=([^\s>]+)\s+"
        r"pr=(\d+)\s+head=([0-9a-fA-F]{40})\s*-->"
    )
    for comment in reversed(list(comments)):
        user = comment.get("user") or {}
        if str(user.get("login") or "") != GITHUB_ACTIONS_BOT:
            continue
        match = pattern.search(str(comment.get("body") or ""))
        if match:
            return (
                int(match.group(1)),
                match.group(2),
                int(match.group(3)),
                match.group(4).lower(),
            )
    return None


def completed_jules_pr_number(
    comments: Iterable[dict[str, Any]], repo: str
) -> int | None:
    """Backward-compatible PR lookup for historical trusted completion comments."""
    output = completed_jules_output(comments)
    if output is not None:
        return output[2]
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


def legacy_completed_jules_output(
    comments: Iterable[dict[str, Any]], repo: str
) -> tuple[str, int] | None:
    pattern = re.compile(
        rf"Jules completed session `([^`]+)`.*?"
        rf"Pull request:\s*https://github\.com/{re.escape(repo)}/pull/(\d+)",
        re.IGNORECASE | re.DOTALL,
    )
    for comment in reversed(list(comments)):
        user = comment.get("user") or {}
        if str(user.get("login") or "") != GITHUB_ACTIONS_BOT:
            continue
        match = pattern.search(str(comment.get("body") or ""))
        if match:
            return match.group(1), int(match.group(2))
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
        comments = load_comments(number)
        output = completed_jules_output(comments)
        if output is not None:
            recorded_issue, session_id, pr_number, head_sha = output
            if recorded_issue != number:
                raise RuntimeError(
                    f"Durable Jules output for issue #{number} records issue #{recorded_issue}"
                )
            issue["_jules_output"] = {
                "issue": recorded_issue,
                "session": session_id,
                "pr": pr_number,
                "head": head_sha,
                "durable": True,
            }
        else:
            legacy = legacy_completed_jules_output(comments, repo)
            if legacy is None:
                continue
            session_id, pr_number = legacy
            issue["_jules_output"] = {
                "issue": number,
                "session": session_id,
                "pr": pr_number,
                "head": "",
                "durable": False,
            }
        existing = mapping.get(pr_number)
        if existing is not None and int(existing.get("number") or 0) != number:
            raise RuntimeError(
                f"PR #{pr_number} is recorded as Jules output for multiple issues"
            )
        mapping[pr_number] = issue
    return mapping


def durable_output_for_issue(
    issue: dict[str, Any],
    *,
    load_comments: Callable[[int], list[dict[str, Any]]],
) -> tuple[int, str, int, str] | None:
    number = int(issue.get("number") or 0)
    output = completed_jules_output(load_comments(number))
    if output is None:
        return None
    if output[0] != number:
        raise RuntimeError(
            f"Durable Jules output for issue #{number} records issue #{output[0]}"
        )
    return output


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


def generated_artifact_paths(paths: Iterable[str]) -> list[str]:
    return [
        path
        for path in paths
        if any(fnmatch(path, pattern) for pattern in GENERATED_ARTIFACT_PATTERNS)
    ]


def workflow_regression_test_candidates(path: str) -> frozenset[str]:
    """Return conventional regression-test paths for one workflow file."""
    name = path.rsplit("/", 1)[-1]
    stem = re.sub(r"\.ya?ml$", "", name)
    normalized = stem.replace("-", "_")
    return frozenset(
        {
            f"tests/test_{normalized}_workflow.py",
            f"tests/test_{normalized}.py",
            f"tests/{stem}.test.cjs",
        }
    )


def control_plane_pr_eligible(
    pr: dict[str, Any],
    *,
    repo: str,
    files: Iterable[dict[str, Any]],
    quality_runs: Iterable[dict[str, Any]],
    require_quality: bool = True,
) -> tuple[bool, str]:
    """Allow bounded workflow/control-plane changes with an explicit test contract."""
    if str(pr.get("state") or "") != "open":
        return False, "pull request is not open"
    if bool(pr.get("draft")):
        return False, "pull request is a draft"

    head = pr.get("head") or {}
    if (head.get("repo") or {}).get("full_name") != repo:
        return False, "pull request branch is not in the source repository"

    rows = list(files)
    paths = {str(row.get("filename") or "") for row in rows if row.get("filename")}
    if not paths:
        return False, "control-plane lane has no changed paths"
    if generated_artifact_paths(paths):
        return False, "control-plane lane contains generated artifacts"

    workflow_paths = {
        path for path in paths if fnmatch(path, ".github/workflows/**")
    }
    if not workflow_paths:
        return False, "control-plane lane does not change a workflow"

    conventional_tests = set().union(
        *(workflow_regression_test_candidates(path) for path in workflow_paths)
    )
    scratch_removals = {
        str(row.get("filename") or "")
        for row in rows
        if str(row.get("status") or "") == "removed"
        and any(
            fnmatch(str(row.get("filename") or ""), pattern)
            for pattern in CONTROL_PLANE_REMOVABLE_SCRATCH_PATTERNS
        )
    }
    allowed_paths = (
        workflow_paths
        | conventional_tests
        | CONTROL_PLANE_STATIC_ALLOWED_PATHS
        | scratch_removals
    )
    if not paths <= allowed_paths:
        return False, "control-plane lane contains a non-allowlisted path"

    missing_tests = [
        path
        for path in sorted(workflow_paths)
        if not (
            workflow_regression_test_candidates(path) & paths
            or CONTROL_PLANE_LEGACY_REQUIRED_TEST in paths
        )
    ]
    if missing_tests:
        expected = sorted(workflow_regression_test_candidates(missing_tests[0]))[0]
        return False, f"control-plane change lacks paired regression test: {expected}"
    if len(paths) > CONTROL_PLANE_MAX_FILES:
        return False, "control-plane lane changes too many files"
    if sum(int(row.get("changes") or 0) for row in rows) > CONTROL_PLANE_MAX_CHANGES:
        return False, "control-plane lane diff is too large"

    head_sha = str(head.get("sha") or "")
    if not head_sha:
        return False, "pull request has no head commit"
    if require_quality and not exact_head_quality_passed(quality_runs, head_sha):
        return False, "exact pull request head has not passed Quality checks"
    return True, "control-plane-eligible"


def pull_request_queue_priority(paths: Iterable[str]) -> int:
    paths = tuple(paths)
    if any(
        fnmatch(path, pattern)
        for path in paths
        for pattern in LIFECYCLE_PRIORITY_PATTERNS
    ):
        return 0
    if any(
        fnmatch(path, pattern)
        for path in paths
        for pattern in CI_PRIORITY_PATTERNS
    ):
        return 1
    return 2


def prioritize_pull_requests(
    pull_requests: Iterable[dict[str, Any]],
    changed_paths_by_pr: dict[int, list[str]],
) -> list[dict[str, Any]]:
    return sorted(
        pull_requests,
        key=lambda pr: (
            pull_request_queue_priority(
                changed_paths_by_pr.get(int(pr["number"]), [])
            ),
            int(pr["number"]),
        ),
    )


def exact_head_quality_passed(runs: Iterable[dict[str, Any]], head_sha: str) -> bool:
    return any(
        str(run.get("name") or "") == QUALITY_WORKFLOW
        and str(run.get("head_sha") or "") == head_sha
        and str(run.get("status") or "") == "completed"
        and str(run.get("conclusion") or "") == "success"
        for run in runs
    )


def trusted_repair_head_allowed(
    commits: Iterable[dict[str, Any]],
    *,
    recorded_head: str,
    current_head: str,
    repo: str,
    quality_runs: Iterable[dict[str, Any]],
) -> bool:
    """Allow a durable Jules head to advance only through trusted, green repairs."""
    rows = list(commits)
    shas = [str(row.get("sha") or "") for row in rows]
    if (
        not recorded_head
        or not current_head
        or recorded_head not in shas
        or current_head not in shas
        or shas[-1] != current_head
        or shas.index(recorded_head) >= shas.index(current_head)
        or not exact_head_quality_passed(quality_runs, current_head)
    ):
        return False

    owner = repo.split("/", 1)[0]
    trusted = {owner, GITHUB_ACTIONS_BOT, "google-labs-jules[bot]"}
    repair_commits = rows[shas.index(recorded_head) + 1 :]
    if not repair_commits:
        return False
    for commit in repair_commits:
        author = str((commit.get("author") or {}).get("login") or "")
        committer = str((commit.get("committer") or {}).get("login") or "")
        if author not in trusted or committer not in trusted:
            return False
    return True


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


def superseded_action_required_run_ids(
    runs: Iterable[dict[str, Any]], head_sha: str
) -> list[int]:
    """Return approval-gated PR runs superseded by exact-head manual Quality CI."""
    rows = list(runs)
    replacement_exists = any(
        str(run.get("name") or "") == QUALITY_WORKFLOW
        and str(run.get("head_sha") or "") == head_sha
        and str(run.get("event") or "") == "workflow_dispatch"
        for run in rows
    )
    if not replacement_exists:
        return []

    run_ids: list[int] = []
    for run in rows:
        if (
            str(run.get("name") or "") == QUALITY_WORKFLOW
            and str(run.get("head_sha") or "") == head_sha
            and str(run.get("event") or "") == "pull_request"
            and str(run.get("status") or "") == "completed"
            and str(run.get("conclusion") or "") == "action_required"
            and run.get("id") is not None
        ):
            run_ids.append(int(run["id"]))
    return run_ids


def delete_superseded_action_required_runs(
    repo: str,
    runs: Iterable[dict[str, Any]],
    head_sha: str,
) -> list[int]:
    """Delete obsolete approval-gated runs only after replacement CI exists."""
    run_ids = superseded_action_required_run_ids(runs, head_sha)
    for run_id in run_ids:
        gh_run(
            "api",
            "--method", "DELETE",
            f"repos/{repo}/actions/runs/{run_id}",
        )
    return run_ids


def autonomous_issue_ready(issue: dict[str, Any]) -> bool:
    labels = label_names(issue)
    return (
        str(issue.get("state") or "") == "open"
        and REQUIRED_ISSUE_LABEL in labels
        and bool(labels & TERMINAL_AGENT_LABELS)
        and "blocked" not in labels
        and "needs-product-decision" not in labels
    )


def conflicted_pr_can_supersede(issue: dict[str, Any] | None) -> bool:
    """Only trusted review-ready autonomous issues may be re-derived from current main."""
    return issue is not None and autonomous_issue_ready(issue)


def maintenance_pr_eligible(
    pr: dict[str, Any],
    *,
    repo: str,
    files: Iterable[dict[str, Any]],
    quality_runs: Iterable[dict[str, Any]],
    require_quality: bool = True,
) -> tuple[bool, str]:
    """Allow only small, test-paired dispatcher/triage repairs through the maintenance lane."""
    if str(pr.get("state") or "") != "open":
        return False, "pull request is not open"
    if bool(pr.get("draft")):
        return False, "pull request is a draft"

    head = pr.get("head") or {}
    head_repo = (head.get("repo") or {}).get("full_name")
    if head_repo != repo:
        return False, "pull request branch is not in the source repository"

    rows = list(files)
    paths = {str(row.get("filename") or "") for row in rows if row.get("filename")}
    if not paths or not paths <= MAINTENANCE_ALLOWED_PATHS:
        return False, "maintenance lane contains a non-maintenance path"
    if len(paths) > MAINTENANCE_MAX_FILES:
        return False, "maintenance lane changes too many files"

    changed_controls = paths & MAINTENANCE_TEST_BY_PATH.keys()
    if not changed_controls:
        return False, "maintenance lane does not change a control-plane script"
    for control_path in changed_controls:
        required_test = MAINTENANCE_TEST_BY_PATH[control_path]
        if required_test not in paths:
            return False, f"maintenance change lacks paired regression test: {required_test}"

    total_changes = sum(int(row.get("changes") or 0) for row in rows)
    if total_changes > MAINTENANCE_MAX_CHANGES:
        return False, "maintenance lane diff is too large"

    head_sha = str(head.get("sha") or "")
    if not head_sha:
        return False, "pull request has no head commit"
    if require_quality and not exact_head_quality_passed(quality_runs, head_sha):
        return False, "exact pull request head has not passed Quality checks"
    return True, "maintenance-eligible"


def supersession_candidate(
    pr: dict[str, Any],
    *,
    repo: str,
    issue: dict[str, Any],
    files: Iterable[dict[str, Any]],
) -> tuple[bool, str]:
    """Return whether a broad protected-path PR should be replaced from current main."""
    if str(pr.get("state") or "") != "open" or bool(pr.get("draft")):
        return False, "pull request is not an open ready-for-review PR"
    head = pr.get("head") or {}
    if (head.get("repo") or {}).get("full_name") != repo:
        return False, "pull request branch is not in the source repository"
    issue_number = linked_issue_number(str(pr.get("body") or ""))
    if issue_number is None or int(issue.get("number") or 0) != issue_number:
        return False, "pull request is not linked to the fetched issue"
    if not autonomous_issue_ready(issue):
        return False, "linked autonomous issue is not ready for supersession"

    rows = list(files)
    paths = [str(row.get("filename") or "") for row in rows if row.get("filename")]
    protected = blocked_changed_paths(paths)
    if not protected:
        return False, "pull request does not touch protected paths"
    total_changes = sum(int(row.get("changes") or 0) for row in rows)
    if len(paths) <= SUPERSEDE_PROTECTED_MAX_FILES and total_changes <= SUPERSEDE_PROTECTED_MAX_CHANGES:
        return False, "protected-path change is still bounded"
    return True, "broad protected-path pull request should be superseded"


def replacement_issue_body(original_issue: dict[str, Any], pr_number: int) -> str:
    body = str(original_issue.get("body") or "").rstrip()
    marker = SUPERSEDE_MARKER_TEMPLATE.format(pr_number=pr_number)
    context = (
        f"{marker}\n\n"
        "## Supersession context\n"
        f"PR #{pr_number} became too broad and mixed protected control-plane changes with "
        "the original task. Re-do only the original acceptance criteria from current main. "
        "Do not port the stale branch wholesale; measure current behavior first and make the "
        "smallest root-cause change still required."
    )
    return f"{body}\n\n{context}" if body else context


def conflict_replacement_issue_body(
    original_issue: dict[str, Any], pr_number: int, base_ref: str
) -> str:
    body = str(original_issue.get("body") or "").rstrip()
    marker = SUPERSEDE_MARKER_TEMPLATE.format(pr_number=pr_number)
    context = (
        f"{marker}\n\n"
        "## Merge-conflict recovery context\n"
        f"PR #{pr_number} could not be updated onto current {base_ref} without conflicts. "
        "Re-do only the original acceptance criteria from current main. Do not port or "
        "resolve the stale branch wholesale; inspect current behavior first and make the "
        "smallest root-cause change still required."
    )
    return f"{body}\n\n{context}" if body else context


def find_existing_replacement_issue(repo: str, pr_number: int) -> dict[str, Any] | None:
    marker = SUPERSEDE_MARKER_TEMPLATE.format(pr_number=pr_number)
    issues = gh_paginated_json(
        "api",
        f"repos/{repo}/issues?state=open&per_page=100",
    )
    for issue in issues:
        if "pull_request" in issue:
            continue
        if marker in str(issue.get("body") or ""):
            return issue
    return None


def create_or_find_replacement_issue(
    repo: str,
    original_issue: dict[str, Any],
    pr_number: int,
) -> dict[str, Any]:
    existing = find_existing_replacement_issue(repo, pr_number)
    if existing is not None:
        return existing
    title = f"Rework from current main: {str(original_issue.get('title') or '').strip()}"
    return gh_json(
        "api",
        "--method", "POST",
        f"repos/{repo}/issues",
        "-f", f"title={title}",
        "-f", f"body={replacement_issue_body(original_issue, pr_number)}",
        "-f", "labels[]=autonomous-backlog",
        "-f", "labels[]=agent-ready",
    )


def create_or_find_conflict_replacement_issue(
    repo: str,
    original_issue: dict[str, Any],
    pr_number: int,
    base_ref: str,
) -> dict[str, Any]:
    existing = find_existing_replacement_issue(repo, pr_number)
    if existing is not None:
        return existing
    title = f"Rework from current main: {str(original_issue.get('title') or '').strip()}"
    return gh_json(
        "api",
        "--method", "POST",
        f"repos/{repo}/issues",
        "-f", f"title={title}",
        "-f", f"body={conflict_replacement_issue_body(original_issue, pr_number, base_ref)}",
        "-f", "labels[]=autonomous-backlog",
        "-f", "labels[]=agent-ready",
    )


def supersede_conflicted_pull_request(
    repo: str,
    pr: dict[str, Any],
    issue: dict[str, Any],
    base_ref: str,
) -> int:
    number = int(pr["number"])
    replacement = create_or_find_conflict_replacement_issue(
        repo, issue, number, base_ref
    )
    replacement_number = int(replacement["number"])
    gh_run(
        "issue", "comment", str(number), "--repo", repo,
        "--body",
        (
            f"Superseded automatically by #{replacement_number}. This PR conflicts with "
            f"current {base_ref}, so the remaining work is being re-derived from current "
            "main instead of requiring manual conflict resolution."
        ),
    )
    gh_run(
        "api", "--method", "PATCH", f"repos/{repo}/pulls/{number}", "-f", "state=closed"
    )
    original_number = int(issue["number"])
    gh_run(
        "issue", "comment", str(original_number), "--repo", repo,
        "--body",
        (
            f"Superseded by fresh current-main issue #{replacement_number} after PR #{number} "
            f"could not be updated onto {base_ref} without merge conflicts."
        ),
    )
    gh_run(
        "api", "--method", "PATCH", f"repos/{repo}/issues/{original_number}",
        "-f", "state=closed", "-f", "state_reason=not_planned",
    )
    return replacement_number


def supersede_pull_request(
    repo: str,
    pr: dict[str, Any],
    issue: dict[str, Any],
) -> int:
    number = int(pr["number"])
    replacement = create_or_find_replacement_issue(repo, issue, number)
    replacement_number = int(replacement["number"])
    gh_run(
        "issue", "comment", str(number), "--repo", repo,
        "--body",
        (
            f"Superseded automatically by #{replacement_number}. This PR mixed broad stale "
            "changes with protected control-plane files, so the remaining work is being "
            "re-derived from current main instead of porting this branch wholesale."
        ),
    )
    gh_run(
        "api", "--method", "PATCH", f"repos/{repo}/pulls/{number}", "-f", "state=closed"
    )
    original_number = int(issue["number"])
    gh_run(
        "issue", "comment", str(original_number), "--repo", repo,
        "--body",
        (
            f"Superseded by fresh current-main issue #{replacement_number} after PR #{number} "
            "became too broad to merge safely."
        ),
    )
    gh_run(
        "api", "--method", "PATCH", f"repos/{repo}/issues/{original_number}",
        "-f", "state=closed", "-f", "state_reason=not_planned",
    )
    return replacement_number


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


def github_reports_safe_mergeability(pr: dict[str, Any]) -> bool:
    """Allow GitHub states that are mergeable under this policy.

    `behind` is safe here only after the stale-branch overlap check has already
    decided that current base changes do not touch the PR's changed paths.
    GitHub still enforces repository merge rules on the merge API call itself.
    """
    return (
        pr.get("mergeable") is True
        and str(pr.get("mergeable_state") or "") in SAFE_MERGEABLE_STATES
    )


def comparison_changed_paths(comparison: dict[str, Any]) -> set[str]:
    return {
        str(row.get("filename") or "")
        for row in comparison.get("files", [])
        if str(row.get("filename") or "")
    }


def branch_refresh_required(
    *,
    comparison: dict[str, Any],
    pr_changed_paths: Iterable[str],
    base_changed_paths: Iterable[str],
) -> bool:
    """Refresh only when stale-base changes overlap the PR's changed paths.

    A green, mergeable PR that is merely behind main because unrelated files
    changed does not need another branch-update/CI cycle. If the base changed a
    file the PR also changes, retain the conservative refresh-and-retest path.
    """
    if int(comparison.get("behind_by") or 0) <= 0:
        return False
    pr_paths = {str(path) for path in pr_changed_paths if str(path)}
    base_paths = {str(path) for path in base_changed_paths if str(path)}
    return bool(pr_paths & base_paths)


def gh_json(*args: str) -> Any:
    result = subprocess.run(["gh", *args], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def gh_run(*args: str) -> None:
    subprocess.run(["gh", *args], check=True)


def try_guarded_squash_merge(repo: str, number: int, head_sha: str) -> tuple[bool, str]:
    """Let GitHub's merge endpoint be the final authority for a proven-safe stale PR."""
    result = subprocess.run(
        [
            "gh", "api", "--method", "PUT",
            f"repos/{repo}/pulls/{number}/merge",
            "-f", "merge_method=squash",
            "-f", f"sha={head_sha}",
        ],
        text=True,
        capture_output=True,
    )
    detail = (result.stderr or result.stdout or "").strip()
    return result.returncode == 0, detail


def close_linked_issue_after_merge(repo: str, issue_number: int | None) -> None:
    """Best-effort, idempotent issue closure after a successful merge.

    A merge is already irreversible queue progress. Issue bookkeeping must therefore
    never abort the remaining scan. Closing keywords may also close the issue before
    this function runs, so an already-closed issue is a successful no-op.
    """
    if issue_number is None:
        return

    path = f"repos/{repo}/issues/{issue_number}"
    try:
        current = gh_json("api", path)
    except (subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(
            f"WARNING: merged PR but could not inspect linked issue #{issue_number} "
            f"before closure: {exc}"
        )
        return

    if str(current.get("state") or "") == "closed":
        return

    result = subprocess.run(
        [
            "gh", "api", "--method", "PATCH", path,
            "-f", "state=closed",
            "-f", "state_reason=completed",
        ],
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return

    # GitHub may race closing-keyword processing with the explicit PATCH. Re-check
    # before reporting a bookkeeping failure.
    try:
        refreshed = gh_json("api", path)
        if str(refreshed.get("state") or "") == "closed":
            return
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        pass

    detail = (result.stderr or result.stdout or "unknown GitHub error").strip()
    print(
        f"WARNING: merged PR but could not close linked issue #{issue_number}; "
        f"queue scan will continue: {detail}"
    )


def remove_generated_artifacts(
    repo: str,
    number: int,
    head_sha: str,
    head_ref: str,
    paths: Iterable[str],
) -> None:
    """Remove known generated junk from a PR branch and let exact-head CI rerun."""
    clean_paths = sorted(set(paths))
    if not clean_paths:
        return
    subprocess.run(
        ["git", "fetch", "--no-tags", "origin", f"+refs/heads/{head_ref}:refs/remotes/origin/{head_ref}"],
        check=True,
        text=True,
        capture_output=True,
    )
    remote_head = subprocess.run(
        ["git", "rev-parse", f"refs/remotes/origin/{head_ref}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if remote_head != head_sha:
        raise RuntimeError(
            f"PR #{number} in {repo} moved from {head_sha} to {remote_head} during generated-artifact cleanup"
        )
    subprocess.run(["git", "checkout", "--detach", head_sha], check=True, text=True, capture_output=True)
    subprocess.run(["git", "rm", "--", *clean_paths], check=True, text=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c", "user.name=github-actions[bot]",
            "-c", "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "commit", "-m", "chore: remove generated artifacts",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    subprocess.run(
        [
            "git", "push", "origin", f"HEAD:refs/heads/{head_ref}",
            f"--force-with-lease=refs/heads/{head_ref}:{head_sha}",
        ],
        check=True,
        text=True,
        capture_output=True,
    )


def update_pull_request_branch(
    repo: str,
    number: int,
    head_sha: str,
    head_ref: str,
    base_ref: str,
) -> tuple[bool, str]:
    """Merge the current base into a PR branch without creating recursive PR CI.

    GitHub's update-branch API emits a bot-authored pull_request synchronize event.
    In this repository those runs require maintainer approval, producing an
    action_required queue. A normal GITHUB_TOKEN git push does not recursively
    trigger Actions, so we push the merge commit directly and then explicitly
    workflow-dispatch exact-head Quality checks.
    """
    fetch = subprocess.run(
        [
            "git",
            "fetch",
            "--no-tags",
            "origin",
            f"+refs/heads/{base_ref}:refs/remotes/origin/{base_ref}",
            f"+refs/heads/{head_ref}:refs/remotes/origin/{head_ref}",
        ],
        text=True,
        capture_output=True,
    )
    if fetch.returncode != 0:
        raise subprocess.CalledProcessError(
            fetch.returncode,
            fetch.args,
            output=fetch.stdout,
            stderr=fetch.stderr,
        )

    remote_head = subprocess.run(
        ["git", "rev-parse", f"refs/remotes/origin/{head_ref}"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    if remote_head != head_sha:
        raise RuntimeError(
            f"PR #{number} in {repo} moved from {head_sha} to {remote_head} during branch sync"
        )

    subprocess.run(
        ["git", "checkout", "--detach", head_sha],
        check=True,
        text=True,
        capture_output=True,
    )
    merge = subprocess.run(
        [
            "git",
            "-c",
            "user.name=github-actions[bot]",
            "-c",
            "user.email=41898282+github-actions[bot]@users.noreply.github.com",
            "merge",
            "--no-edit",
            f"refs/remotes/origin/{base_ref}",
        ],
        text=True,
        capture_output=True,
    )
    if merge.returncode != 0:
        detail = "\n".join(
            part for part in (merge.stdout, merge.stderr) if part
        ).strip()
        subprocess.run(
            ["git", "merge", "--abort"],
            text=True,
            capture_output=True,
        )
        lowered = detail.casefold()
        if "conflict" in lowered or "automatic merge failed" in lowered:
            return False, detail
        raise subprocess.CalledProcessError(
            merge.returncode,
            merge.args,
            output=merge.stdout,
            stderr=merge.stderr,
        )

    push = subprocess.run(
        [
            "git",
            "push",
            "origin",
            f"HEAD:refs/heads/{head_ref}",
            f"--force-with-lease=refs/heads/{head_ref}:{head_sha}",
        ],
        text=True,
        capture_output=True,
    )
    if push.returncode != 0:
        raise subprocess.CalledProcessError(
            push.returncode,
            push.args,
            output=push.stdout,
            stderr=push.stderr,
        )
    return True, ""


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
    files_by_pr: dict[int, list[dict[str, Any]]] = {}
    changed_paths_by_pr: dict[int, list[str]] = {}
    for pr in pull_requests:
        number = int(pr["number"])
        files = gh_paginated_json(
            "api",
            f"repos/{repo}/pulls/{number}/files?per_page=100",
        )
        files_by_pr[number] = files
        changed_paths_by_pr[number] = [
            str(row.get("filename") or "") for row in files
        ]
    pull_requests = prioritize_pull_requests(pull_requests, changed_paths_by_pr)

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
        files = files_by_pr[number]
        head_sha = str((pr.get("head") or {}).get("sha") or "")
        runs = gh_json(
            "api",
            quality_runs_api_path(repo, head_sha),
        ).get("workflow_runs", [])
        generated = generated_artifact_paths(
            str(row.get("filename") or "") for row in files
        )
        head_ref = str((pr.get("head") or {}).get("ref") or "")

        maintenance_pre_ci, maintenance_reason = maintenance_pr_eligible(
            pr,
            repo=repo,
            files=files,
            quality_runs=runs,
            require_quality=False,
        )
        control_plane_pre_ci, control_plane_reason = control_plane_pr_eligible(
            pr,
            repo=repo,
            files=files,
            quality_runs=runs,
            require_quality=False,
        )

        owner_comments: list[dict[str, Any]] = []
        if OWNER_AUTHORIZED_AUTOMERGE_MARKER not in str(pr.get("body") or ""):
            owner_comments = gh_paginated_json(
                "api",
                f"repos/{repo}/issues/{number}/comments?per_page=100",
            )
        owner_authorized = owner_authorized_pr(pr, repo, owner_comments)
        issue_number = linked_issue_number(str(pr.get("body") or ""))
        issue = None
        if issue_number is not None:
            issue = gh_json("api", f"repos/{repo}/issues/{issue_number}")
            should_supersede, supersede_reason = supersession_candidate(
                pr,
                repo=repo,
                issue=issue,
                files=files,
            )
            if should_supersede:
                replacement_number = supersede_pull_request(repo, pr, issue)
                print(
                    f"Superseded broad protected-path PR #{number} with fresh current-main "
                    f"issue #{replacement_number}."
                )
                continue
        if issue_number is None and not maintenance_pre_ci and not owner_authorized:
            issue = recovered_issue_by_pr.get(number)
            if issue is None:
                print(
                    f"BLOCKED_REQUIRES_DECISION PR #{number}: no trusted autonomous issue linkage."
                )
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

        if issue is None and not maintenance_pre_ci and not owner_authorized:
            issue = gh_json("api", f"repos/{repo}/issues/{issue_number}")

        if issue is not None and JULES_REVIEW_READY_LABEL in label_names(issue):
            output_meta = issue.get("_jules_output")
            if output_meta is None:
                comments = gh_paginated_json(
                    "api",
                    f"repos/{repo}/issues/{issue_number}/comments?per_page=100",
                )
                durable = completed_jules_output(comments)
                if durable is not None:
                    recorded_issue, session_id, recorded_pr, recorded_head = durable
                    output_meta = {
                        "issue": recorded_issue,
                        "session": session_id,
                        "pr": recorded_pr,
                        "head": recorded_head,
                        "durable": True,
                    }
                else:
                    legacy = legacy_completed_jules_output(comments, repo)
                    if legacy is not None:
                        session_id, recorded_pr = legacy
                        output_meta = {
                            "issue": issue_number,
                            "session": session_id,
                            "pr": recorded_pr,
                            "head": "",
                            "durable": False,
                        }
            if output_meta is None:
                print(
                    f"BLOCKED_REQUIRES_DECISION PR #{number}: review-ready Jules issue "
                    f"#{issue_number} has no trusted output record."
                )
                continue
            if int(output_meta["issue"]) != int(issue_number) or int(output_meta["pr"]) != number:
                print(
                    f"BLOCKED_REQUIRES_DECISION PR #{number}: durable Jules output identity "
                    f"does not match issue #{issue_number}."
                )
                continue
            recorded_head = str(output_meta.get("head") or "")
            if recorded_head and recorded_head != head_sha:
                commits = gh_paginated_json(
                    "api",
                    f"repos/{repo}/pulls/{number}/commits?per_page=100",
                )
                if not trusted_repair_head_allowed(
                    commits,
                    recorded_head=recorded_head,
                    current_head=head_sha,
                    repo=repo,
                    quality_runs=runs,
                ):
                    print(
                        f"BLOCKED_REQUIRES_DECISION PR #{number}: durable Jules output head "
                        f"{recorded_head} does not match current head {head_sha}."
                    )
                    continue
                marker = (
                    f"<!-- jules-output: issue={issue_number} "
                    f"session={output_meta['session']} pr={number} head={head_sha} -->"
                )
                gh_run(
                    "issue", "comment", str(issue_number), "--repo", repo,
                    "--body",
                    (
                        f"{marker}\nAdvanced durable Jules output identity after trusted "
                        "repair commits passed exact-head Quality checks."
                    ),
                )
                output_meta["head"] = head_sha
                output_meta["durable"] = True
                print(
                    f"Advanced Jules output identity for issue #{issue_number}, PR #{number}, "
                    f"to trusted green repair head {head_sha}."
                )
                recorded_head = head_sha
            if not recorded_head:
                marker = (
                    f"<!-- jules-output: issue={issue_number} "
                    f"session={output_meta['session']} pr={number} head={head_sha} -->"
                )
                gh_run(
                    "issue", "comment", str(issue_number), "--repo", repo,
                    "--body",
                    (
                        f"{marker}\nMigrated trusted legacy Jules completion metadata "
                        "to the durable output identity contract."
                    ),
                )
                output_meta["head"] = head_sha
                output_meta["durable"] = True
                print(
                    f"Migrated Jules output identity for issue #{issue_number}, PR #{number}."
                )

        if generated:
            if (
                (issue is None or not autonomous_issue_ready(issue))
                and not owner_authorized
                or not head_ref
            ):
                print(
                    f"BLOCKED_REQUIRES_DECISION PR #{number}: generated artifacts require trusted autonomous issue linkage."
                )
                continue
            remove_generated_artifacts(
                repo,
                number,
                head_sha,
                head_ref,
                generated,
            )
            gh_run(
                "workflow", "run", "quality.yml",
                "--repo", repo,
                "--ref", head_ref,
            )
            print(
                f"Repaired PR #{number} by removing generated artifacts and dispatched fresh Quality checks."
            )
            continue

        if control_plane_pre_ci and not owner_authorized and (
            issue is None or not autonomous_issue_ready(issue)
        ):
            control_plane_pre_ci = False
            control_plane_reason = "linked autonomous issue is not ready for merge"

        deleted_run_ids = delete_superseded_action_required_runs(
            repo,
            runs,
            head_sha,
        )
        if deleted_run_ids:
            print(
                f"Deleted {len(deleted_run_ids)} superseded approval-gated "
                f"Quality run(s) for PR #{number}."
            )

        changed_paths = [str(row.get("filename") or "") for row in files]
        if owner_authorized:
            pre_ci_eligible, reason = True, "owner-authorized"
        elif maintenance_pre_ci:
            pre_ci_eligible, reason = True, "maintenance-eligible"
        elif control_plane_pre_ci:
            pre_ci_eligible, reason = True, "control-plane-eligible"
        else:
            pre_ci_eligible, reason = eligible_pr(
                pr,
                repo=repo,
                issue=issue,
                changed_paths=changed_paths,
                quality_runs=runs,
                require_quality=False,
            )
        if not pre_ci_eligible:
            details = [reason]
            if maintenance_reason != "maintenance-eligible":
                details.append(maintenance_reason)
            if control_plane_reason != "control-plane-eligible":
                details.append(control_plane_reason)
            disposition = "; ".join(dict.fromkeys(details))
            print(f"BLOCKED_REQUIRES_DECISION PR #{number}: {disposition}.")
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

        if owner_authorized:
            eligible, reason = (
                exact_head_quality_passed(runs, head_sha),
                "owner-authorized" if exact_head_quality_passed(runs, head_sha)
                else "exact-head Quality checks have not passed",
            )
        elif maintenance_pre_ci:
            eligible, reason = maintenance_pr_eligible(
                pr,
                repo=repo,
                files=files,
                quality_runs=runs,
            )
        elif control_plane_pre_ci:
            eligible, reason = control_plane_pr_eligible(
                pr,
                repo=repo,
                files=files,
                quality_runs=runs,
            )
        else:
            eligible, reason = eligible_pr(
                pr,
                repo=repo,
                issue=issue,
                changed_paths=changed_paths,
                quality_runs=runs,
            )
        if not eligible:
            print(f"BLOCKED_REQUIRES_DECISION PR #{number}: {reason}.")
            continue

        base_ref = str((pr.get("base") or {}).get("ref") or "main")
        stale_nonoverlap_safe = False
        comparison = gh_json("api", f"repos/{repo}/compare/{base_ref}...{head_sha}")
        if int(comparison.get("behind_by") or 0) > 0:
            merge_base = comparison.get("merge_base_commit") or {}
            merge_base_sha = str(merge_base.get("sha") or "")
            if not merge_base_sha:
                raise RuntimeError(
                    f"PR #{number} comparison has no merge base for stale-branch safety check"
                )
            base_delta = gh_json(
                "api",
                f"repos/{repo}/compare/{merge_base_sha}...{base_ref}",
            )
            base_changed_paths = comparison_changed_paths(base_delta)
            if branch_refresh_required(
                comparison=comparison,
                pr_changed_paths=changed_paths,
                base_changed_paths=base_changed_paths,
            ):
                updated, detail = update_pull_request_branch(
                    repo,
                    number,
                    head_sha,
                    head_ref,
                    base_ref,
                )
                if not updated:
                    if conflicted_pr_can_supersede(issue):
                        replacement_number = supersede_conflicted_pull_request(
                            repo,
                            pr,
                            issue,
                            base_ref,
                        )
                        print(
                            f"Superseded conflicted PR #{number} with fresh current-main "
                            f"issue #{replacement_number}."
                        )
                    else:
                        print(
                            f"BLOCKED_REQUIRES_DECISION PR #{number}: branch conflicts with "
                            f"current {base_ref} and no trusted autonomous issue is available "
                            "for safe supersession."
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
                    "Quality checks because main changed overlapping paths."
                )
                continue
            stale_nonoverlap_safe = True
            print(
                f"PR #{number} is behind {base_ref}, but base changes do not overlap "
                "its changed paths; preserving green exact-head CI and fast-merging."
            )

        fresh = gh_json("api", f"repos/{repo}/pulls/{number}")
        if not github_reports_safe_mergeability(fresh):
            mergeable = fresh.get("mergeable")
            mergeable_state = str(fresh.get("mergeable_state") or "")
            if mergeable is None or mergeable_state in {"", "unknown"}:
                if stale_nonoverlap_safe:
                    merged, detail = try_guarded_squash_merge(
                        repo,
                        number,
                        head_sha,
                    )
                    if merged:
                        print(
                            f"Squash-merged eligible autonomous PR #{number} through guarded "
                            "merge fallback while GitHub mergeability was recomputing."
                        )
                        close_linked_issue_after_merge(repo, issue_number)
                        merged_count += 1
                        continue
                    print(
                        f"REPAIR_AND_RETRY PR #{number}: guarded merge was not yet accepted "
                        "while GitHub mergeability was recomputing."
                    )
                    if detail:
                        print(detail)
                else:
                    print(
                        f"REPAIR_AND_RETRY PR #{number}: GitHub mergeability is still being recomputed."
                    )
            else:
                print(
                    f"BLOCKED_REQUIRES_DECISION PR #{number}: GitHub reports mergeable={mergeable} "
                    f"state={mergeable_state or 'unknown'}."
                )
            continue

        merged, detail = try_guarded_squash_merge(repo, number, head_sha)
        if not merged:
            print(
                f"REPAIR_AND_RETRY PR #{number}: guarded merge was not accepted despite "
                "safe mergeability."
            )
            if detail:
                print(detail)
            continue
        close_linked_issue_after_merge(repo, issue_number)
        print(f"Squash-merged eligible autonomous PR #{number}.")
        merged_count += 1

    if merged_count:
        print(f"Squash-merged {merged_count} eligible autonomous pull request(s).")
        gh_run(
            "workflow", "run", "auto-merge-agent-prs.yml",
            "--repo", repo,
        )
        print(
            "Queued one follow-up auto-merge scan because this run advanced main; "
            "GITHUB_TOKEN-authored merges do not reliably recurse through push triggers."
        )
    else:
        print("No autonomous pull request is currently eligible for automatic merge.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
