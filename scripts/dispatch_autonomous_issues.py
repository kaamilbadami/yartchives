#!/usr/bin/env python3
"""Dispatch the highest-priority safe, non-overlapping GitHub issue to Jules."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Iterable, NamedTuple

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
MAX_ACTIVE = 2
AUTONOMOUS_MARKER = "<!-- autonomous-task -->"


class Task(NamedTuple):
    number: int
    title: str
    body: str
    priority: str
    area: str
    labels: frozenset[str]


def label_names(issue: dict[str, Any]) -> frozenset[str]:
    names: set[str] = set()
    for label in issue.get("labels", []):
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and label.get("name"):
            names.add(str(label["name"]))
    return frozenset(names)


def metadata_value(body: str, key: str) -> str | None:
    match = re.search(rf"(?mi)^\s*{re.escape(key)}\s*:\s*([^\n]+?)\s*$", body)
    return match.group(1).strip() if match else None


def task_from_issue(issue: dict[str, Any]) -> Task | None:
    body = str(issue.get("body") or "")
    if AUTONOMOUS_MARKER not in body:
        return None
    safe = (metadata_value(body, "autonomous") or "").casefold()
    priority = (metadata_value(body, "priority") or "").upper()
    area = (metadata_value(body, "area") or "").casefold()
    if safe != "true" or priority not in PRIORITY_ORDER or not area:
        return None
    return Task(
        number=int(issue["number"]),
        title=str(issue.get("title") or ""),
        body=body,
        priority=priority,
        area=area,
        labels=label_names(issue),
    )


def active_area(issue: dict[str, Any]) -> str | None:
    labels = label_names(issue)
    if "jules" not in labels:
        return None
    task = task_from_issue(issue)
    if task:
        return task.area
    title = str(issue.get("title") or "").casefold()
    body = str(issue.get("body") or "").casefold()
    if "update opportunity feed" in title or "update opportunity feed" in body:
        return "feed"
    if "quality checks" in title or "quality checks" in body:
        return "quality"
    return "unknown"


def select_tasks(issues: Iterable[dict[str, Any]], max_active: int = MAX_ACTIVE) -> list[Task]:
    issue_list = list(issues)
    active = [issue for issue in issue_list if "jules" in label_names(issue)]
    slots = max(0, max_active - len(active))
    if slots == 0:
        return []

    active_areas = {area for issue in active if (area := active_area(issue))}
    candidates: list[Task] = []
    for issue in issue_list:
        if str(issue.get("state") or "open") != "open":
            continue
        task = task_from_issue(issue)
        if not task:
            continue
        if task.labels & {"jules", "agent-ready", "blocked", "needs-product-decision"}:
            continue
        candidates.append(task)

    candidates.sort(key=lambda task: (PRIORITY_ORDER[task.priority], task.number))
    selected: list[Task] = []
    occupied = set(active_areas)
    for task in candidates:
        if len(selected) >= slots:
            break
        if task.area in occupied:
            continue
        selected.append(task)
        occupied.add(task.area)
    return selected


def gh_json(*args: str) -> Any:
    result = subprocess.run(["gh", *args], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def gh_run(*args: str) -> None:
    subprocess.run(["gh", *args], check=True)


def ensure_labels(repo: str) -> None:
    for name, color, description in (
        ("agent-ready", "0E8A16", "Bounded task suitable for an automated coding agent"),
        ("jules", "715CD7", "Dispatch this issue to Google Jules"),
        ("blocked", "B60205", "Blocked by another task or prerequisite"),
        ("needs-product-decision", "FBCA04", "Requires product judgment before autonomous execution"),
        ("autonomous-backlog", "1D76DB", "Approved backlog item eligible for autonomous dispatch"),
    ):
        gh_run(
            "label", "create", name, "--repo", repo, "--color", color,
            "--description", description, "--force",
        )


def main() -> int:
    repo = os.environ["REPOSITORY"]
    ensure_labels(repo)
    issues = gh_json(
        "api", "--paginate",
        f"repos/{repo}/issues?state=open&per_page=100",
    )
    issues = [issue for issue in issues if "pull_request" not in issue]
    selected = select_tasks(issues)
    if not selected:
        print("No safe autonomous task is currently dispatchable.")
        return 0

    for task in selected:
        gh_run(
            "issue", "edit", str(task.number), "--repo", repo,
            "--add-label", "autonomous-backlog",
            "--add-label", "agent-ready",
            "--add-label", "jules",
        )
        gh_run(
            "issue", "comment", str(task.number), "--repo", repo,
            "--body",
            (
                f"Autonomous dispatcher selected this {task.priority} task for Jules "
                f"in area `{task.area}`.\n\n"
                "Work from current `main`, keep the change bounded to this issue, add regression "
                "coverage where behavior changes, and open a PR that includes "
                f"`Closes #{task.number}`. Do not merge the PR yourself."
            ),
        )
        print(f"Dispatched #{task.number}: {task.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
