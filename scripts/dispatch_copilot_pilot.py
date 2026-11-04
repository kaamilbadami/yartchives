#!/usr/bin/env python3
"""Opt-in, at-most-once pilot dispatcher for GitHub's Copilot coding agent.

This intentionally does not replace the Jules dispatcher before an actual
Copilot issue -> PR -> protected merge pilot succeeds.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Callable

try:
    from scripts.dispatch_autonomous_issues import (
    JULES_ACTIVE_LABEL,
    JULES_FEEDBACK_LABEL,
    JULES_REVIEW_READY_LABEL,
    JULES_FAILED_LABEL,
    JULES_RETRY_LABEL,
    has_codex_reservation,
    label_names,
    task_from_issue,
    task_lock_keys,
    )
except ModuleNotFoundError:
    from dispatch_autonomous_issues import (
        JULES_ACTIVE_LABEL, JULES_FEEDBACK_LABEL, JULES_REVIEW_READY_LABEL,
        JULES_FAILED_LABEL, JULES_RETRY_LABEL, has_codex_reservation,
        label_names, task_from_issue, task_lock_keys,
    )

PILOT_LABEL = "copilot-pilot"
DISPATCH_MODES = frozenset({"pilot", "default", "queue-only"})
# Student supports Auto only. After upgrading to Pro, set the repository
# COPILOT_PILOT_MODEL variable to gpt-6-luna for low-cost pilot dispatch.
# Restrict selections until their API spelling and account eligibility are tested.
ALLOWED_MODELS = frozenset({"auto", "gpt-6-luna"})
ATTEMPT_MARKER = "<!-- copilot-dispatch-attempt:v1 -->"
COPILOT_LOGINS = frozenset({"copilot", "copilot-swe-agent", "copilot-swe-agent[bot]"})
BLOCKING_LABELS = frozenset({
    JULES_ACTIVE_LABEL, JULES_FEEDBACK_LABEL, JULES_REVIEW_READY_LABEL,
    JULES_FAILED_LABEL, JULES_RETRY_LABEL, "blocked",
    "needs-product-decision", "needs-human-decision", "agent-excluded",
    "invalid-autonomous-task", "initiative",
})


def gh_api(path: str, *, method: str = "GET", payload: dict[str, Any] | None = None,
           token: str | None = None) -> Any:
    args = ["gh", "api", "--method", method, path]
    if payload is not None:
        args += ["--input", "-"]
    env = os.environ.copy()
    if token is not None:
        env["GH_TOKEN"] = token
    response = subprocess.run(
        args, input=json.dumps(payload) if payload is not None else None,
        capture_output=True, text=True, check=True, env=env,
    )
    return json.loads(response.stdout) if response.stdout.strip() else {}


def issue_is_eligible(issue: dict[str, Any], open_numbers: set[int],
                      occupied: set[str], *, mode: str = "pilot") -> bool:
    if issue.get("state") != "open" or "pull_request" in issue:
        return False
    labels = label_names(issue)
    if (mode not in DISPATCH_MODES or mode == "queue-only"
            or (mode == "pilot" and PILOT_LABEL not in labels)
            or labels & BLOCKING_LABELS or has_codex_reservation(labels)):
        return False
    if issue.get("assignees"):
        return False
    task = task_from_issue(issue)
    if task is None or task.dependencies & open_numbers:
        return False
    return not (task_lock_keys(task) & occupied)


def preexisting_pr(prs: list[dict[str, Any]], issue_number: int) -> bool:
    # Fail closed for a known issue with a linked open PR, regardless of author.
    pattern = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#"
                         + str(issue_number) + r"\b")
    return any(pattern.search(str(pr.get("body") or "")) for pr in prs)


def run_cycle(repo: str, assignment_token: str,
              api: Callable[..., Any] = gh_api, *, model: str = "",
              mode: str = "pilot") -> str:
    if mode not in DISPATCH_MODES:
        raise ValueError("unsupported COPILOT_DISPATCH_MODE; refusing assignment")
    if mode == "queue-only":
        return "queue-only: no Copilot assignments permitted"
    if not assignment_token:
        return "disabled: COPILOT_ASSIGNMENT_TOKEN is not configured"
    selected_model = model.strip().casefold()
    if selected_model and selected_model not in ALLOWED_MODELS:
        raise ValueError("unsupported COPILOT_PILOT_MODEL; refusing assignment")
    issues = api(f"repos/{repo}/issues?state=open&per_page=100")
    prs = api(f"repos/{repo}/pulls?state=open&per_page=100")
    if not isinstance(issues, list) or not isinstance(prs, list):
        raise ValueError("unexpected GitHub API response; refusing dispatch")
    # A truncated inventory could conceal locks, open PRs or earlier attempts.
    # Fail closed rather than dispatch against incomplete repository state.
    if len(issues) >= 100 or len(prs) >= 100:
        raise RuntimeError("incomplete issue/PR inventory; refusing Copilot dispatch")
    # The existing workflow has one serialized writer group with Jules.
    # A conservative global occupied set prevents overlapping resource work.
    occupied: set[str] = set()
    for issue in issues:
        labels = label_names(issue)
        if (labels & {JULES_ACTIVE_LABEL, JULES_FEEDBACK_LABEL, JULES_REVIEW_READY_LABEL}
                or has_codex_reservation(labels) or COPILOT_LOGINS.intersection([
                    str(a.get("login") or "").casefold()
                    for a in issue.get("assignees") or [] if isinstance(a, dict)
                ])):
            task = task_from_issue(issue)
            if task:
                occupied.update(task_lock_keys(task))
    open_numbers = {int(i["number"]) for i in issues if i.get("state") == "open"
                    and "pull_request" not in i}
    # Keep exactly one outstanding pilot across *multiple* scheduled runs.
    # An attempted assignment may still be working even if Copilot has
    # temporarily removed its assignee; only an issue closure releases it.
    for other in issues:
        if "pull_request" in other or (mode == "pilot" and PILOT_LABEL not in label_names(other)):
            continue
        if task_from_issue(other) is None:
            continue
        if any(str(a.get("login") or "").casefold() in COPILOT_LOGINS
               for a in other.get("assignees") or [] if isinstance(a, dict)):
            return f"Copilot pilot #{other['number']} is already assigned"
        history = api(f"repos/{repo}/issues/{other['number']}/comments?per_page=100")
        if not isinstance(history, list):
            raise ValueError("cannot verify existing pilot history")
        if any(ATTEMPT_MARKER in str(c.get("body") or "") for c in history):
            return f"Copilot pilot #{other['number']} already attempted; awaiting outcome"
    # One explicit pilot at a time, so that the live result is interpretable.
    for issue in sorted(issues, key=lambda i: int(i["number"])):
        if not issue_is_eligible(issue, open_numbers, occupied, mode=mode):
            continue
        number = int(issue["number"])
        if preexisting_pr(prs, number):
            continue
        comments = api(f"repos/{repo}/issues/{number}/comments?per_page=100")
        if not isinstance(comments, list):
            raise ValueError("cannot verify dispatch history")
        if any(ATTEMPT_MARKER in str(c.get("body") or "") for c in comments):
            continue
        latest = api(f"repos/{repo}/issues/{number}")
        if (not issue_is_eligible(latest, open_numbers, occupied, mode=mode)
                or latest.get("body") != issue.get("body")
                or label_names(latest) != label_names(issue)):
            continue
        # Durable marker BEFORE the external assignment: ambiguous network
        # failures must not silently create duplicate Copilot agent sessions.
        api(f"repos/{repo}/issues/{number}/comments", method="POST", payload={
            "body": ATTEMPT_MARKER + "\nTrusted dispatch attempted once for "
                    + f"#{number}; pending Copilot API result. Do not retry automatically."
        })
        # Per GitHub documentation this call requires an authorized *user*
        # token; ordinary workflow GITHUB_TOKEN is not sufficient.
        assignment = {"target_repo": repo, "base_branch": "main"}
        if selected_model and selected_model != "auto":
            assignment["model"] = selected_model
        result = api(
            f"repos/{repo}/issues/{number}/assignees", method="POST",
            payload={
                "assignees": ["copilot-swe-agent[bot]"],
                "agent_assignment": assignment,
            },
            token=assignment_token,
        )
        assigned = [str(x.get("login") or "").casefold()
                    for x in result.get("assignees") or [] if isinstance(x, dict)]
        if not COPILOT_LOGINS.intersection(assigned):
            raise RuntimeError(
                f"Copilot assignment for #{number} was not confirmed; "
                "do not retry without examining the durable attempt"
            )
        return f"assigned Copilot to issue #{number}; awaiting PR evidence"
    return "no authorized, unassigned, unlocked Copilot pilot issue available"


def main() -> int:
    repo = os.environ["REPOSITORY"]
    token = os.environ.get("COPILOT_ASSIGNMENT_TOKEN", "")
    print(run_cycle(repo, token, model=os.environ.get("COPILOT_PILOT_MODEL", ""),
                    mode=os.environ.get("COPILOT_DISPATCH_MODE", "pilot")) )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
