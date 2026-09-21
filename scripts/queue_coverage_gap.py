#!/usr/bin/env python3
"""Queue the next bounded generic coverage gap as an autonomous issue."""

import argparse
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.provider_fingerprint import fingerprint_provider
from scripts.dispatch_autonomous_issues import Task, task_from_issue, active_jules_task, task_lock_keys, JULES_FEEDBACK_LABEL

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

def find_all_gaps(universe: dict[str, Any]) -> list[tuple[str, int, list[dict[str, Any]], str]]:
    benchmark_employers = []
    for e in universe.get("employers", []):
        seeds = e.get("seed_sets", [])
        if "fortune-500-2026" in seeds or "cs-benchmark" in seeds:
            benchmark_employers.append(e)

    no_hint = []
    unresolved_families = defaultdict(list)

    for e in benchmark_employers:
        if e.get("provider", {}).get("status") == "resolved":
            continue

        providers = set()
        for md in e.get("seed_metadata", {}).values():
            if isinstance(md, dict):
                for hint in md.get("domain_hints", []):
                    p_info = fingerprint_provider(hint)
                    providers.add(p_info.get("family", "unknown"))

        if providers:
            for p in providers:
                unresolved_families[p].append(e)
        else:
            no_hint.append(e)

    gaps = []
    if no_hint:
        gaps.append(("Discovery gap (No domain hint)", len(no_hint), no_hint, "discovery"))

    for f, emps in unresolved_families.items():
        if f not in {"unknown", "unknown/none", "custom_unknown"}:
            gaps.append((f"ATS Family integration ({f})", len(emps), emps, f"ats-{f}"))

    gaps.sort(key=lambda x: -x[1])
    return gaps

def get_active_and_coverage_issues(repo: str) -> tuple[list[Any], list[dict[str, Any]]]:
    issues = _gh_json(
        "api",
        "--paginate",
        f"repos/{repo}/issues?state=open&per_page=100",
    )
    open_issues = [issue for issue in issues if "pull_request" not in issue]

    active_issues = []
    for issue in open_issues:
        labels = {
            label if isinstance(label, str) else label.get("name")
            for label in issue.get("labels", [])
        }
        task = task_from_issue(issue)
        if task and ("jules-session" in labels or JULES_FEEDBACK_LABEL in labels or "jules" in labels):
             active_issues.append(task)

    # Gap identity is persisted in the issue body marker, not in an optional
    # classification label. Scan all open issues so duplicate prevention keeps
    # working even if labels are renamed, removed, or never created.
    return active_issues, open_issues

def issue_already_queued(coverage_issues: list[dict[str, Any]], gap_id: str) -> bool:
    for issue in coverage_issues:
        body = issue.get("body") or ""
        if f"<!-- coverage-gap: {gap_id} -->" in body:
            return True
    return False

def resources_conflict_with_active_work(active_tasks: list[Any]) -> bool:
    candidate = Task(
        0,
        "coverage automation candidate",
        "",
        "P2",
        "coverage-automation",
        frozenset(),
        frozenset({"automation", "coverage-analysis"}),
        frozenset(),
    )
    new_task_locks = task_lock_keys(candidate)
    for task in active_tasks:
        locks = task_lock_keys(task)
        if locks & new_task_locks:
            return True
        if "resource:feed-core" in locks:
            return True
    return False

def create_issue(repo: str, gap_name: str, count: int, gap_id: str, employers: list[dict[str, Any]]) -> None:
    title = f"Automate coverage gap: {gap_name}"
    employer_list = "\n".join(f"- {e['name']}" for e in employers[:10])
    if len(employers) > 10:
        employer_list += f"\n- ...and {len(employers) - 10} more"

    body = f"""<!-- coverage-gap: {gap_id} -->
<!-- autonomous-task -->
priority: P2
area: coverage-automation
resources: automation, coverage-analysis
autonomous: true

## Coverage Gap Identified

A coverage gap was identified among benchmark employers:
- **Measured impact**: {count} unresolved benchmark employers
- **Affected family/cause**: {gap_name}
- **Expected scope**: Bound the fix to this generic gap rather than manual additions.

### Examples affected:
{employer_list}

## Instructions
Please investigate this gap.
- If this is an ATS integration gap, consider adding or fixing the integration for this family.
- If this is a discovery gap, consider adding ways to seed these employers (e.g. from their corporate domains, or adding an aggregator logic).
- Do not scrape LinkedIn or Handshake directly.
- Work boundedly to resolve root causes rather than manually adding direct entries if possible.
- Update `employer_universe.json` or source scripts to recover these.

## Stop condition
Exactly one next task may be created or refreshed. Stop if no generic improvements remain. Do not create a batch of employer-specific issues.
"""
    _gh_run(
        "issue",
        "create",
        "--repo", repo,
        "--title", title,
        "--body", body,
        "--label", "autonomous-backlog",
        "--label", "agent-ready"
    )

def main() -> None:
    parser = argparse.ArgumentParser(description="Queue the next bounded generic coverage gap.")
    parser.add_argument("--repo", default=os.environ.get("REPOSITORY"))
    parser.add_argument("--universe", type=Path, default=Path(ROOT / "employer_universe.json"))
    args = parser.parse_args()

    if not args.repo:
        print("REPOSITORY environment variable or --repo argument is required.")
        sys.exit(1)

    universe = json.loads(args.universe.read_text(encoding="utf-8"))
    gaps = find_all_gaps(universe)

    if not gaps:
        print("No actionable coverage gap found.")
        return

    active_tasks, coverage_issues = get_active_and_coverage_issues(args.repo)

    if resources_conflict_with_active_work(active_tasks):
        print("Active feed work or coverage tasks prevent queuing new tasks at this time.")
        return

    selected_gap = None
    for gap in gaps:
        gap_name, count, employers, gap_id = gap
        if count < 2:
            print(f"Skipping {gap_id} (count {count}): insufficient generic impact.")
            continue

        if issue_already_queued(coverage_issues, gap_id):
            print(f"Issue for gap {gap_id} already exists or is in progress. Skipping.")
            continue

        selected_gap = gap
        break

    if not selected_gap:
        print("No unsupported generic gaps remaining to queue.")
        return

    gap_name, count, employers, gap_id = selected_gap
    print(f"Queuing next actionable gap: {gap_name} affecting {count} employers.")

    create_issue(args.repo, gap_name, count, gap_id, employers)
    print(f"Queued issue for gap: {gap_id}")

if __name__ == "__main__":
    main()
