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

REPO = os.environ["REPOSITORY"]
PR_NUMBER = int(os.environ["PR_NUMBER"])
REFERENCE_RE = re.compile(r"(?im)\b(?:updates?|refs?|references?|related\s+to)\s+#(\d+)\b")
COMPLETE_RE = re.compile(r"(?im)^\s*Completes acceptance criteria for #(\d+)\s*$")
CLOSING_RE = re.compile(r"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)\b")

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
