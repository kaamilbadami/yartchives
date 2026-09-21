#!/usr/bin/env python3
"""Create/resolve workflow-failure issues that dispatch bounded work to Jules."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable, NamedTuple

GhJson = Callable[..., Any]
GhRun = Callable[..., None]

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
