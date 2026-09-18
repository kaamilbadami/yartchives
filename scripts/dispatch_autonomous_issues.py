#!/usr/bin/env python3
"""Dispatch the highest-priority safe, non-overlapping GitHub issue to Jules."""

from __future__ import annotations

import json
import os
import re
import subprocess
from typing import Any, Callable, Iterable, NamedTuple
from urllib import parse, request

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
MAX_ACTIVE = 2
AUTONOMOUS_MARKER = "<!-- autonomous-task -->"
JULES_API_ROOT = "https://jules.googleapis.com/v1alpha"
JULES_ACTIVE_LABEL = "jules-session"
JULES_REVIEW_READY_LABEL = "jules-review-ready"
JULES_FAILED_LABEL = "jules-failed"
JULES_SESSION_MARKER = "<!-- jules-session-id: {session_id} -->"
JULES_TERMINAL_STATES = {"COMPLETED", "FAILED"}
CODEX_RESERVED_LABEL = "codex"
CODEX_WORKER_PREFIX = "codex-worker-"


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


def active_jules_task(issue: dict[str, Any]) -> Task | None:
    """Return active Jules work only after a real Jules session exists."""
    if JULES_ACTIVE_LABEL not in label_names(issue):
        return None
    return task_from_issue(issue)


def session_id_from_comments(comments: Iterable[dict[str, Any]]) -> str | None:
    """Read the persisted Jules session ID from new or legacy dispatcher comments."""
    marker = re.compile(r"<!--\s*jules-session-id:\s*([^\s>]+)\s*-->")
    legacy = re.compile(r"created Jules session ['\x60]?([^'\x60\s]+)['\x60]?")
    for comment in reversed(list(comments)):
        body = str(comment.get("body") or "")
        match = marker.search(body) or legacy.search(body)
        if match:
            return match.group(1)
    return None


def pull_request_url(session: dict[str, Any]) -> str | None:
    for output in session.get("outputs", []):
        if not isinstance(output, dict):
            continue
        pull_request = output.get("pullRequest")
        if isinstance(pull_request, dict) and pull_request.get("url"):
            return str(pull_request["url"])
    return None


def replace_issue_labels_in_memory(
    issue: dict[str, Any],
    *,
    remove: Iterable[str] = (),
    add: Iterable[str] = (),
) -> None:
    labels = set(label_names(issue))
    labels.difference_update(remove)
    labels.update(add)
    issue["labels"] = [{"name": label} for label in sorted(labels)]


def reconcile_jules_sessions(
    issues: list[dict[str, Any]],
    *,
    repo: str,
    api_key: str,
    load_comments: Callable[[int], list[dict[str, Any]]],
    get_session: Callable[..., dict[str, Any]] | None = None,
    run_gh: Callable[..., None] | None = None,
) -> None:
    """Release terminal Jules sessions before selecting more autonomous work."""
    if get_session is None:
        get_session = jules_json
    if run_gh is None:
        run_gh = gh_run

    for issue in issues:
        labels = label_names(issue)
        if JULES_ACTIVE_LABEL not in labels:
            continue

        number = int(issue["number"])
        session_id = session_id_from_comments(load_comments(number))
        if not session_id:
            print(
                f"Keeping #{number} active: no persisted Jules session ID could be found."
            )
            continue

        session = get_session(api_key, f"/sessions/{session_id}")
        state = str(session.get("state") or "STATE_UNSPECIFIED")
        if state not in JULES_TERMINAL_STATES:
            print(f"Jules session {session_id} for #{number} is still {state}.")
            continue

        terminal_label = (
            JULES_REVIEW_READY_LABEL if state == "COMPLETED" else JULES_FAILED_LABEL
        )
        run_gh(
            "issue", "edit", str(number), "--repo", repo,
            "--remove-label", JULES_ACTIVE_LABEL,
            "--remove-label", "jules",
            "--add-label", terminal_label,
        )
        replace_issue_labels_in_memory(
            issue,
            remove=(JULES_ACTIVE_LABEL, "jules"),
            add=(terminal_label,),
        )

        pr_url = pull_request_url(session)
        if state == "COMPLETED":
            detail = (
                f"Jules completed session `{session_id}` and released this automation slot."
            )
            if pr_url:
                detail += f"\n\nPull request: {pr_url}"
            else:
                detail += "\n\nNo pull request output was reported by the Jules API."
        else:
            detail = (
                f"Jules session `{session_id}` ended in FAILED state and released this "
                "automation slot. It will not be retried automatically."
            )

        run_gh(
            "issue", "comment", str(number), "--repo", repo,
            "--body", detail,
        )
        print(f"Reconciled Jules session {session_id} for #{number}: {state}.")


