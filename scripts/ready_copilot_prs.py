#!/usr/bin/env python3
"""Trusted-main reconciliation for completed, low-risk Copilot draft PRs.

Ready-for-review is a lifecycle transition, never merge authorization.
No PR code is checked out or executed here.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any

COPILOT = "copilot"
COPILOT_APP = "copilot-swe-agent"
CLOSING_REF = re.compile(
    r"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
    r"(?:(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?#(?P<number>\d+)\b"
)
RECOVERY_MARKER = "<!-- copilot-draft-ci-recovery: head={head} -->"


def gh_json(endpoint: str) -> Any:
    result = subprocess.run(["gh", "api", endpoint], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def gh_pages(endpoint: str) -> list[dict[str, Any]]:
    result = subprocess.run(
        ["gh", "api", "--paginate", "--slurp", endpoint],
        check=True, text=True, capture_output=True,
    )
    return [row for page in json.loads(result.stdout) for row in page]


def gh_write(*args: str) -> None:
    subprocess.run(["gh", *args], check=True)


def linked_issue(pr: dict[str, Any], repo: str) -> int | None:
    refs = list(CLOSING_REF.finditer(str(pr.get("body") or "")))
    if not refs:
        return None
    if any(m.group("repo") and m.group("repo").casefold() != repo.casefold() for m in refs):
        return None
    numbers = {int(m.group("number")) for m in refs}
    return next(iter(numbers)) if len(numbers) == 1 else None


def safe_low_risk_files(files: list[dict[str, Any]]) -> bool:
    """Deliberately narrow: expand only after independent security review."""
    if not files:
        return False
    for item in files:
        path = str(item.get("filename") or "")
        # A rename reports only the destination in filename; the source may
        # be a protected workflow or policy file. Deny renames by default.
        if item.get("status") == "renamed" or item.get("previous_filename"):
            return False
        if not path or path.startswith(".github/") or ".." in path.split("/"):
            return False
        if path.startswith(("tests/", "docs/")):
            continue
        if "/" not in path and (
            path in {"README.md", "index.html"}
            or path.endswith((".js", ".css", ".html"))
        ):
            continue
        return False
    return True


def provenance_verified(
    pr: dict[str, Any],
    issue: dict[str, Any],
    files: list[dict[str, Any]],
    pr_events: list[dict[str, Any]],
    issue_events: list[dict[str, Any]],
    repo: str,
) -> tuple[bool, str]:
    if pr.get("state") != "open" or pr.get("draft") is not True:
        return False, "not an open draft"
    if str((pr.get("user") or {}).get("login") or "").casefold() != COPILOT:
        return False, "not authored by Copilot"
    head = pr.get("head") or {}
    if (
        (head.get("repo") or {}).get("full_name") != repo
        or not str(head.get("ref") or "").startswith("copilot/")
        or not re.fullmatch(r"[a-f0-9]{40}", str(head.get("sha") or ""))
        or (pr.get("base") or {}).get("ref") != "main"
    ):
        return False, "unverified branch/base/head"
    number = linked_issue(pr, repo)
    if number is None or issue.get("number") != number or issue.get("state") != "open":
        return False, "no unique open linked issue"
    if not isinstance(issue.get("labels"), list) or not isinstance(issue.get("assignees"), list):
        return False, "missing issue authorization metadata"
    if any((label.get("name") if isinstance(label, dict) else label) == "initiative"
           for label in issue["labels"]):
        return False, "parent initiative"
    if not any(str(a.get("login") or "").casefold() == COPILOT
               for a in issue["assignees"] if isinstance(a, dict)):
        return False, "issue was not assigned to Copilot"
    if not safe_low_risk_files(files):
        return False, "sensitive or unallowlisted files"
    pr_number = pr.get("number")
    if not any(
        e.get("event") == "connected"
        and str((e.get("actor") or {}).get("login") or "").casefold() == COPILOT
        and (e.get("subject") or {}).get("number") == pr_number
        and ((e.get("subject") or {}).get("repository") or {}).get("full_name") == repo
        for e in issue_events
    ):
        return False, "missing Copilot issue-to-PR connection"
    finished = [
        str(e.get("created_at") or "") for e in pr_events
        if e.get("event") == "copilot_work_finished"
        and (e.get("performed_via_github_app") or {}).get("slug") == COPILOT_APP
    ]
    if not finished:
        return False, "Copilot has not reported work finished"
    last_finished = max(finished)
    if any(
        e.get("event") == "copilot_work_started"
        and str(e.get("created_at") or "") > last_finished
        for e in pr_events
    ):
        return False, "Copilot resumed work after last completion"
    if not any(
        e.get("event") == "review_requested"
        and str((e.get("actor") or {}).get("login") or "").casefold() == COPILOT
        and str(e.get("created_at") or "") >= last_finished
        for e in pr_events
    ):
        return False, "Copilot has not requested review after completion"
    return True, "completed low-risk Copilot draft"


def exact_head_quality_green(runs: list[dict[str, Any]], sha: str) -> bool:
    return any(
        r.get("name") == "Quality checks" and r.get("head_sha") == sha
        and r.get("status") == "completed" and r.get("conclusion") == "success"
        for r in runs
    )


def exact_merge_tests_green(status: dict[str, Any], merge_sha: str) -> bool:
    """Accept only the required tests context on the current synthetic merge SHA."""
    if not re.fullmatch(r"[a-f0-9]{40}", merge_sha):
        return False
    # GitHub returns combined-status entries newest first. An older green
    # status must not override a newer failure/pending status in the same context.
    latest_tests = next(
        (entry for entry in (status.get("statuses") or [])
         if entry.get("context") == "tests"), None
    )
    return bool(latest_tests and latest_tests.get("state") == "success")


def recovery_allowed(runs: list[dict[str, Any]], sha: str) -> bool:
    """One trusted recovery attempt only for missing or approval-gated CI."""
    current = [r for r in runs if r.get("name") == "Quality checks"
               and r.get("head_sha") == sha]
    return not current or all(
        r.get("status") == "completed" and r.get("conclusion") == "action_required"
        for r in current
    )


def main() -> int:
    repo = os.environ["REPOSITORY"]
    drafts = [pr for pr in gh_pages(f"repos/{repo}/pulls?state=open&per_page=100")
              if pr.get("draft")]
    for pr in drafts:
        number = int(pr["number"])
        try:
            issue_number = linked_issue(pr, repo)
            if issue_number is None:
                print(f"PR #{number}: no unique local issue linkage; skipping.")
                continue
            issue = gh_json(f"repos/{repo}/issues/{issue_number}")
            files = gh_pages(f"repos/{repo}/pulls/{number}/files?per_page=100")
            pr_events = gh_pages(f"repos/{repo}/issues/{number}/timeline?per_page=100")
            issue_events = gh_pages(f"repos/{repo}/issues/{issue_number}/timeline?per_page=100")
            ok, reason = provenance_verified(pr, issue, files, pr_events, issue_events, repo)
            if not ok:
                print(f"PR #{number}: {reason}; keeping draft.")
                continue
            head = pr["head"]
            sha = head["sha"]
            runs = gh_json(
                f"repos/{repo}/actions/runs?head_sha={sha}&per_page=100"
            ).get("workflow_runs") or []
            fresh = gh_json(f"repos/{repo}/pulls/{number}")
            if (fresh.get("state") != "open" or fresh.get("draft") is not True
                    or (fresh.get("head") or {}).get("sha") != sha
                    or (fresh.get("base") or {}).get("ref") != "main"):
                print(f"PR #{number}: head/state changed during validation; skipping.")
                continue
            # A trusted main-branch recovery run tests refs/pull/N/merge and
            # publishes the required 'tests' status on that exact merge SHA.
            # Never treat a status on a stale synthetic merge as current.
            merge_sha = str(fresh.get("merge_commit_sha") or "")
            merge_green = False
            if re.fullmatch(r"[a-f0-9]{40}", merge_sha):
                merge_status = gh_json(f"repos/{repo}/commits/{merge_sha}/status")
                merge_green = exact_merge_tests_green(merge_status, merge_sha)
            if exact_head_quality_green(runs, sha) or merge_green:
                current_issue = gh_json(f"repos/{repo}/issues/{issue_number}")
                still_ok, reason = provenance_verified(
                    fresh, current_issue, files, pr_events, issue_events, repo
                )
                if not still_ok:
                    print(f"PR #{number}: {reason} on recheck; keeping draft.")
                    continue
                gh_write("pr", "ready", str(number), "--repo", repo)
                print(f"PR #{number}: ready for review at verified head {sha}; NOT merge approval.")
                continue
            if not recovery_allowed(runs, sha):
                print(f"PR #{number}: CI in progress or failed; no draft transition.")
                continue
            comments = gh_pages(f"repos/{repo}/issues/{number}/comments?per_page=100")
            marker = RECOVERY_MARKER.format(head=sha)
            if any(marker in str(c.get("body") or "") for c in comments):
                print(f"PR #{number}: CI recovery already attempted for {sha}; bounded wait.")
                continue
            # Durable attempt marker before dispatch prevents duplicate costly runs.
            gh_write("api", "--method", "POST",
                     f"repos/{repo}/issues/{number}/comments",
                     "-f", f"body={marker}\nOne bounded read-only Quality recovery attempt for this exact draft head.")
            # Run the trusted workflow from main, not the untrusted PR branch.
            # quality.yml checks out the current synthetic merge and publishes
            # the required tests status only if its merge SHA stays unchanged.
            gh_write("workflow", "run", "quality.yml", "--repo", repo,
                     "--ref", "main", "-f", "pr_recovery=true",
                     "-f", f"pr_number={number}")
            print(f"PR #{number}: dispatched one current-merge Quality recovery; remains draft.")
        except (subprocess.CalledProcessError, ValueError, KeyError, TypeError) as exc:
            print(f"PR #{number}: blocked safely by verification/API error: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
