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
RECOVERY_MARKER = "<!-- copilot-draft-ci-recovery: head={head} merge={merge} -->"
RECOVERY_RE = re.compile(
    r"<!-- copilot-draft-ci-recovery: head=([a-f0-9]{40})(?: merge=([a-f0-9]{40}))? -->"
)
MAX_RECOVERY_ATTEMPTS_PER_HEAD = 2


def recovery_attempts(comments: list[dict[str, Any]], head: str) -> list[str | None]:
    """Count only trusted controller attempts, including legacy head-only markers."""
    attempts: list[str | None] = []
    for comment in comments:
        author = str((comment.get("user") or {}).get("login") or "").casefold()
        if author != "github-actions[bot]":
            continue
        for match in RECOVERY_RE.finditer(str(comment.get("body") or "")):
            if match.group(1) == head:
                attempts.append(match.group(2))
    return attempts


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
    # A historical Copilot connection is not sufficient: the issue can be
    # disconnected from this PR after the agent finishes. GitHub timelines are
    # chronological, so require the latest matching link event to be a
    # Copilot-authored connection (and not a later disconnection).
    link_events = [
        e for e in issue_events
        if e.get("event") in {"connected", "disconnected"}
        and (e.get("subject") or {}).get("number") == pr_number
        and ((e.get("subject") or {}).get("repository") or {}).get("full_name") == repo
    ]
    if (not link_events or link_events[-1].get("event") != "connected"
            or str((link_events[-1].get("actor") or {}).get("login") or "").casefold() != COPILOT):
        return False, "missing or disconnected Copilot issue-to-PR connection"
    # GitHub's PR timeline is ordered and includes 'committed' events without
    # created_at. Compare event positions, not only timestamps: a push after
    # Copilot finished invalidates completion even if the head later passes CI.
    finished_positions = [
        idx for idx, event in enumerate(pr_events)
        if event.get("event") == "copilot_work_finished"
        and (event.get("performed_via_github_app") or {}).get("slug") == COPILOT_APP
    ]
    if not finished_positions:
        return False, "Copilot has not reported work finished"
    last_finished_pos = finished_positions[-1]
    later_events = pr_events[last_finished_pos + 1:]
    if any(event.get("event") in {
        "copilot_work_started", "committed", "head_ref_force_pushed", "synchronize"
    } for event in later_events):
        return False, "PR head changed or Copilot resumed after completion"
    # A request that was subsequently withdrawn is not an outstanding
    # Copilot review request. GitHub records review_request_removed separately
    # from review_requested; treat later removals as revoking readiness until
    # Copilot explicitly requests review again. Conservative for multiple
    # reviewers: an ambiguous removal blocks rather than inferring consent.
    review_events = [
        event for event in later_events
        if event.get("event") in {"review_requested", "review_request_removed"}
    ]
    if (not review_events or review_events[-1].get("event") != "review_requested"
            or str((review_events[-1].get("actor") or {}).get("login") or "").casefold() != COPILOT):
        return False, "no outstanding Copilot review request after completion"
    return True, "completed low-risk Copilot draft"


def exact_head_quality_green(runs: list[dict[str, Any]], sha: str) -> bool:
    # A previous success must not override a newer failure or pending run for
    # the same head. GitHub returns newest runs first; timestamps/IDs make the
    # choice explicit when available, preserving API order on exact ties.
    current = [r for r in runs if r.get("name") == "Quality checks"
               and r.get("head_sha") == sha]
    # GitHub may emit a newer approval-gated pull_request run even after an
    # independently executed read-only Quality run succeeded for this *same*
    # immutable head. action_required did not execute tests, so it must not
    # invalidate real CI evidence. A newer *executed* failure or pending run
    # still blocks readiness. With only gated runs, readiness remains blocked.
    executed = [r for r in current if not (
        r.get("status") == "completed" and r.get("conclusion") == "action_required"
    )]
    if not executed:
        return False
    latest = max(executed, key=lambda r: (
        str(r.get("created_at") or ""), int(r.get("id") or 0)
    ))
    return latest.get("status") == "completed" and latest.get("conclusion") == "success"


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