def has_codex_reservation(labels: frozenset[str]) -> bool:
    return CODEX_RESERVED_LABEL in labels or any(
        label.startswith(CODEX_WORKER_PREFIX) for label in labels
    )


def reserved_codex_task(issue: dict[str, Any]) -> Task | None:
    """Return autonomous work reserved for one of the Codex scheduled workers."""
    if not has_codex_reservation(label_names(issue)):
        return None
    return task_from_issue(issue)


def select_tasks(issues: Iterable[dict[str, Any]], max_active: int = MAX_ACTIVE) -> list[Task]:
    issue_list = list(issues)
    active_jules = [
        task
        for issue in issue_list
        if (task := active_jules_task(issue)) is not None
    ]
    slots = max(0, max_active - len(active_jules))
    if slots == 0:
        return []

    reserved_codex = [
        task
        for issue in issue_list
        if (task := reserved_codex_task(issue)) is not None
    ]
    active_areas = {task.area for task in [*active_jules, *reserved_codex]}
    candidates: list[Task] = []
    for issue in issue_list:
        if str(issue.get("state") or "open") != "open":
            continue
        task = task_from_issue(issue)
        if not task:
            continue
        if (
            task.labels
            & {
                JULES_ACTIVE_LABEL,
                JULES_REVIEW_READY_LABEL,
                JULES_FAILED_LABEL,
                "blocked",
                "needs-product-decision",
            }
            or has_codex_reservation(task.labels)
        ):
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


def flatten_paginated_pages(pages: Any) -> list[Any]:
    if not isinstance(pages, list):
        raise TypeError("paginated GitHub response must be a list")
    flattened: list[Any] = []
    for page in pages:
        if not isinstance(page, list):
            raise TypeError("each paginated GitHub response page must be a list")
        flattened.extend(page)
    return flattened


def gh_paginated_json(*args: str) -> list[Any]:
    result = subprocess.run(
        ["gh", *args, "--paginate", "--slurp"],
        check=True,
        text=True,
        capture_output=True,
    )
    return flatten_paginated_pages(json.loads(result.stdout))


def gh_run(*args: str) -> None:
    subprocess.run(["gh", *args], check=True)


def jules_json(
    api_key: str,
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{JULES_API_ROOT}{path}",
        method=method,
        data=data,
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
    )
    with request.urlopen(req, timeout=30) as response:
        decoded = response.read().decode("utf-8")
    return json.loads(decoded) if decoded else {}


def find_jules_source(
    api_key: str,
    repo: str,
    api_get: Callable[..., dict[str, Any]] = jules_json,
) -> str:
    owner, name = repo.split("/", 1)
    page_token: str | None = None
    while True:
        query = {"pageSize": 100}
        if page_token:
            query["pageToken"] = page_token
        response = api_get(api_key, f"/sources?{parse.urlencode(query)}")
        for source in response.get("sources", []):
            github_repo = source.get("githubRepo") or {}
            if (
                str(github_repo.get("owner") or "").casefold() == owner.casefold()
                and str(github_repo.get("repo") or "").casefold() == name.casefold()
            ):
                source_name = str(source.get("name") or "")
                if source_name:
                    return source_name
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    raise RuntimeError(f"Jules has no connected GitHub source for {repo}")


def session_title(repo: str, task: Task) -> str:
    return f"[{repo} #{task.number}] {task.title}"


