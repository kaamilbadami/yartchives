#!/usr/bin/env python3
"""Create/resolve workflow-failure issues that dispatch bounded work to Jules."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Callable, NamedTuple

GhJson = Callable[..., Any]
GhRun = Callable[..., None]


JULES_OUTPUT_MARKER_REGEX = re.compile(
    r"<!--\s*jules-output:\s*issue=(?P<issue>\d+)\s+session=(?P<session>[^\s]+)\s+"
    r"pr=(?P<pr>\d+)\s+head=(?P<head>[a-zA-Z0-9\-]+)\s*-->"
)

REPAIR_BUDGET = 2

def _get_target_issue_for_head(ctx: Context, gh_json: GhJson) -> dict[str, Any] | None:
    issues = gh_json(
        "api",
        "--paginate",
        f"repos/{ctx.repo}/issues?state=open&per_page=100",
    )

    # We only care about issues with a jules label
    candidate_issues = []
    for issue in issues:
        if "pull_request" in issue:
            continue
        labels = _label_names(issue)
        if any(label.startswith("jules") for label in labels):
            candidate_issues.append(issue)

    for issue in candidate_issues:
        body = issue.get("body") or ""
        # Find all jules-output markers
        matches = list(JULES_OUTPUT_MARKER_REGEX.finditer(body))
        if matches:
            # Check the latest one
            latest_match = matches[-1]
            if latest_match.group("head") == ctx.head_sha:
                return issue
    return None

def _get_log_excerpt(repo: str, run_id: str, job_id: str | None, job_name: str) -> str:
    try:
        # Use gh run view to get the log
        target = job_id if job_id else job_name
        result = subprocess.run(
            ["gh", "run", "view", run_id, "--repo", repo, "--job", target, "--log"],
            capture_output=True, text=True, check=True
        )
        lines = result.stdout.splitlines()
        # Grab the last 50 lines as excerpt
        excerpt = "\n".join(lines[-50:])
        return excerpt
    except Exception as e:
        return f"Could not fetch log excerpt: {e}"

def handle_agent_pr_failure(ctx: Context, gh_json: GhJson, gh_run: GhRun) -> None:
    issue = _get_target_issue_for_head(ctx, gh_json)
    if not issue:
        print(f"Skipping {ctx.workflow} {ctx.conclusion} on {ctx.head_branch}: not a trusted autonomous PR.")
        return

    job_name, step_name = _failed_job_and_step(ctx, gh_json)

    # Only repair code/test failures, not arbitrary infra/setup failures
    # Based on the typical Quality checks steps
    REPAIRABLE_STEPS = {"Python tests", "Frontend tests", "Repository health checks"}
    if step_name not in REPAIRABLE_STEPS:
        print(f"Skipping repair for non-repairable step: {step_name}")
        return

    number = str(issue["number"])
    labels = _label_names(issue)

    # Find session from the body
    body = issue.get("body") or ""
    matches = list(JULES_OUTPUT_MARKER_REGEX.finditer(body))
    if not matches:
        return
    session_id = matches[-1].group("session")

    # Read comments to check for idempotency and budget
    comments = gh_json(
        "api",
        "--paginate",
        f"repos/{ctx.repo}/issues/{number}/comments?per_page=100",
    )

    repair_marker = f"<!-- ci-repair-delivered: {ctx.head_sha}::{job_name}::{step_name} -->"

    repair_count = 0
    for comment in comments:
        c_body = comment.get("body") or ""
        if repair_marker in c_body:
            print(f"Duplicate failure event for {ctx.head_sha} {step_name}, ignoring.")
            return
        if "<!-- ci-repair-delivered:" in c_body:
            repair_count += 1

    if repair_count >= REPAIR_BUDGET:
        # Park the task
        edit_args = ["issue", "edit", number, "--repo", ctx.repo]
        if "jules-review-ready" in labels:
            edit_args += ["--remove-label", "jules-review-ready"]
        if "jules-retry-ready" in labels:
            edit_args += ["--remove-label", "jules-retry-ready"]
        edit_args += ["--add-label", "jules-failed"]
        gh_run(*edit_args)

        gh_run(
            "issue", "comment", number, "--repo", ctx.repo,
            "--body",
            f"{repair_marker}\n"
            f"CI repair budget exhausted ({REPAIR_BUDGET} repairs). "
            f"The task failed on `{step_name}` for commit `{ctx.head_sha}`.\n\n"
            f"Run: {ctx.run_url}\n\n"
            f"Parking the task for manual intervention."
        )
        return

    job_id = _failed_job_id(ctx, gh_json, job_name)
    excerpt = _get_log_excerpt(ctx.repo, ctx.run_id, job_id, job_name)

    diagnostic = (
        f"{repair_marker}\n"
        f"<!-- jules-retry-from: {session_id} -->\n"
        f"Automated Quality checks failed on your PR for commit `{ctx.head_sha}`.\n\n"
        f"- Failed job: **{job_name}**\n"
        f"- Failed step: **{step_name}**\n"
        f"- Run: {ctx.run_url}\n\n"
        f"### Log Excerpt\n```text\n{excerpt}\n```\n\n"
        f"Please repair this failure in a new commit."
    )

    edit_args = ["issue", "edit", number, "--repo", ctx.repo]
    if "jules-review-ready" in labels:
        edit_args += ["--remove-label", "jules-review-ready"]
    edit_args += ["--add-label", "jules-retry-ready"]
    gh_run(*edit_args)

    gh_run(
        "issue", "comment", number, "--repo", ctx.repo,
        "--body", diagnostic
    )

def handle_agent_pr_success(ctx: Context, gh_json: GhJson, gh_run: GhRun) -> None:
    issue = _get_target_issue_for_head(ctx, gh_json)
    if not issue:
        return

    number = str(issue["number"])
    labels = _label_names(issue)

    if "jules-retry-ready" in labels or "jules-failed" in labels:
        edit_args = ["issue", "edit", number, "--repo", ctx.repo]
        if "jules-retry-ready" in labels:
            edit_args += ["--remove-label", "jules-retry-ready"]
        if "jules-failed" in labels:
            edit_args += ["--remove-label", "jules-failed"]
        edit_args += ["--add-label", "jules-review-ready"]
        gh_run(*edit_args)

        gh_run(
            "issue", "comment", number, "--repo", ctx.repo,
            "--body",
            f"Resolved by successful **{ctx.workflow}** run on "
            f"`{ctx.head_sha}`: {ctx.run_url}\n\n"
            "CI is green again. Proceeding toward auto-merge."
        )

        # Wake auto-merge
        try:
            gh_run(
                "workflow", "run", "auto-merge-agent-prs.yml",
                "--repo", ctx.repo,
                "--ref", ctx.default_branch,
                "-f", f"wait_for_quality_run_id={ctx.run_id}"
            )
        except Exception as e:
            print(f"Failed to trigger auto-merge: {e}")

CONTROL_PLANE_WORKFLOWS = {
    "Dispatch autonomous backlog",
    "Auto-merge autonomous agent PRs",
}


class Context(NamedTuple):
    repo: str
    run_id: str
    run_url: str
    workflow: str
    head_sha: str
    conclusion: str
    head_branch: str
    default_branch: str


def _label_names(issue: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for label in issue.get("labels", []):
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and label.get("name"):
            names.add(str(label["name"]))
    return names


def _marker(workflow: str, job: str, step: str) -> str:
    return f"<!-- workflow-failure-signature: {workflow}::{job}::{step} -->"


def _workflow_marker_prefix(workflow: str) -> str:
    return f"<!-- workflow-failure-signature: {workflow}::"


def _open_failure_issues(ctx: Context, gh_json: GhJson) -> list[dict[str, Any]]:
    issues = gh_json(
        "api",
        "--paginate",
        f"repos/{ctx.repo}/issues?state=open&labels=workflow-failure&per_page=100",
    )
    return [issue for issue in issues if "pull_request" not in issue]


def _ensure_labels(ctx: Context, gh_run: GhRun) -> None:
    labels = (
        ("workflow-failure", "D73A4A", "Created automatically from a failed GitHub Actions workflow"),
        ("agent-ready", "0E8A16", "Bounded task suitable for an automated coding agent"),
        ("autonomous-backlog", "1D76DB", "Approved backlog item eligible for autonomous dispatch"),
    )
    for name, color, description in labels:
        gh_run(
            "label",
            "create",
            name,
            "--repo",
            ctx.repo,
            "--color",
            color,
            "--description",
            description,
            "--force",
        )


def _failed_jobs_and_steps(ctx: Context, gh_json: GhJson) -> list[tuple[str, str]]:
    jobs = gh_json(
        "api",
        f"repos/{ctx.repo}/actions/runs/{ctx.run_id}/jobs?filter=latest&per_page=100",
    ).get("jobs", [])

    failed = []
    for job in jobs:
        if job.get("conclusion") == "failure":
            job_name = job.get("name", "unknown job")
            for step in job.get("steps", []):
                if step.get("conclusion") == "failure":
                    failed.append((job_name, step.get("name", "unknown step")))

    # fallback if a job failed but no steps are marked failure
    if not failed:
        for job in jobs:
            if job.get("conclusion") == "failure":
                failed.append((job.get("name", "unknown job"), "unknown step"))

    return failed or [("unknown job", "unknown step")]

def _failed_job_and_step(ctx: Context, gh_json: GhJson) -> tuple[str, str]:
    return _failed_jobs_and_steps(ctx, gh_json)[0]

def _failed_job_id(ctx: Context, gh_json: GhJson, target_job_name: str) -> str | None:
    jobs = gh_json(
        "api",
        f"repos/{ctx.repo}/actions/runs/{ctx.run_id}/jobs?filter=latest&per_page=100",
    ).get("jobs", [])
    for job in jobs:
        if job.get("name") == target_job_name:
            return str(job.get("id"))
    return None


def handle_failure(ctx: Context, gh_json: GhJson, gh_run: GhRun) -> None:
    _ensure_labels(ctx, gh_run)
    job_name, step_name = _failed_job_and_step(ctx, gh_json)
    marker = _marker(ctx.workflow, job_name, step_name)
    title = f"[workflow failure] {ctx.workflow}: {step_name}"

    body = f"""{marker}
