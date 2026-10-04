#!/usr/bin/env python3
"""Reconcile open issues explicitly referenced by a merged pull request.

GitHub already handles closing keywords. This catches softer references such as
"Updates #123" without guessing whether partial work completed the parent issue.
A merged PR can opt an issue into deterministic closure with:
  Completes acceptance criteria for #123
Otherwise the workflow leaves the issue open and records the merged evidence.
"""
from __future__ import annotations
import json, os, re, subprocess, sys

REPO = os.environ.get("REPOSITORY", "dummy/repo")
PR_NUMBER = int(os.environ.get("PR_NUMBER", "0"))
REFERENCE_RE = re.compile(r"(?im)\b(?:updates?|refs?|references?|related\s+to)\s+#(\d+)\b")
COMPLETE_RE = re.compile(r"(?im)^\s*Completes acceptance criteria for #(\d+)\s*$")
CLOSING_RE = re.compile(r"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b")
SUPERSEDE_RE = re.compile(r"<!--\s*supersedes-stale-pr:\s*(\d+)(?:\s+original-issue:\s*(\d+))?\s*-->")

def gh(*args):
    return subprocess.check_output(["gh", *args, "--repo", REPO], text=True)

def main():
    pr = json.loads(gh("pr", "view", str(PR_NUMBER), "--json", "body,mergedAt,url"))
    if not pr.get("mergedAt"):
        return 0
    body = pr.get("body") or ""
    closing = {int(x) for x in CLOSING_RE.findall(body)}
    referenced = {int(x) for x in REFERENCE_RE.findall(body)}
    completed = {int(x) for x in COMPLETE_RE.findall(body)}

    superseded_by_this_pr: dict[int, tuple[int, bool]] = {}

    def extract_superseded(text: str, is_fully_completed: bool):
        for stale_pr_str, orig_issue_str in SUPERSEDE_RE.findall(text):
            stale_pr = int(stale_pr_str)
            orig_issue = None
            if orig_issue_str:
                orig_issue = int(orig_issue_str)
            else:
                try:
                    stale_data = json.loads(gh("pr", "view", str(stale_pr), "--json", "body"))
                    stale_body = stale_data.get("body") or ""
                    linked = CLOSING_RE.findall(stale_body) or REFERENCE_RE.findall(stale_body)
                    if linked:
                        orig_issue = int(linked[0])
                except Exception:
                    pass

            if orig_issue:
                if orig_issue not in superseded_by_this_pr:
                    superseded_by_this_pr[orig_issue] = (stale_pr, is_fully_completed)
                elif is_fully_completed:
                    superseded_by_this_pr[orig_issue] = (stale_pr, True)

    # For PR body, we don't assume full completion unless it's in `closing` or `completed`
    # But wait, the PR body might just have the marker. If it does, we assume it's fully completed
    # UNLESS we can check its presence in the explicitly requested lists. But if there's no other issue referenced,
    # we just fall back to fully completed. To be safe, if we find a marker for issue X in the PR body,
    # we check if X is explicitly referenced but NOT closed.
    for stale_pr_str, orig_issue_str in SUPERSEDE_RE.findall(body):
        # We need to figure out orig_issue first
        stale_pr = int(stale_pr_str)
        orig_issue = None
        if orig_issue_str:
            orig_issue = int(orig_issue_str)
        else:
            try:
                stale_data = json.loads(gh("pr", "view", str(stale_pr), "--json", "body"))
                stale_body = stale_data.get("body") or ""
                linked = CLOSING_RE.findall(stale_body) or REFERENCE_RE.findall(stale_body)
                if linked:
                    orig_issue = int(linked[0])
            except Exception:
                pass

        if orig_issue:
            is_completed = (orig_issue not in referenced) or (orig_issue in closing) or (orig_issue in completed)
            if orig_issue not in superseded_by_this_pr:
                superseded_by_this_pr[orig_issue] = (stale_pr, is_completed)
            elif is_completed:
                superseded_by_this_pr[orig_issue] = (stale_pr, True)

    for issue_num in (closing | referenced):
        try:
            issue_data = json.loads(gh("issue", "view", str(issue_num), "--json", "body"))
            issue_body = issue_data.get("body") or ""
            is_completed = (issue_num in closing) or (issue_num in completed)
            extract_superseded(issue_body, is_completed)
        except Exception:
            pass

    for orig_issue, (stale_pr, is_completed) in sorted(superseded_by_this_pr.items()):
        try:
            orig_data = json.loads(gh("issue", "view", str(orig_issue), "--json", "state,stateReason,labels,body"))

            labels_to_remove = [
                l["name"] for l in orig_data.get("labels", [])
                if l["name"] in ("jules", "jules-session", "jules-review-ready", "autonomous-backlog")
                or l["name"].startswith("jules-retry-")
                or l["name"].startswith("jules-failure-")
            ]

            if labels_to_remove:
                args = ["issue", "edit", str(orig_issue)]
                for lbl in labels_to_remove:
                    args.extend(["--remove-label", lbl])
                gh(*args)

            marker = f"<!-- post-merge-reconciliation: pr={PR_NUMBER} issue={orig_issue} -->"
            old_body = orig_data.get("body") or ""

            if is_completed:
                if marker not in old_body and orig_data.get("stateReason") != "COMPLETED":
                    if orig_data.get("state") != "OPEN":
                        gh("issue", "reopen", str(orig_issue))
                    new_body = old_body + f"\n\n{marker}"
                    gh("issue", "comment", str(orig_issue), "--body",
                       f"Post-merge reconciliation: Recovery PR #{PR_NUMBER} merged and completes the acceptance criteria originally attempted in stale PR #{stale_pr}. Closing as completed.")
                    gh("issue", "edit", str(orig_issue), "--body", new_body)
                    gh("issue", "close", str(orig_issue), "--reason", "completed")
            else:
                if orig_data.get("state") != "OPEN" and marker not in old_body:
                    gh("issue", "reopen", str(orig_issue))

                if marker not in old_body:
                    new_body = old_body + f"\n\n## Partial Recovery\n{marker}\nSome work was recovered and merged in PR #{PR_NUMBER}. The remaining acceptance criteria should be evaluated from current main."
                    gh("issue", "comment", str(orig_issue), "--body",
                       f"{marker}\nPost-merge reconciliation: Recovery PR #{PR_NUMBER} merged and partially subsumed work originally attempted in stale PR #{stale_pr}. The remaining acceptance criteria should be evaluated from current main. Leaving it open.")
                    gh("issue", "edit", str(orig_issue), "--body", new_body)

        except Exception as e:
            pass

    for number in sorted(referenced - closing):
        issue = json.loads(gh("issue", "view", str(number), "--json", "state,url"))
        if issue.get("state") != "OPEN":
            continue
        if number in completed:
            gh("issue", "comment", str(number), "--body",
               f"Post-merge reconciliation: PR #{PR_NUMBER} merged and explicitly records that it completes this issue's acceptance criteria. Closing as completed.")
            gh("issue", "close", str(number), "--reason", "completed")
        else:
            marker = f"<!-- post-merge-reconciliation: pr={PR_NUMBER} issue={number} -->"
            gh("issue", "comment", str(number), "--body",
               marker + f"\nPost-merge reconciliation: PR #{PR_NUMBER} merged and references this issue, but does not explicitly state that all acceptance criteria are complete. Leaving it open.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