def session_prompt(repo: str, task: Task) -> str:
    issue_url = f"https://github.com/{repo}/issues/{task.number}"
    return (
        f"Work on GitHub issue #{task.number}: {task.title}\n"
        f"{issue_url}\n\n"
        f"{task.body.strip()}\n\n"
        "Treat the current repository as the source of truth. Work from current main. "
        "Keep the change bounded to this issue, prefer root-cause fixes, and add regression "
        "coverage where behavior changes. Open a pull request that includes "
        f"'Closes #{task.number}'. Do not merge the pull request yourself."
    )


def create_jules_session(
    api_key: str,
    source_name: str,
    repo: str,
    task: Task,
    api_post: Callable[..., dict[str, Any]] = jules_json,
) -> dict[str, Any]:
    return api_post(
        api_key,
        "/sessions",
        method="POST",
        payload={
            "prompt": session_prompt(repo, task),
            "title": session_title(repo, task),
            "sourceContext": {
                "source": source_name,
                "githubRepoContext": {"startingBranch": "main"},
            },
            "requirePlanApproval": False,
            "automationMode": "AUTO_CREATE_PR",
        },
    )


def dispatch_task(
    task: Task,
    *,
    repo: str,
    api_key: str,
    source_name: str,
    create_session: Callable[..., dict[str, Any]] = create_jules_session,
    run_gh: Callable[..., None] = gh_run,
) -> dict[str, Any]:
    session = create_session(api_key, source_name, repo, task)
    session_id = str(session.get("id") or "")
    session_url = str(session.get("url") or "")
    if not session_id or not session_url:
        raise RuntimeError(f"Jules session creation for issue #{task.number} returned no id/url")

    run_gh(
        "issue", "edit", str(task.number), "--repo", repo,
        "--add-label", "autonomous-backlog",
        "--add-label", "agent-ready",
        "--add-label", "jules",
        "--add-label", JULES_ACTIVE_LABEL,
    )
    run_gh(
        "issue", "comment", str(task.number), "--repo", repo,
        "--body",
        (
            f"{JULES_SESSION_MARKER.format(session_id=session_id)}\n"
            f"Autonomous dispatcher created Jules session '{session_id}' for this "
            f"{task.priority} task in area '{task.area}'.\n\n"
            f"Jules session: {session_url}\n\n"
            "The issue is counted as active only while the Jules API reports it non-terminal."
        ),
    )
    return session


def ensure_labels(repo: str) -> None:
    for name, color, description in (
        ("agent-ready", "0E8A16", "Bounded task suitable for an automated coding agent"),
        ("jules", "715CD7", "Assigned to Google Jules"),
        (JULES_ACTIVE_LABEL, "5319E7", "A real Jules API session is actively using a Jules slot"),
        (JULES_REVIEW_READY_LABEL, "8250DF", "Jules finished; review the resulting GitHub PR"),
        (JULES_FAILED_LABEL, "D73A4A", "Jules session failed and requires follow-up"),
        (CODEX_RESERVED_LABEL, "0969DA", "Reserved for a scheduled Codex worker"),
        ("codex-worker-1", "1F6FEB", "Reserved for Codex scheduled worker 1"),
        ("codex-worker-2", "54AEFF", "Reserved for Codex scheduled worker 2"),
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
    issues = gh_paginated_json(
        "api",
        f"repos/{repo}/issues?state=open&per_page=100",
    )
    issues = [issue for issue in issues if "pull_request" not in issue]
    api_key = os.environ["JULES_API_KEY"]

    def load_comments(number: int) -> list[dict[str, Any]]:
        return gh_paginated_json(
            "api",
            f"repos/{repo}/issues/{number}/comments?per_page=100",
        )

    reconcile_jules_sessions(
        issues,
        repo=repo,
        api_key=api_key,
        load_comments=load_comments,
    )
    selected = select_tasks(issues)
    if not selected:
        print("No safe autonomous task is currently dispatchable.")
        return 0

    source_name = find_jules_source(api_key, repo)
    for task in selected:
        session = dispatch_task(
            task,
            repo=repo,
            api_key=api_key,
            source_name=source_name,
        )
        print(
            f"Started Jules session {session['id']} for #{task.number}: {task.title} "
            f"({session['url']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