def trusted_recovery_head_green(status: dict[str, Any], sha: str, repo: str) -> bool:
    """Accept an exact-head result only from a trusted-main recovery run.

    The read-only head job cannot publish statuses. A separate trusted job
    publishes this context after verifying the tested immutable head still
    belongs to the open PR. An untrusted or stale context is not evidence.
    """
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        return False
    latest = next((entry for entry in status.get("statuses") or []
                   if entry.get("context") == "copilot-head-tests"), None)
    if not latest or latest.get("state") != "success":
        return False
    if str((latest.get("creator") or {}).get("login") or "").casefold() != "github-actions[bot]":
        return False
    target = str(latest.get("target_url") or "")
    return bool(re.fullmatch(
        rf"https://github\\.com/{re.escape(repo)}/actions/runs/[0-9]+", target
    ))


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
            merge_failed = False
            if re.fullmatch(r"[a-f0-9]{40}", merge_sha):
                merge_status = gh_json(f"repos/{repo}/commits/{merge_sha}/status")
                merge_green = exact_merge_tests_green(merge_status, merge_sha)
                latest_tests = next(
                    (entry for entry in (merge_status.get("statuses") or [])
                     if entry.get("context") == "tests"), None
                )
                merge_failed = bool(latest_tests and
                                    latest_tests.get("state") in {"failure", "error"})
            if merge_failed:
                print(f"BLOCKED_REQUIRES_DECISION PR #{number}: current synthetic merge tests failed; no automatic retry.")
                continue
            head_green = exact_head_quality_green(runs, sha)
            head_recoverable = recovery_allowed(runs, sha)
            if not head_green and head_recoverable:
                # GitHub approval-gates Copilot pull_request workflows. A
                # trusted-main, read-only exact-head recovery can independently
                # verify that immutable head without approving untrusted CI.
                head_status = gh_json(f"repos/{repo}/commits/{sha}/status")
                head_green = trusted_recovery_head_green(head_status, sha, repo)
            # Head-only green CI is not the required synthetic merge-commit
            # status. Recover the current merge even when the head is green;
            # otherwise a Copilot draft can become ready with no path to
            # publishing the required 'tests' status before safe merge.
            # A synthetic merge result validates integration, but cannot stand in
            # for an executed exact-head Quality run. Approval-gated or absent
            # head CI is not evidence of a passing head; never mark ready on
            # merge status alone.
            if merge_green and head_green:
                current_issue = gh_json(f"repos/{repo}/issues/{issue_number}")
                current_events = gh_pages(f"repos/{repo}/issues/{number}/timeline?per_page=100")
                current_issue_events = gh_pages(
                    f"repos/{repo}/issues/{issue_number}/timeline?per_page=100"
                )
                still_ok, reason = provenance_verified(
                    fresh, current_issue, files, current_events, current_issue_events, repo
                )
                if not still_ok:
                    print(f"PR #{number}: {reason} on recheck; keeping draft.")
                    continue
                # Main can advance while timeline/provenance is rechecked,
                # changing refs/pull/N/merge without changing the PR head.
                # Never transition on a stale merge-status result.
                latest_pr = gh_json(f"repos/{repo}/pulls/{number}")
                if (latest_pr.get("state") != "open"
                        or latest_pr.get("draft") is not True
                        or (latest_pr.get("head") or {}).get("sha") != sha
                        or (latest_pr.get("base") or {}).get("ref") != "main"
                        or latest_pr.get("merge_commit_sha") != merge_sha
                        # A new main commit can advance base.sha before GitHub
                        # recomputes refs/pull/N/merge. The old merge SHA may
                        # still appear green, so pin the verified base commit.
                        or not re.fullmatch(
                            r"[a-f0-9]{40}",
                            str((fresh.get("base") or {}).get("sha") or ""),
                        )
                        or (latest_pr.get("base") or {}).get("sha") != (
                            fresh.get("base") or {}).get("sha")
                        # The PR body is an authorization input: a late edit
                        # could replace the verified child issue with an
                        # initiative-closing keyword without changing its head.
                        or latest_pr.get("body") != fresh.get("body")
                        or (latest_pr.get("user") or {}).get("login") != (fresh.get("user") or {}).get("login")
                        or (latest_pr.get("head") or {}).get("ref") != head.get("ref")
                        or ((latest_pr.get("head") or {}).get("repo") or {}).get("full_name") != ((head.get("repo") or {}).get("full_name"))):
                    print(f"PR #{number}: head/merge/state drift before ready; keeping draft.")
                    continue
                gh_write("pr", "ready", str(number), "--repo", repo)
                print(f"PR #{number}: ready for review at verified head {sha} and merge {merge_sha}; NOT merge approval.")
                continue
            if not (head_green or head_recoverable):
                print(f"PR #{number}: head CI in progress or failed; no draft transition or recovery.")
                continue
            if not re.fullmatch(r"[a-f0-9]{40}", merge_sha):
                print(f"PR #{number}: current synthetic merge SHA unavailable; keeping draft.")
                continue
            # Even a green merge is insufficient when Copilot's exact-head
            # pull_request run was approval-gated. Dispatch the same bounded
            # recovery to validate the immutable head in a read-only job.
            comments = gh_pages(f"repos/{repo}/issues/{number}/comments?per_page=100")
            attempts = recovery_attempts(comments, sha)
            if merge_sha in attempts or None in attempts:
                # Legacy head-only markers lack a merge identity; fail closed
                # rather than silently replay an already dispatched recovery.
                print(f"PR #{number}: CI recovery already attempted for this merge/head; bounded wait.")
                continue
            if len(attempts) >= MAX_RECOVERY_ATTEMPTS_PER_HEAD:
                print(f"BLOCKED_REQUIRES_DECISION PR #{number}: exhausted "
                      f"{MAX_RECOVERY_ATTEMPTS_PER_HEAD} trusted merge-CI attempts for head {sha}.")
                continue
            marker = RECOVERY_MARKER.format(head=sha, merge=merge_sha)
            # Durable marker before dispatch prevents duplicate costly runs.
            # One additional attempt is allowed if main advances and changes
            # the synthetic merge SHA, but the per-head budget stays bounded.
            gh_write("api", "--method", "POST",
                     f"repos/{repo}/issues/{number}/comments",
                     "-f", f"body={marker}\nBounded read-only Quality recovery for this exact draft head and merge.")
            # Run the trusted workflow from main, not the untrusted PR branch.
            # quality.yml checks out the current synthetic merge and publishes
            # the required tests status only if its merge SHA stays unchanged.
            gh_write("workflow", "run", "quality.yml", "--repo", repo,
                     "--ref", "main", "-f", "pr_recovery=true",
                     "-f", f"pr_number={number}", "-f", f"pr_head_sha={sha}")
            print(f"PR #{number}: dispatched one current-merge Quality recovery; remains draft.")
        except (subprocess.CalledProcessError, ValueError, KeyError, TypeError) as exc:
            print(f"PR #{number}: blocked safely by verification/API error: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
