#!/usr/bin/env python3
"""Trusted, bounded failure-to-Copilot PR repair handoff.

Disabled unless explicitly configured. This requests a repair, never approves
or merges a PR, and never executes code from the PR in the privileged job.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Callable

REPAIR_MARKER = "<!-- copilot-ci-repair-attempt:v1 "
MAX_REPAIRS_PER_PR = 2
REPAIRABLE_STEPS = frozenset({
    "Python tests", "Frontend tests", "Repository health checks",
    "Run affected frontend checks", "Test targeted preflight planner",
})
BOT = "github-actions[bot]"
COPILOT_LOGINS = {"copilot", "copilot-swe-agent", "copilot-swe-agent[bot]"}


def gh_api(path: str, *, method: str = "GET", body: dict | None = None,
           token: str | None = None) -> Any:
    args = ["gh", "api", "--method", method, path]
    if body is not None:
        args += ["--input", "-"]
    env = os.environ.copy()
    if token is not None:
        env["GH_TOKEN"] = token
    proc = subprocess.run(args, check=True, capture_output=True, text=True,
                          input=json.dumps(body) if body is not None else None,
                          env=env)
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


def failed_test_steps(jobs: list[dict]) -> list[str]:
    failed = []
    for job in jobs:
        if job.get("conclusion") != "failure":
            continue
        steps = [step.get("name") for step in job.get("steps", [])
                 if step.get("conclusion") == "failure"]
        if not steps or any(step not in REPAIRABLE_STEPS for step in steps):
            return []
        failed.extend(steps)
    return list(dict.fromkeys(failed))


def dispatch(event: dict, repo: str, token: str,
             api: Callable[..., Any] = gh_api) -> str:
    run = event.get("workflow_run") or {}
    if (not token or run.get("name") != "Quality checks"
            or run.get("event") != "pull_request"
            or run.get("conclusion") != "failure"):
        return "disabled or not a repairable PR Quality failure"
    head_sha = str(run.get("head_sha") or "")
    if not re.fullmatch(r"[a-f0-9]{40}", head_sha):
        return "missing immutable run head"
    prs = run.get("pull_requests") or []
    if len(prs) != 1 or not isinstance(prs[0].get("number"), int):
        return "ambiguous run-to-PR identity"
    number = prs[0]["number"]
    pr = api(f"repos/{repo}/pulls/{number}")
    head = pr.get("head") or {}
    if (pr.get("state") != "open"
            or pr.get("number") != number
            or (pr.get("user") or {}).get("login", "").casefold() != "copilot"
            or head.get("sha") != head_sha
            or not str(head.get("ref") or "").startswith("copilot/")
            or (head.get("repo") or {}).get("full_name") != repo
            or (pr.get("base") or {}).get("ref") != "main"):
        return "not a current, trusted Copilot PR"
    # Use the existing, deliberately narrow product/test-file eligibility policy.
    try:
        from scripts.ready_copilot_prs import linked_issue, safe_low_risk_files
    except ModuleNotFoundError:
        from ready_copilot_prs import linked_issue, safe_low_risk_files
    issue_number = linked_issue(pr, repo)
    if issue_number is None:
        return "no unique local linked issue"
    issue = api(f"repos/{repo}/issues/{issue_number}")
    labels = {label.get("name") if isinstance(label, dict) else label
              for label in issue.get("labels") or []}
    if (issue.get("state") != "open"
            or labels & {"initiative", "agent-excluded", "needs-human-decision", "blocked"}
            or not any(str(a.get("login") or "").casefold() in COPILOT_LOGINS
                       for a in issue.get("assignees") or [])):
        return "linked issue not authorized"
    files = api(f"repos/{repo}/pulls/{number}/files?per_page=100")
    if not isinstance(files, list) or len(files) >= 100 or not safe_low_risk_files(files):
        return "PR changes are sensitive, untrusted or incomplete"
    run_id = run.get("id")
    if not isinstance(run_id, int):
        return "invalid workflow run ID"
    jobs = api(f"repos/{repo}/actions/runs/{run_id}/jobs?filter=latest&per_page=100")
    if not isinstance(jobs.get("jobs"), list) or len(jobs["jobs"]) >= 100:
        return "incomplete job evidence"
    steps = failed_test_steps(jobs["jobs"])
    if not steps:
        return "failure not classified as ordinary code/test repair"
    comments = api(f"repos/{repo}/issues/{number}/comments?per_page=100")
    if not isinstance(comments, list) or len(comments) >= 100:
        return "incomplete repair history"
    attempts = [c for c in comments if REPAIR_MARKER in str(c.get("body") or "")
                and (c.get("user") or {}).get("login", "").casefold() == BOT]
    if any(f"head={head_sha} " in str(c.get("body") or "") for c in attempts):
        return "repair already requested for this head"
    if len(attempts) >= MAX_REPAIRS_PER_PR:
        exhausted_marker = "<!-- copilot-ci-repair-exhausted:v1 -->"
        if not any(exhausted_marker in str(c.get("body") or "")
                   and (c.get("user") or {}).get("login", "").casefold() == BOT
                   for c in comments):
            api(f"repos/{repo}/issues/{number}/comments", method="POST",
                body={"body": exhausted_marker + "\\n"
                      + f"Automatic Copilot CI repair exhausted its {MAX_REPAIRS_PER_PR} "
                      + "attempts. No further automatic repair requests will be sent. "
                      + "Investigate the current Quality run and authorize the next "
                      + "step explicitly."})
        return f"repair budget exhausted ({MAX_REPAIRS_PER_PR}); escalation recorded"
    # Final head check immediately before the first write. A marker is persisted
    # BEFORE mentioning Copilot so ambiguous delivery never causes a retry storm.
    latest = api(f"repos/{repo}/pulls/{number}")
    if (latest.get("state") != "open"
            or (latest.get("head") or {}).get("sha") != head_sha
            or latest.get("body") != pr.get("body")
            or latest.get("draft") != pr.get("draft")):
        return "PR drifted before repair handoff"
    # Revalidate the linked issue immediately before delivery: issue state,
    # labels and Copilot assignment can change without moving the PR head.
    latest_issue = api(f"repos/{repo}/issues/{issue_number}")
    latest_labels = {label.get("name") if isinstance(label, dict) else label
                     for label in latest_issue.get("labels") or []}
    if (latest_issue.get("state") != "open"
            or latest_labels & {"initiative", "agent-excluded",
                                "needs-human-decision", "blocked"}
            or not any(str(a.get("login") or "").casefold() in COPILOT_LOGINS
                       for a in latest_issue.get("assignees") or [])):
        return "linked issue drifted before repair handoff"
    marker = f"{REPAIR_MARKER}head={head_sha} run={run_id} -->"
    api(f"repos/{repo}/issues/{number}/comments", method="POST",
        body={"body": marker + "\nTrusted CI repair delivery attempted; investigate if Copilot does not respond."})
    names = ", ".join(steps)
    run_url = str(run.get("html_url") or f"https://github.com/{repo}/actions/runs/{run_id}")
    # No raw untrusted log text is sent as agent instructions. The run is linked
    # so Copilot can inspect exact failures; protected files remain out of scope.
    message = ("@copilot Please repair the failing ordinary test checks on this PR "
               f"for head `{head_sha}`. Failed steps: {names}. "
               f"Run: {run_url}. Investigate the logs and fix the root cause with "
               "regression coverage. Only modify existing low-risk product/test "
               "files; do not edit workflows, secrets, CI/merge/dispatch policy, "
               "or other protected paths. Push to this PR branch, not a new PR.")
    api(f"repos/{repo}/issues/{number}/comments", method="POST",
        body={"body": message}, token=token)
    return f"requested Copilot repair for PR #{number}, run {run_id}"


def main() -> None:
    if os.environ.get("COPILOT_REPAIR_ENABLED", "").lower() != "true":
        print("Copilot repair handoff disabled (opt-in required)")
        return
    token = os.environ.get("COPILOT_ASSIGNMENT_TOKEN", "")
    if not token:
        print("Copilot repair handoff blocked: missing user credential")
        return
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    print(dispatch(event, os.environ["REPOSITORY"], token))


if __name__ == "__main__":
    main()