An automated Yartchives workflow failed.

- Workflow: **{ctx.workflow}**
- Failed job: **{job_name}**
- Failed step: **{step_name}**
- Commit: `{ctx.head_sha}`
- Run: {ctx.run_url}

This issue is deduplicated by workflow, failed job, and failed step. A successful default-branch run resolves it; a later regression creates a fresh issue and therefore a fresh Jules dispatch.

## Agent guidance
Treat the current repository as the source of truth. Diagnose the root cause before changing code. Prefer a regression test and a generic fix over a narrow patch. Do not weaken feed, link, eligibility, or benchmark contracts just to make CI pass.
"""

    issues = _open_failure_issues(ctx, gh_json)

    # Close any stale issues for this workflow that are no longer failing
    failed_signatures = {
        _marker(ctx.workflow, j, s) for j, s in _failed_jobs_and_steps(ctx, gh_json)
    }
    prefix = _workflow_marker_prefix(ctx.workflow)
    for issue in issues:
        body_text = issue.get("body") or ""
        if prefix in body_text and not any(sig in body_text for sig in failed_signatures):
            number = str(issue["number"])
            labels = _label_names(issue)
            edit_args = ["issue", "edit", number, "--repo", ctx.repo]
            for label in ("jules", "jules-session", "agent-ready", "autonomous-backlog"):
                if label in labels:
                    edit_args += ["--remove-label", label]
            if len(edit_args) > 5:
                gh_run(*edit_args)

            gh_run(
                "issue",
                "comment",
                number,
                "--repo",
                ctx.repo,
                "--body",
                (
                    f"Resolved by run on `{ctx.head_sha}`: {ctx.run_url}\n\n"
                    "Closing this failure cycle as this step is no longer failing. "
                    "If the same failure returns later, triage will create a fresh issue."
                ),
            )
            gh_run("issue", "close", number, "--repo", ctx.repo)

    existing = next((issue for issue in issues if marker in (issue.get("body") or "")), None)

    if existing:
        labels = _label_names(existing)
        edit_args = [
            "issue",
            "edit",
            str(existing["number"]),
            "--repo",
            ctx.repo,
        ]
        if "agent-ready" not in labels:
            edit_args += ["--add-label", "agent-ready"]
        if "autonomous-backlog" not in labels:
            edit_args += ["--add-label", "autonomous-backlog"]
        if len(edit_args) > 5:
            gh_run(*edit_args)

        gh_run(
            "issue",
            "comment",
            str(existing["number"]),
            "--repo",
            ctx.repo,
            "--body",
            (
                f"Failure recurred on commit `{ctx.head_sha}`.\n\n"
                f"- Failed job: **{job_name}**\n"
                f"- Failed step: **{step_name}**\n"
                f"- Run: {ctx.run_url}"
            ),
        )
        return

    gh_run(
        "issue",
        "create",
        "--repo",
        ctx.repo,
        "--title",
        title,
        "--body",
        body,
        "--label",
        "workflow-failure",
        "--label",
        "agent-ready",
        "--label",
        "autonomous-backlog",
    )


def handle_success(ctx: Context, gh_json: GhJson, gh_run: GhRun) -> None:
    prefix = _workflow_marker_prefix(ctx.workflow)
    for issue in _open_failure_issues(ctx, gh_json):
        if prefix not in (issue.get("body") or ""):
            continue

        number = str(issue["number"])
        labels = _label_names(issue)
        edit_args = ["issue", "edit", number, "--repo", ctx.repo]
        for label in ("jules", "jules-session", "agent-ready", "autonomous-backlog"):
            if label in labels:
                edit_args += ["--remove-label", label]
        if len(edit_args) > 5:
            gh_run(*edit_args)

        gh_run(
            "issue",
            "comment",
            number,
            "--repo",
            ctx.repo,
            "--body",
            (
                f"Resolved by successful **{ctx.workflow}** run on "
                f"`{ctx.head_sha}`: {ctx.run_url}\n\n"
                "Closing this failure cycle. If the same failure returns later, "
                "triage will create a fresh issue so the dispatcher can start a fresh task."
            ),
        )
        gh_run("issue", "close", number, "--repo", ctx.repo)


def triage(ctx: Context, gh_json: GhJson, gh_run: GhRun) -> None:
    if (
        ctx.head_branch != ctx.default_branch
        and ctx.workflow not in CONTROL_PLANE_WORKFLOWS
    ):
        if ctx.workflow == "Quality checks":
            if ctx.conclusion == "failure":
                handle_agent_pr_failure(ctx, gh_json, gh_run)
            elif ctx.conclusion == "success":
                handle_agent_pr_success(ctx, gh_json, gh_run)
            return

        print(
            f"Skipping {ctx.workflow} {ctx.conclusion} on non-default branch "
            f"{ctx.head_branch!r}; coding-agent triage is for {ctx.default_branch!r}."
        )
        return

    if ctx.conclusion == "failure":
        handle_failure(ctx, gh_json, gh_run)
    elif ctx.conclusion == "success":
        handle_success(ctx, gh_json, gh_run)
    else:
        print(f"No triage action for conclusion {ctx.conclusion!r}.")


def _gh_json(*args: str) -> Any:
    result = subprocess.run(
        ["gh", *args],
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def _gh_run(*args: str) -> None:
    subprocess.run(["gh", *args], check=True)


def _context_from_env() -> Context:
    return Context(
        repo=os.environ["REPOSITORY"],
        run_id=os.environ["RUN_ID"],
        run_url=os.environ["RUN_URL"],
        workflow=os.environ["WORKFLOW_NAME"],
        head_sha=os.environ["HEAD_SHA"],
        conclusion=os.environ["CONCLUSION"],
        head_branch=os.environ["HEAD_BRANCH"],
        default_branch=os.environ["DEFAULT_BRANCH"],
    )


def main() -> None:
    triage(_context_from_env(), _gh_json, _gh_run)


if __name__ == "__main__":
    main()
