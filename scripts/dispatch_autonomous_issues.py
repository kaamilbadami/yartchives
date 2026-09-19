#!/usr/bin/env python3
"""Dispatch the highest-priority safe, non-overlapping GitHub issue to Jules."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, NamedTuple
from urllib import parse, request

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
MAX_ACTIVE = 15
AREA_RESOURCE_LOCKS = {
    "feed": frozenset({"feed-core"}),
    "feed-quality": frozenset({"feed-core"}),
    "dedupe": frozenset({"feed-core", "identity"}),
    "identity": frozenset({"feed-core", "identity"}),
    "frontend": frozenset({"frontend-state"}),
    "frontend-state": frozenset({"frontend-state"}),
    "link-precedence": frozenset({"feed-core", "links"}),
    "listing-lifecycle": frozenset({"feed-core", "links"}),
    "link-quality": frozenset({"links"}),
    "evidence-cache": frozenset({"requirements", "cache"}),
    "requirement-extraction": frozenset({"requirements", "cache"}),
    "provider-audit": frozenset({"authoritative-evidence", "requirements"}),
    "evidence": frozenset({"authoritative-evidence", "requirements"}),
    "apply-next-ui": frozenset({"frontend-state", "ranking", "apply-next-ui"}),
    "apply-next-explanation": frozenset({"frontend-state", "apply-next-ui", "requirements"}),
    "evidence-ux": frozenset({"frontend-state", "apply-next-ui", "authoritative-evidence"}),
    "action-reversibility": frozenset({"frontend-state", "apply-next-ui"}),
    "ranking": frozenset({"ranking"}),
    "ranking-sensitivity": frozenset({"ranking"}),
    "ranking-regression": frozenset({"ranking"}),
    "ranking-stability": frozenset({"ranking"}),
    "coverage": frozenset({"coverage"}),
    "coverage-benchmark": frozenset({"coverage"}),
    "coverage-diagnostics": frozenset({"coverage"}),
    "employer-resolution": frozenset({"coverage", "source-collection"}),
    "performance": frozenset({"frontend-state"}),
    "automation": frozenset({"automation"}),
    "quality": frozenset({"quality"}),
}
AUTONOMOUS_MARKER = "<!-- autonomous-task -->"
JULES_API_ROOT = "https://jules.googleapis.com/v1alpha"
JULES_ACTIVE_LABEL = "jules-session"
JULES_REVIEW_READY_LABEL = "jules-review-ready"
JULES_FAILED_LABEL = "jules-failed"
JULES_FEEDBACK_LABEL = "jules-needs-feedback"
JULES_RETRY_LABEL = "jules-retry-ready"
JULES_SESSION_MARKER = "<!-- jules-session-id: {session_id} -->"
JULES_RETRY_MARKER = "<!-- jules-retry-from: {session_id} -->"
JULES_INFRA_RETRY_MARKER = "<!-- jules-infra-retry-from: {session_id} -->"
JULES_FEEDBACK_MARKER = "<!-- jules-feedback: {session_id} -->"
JULES_FEEDBACK_SENT_MARKER = "<!-- jules-feedback-sent: {comment_id} -->"
JULES_AUTO_FEEDBACK_MARKER = "<!-- jules-auto-feedback: {session_id}:{question_key} -->"
JULES_CLARIFICATION_HANDLED_MARKER = (
    "<!-- jules-clarification-handled: {session_id}:{question_key} -->"
)
JULES_TERMINAL_STATES = {"COMPLETED", "FAILED"}
JULES_PRODUCTIVE_STATES = {"QUEUED", "PLANNING", "IN_PROGRESS"}
CODEX_RESERVED_LABEL = "codex"
CODEX_WORKER_PREFIX = "codex-worker-"
DEFAULT_POLL_SECONDS = 30
DEFAULT_WATCH_SECONDS = 13 * 60
DEFAULT_STALE_SECONDS = 3 * 60 * 60
MAX_AUTO_CLARIFICATIONS = 2


class Task(NamedTuple):
    number: int
    title: str
    body: str
    priority: str
    area: str
    labels: frozenset[str]
    resources: frozenset[str] = frozenset()
    dependencies: frozenset[int] = frozenset()


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


def dependency_numbers(body: str) -> frozenset[int] | None:
    value = metadata_value(body, "depends_on")
    if not value:
        return frozenset()
    dependencies: set[int] = set()
    for token in re.split(r"[,\s]+", value):
        if not token:
            continue
        match = re.fullmatch(r"#?(\d+)", token)
        if match is None:
            return None
        dependencies.add(int(match.group(1)))
    return frozenset(dependencies)


def task_from_issue(issue: dict[str, Any]) -> Task | None:
    body = str(issue.get("body") or "")
    if AUTONOMOUS_MARKER not in body:
        return None
    safe = (metadata_value(body, "autonomous") or "").casefold()
    priority = (metadata_value(body, "priority") or "").upper()
    area = (metadata_value(body, "area") or "").casefold()
    resources_value = metadata_value(body, "resources") or ""
    resources = frozenset(
        resource.strip().casefold()
        for resource in resources_value.split(",")
        if resource.strip()
    )
    dependencies = dependency_numbers(body)
    if (
        safe != "true"
        or priority not in PRIORITY_ORDER
        or not area
        or dependencies is None
        or (area not in AREA_RESOURCE_LOCKS and not resources)
    ):
        return None
    return Task(
        number=int(issue["number"]),
        title=str(issue.get("title") or ""),
        body=body,
        priority=priority,
        area=area,
        labels=label_names(issue),
        resources=resources,
        dependencies=dependencies,
    )


def task_lock_keys(task: Task) -> frozenset[str]:
    """Return the scheduler locks held by a task.

    Every task always locks its exact area. Known areas also use conservative
    shared-resource defaults for cross-area hot paths, and optional issue metadata
    can add locks with `resources: foo, bar`.
    """
    resources = AREA_RESOURCE_LOCKS.get(task.area, frozenset()) | task.resources
    return frozenset(
        {f"area:{task.area}", *(f"resource:{resource}" for resource in resources)}
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


def pending_feedback_from_comments(
    comments: Iterable[dict[str, Any]],
    session_id: str,
) -> tuple[str, str] | None:
    """Return the newest explicit, not-yet-forwarded GitHub feedback comment."""
    comment_list = list(comments)
    sent_ids: set[str] = set()
    sent_pattern = re.compile(r"<!--\s*jules-feedback-sent:\s*(\d+)\s*-->")
    for comment in comment_list:
        body = str(comment.get("body") or "")
        sent_ids.update(sent_pattern.findall(body))

    marker = re.compile(
        rf"<!--\s*jules-feedback:\s*{re.escape(session_id)}\s*-->"
    )
    for comment in reversed(comment_list):
        comment_id = str(comment.get("id") or "")
        if not comment_id or comment_id in sent_ids:
            continue
        body = str(comment.get("body") or "")
        if not marker.search(body):
            continue
        prompt = marker.sub("", body, count=1).strip()
        if prompt:
            return comment_id, prompt
    return None


def clarification_key(question: str) -> str:
    """Return a stable short key for one Jules clarification message."""
    normalized = " ".join(question.casefold().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def clarification_handled_for_question(
    comments: Iterable[dict[str, Any]], session_id: str, question: str
) -> bool:
    """Return whether this exact clarification was already answered."""
    key = clarification_key(question)
    marker = re.compile(
        rf"<!--\s*jules-clarification-handled:\s*"
        rf"{re.escape(session_id)}:{re.escape(key)}\s*-->"
    )
    return any(marker.search(str(comment.get("body") or "")) for comment in comments)


def auto_clarification_count(
    comments: Iterable[dict[str, Any]], session_id: str
) -> int:
    """Count routine clarifications already auto-answered for one Jules session."""
    marker = re.compile(
        rf"<!--\s*jules-auto-feedback:\s*{re.escape(session_id)}:[^\s>]+\s*-->"
    )
    return sum(
        1
        for comment in comments
        if marker.search(str(comment.get("body") or ""))
    )


def clarification_requires_product_decision(question: str) -> bool:
    """Keep only genuine user-facing/product-policy choices gated on the user."""
    text = " ".join(question.casefold().split())
    direct_product_signals = (
        "product decision",
        "user-facing",
        "user facing",
        "default behavior",
        "default option",
        "default sort",
        "should be the default",
        "what should the default",
        "which should be the default",
        "eligibility policy",
        "location preference",
        "relocation preference",
        "should users",
        "should the user",
        "what should users",
        "which option should users",
        "copy should",
        "wording should",
    )
    if any(signal in text for signal in direct_product_signals):
        return True

    weight_terms = ("ranking weight", "score weight", "scoring weight")
    weight_decision_phrases = (
        "what should",
        "which should",
        "should the ranking",
        "should the score",
        "should the scoring",
        "set the ranking",
        "set the score",
        "set the scoring",
    )
    return any(term in text for term in weight_terms) and any(
        phrase in text for phrase in weight_decision_phrases
    )


def routine_clarification_response(question: str) -> str:
    """Tell Jules how to resolve technical ambiguity without inventing product policy."""
    return (
        "Proceed autonomously. Resolve this from current main, the issue acceptance "
        "criteria, existing tests, and repository documentation. Preserve established "
        "user-visible behavior and choose the smallest root-cause implementation that "
        "fits the existing architecture. Do not wait for confirmation on technical "
        "implementation choices, test scope, generated artifacts, or PR creation. If "
        "repository evidence is genuinely conflicting and the choice would change "
        "user-facing product semantics, stop and ask again with the conflict and concrete "
        f"options.\n\nClarification to resolve: {question}"
    )


def retry_marker_from_comments(comments: Iterable[dict[str, Any]]) -> str | None:
    pattern = re.compile(r"<!--\s*jules-retry-from:\s*([^\s>]+)\s*-->")
    for comment in reversed(list(comments)):
        match = pattern.search(str(comment.get("body") or ""))
        if match:
            return match.group(1)
    return None


def infrastructure_retry_marker_from_comments(
    comments: Iterable[dict[str, Any]],
) -> str | None:
    pattern = re.compile(r"<!--\s*jules-infra-retry-from:\s*([^\s>]+)\s*-->")
    for comment in reversed(list(comments)):
        match = pattern.search(str(comment.get("body") or ""))
        if match:
            return match.group(1)
    return None


def latest_retry_marker_from_comments(
    comments: Iterable[dict[str, Any]],
) -> str | None:
    pattern = re.compile(
        r"<!--\s*jules-(?:infra-)?retry-from:\s*([^\s>]+)\s*-->"
    )
    for comment in reversed(list(comments)):
        match = pattern.search(str(comment.get("body") or ""))
        if match:
            return match.group(1)
    return None


def retry_context_from_comments(comments: Iterable[dict[str, Any]]) -> str | None:
    pattern = re.compile(
        r"<!--\s*jules-(?:infra-)?retry-from:\s*[^\s>]+\s*-->"
    )
    for comment in reversed(list(comments)):
        body = str(comment.get("body") or "")
        if pattern.search(body):
            return pattern.sub("", body, count=1).strip()
    return None


def legacy_failed_retry_context(
    comments: Iterable[dict[str, Any]],
) -> tuple[str, str] | None:
    """Return one retry context for failures parked before retry support existed."""
    comment_list = list(comments)
    if retry_marker_from_comments(comment_list) is not None:
        return None

    session_id = session_id_from_comments(comment_list)
    if not session_id:
        return None

    terminal_prefix = (
        f"Jules session `{session_id}` ended in FAILED state and released this "
        "automation slot. It will not be retried automatically."
    )
    terminal_body: str | None = None
    for comment in reversed(comment_list):
        body = str(comment.get("body") or "")
        if terminal_prefix in body:
            terminal_body = body
            break
    if terminal_body is None:
        return None

    # Re-evaluate historical parked failures through the current retry classifier.
    # This lets newly-recognized Jules/platform failures receive their one migration
    # retry without reopening genuine code/test failures or already-retried work.
    no_diagnostics = "No additional failure diagnostics were reported by the Jules API."
    diagnostics_header = "Failure diagnostics:"
    if no_diagnostics in terminal_body:
        return None
    if diagnostics_header in terminal_body and not retryable_jules_failure([terminal_body]):
        return None

    context = (
        "This Jules failure was parked before the current one-retry classification "
        "was available. Treat it as the single legacy migration retry and preserve "
        "the recorded failure context."
    )
    prior_feedback = explicit_feedback_for_session(comment_list, session_id)
    if prior_feedback:
        context += (
            "\n\nPrior explicit GitHub feedback that must be preserved in the retry:"
            f"\n\n> {prior_feedback.replace(chr(10), chr(10) + '> ')}"
        )
    if diagnostics_header in terminal_body:
        context += f"\n\nPrior failure record:\n\n{terminal_body}"
    return session_id, context


def latest_retryable_failed_session(
    comments: Iterable[dict[str, Any]],
) -> tuple[str, str] | None:
    """Return the newest durable FAILED record that is clearly Jules/platform retryable."""
    pattern = re.compile(
        r"Jules session `([^`]+)` ended in FAILED state and released this "
        r"automation slot\.",
        re.IGNORECASE,
    )
    for comment in reversed(list(comments)):
        body = str(comment.get("body") or "")
        match = pattern.search(body)
        if match and retryable_jules_failure([body]):
            return match.group(1), body
    return None


def migrate_legacy_jules_failures(
    issues: list[dict[str, Any]],
    *,
    repo: str,
    load_comments: Callable[[int], list[dict[str, Any]]],
    run_gh: Callable[..., None] | None = None,
) -> None:
    """Move eligible historical failures into bounded task or infrastructure retry paths."""
    if run_gh is None:
        run_gh = gh_run

    for issue in issues:
        if JULES_FAILED_LABEL not in label_names(issue):
            continue
        number = int(issue["number"])
        comments = load_comments(number)

        infra_failure = latest_retryable_failed_session(comments)
        if (
            infra_failure is not None
            and infrastructure_retry_marker_from_comments(comments) is None
        ):
            session_id, failure_record = infra_failure
            marker = JULES_INFRA_RETRY_MARKER.format(session_id=session_id)
            context = (
                "This is one bounded infrastructure retry. The prior attempt failed "
                "inside Jules/platform execution rather than from a demonstrated repository "
                "code/test defect. Preserve useful prior task context, but do not treat this "
                "platform failure as consuming the task-level retry budget."
                f"\n\nPrior infrastructure failure record:\n\n{failure_record}"
            )
        else:
            retry = legacy_failed_retry_context(comments)
            if retry is None:
                continue
            session_id, context = retry
            marker = JULES_RETRY_MARKER.format(session_id=session_id)

        run_gh(
            "issue", "edit", str(number), "--repo", repo,
            "--remove-label", JULES_FAILED_LABEL,
            "--add-label", JULES_RETRY_LABEL,
        )
        replace_issue_labels_in_memory(
            issue,
            remove=(JULES_FAILED_LABEL,),
            add=(JULES_RETRY_LABEL,),
        )
        run_gh(
            "issue", "comment", str(number), "--repo", repo,
            "--body", f"{marker}\n{context}",
        )
        print(f"Migrated Jules failure for #{number} into one bounded retry.")

def explicit_feedback_for_session(
    comments: Iterable[dict[str, Any]], session_id: str
) -> str | None:
    marker = re.compile(
        rf"<!--\s*jules-feedback:\s*{re.escape(session_id)}\s*-->"
    )
    for comment in reversed(list(comments)):
        body = str(comment.get("body") or "")
        if marker.search(body):
            prompt = marker.sub("", body, count=1).strip()
            if prompt:
                return prompt
    return None


def jules_capacity_exhausted(value: Any) -> bool:
    """Return whether a Jules response/error indicates temporary account capacity exhaustion."""
    text = str(value).casefold().replace("_", " ")
    capacity_signals = (
        "quota exceeded",
        "resource exhausted",
        "too many requests",
        "http error 429",
        "status code 429",
        "daily task limit",
        "weekly task limit",
        "task limit reached",
        "task quota",
    )
    return any(signal in text for signal in capacity_signals)


def retryable_jules_failure(diagnostics: Iterable[str]) -> bool:
    text = "\n".join(str(item).casefold() for item in diagnostics)
    non_retryable = (
        "quota exceeded",
        "permission denied",
        "invalid argument",
        "authentication",
        "test failed",
        "tests failed",
        "merge conflict",
    )
    if any(pattern in text for pattern in non_retryable):
        return False
    retryable = (
        "workspace became unavailable",
        "workspace unavailable",
        "service unavailable",
        "temporarily unavailable",
        "server error",
        "backend error",
        "infrastructure",
        "preparing the virtual machine environment",
        "failed to prepare the virtual machine environment",
        "virtual machine environment for the task",
        "internal execution stopped",
        "internal error",
        "jules encountered an error when working on the task",
        "jules was unable to complete the task",
    )
    return any(pattern in text for pattern in retryable)


def send_jules_message(api_key: str, session_id: str, prompt: str) -> None:
    """Send explicit user feedback to an existing Jules session."""
    jules_json(
        api_key,
        f"/sessions/{session_id}:sendMessage",
        method="POST",
        payload={"prompt": prompt},
    )


def delete_jules_session(api_key: str, session_id: str) -> None:
    """Delete one superseded Jules session."""
    jules_json(
        api_key,
        f"/sessions/{session_id}",
        method="DELETE",
    )


def completed_session_pr_from_comments(
    comments: Iterable[dict[str, Any]],
    repo: str,
) -> tuple[str, int] | None:
    """Return the newest completed Jules session tied to a PR in this repository."""
    owner, name = (re.escape(part) for part in repo.split("/", 1))
    pattern = re.compile(
        rf"Jules completed session \`([^\`]+)\`.*?"
        rf"Pull request:\s*https://github\.com/{owner}/{name}/pull/(\d+)",
        re.IGNORECASE | re.DOTALL,
    )
    for comment in reversed(list(comments)):
        match = pattern.search(str(comment.get("body") or ""))
        if match:
            return match.group(1), int(match.group(2))
    return None


def reconcile_historical_merged_jules_issues(
    repo: str,
    *,
    load_open_autonomous: Callable[[], list[dict[str, Any]]] | None = None,
    load_comments: Callable[[int], list[dict[str, Any]]] | None = None,
    get_pr: Callable[[int], dict[str, Any]] | None = None,
    run_gh: Callable[..., None] | None = None,
) -> None:
    """Close historical open autonomous issues whose exact Jules PR already merged."""
    if load_open_autonomous is None:
        load_open_autonomous = lambda: gh_paginated_json(
            "api",
            f"repos/{repo}/issues?state=open&labels={parse.quote('autonomous-backlog')}&per_page=100",
        )
    if load_comments is None:
        load_comments = lambda number: gh_paginated_json(
            "api",
            f"repos/{repo}/issues/{number}/comments?per_page=100",
        )
    if get_pr is None:
        get_pr = lambda number: gh_json("api", f"repos/{repo}/pulls/{number}")
    if run_gh is None:
        run_gh = gh_run

    for issue in load_open_autonomous():
        if "pull_request" in issue:
            continue
        number = int(issue["number"])
        completed = completed_session_pr_from_comments(load_comments(number), repo)
        if completed is None:
            continue
        _, pr_number = completed
        pr = get_pr(pr_number)
        if pr.get("merged") is not True:
            continue

        run_gh(
            "api", "--method", "PATCH", f"repos/{repo}/issues/{number}",
            "-f", "state=closed", "-f", "state_reason=completed",
        )
        print(
            f"Closed historical autonomous issue #{number} after verifying merged "
            f"Jules PR #{pr_number}."
        )


def migrate_historical_no_pr_review_ready(
    repo: str,
    *,
    load_review_ready: Callable[[], list[dict[str, Any]]] | None = None,
    load_comments: Callable[[int], list[dict[str, Any]]] | None = None,
    run_gh: Callable[..., None] | None = None,
) -> None:
    """Repair review-ready issues created before completed-without-PR handling existed."""
    if load_review_ready is None:
        load_review_ready = lambda: gh_paginated_json(
            "api",
            f"repos/{repo}/issues?state=open&labels={parse.quote(JULES_REVIEW_READY_LABEL)}&per_page=100",
        )
    if load_comments is None:
        load_comments = lambda number: gh_paginated_json(
            "api",
            f"repos/{repo}/issues/{number}/comments?per_page=100",
        )
    if run_gh is None:
        run_gh = gh_run

    completed_pattern = re.compile(
        r"Jules completed session `([^`]+)` and released this automation slot\.",
        re.IGNORECASE,
    )
    no_pr_text = "No pull request output was reported by the Jules API."

    for issue in load_review_ready():
        if "pull_request" in issue:
            continue
        if AUTONOMOUS_MARKER not in str(issue.get("body") or ""):
            continue

        number = int(issue["number"])
        comments = load_comments(number)
        latest_completed: tuple[str, str] | None = None
        for comment in reversed(comments):
            body = str(comment.get("body") or "")
            match = completed_pattern.search(body)
            if match:
                latest_completed = (match.group(1), body)
                break
        if latest_completed is None:
            continue

        session_id, body = latest_completed
        if no_pr_text not in body:
            continue

        already_retried = retry_marker_from_comments(comments) is not None
        terminal_label = JULES_FAILED_LABEL if already_retried else JULES_RETRY_LABEL
        run_gh(
            "issue", "edit", str(number), "--repo", repo,
            "--remove-label", JULES_REVIEW_READY_LABEL,
            "--add-label", terminal_label,
        )

        if already_retried:
            detail = (
                f"Historical lifecycle repair: Jules session `{session_id}` completed "
                "without producing a pull request after an earlier automatic retry. "
                "Moved this issue from review-ready to failed instead of leaving a "
                "nonexistent review blocking dependencies."
            )
        else:
            detail = (
                f"{JULES_RETRY_MARKER.format(session_id=session_id)}\n"
                f"Historical lifecycle repair: Jules session `{session_id}` completed "
                "without producing a pull request before no-PR lifecycle handling existed. "
                "Moved this issue from review-ready to one context-preserving retry."
            )
        run_gh(
            "issue", "comment", str(number), "--repo", repo,
            "--body", detail,
        )
        print(
            f"Migrated historical no-PR review-ready issue #{number} to {terminal_label}."
        )


def cleanup_merged_jules_sessions(
    repo: str,
    api_key: str,
    *,
    load_review_ready: Callable[[], list[dict[str, Any]]] | None = None,
    load_comments: Callable[[int], list[dict[str, Any]]] | None = None,
    get_pr: Callable[[int], dict[str, Any]] | None = None,
    delete_session: Callable[[str], None] | None = None,
    run_gh: Callable[..., None] | None = None,
) -> None:
    """Delete completed Jules sessions only after their exact linked PR is merged."""
    if load_review_ready is None:
        load_review_ready = lambda: gh_paginated_json(
            "api",
            f"repos/{repo}/issues?state=all&labels={parse.quote(JULES_REVIEW_READY_LABEL)}&per_page=100",
        )
    if load_comments is None:
        load_comments = lambda number: gh_paginated_json(
            "api",
            f"repos/{repo}/issues/{number}/comments?per_page=100",
        )
    if get_pr is None:
        get_pr = lambda number: gh_json("api", f"repos/{repo}/pulls/{number}")
    if delete_session is None:
        delete_session = lambda session_id: delete_jules_session(api_key, session_id)
    if run_gh is None:
        run_gh = gh_run

    for issue in load_review_ready():
        if "pull_request" in issue:
            continue
        number = int(issue["number"])
        completed = completed_session_pr_from_comments(load_comments(number), repo)
        if completed is None:
            continue
        session_id, pr_number = completed
        pr = get_pr(pr_number)
        if pr.get("merged") is not True:
            continue

        try:
            delete_session(session_id)
            print(
                f"Deleted completed Jules session {session_id} after merged PR "
                f"#{pr_number} for issue #{number}."
            )
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                print(
                    f"Could not delete completed Jules session {session_id} after merged "
                    f"PR #{pr_number}; keeping review-ready state for retry: {exc}"
                )
                continue
            print(
                f"Completed Jules session {session_id} was already deleted after merged "
                f"PR #{pr_number}; marking cleanup complete."
            )

        run_gh(
            "api", "--method", "PATCH", f"repos/{repo}/issues/{number}",
            "-f", "state=closed", "-f", "state_reason=completed",
        )
        run_gh(
            "issue", "edit", str(number), "--repo", repo,
            "--remove-label", JULES_REVIEW_READY_LABEL,
        )


def pull_request_url(session: dict[str, Any]) -> str | None:
    for output in session.get("outputs", []):
        if not isinstance(output, dict):
            continue
        pull_request = output.get("pullRequest")
        if isinstance(pull_request, dict) and pull_request.get("url"):
            return str(pull_request["url"])
    return None


def latest_agent_message(activities: Iterable[dict[str, Any]]) -> str | None:
    """Return the newest user-facing Jules message from a session activity list."""
    ordered = sorted(
        (activity for activity in activities if isinstance(activity, dict)),
        key=lambda activity: str(activity.get("createTime") or ""),
        reverse=True,
    )
    for activity in ordered:
        agent_messaged = activity.get("agentMessaged")
        if isinstance(agent_messaged, dict) and agent_messaged.get("agentMessage"):
            return str(agent_messaged["agentMessage"]).strip()
    return None


def failure_diagnostics(
    session: dict[str, Any],
    activities: Iterable[dict[str, Any]],
    *,
    max_items: int = 4,
) -> list[str]:
    """Extract bounded human-readable failure context from Jules API payloads."""
    interesting_keys = {
        "message",
        "error",
        "reason",
        "statusmessage",
        "failurereason",
        "agentmessage",
        # Jules documents failure context in activity descriptions and bash artifacts.
        # Capture those too so a generic sessionFailed.reason does not hide the
        # actionable setup/install error that preceded it.
        "description",
        "output",
    }
    found: list[str] = []

    def collect(value: Any, key: str = "") -> None:
        if len(found) >= max_items:
            return
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                collect(child_value, str(child_key))
                if len(found) >= max_items:
                    return
        elif isinstance(value, list):
            for child in value:
                collect(child, key)
                if len(found) >= max_items:
                    return
        elif key.casefold() in interesting_keys and value not in (None, ""):
            text = str(value).strip()
            if text and text not in found:
                found.append(text[:1000])

    collect(session)
    ordered = sorted(
        (activity for activity in activities if isinstance(activity, dict)),
        key=lambda activity: str(activity.get("createTime") or ""),
        reverse=True,
    )
    for activity in ordered[:10]:
        collect(activity)
        if len(found) >= max_items:
            break
    return found


def list_jules_activities(api_key: str, session_id: str) -> list[dict[str, Any]]:
    """List every activity for one Jules session."""
    activities: list[dict[str, Any]] = []
    page_token: str | None = None
    while True:
        query: dict[str, Any] = {"pageSize": 100}
        if page_token:
            query["pageToken"] = page_token
        response = jules_json(
            api_key,
            f"/sessions/{session_id}/activities?{parse.urlencode(query)}",
        )
        page = response.get("activities", [])
        if isinstance(page, list):
            activities.extend(
                activity for activity in page if isinstance(activity, dict)
            )
        page_token = str(response.get("nextPageToken") or "") or None
        if not page_token:
            return activities


def parse_jules_time(value: Any) -> datetime | None:
    """Parse Jules RFC3339 timestamps without making missing timestamps fatal."""
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def latest_jules_activity_time(
    session: dict[str, Any],
    activities: Iterable[dict[str, Any]],
) -> datetime | None:
    """Return the newest API-observed session/activity timestamp."""
    timestamps = [
        parse_jules_time(session.get("updateTime")),
        parse_jules_time(session.get("createTime")),
    ]
    timestamps.extend(
        parse_jules_time(activity.get("createTime"))
        for activity in activities
        if isinstance(activity, dict)
    )
    valid = [timestamp for timestamp in timestamps if timestamp is not None]
    return max(valid) if valid else None


def stale_jules_session(
    session: dict[str, Any],
    activities: Iterable[dict[str, Any]],
    *,
    now: datetime,
    stale_seconds: int,
) -> tuple[bool, datetime | None]:
    """Return whether a nonterminal Jules session has gone silent past the watchdog."""
    last_activity = latest_jules_activity_time(session, activities)
    if last_activity is None:
        return False, None
    return (now - last_activity).total_seconds() >= stale_seconds, last_activity


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
    load_activities: Callable[[str], list[dict[str, Any]]] | None = None,
    send_feedback: Callable[[str, str], None] | None = None,
    delete_session: Callable[[str], None] | None = None,
    run_gh: Callable[..., None] | None = None,
    now_fn: Callable[[], datetime] | None = None,
    stale_seconds: int = DEFAULT_STALE_SECONDS,
) -> bool:
    """Reconcile Jules sessions and report whether account capacity is exhausted."""
    if get_session is None:
        get_session = jules_json
    if send_feedback is None:
        send_feedback = lambda session_id, prompt: send_jules_message(
            api_key, session_id, prompt
        )
    if delete_session is None:
        delete_session = lambda session_id: delete_jules_session(api_key, session_id)
    if run_gh is None:
        run_gh = gh_run
    if now_fn is None:
        now_fn = lambda: datetime.now(timezone.utc)

    capacity_paused = False

    for issue in issues:
        labels = label_names(issue)
        if not ({JULES_ACTIVE_LABEL, JULES_FEEDBACK_LABEL} & labels):
            continue

        number = int(issue["number"])
        comments = load_comments(number)
        session_id = session_id_from_comments(comments)
        if not session_id:
            print(
                f"Keeping #{number} active: no persisted Jules session ID could be found."
            )
            continue

        try:
            session = get_session(api_key, f"/sessions/{session_id}")
        except Exception as exc:
            if getattr(exc, "code", None) != 404:
                raise

            already_retried = retry_marker_from_comments(comments) is not None
            terminal_label = JULES_FAILED_LABEL if already_retried else JULES_RETRY_LABEL
            run_gh(
                "issue", "edit", str(number), "--repo", repo,
                "--remove-label", JULES_ACTIVE_LABEL,
                "--remove-label", JULES_FEEDBACK_LABEL,
                "--remove-label", "jules",
                "--add-label", terminal_label,
            )
            replace_issue_labels_in_memory(
                issue,
                remove=(JULES_ACTIVE_LABEL, JULES_FEEDBACK_LABEL, "jules"),
                add=(terminal_label,),
            )
            if already_retried:
                detail = (
                    f"Jules session `{session_id}` is no longer available from the Jules API "
                    "after its automatic retry. The dispatcher released the stale slot and "
                    "parked the issue as failed instead of creating another duplicate session."
                )
            else:
                detail = (
                    f"{JULES_RETRY_MARKER.format(session_id=session_id)}\n"
                    f"Jules session `{session_id}` is no longer available from the Jules API. "
                    "The dispatcher released the stale slot. One automatic context-preserving "
                    "retry is allowed."
                )
            run_gh(
                "issue", "comment", str(number), "--repo", repo,
                "--body", detail,
            )
            print(
                f"Released missing Jules session {session_id} for #{number}; "
                f"marked {terminal_label}."
            )
            continue

        state = str(session.get("state") or "STATE_UNSPECIFIED")

        if state not in JULES_TERMINAL_STATES:
            session_time = latest_jules_activity_time(session, ())
            now = now_fn()
            should_probe = (
                session_time is not None
                and (now - session_time).total_seconds() >= stale_seconds
            )
            if should_probe:
                activities = (
                    load_activities(session_id)
                    if load_activities is not None
                    else list_jules_activities(api_key, session_id)
                )
                is_stale, last_activity = stale_jules_session(
                    session,
                    activities,
                    now=now,
                    stale_seconds=stale_seconds,
                )
                if is_stale:
                    try:
                        delete_session(session_id)
                    except Exception as exc:
                        print(
                            f"Could not delete stale Jules session {session_id} for "
                            f"#{number}; keeping its slot reserved: {exc}"
                        )
                        continue

                    already_retried = retry_marker_from_comments(comments) is not None
                    terminal_label = (
                        JULES_FAILED_LABEL if already_retried else JULES_RETRY_LABEL
                    )
                    run_gh(
                        "issue", "edit", str(number), "--repo", repo,
                        "--remove-label", JULES_ACTIVE_LABEL,
                        "--remove-label", JULES_FEEDBACK_LABEL,
                        "--remove-label", "jules",
                        "--add-label", terminal_label,
                    )
                    replace_issue_labels_in_memory(
                        issue,
                        remove=(JULES_ACTIVE_LABEL, JULES_FEEDBACK_LABEL, "jules"),
                        add=(terminal_label,),
                    )
                    silence = int((now - last_activity).total_seconds()) if last_activity else stale_seconds
                    if already_retried:
                        detail = (
                            f"Jules session `{session_id}` stayed nonterminal with no API "
                            f"activity for {silence // 60} minutes after its automatic retry. "
                            "The dispatcher deleted the stale session, released its slot, and "
                            "parked the issue as failed instead of retrying indefinitely."
                        )
                    else:
                        detail = (
                            f"{JULES_RETRY_MARKER.format(session_id=session_id)}\n"
                            f"Jules session `{session_id}` stayed nonterminal with no API "
                            f"activity for {silence // 60} minutes. The dispatcher deleted "
                            "the stale session and released its slot. One automatic "
                            "context-preserving retry is allowed."
                        )
                        last_message = latest_agent_message(activities)
                        if last_message:
                            detail += (
                                "\n\nLast Jules message before the session became stale:\n\n> "
                                + last_message.replace(chr(10), chr(10) + "> ")
                            )
                        prior_feedback = explicit_feedback_for_session(comments, session_id)
                        if prior_feedback:
                            detail += (
                                "\n\nPrior explicit GitHub feedback that must be preserved "
                                "in the retry:\n\n> "
                                + prior_feedback.replace(chr(10), chr(10) + "> ")
                            )
                    run_gh(
                        "issue", "comment", str(number), "--repo", repo,
                        "--body", detail,
                    )
                    print(
                        f"Released stale Jules session {session_id} for #{number} after "
                        f"{silence // 60} minutes without API activity."
                    )
                    continue

        if state == "AWAITING_USER_FEEDBACK":
            activities = (
                load_activities(session_id)
                if load_activities is not None
                else list_jules_activities(api_key, session_id)
            )
            question = latest_agent_message(activities)
            question_key = clarification_key(question) if question else None

            if JULES_FEEDBACK_LABEL in labels:
                pending_feedback = pending_feedback_from_comments(comments, session_id)
                if pending_feedback is not None:
                    comment_id, prompt = pending_feedback
                    send_feedback(session_id, prompt)
                    handled_marker = (
                        JULES_CLARIFICATION_HANDLED_MARKER.format(
                            session_id=session_id,
                            question_key=question_key,
                        )
                        if question_key
                        else ""
                    )
                    run_gh(
                        "issue", "comment", str(number), "--repo", repo,
                        "--body",
                        (
                            f"{JULES_FEEDBACK_SENT_MARKER.format(comment_id=comment_id)}\n"
                            f"{handled_marker}\n"
                            f"Forwarded explicit GitHub feedback to Jules session "
                            f"`{session_id}`."
                        ).strip(),
                    )
                    print(
                        f"Forwarded GitHub feedback comment {comment_id} to Jules "
                        f"session {session_id} for #{number}."
                    )
                    continue

            question_already_handled = bool(
                question
                and clarification_handled_for_question(comments, session_id, question)
            )
            routine_question = bool(
                question and not clarification_requires_product_decision(question)
            )
            auto_answered = auto_clarification_count(comments, session_id)

            if (
                routine_question
                and not question_already_handled
                and auto_answered >= MAX_AUTO_CLARIFICATIONS
            ):
                try:
                    delete_session(session_id)
                except Exception as exc:
                    print(
                        f"Could not delete clarification-loop Jules session {session_id} "
                        f"for #{number}; keeping its slot reserved: {exc}"
                    )
                    continue

                already_retried = retry_marker_from_comments(comments) is not None
                terminal_label = (
                    JULES_FAILED_LABEL if already_retried else JULES_RETRY_LABEL
                )
                run_gh(
                    "issue", "edit", str(number), "--repo", repo,
                    "--remove-label", JULES_ACTIVE_LABEL,
                    "--remove-label", JULES_FEEDBACK_LABEL,
                    "--remove-label", "jules",
                    "--remove-label", "needs-product-decision",
                    "--add-label", terminal_label,
                )
                replace_issue_labels_in_memory(
                    issue,
                    remove=(
                        JULES_ACTIVE_LABEL,
                        JULES_FEEDBACK_LABEL,
                        "jules",
                        "needs-product-decision",
                    ),
                    add=(terminal_label,),
                )
                if already_retried:
                    detail = (
                        f"Jules session `{session_id}` asked more than "
                        f"{MAX_AUTO_CLARIFICATIONS} routine clarifications after its "
                        "automatic retry. The dispatcher deleted the nonproductive session, "
                        "released its slot, and parked the issue as failed instead of "
                        "retrying indefinitely."
                    )
                else:
                    detail = (
                        f"{JULES_RETRY_MARKER.format(session_id=session_id)}\n"
                        f"Jules session `{session_id}` asked more than "
                        f"{MAX_AUTO_CLARIFICATIONS} routine clarifications without making "
                        "productive progress. The dispatcher deleted the session and released "
                        "its slot. One automatic context-preserving retry is allowed."
                    )
                    if question:
                        detail += (
                            "\n\nLatest routine clarification before retry:\n\n> "
                            + question.replace(chr(10), chr(10) + "> ")
                        )
                run_gh(
                    "issue", "comment", str(number), "--repo", repo,
                    "--body", detail,
                )
                print(
                    f"Released clarification-loop Jules session {session_id} for #{number}; "
                    f"marked {terminal_label}."
                )
                continue

            if question_already_handled:
                print(
                    f"Jules session {session_id} for #{number} is processing feedback "
                    "for the current clarification."
                )
                continue

            if routine_question:
                prompt = routine_clarification_response(question)
                send_feedback(session_id, prompt)
                if JULES_FEEDBACK_LABEL in labels:
                    run_gh(
                        "issue", "edit", str(number), "--repo", repo,
                        "--remove-label", JULES_FEEDBACK_LABEL,
                        "--remove-label", "needs-product-decision",
                        "--add-label", JULES_ACTIVE_LABEL,
                    )
                    replace_issue_labels_in_memory(
                        issue,
                        remove=(JULES_FEEDBACK_LABEL, "needs-product-decision"),
                        add=(JULES_ACTIVE_LABEL,),
                    )
                run_gh(
                    "issue", "comment", str(number), "--repo", repo,
                    "--body",
                    (
                        f"{JULES_AUTO_FEEDBACK_MARKER.format(session_id=session_id, question_key=question_key)}\n"
                        f"{JULES_CLARIFICATION_HANDLED_MARKER.format(session_id=session_id, question_key=question_key)}\n"
                        "Automatically answered a routine Jules clarification using the "
                        "repository-first engineering policy. Jules should continue without "
                        "manual review unless it reaches a genuine product decision."
                    ),
                )
                print(f"Auto-answered routine Jules clarification for #{number}.")
                continue

            if JULES_FEEDBACK_LABEL not in labels:
                run_gh(
                    "issue", "edit", str(number), "--repo", repo,
                    "--remove-label", JULES_ACTIVE_LABEL,
                    "--add-label", JULES_FEEDBACK_LABEL,
                    "--add-label", "needs-product-decision",
                )
                replace_issue_labels_in_memory(
                    issue,
                    remove=(JULES_ACTIVE_LABEL,),
                    add=(JULES_FEEDBACK_LABEL, "needs-product-decision"),
                )
            detail = (
                f"Jules session `{session_id}` is waiting on a genuine product decision, "
                "so this session no longer consumes a productive Jules slot."
            )
            if question:
                detail += f"\n\nLatest Jules message:\n\n> {question.replace(chr(10), chr(10) + '> ')}"
            session_url = str(session.get("url") or "")
            if session_url:
                detail += f"\n\nJules session: {session_url}"
            detail += (
                "\n\nAfter explicit feedback is provided and Jules resumes, the dispatcher "
                "will restore the active-session state automatically."
            )
            run_gh(
                "issue", "comment", str(number), "--repo", repo,
                "--body", detail,
            )
            print(f"Released Jules slot for #{number}: awaiting product decision.")
            continue

        if state not in JULES_TERMINAL_STATES:
            if JULES_FEEDBACK_LABEL in labels and state in JULES_PRODUCTIVE_STATES:
                run_gh(
                    "issue", "edit", str(number), "--repo", repo,
                    "--remove-label", JULES_FEEDBACK_LABEL,
                    "--remove-label", "needs-product-decision",
                    "--add-label", JULES_ACTIVE_LABEL,
                )
                replace_issue_labels_in_memory(
                    issue,
                    remove=(JULES_FEEDBACK_LABEL, "needs-product-decision"),
                    add=(JULES_ACTIVE_LABEL,),
                )
                print(f"Jules session {session_id} for #{number} resumed as {state}.")
            else:
                print(f"Jules session {session_id} for #{number} is still {state}.")
            continue

        pr_url = pull_request_url(session)
        activities: list[dict[str, Any]] = []
        diagnostics: list[str] = []
        retryable_failure = False
        if state == "FAILED":
            try:
                activities = (
                    load_activities(session_id)
                    if load_activities is not None
                    else list_jules_activities(api_key, session_id)
                )
                diagnostics = failure_diagnostics(session, activities)
                retryable_failure = retryable_jules_failure(diagnostics)
            except Exception as exc:
                diagnostics = [f"Could not load Jules failure diagnostics: {exc}"]

        capacity_exhausted = (
            state == "FAILED" and jules_capacity_exhausted("\n".join(diagnostics))
        )
        if capacity_exhausted:
            run_gh(
                "issue", "edit", str(number), "--repo", repo,
                "--remove-label", JULES_ACTIVE_LABEL,
                "--remove-label", JULES_FEEDBACK_LABEL,
                "--remove-label", "jules",
            )
            replace_issue_labels_in_memory(
                issue,
                remove=(JULES_ACTIVE_LABEL, JULES_FEEDBACK_LABEL, "jules"),
            )
            detail = (
                f"Jules session `{session_id}` stopped because Jules account capacity/quota "
                "is exhausted. The issue remains eligible and is not marked failed or given "
                "a task-burning retry. The scheduled dispatcher will try it again after "
                "capacity becomes available."
            )
            if diagnostics:
                detail += "\n\nCapacity diagnostics:"
                for diagnostic in diagnostics:
                    quoted = diagnostic.replace(chr(10), chr(10) + "> ")
                    detail += f"\n\n> {quoted}"
            run_gh(
                "issue", "comment", str(number), "--repo", repo,
                "--body", detail,
            )
            capacity_paused = True
            print(f"Paused Jules dispatch after capacity exhaustion on #{number}.")
            continue

        completed_without_pr = state == "COMPLETED" and not pr_url
        completed_without_pr_already_retried = (
            completed_without_pr and retry_marker_from_comments(comments) is not None
        )
        infrastructure_retry_available = (
            state == "FAILED"
            and retryable_failure
            and infrastructure_retry_marker_from_comments(comments) is None
        )
        terminal_label = (
            JULES_REVIEW_READY_LABEL
            if state == "COMPLETED" and pr_url
            else JULES_FAILED_LABEL
            if completed_without_pr_already_retried
            else JULES_RETRY_LABEL
            if completed_without_pr or infrastructure_retry_available
            else JULES_FAILED_LABEL
        )
        run_gh(
            "issue", "edit", str(number), "--repo", repo,
            "--remove-label", JULES_ACTIVE_LABEL,
            "--remove-label", JULES_FEEDBACK_LABEL,
            "--remove-label", "jules",
            "--add-label", terminal_label,
        )
        replace_issue_labels_in_memory(
            issue,
            remove=(JULES_ACTIVE_LABEL, JULES_FEEDBACK_LABEL, "jules"),
            add=(terminal_label,),
        )

        if state == "COMPLETED":
            if pr_url:
                detail = (
                    f"Jules completed session `{session_id}` and released this automation slot."
                    f"\n\nPull request: {pr_url}"
                )
            elif completed_without_pr_already_retried:
                detail = (
                    f"Jules completed session `{session_id}` without producing a pull request "
                    "after its automatic retry. The dispatcher released the slot and parked the "
                    "issue as failed instead of retrying indefinitely."
                )
            else:
                detail = (
                    f"{JULES_RETRY_MARKER.format(session_id=session_id)}\n"
                    f"Jules completed session `{session_id}` without producing a pull request. "
                    "The dispatcher released the slot and queued one context-preserving retry "
                    "instead of leaving the issue permanently review-ready."
                )
        else:
            if infrastructure_retry_available:
                detail = (
                    f"{JULES_INFRA_RETRY_MARKER.format(session_id=session_id)}\n"
                    f"Jules session `{session_id}` ended in FAILED state because the "
                    "diagnostics match a retryable Jules/platform failure. One bounded "
                    "infrastructure retry is allowed without consuming the task-level retry."
                )
            else:
                detail = (
                    f"Jules session `{session_id}` ended in FAILED state and released this "
                    "automation slot. It will not be retried automatically."
                )
            if diagnostics:
                detail += "\n\nFailure diagnostics:"
                for diagnostic in diagnostics:
                    quoted = diagnostic.replace(chr(10), chr(10) + "> ")
                    detail += f"\n\n> {quoted}"
            else:
                detail += "\n\nNo additional failure diagnostics were reported by the Jules API."

            if infrastructure_retry_available:
                last_message = latest_agent_message(activities)
                if last_message:
                    detail += (
                        "\n\nLast Jules message before failure:\n\n> "
                        + last_message.replace(chr(10), chr(10) + "> ")
                    )
                prior_feedback = explicit_feedback_for_session(comments, session_id)
                if prior_feedback:
                    detail += (
                        "\n\nPrior explicit GitHub feedback that must be preserved in the "
                        "retry:\n\n> "
                        + prior_feedback.replace(chr(10), chr(10) + "> ")
                    )

        run_gh(
            "issue", "comment", str(number), "--repo", repo,
            "--body", detail,
        )
        print(f"Reconciled Jules session {session_id} for #{number}: {state}.")

    return capacity_paused


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
    reserved_codex = [
        task
        for issue in issue_list
        if (task := reserved_codex_task(issue)) is not None
    ]
    feedback_waiting = [
        task
        for issue in issue_list
        if JULES_FEEDBACK_LABEL in label_names(issue)
        and (task := task_from_issue(issue)) is not None
    ]

    # Feedback-blocked Jules sessions can resume as soon as feedback is sent,
    # so reserve WIP capacity for them instead of backfilling their slot and
    # accidentally exceeding MAX_ACTIVE when they wake up.
    slots = max(0, max_active - len(active_jules) - len(feedback_waiting))
    if slots == 0:
        return []

    occupied_locks: set[str] = set()
    for task in [*active_jules, *reserved_codex, *feedback_waiting]:
        occupied_locks.update(task_lock_keys(task))
    open_issue_numbers = {
        int(issue["number"])
        for issue in issue_list
        if str(issue.get("state") or "open") == "open"
    }
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
                JULES_FEEDBACK_LABEL,
                "blocked",
                "needs-product-decision",
            }
            or has_codex_reservation(task.labels)
        ):
            continue
        if task.dependencies & open_issue_numbers:
            continue
        candidates.append(task)

    candidates.sort(
        key=lambda task: (
            PRIORITY_ORDER[task.priority],
            0 if JULES_RETRY_LABEL in task.labels else 1,
            task.number,
        )
    )
    selected: list[Task] = []
    for task in candidates:
        if len(selected) >= slots:
            break
        locks = task_lock_keys(task)
        if locks & occupied_locks:
            continue
        selected.append(task)
        occupied_locks.update(locks)
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


def session_prompt(
    repo: str, task: Task, retry_context: str | None = None
) -> str:
    issue_url = f"https://github.com/{repo}/issues/{task.number}"
    prompt = (
        f"Work on GitHub issue #{task.number}: {task.title}\n"
        f"{issue_url}\n\n"
        f"{task.body.strip()}\n\n"
        "Treat the current repository as the source of truth. Work from current main. "
        "Keep the change bounded to this issue, prefer root-cause fixes, and add regression "
        "coverage where behavior changes. Do not ask for confirmation merely to continue "
        "a bounded implementation, run tests, commit changes, or open the pull request; "
        "make the best engineering decision and continue. Ask for user feedback only when "
        "a genuine product decision, conflicting requirement, destructive action, or missing "
        "prerequisite prevents safe progress. Open a pull request that includes "
        f"'Closes #{task.number}'. Do not merge the pull request yourself."
    )
    if retry_context:
        prompt += (
            "\n\nThis is the single automatic retry of a prior Jules/platform failure. "
            "Preserve and apply the following prior session context instead of re-deriving "
            f"or re-asking it:\n\n{retry_context}"
        )
    return prompt


def create_jules_session(
    api_key: str,
    source_name: str,
    repo: str,
    task: Task,
    api_post: Callable[..., dict[str, Any]] = jules_json,
    *,
    retry_context: str | None = None,
) -> dict[str, Any]:
    return api_post(
        api_key,
        "/sessions",
        method="POST",
        payload={
            "prompt": session_prompt(repo, task, retry_context),
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
    comments: Iterable[dict[str, Any]] = (),
    create_session: Callable[..., dict[str, Any]] = create_jules_session,
    delete_session: Callable[[str], None] | None = None,
    run_gh: Callable[..., None] = gh_run,
) -> dict[str, Any]:
    comment_list = list(comments)
    retry_context = (
        retry_context_from_comments(comment_list)
        if JULES_RETRY_LABEL in task.labels
        else None
    )
    superseded_session_id = (
        latest_retry_marker_from_comments(comment_list)
        if JULES_RETRY_LABEL in task.labels
        else None
    )
    if JULES_RETRY_LABEL in task.labels and not retry_context:
        raise RuntimeError(
            f"Retry context for issue #{task.number} is not yet visible; refusing a blind retry"
        )
    if retry_context:
        session = create_session(
            api_key,
            source_name,
            repo,
            task,
            retry_context=retry_context,
        )
    else:
        session = create_session(api_key, source_name, repo, task)
    session_id = str(session.get("id") or "")
    session_url = str(session.get("url") or "")
    if not session_id or not session_url:
        raise RuntimeError(f"Jules session creation for issue #{task.number} returned no id/url")

    edit_args = [
        "issue", "edit", str(task.number), "--repo", repo,
        "--add-label", "autonomous-backlog",
        "--add-label", "agent-ready",
        "--add-label", "jules",
        "--add-label", JULES_ACTIVE_LABEL,
    ]
    if JULES_RETRY_LABEL in task.labels:
        edit_args += ["--remove-label", JULES_RETRY_LABEL]
    run_gh(*edit_args)
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

    if superseded_session_id and superseded_session_id != session_id:
        if delete_session is None:
            delete_session = lambda old_session_id: delete_jules_session(
                api_key, old_session_id
            )
        try:
            delete_session(superseded_session_id)
            print(
                f"Deleted superseded Jules session {superseded_session_id} after "
                f"persisting replacement {session_id} for #{task.number}."
            )
        except Exception as exc:
            print(
                f"Could not delete superseded Jules session {superseded_session_id}; "
                f"replacement {session_id} remains persisted for #{task.number}: {exc}"
            )

    return session


def ensure_labels(repo: str) -> None:
    for name, color, description in (
        ("agent-ready", "0E8A16", "Bounded task suitable for an automated coding agent"),
        ("jules", "715CD7", "Assigned to Google Jules"),
        (JULES_ACTIVE_LABEL, "5319E7", "A real Jules API session is actively using a Jules slot"),
        (JULES_REVIEW_READY_LABEL, "8250DF", "Jules finished; review the resulting GitHub PR"),
        (JULES_FAILED_LABEL, "D73A4A", "Jules session failed and requires follow-up"),
        (JULES_FEEDBACK_LABEL, "FBCA04", "Jules is waiting for user feedback; does not consume productive WIP"),
        (JULES_RETRY_LABEL, "BFD4F2", "One automatic retry is pending after a retryable Jules/platform failure"),
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


def fetch_open_issues(repo: str) -> list[dict[str, Any]]:
    issues = gh_paginated_json(
        "api",
        f"repos/{repo}/issues?state=open&per_page=100",
    )
    return [issue for issue in issues if "pull_request" not in issue]


def dispatch_capacity_summary(
    issues: Iterable[dict[str, Any]],
    selected: Iterable[Task],
    *,
    max_active: int = MAX_ACTIVE,
) -> str:
    """Summarize Jules capacity and explain why otherwise-free slots stay unused."""
    issue_list = list(issues)
    selected_list = list(selected)
    active_tasks = [
        task
        for issue in issue_list
        if (task := active_jules_task(issue)) is not None
    ]
    feedback_tasks = [
        task
        for issue in issue_list
        if JULES_FEEDBACK_LABEL in label_names(issue)
        and (task := task_from_issue(issue)) is not None
    ]
    reserved_codex = [
        task
        for issue in issue_list
        if (task := reserved_codex_task(issue)) is not None
    ]
    failed_count = sum(
        JULES_FAILED_LABEL in label_names(issue)
        and task_from_issue(issue) is not None
        for issue in issue_list
    )
    review_ready_count = sum(
        JULES_REVIEW_READY_LABEL in label_names(issue)
        and task_from_issue(issue) is not None
        for issue in issue_list
    )
    explicitly_blocked = sum(
        bool(label_names(issue) & {"blocked", "needs-product-decision"})
        and task_from_issue(issue) is not None
        for issue in issue_list
    )

    open_issue_numbers = {
        int(issue["number"])
        for issue in issue_list
        if str(issue.get("state") or "open") == "open"
    }
    occupied_locks: set[str] = set()
    for task in [*active_tasks, *feedback_tasks, *reserved_codex]:
        occupied_locks.update(task_lock_keys(task))

    dependency_blocked = 0
    resource_blocked = 0
    eligible_unselected = 0
    selected_numbers_set = {task.number for task in selected_list}
    simulated_locks = set(occupied_locks)
    for issue in issue_list:
        if str(issue.get("state") or "open") != "open":
            continue
        task = task_from_issue(issue)
        if task is None:
            continue
        labels = task.labels
        if (
            labels
            & {
                JULES_ACTIVE_LABEL,
                JULES_REVIEW_READY_LABEL,
                JULES_FAILED_LABEL,
                JULES_FEEDBACK_LABEL,
                "blocked",
                "needs-product-decision",
            }
            or has_codex_reservation(labels)
        ):
            continue
        if task.dependencies & open_issue_numbers:
            dependency_blocked += 1
            continue
        if task.number in selected_numbers_set:
            simulated_locks.update(task_lock_keys(task))
            continue
        locks = task_lock_keys(task)
        if locks & simulated_locks:
            resource_blocked += 1
        else:
            eligible_unselected += 1
            simulated_locks.update(locks)

    raw_slots = max(0, max_active - len(active_tasks) - len(feedback_tasks))
    unfilled = max(0, raw_slots - len(selected_list))
    selected_numbers = ", ".join(f"#{task.number}" for task in selected_list) or "none"
    return (
        f"Dispatcher capacity: {len(active_tasks)} active, "
        f"{len(feedback_tasks)} feedback-reserved, {len(selected_list)} selected "
        f"({selected_numbers}), {unfilled} unfilled; "
        f"{failed_count} failed, {review_ready_count} review-ready, "
        f"{dependency_blocked} dependency-blocked, {resource_blocked} resource-conflicted, "
        f"{explicitly_blocked} explicitly-blocked, {len(reserved_codex)} codex-reserved, "
        f"{eligible_unselected} otherwise-eligible; max {max_active}."
    )


def run_dispatch_cycle(
    repo: str,
    api_key: str,
    source_name: str | None = None,
) -> tuple[bool, str | None]:
    """Reconcile finished work, dispatch available work, and report whether Jules stays active."""
    issues = fetch_open_issues(repo)

    def load_comments(number: int) -> list[dict[str, Any]]:
        return gh_paginated_json(
            "api",
            f"repos/{repo}/issues/{number}/comments?per_page=100",
        )

    capacity_paused = reconcile_jules_sessions(
        issues,
        repo=repo,
        api_key=api_key,
        load_comments=load_comments,
    )
    migrate_legacy_jules_failures(
        issues,
        repo=repo,
        load_comments=load_comments,
    )
    if capacity_paused:
        print(
            "Jules account capacity is exhausted; ending this dispatch cycle cleanly. "
            "The scheduled run will try again later."
        )
        return False, source_name

    selected = select_tasks(issues)
    print(dispatch_capacity_summary(issues, selected))
    if selected and source_name is None:
        try:
            source_name = find_jules_source(api_key, repo)
        except Exception as exc:
            if jules_capacity_exhausted(exc):
                print(
                    "Jules account capacity is exhausted while resolving the repository "
                    "source; ending this cycle cleanly."
                )
                return False, source_name
            raise

    started_any = False
    for task in selected:
        assert source_name is not None
        try:
            session = dispatch_task(
                task,
                repo=repo,
                api_key=api_key,
                source_name=source_name,
                comments=(
                    load_comments(task.number)
                    if JULES_RETRY_LABEL in task.labels
                    else ()
                ),
            )
        except Exception as exc:
            if jules_capacity_exhausted(exc):
                print(
                    f"Jules account capacity is exhausted before issue #{task.number} "
                    "could start. The issue remains eligible for a later scheduled run."
                )
                return False, source_name
            raise
        started_any = True
        print(
            f"Started Jules session {session['id']} for #{task.number}: {task.title} "
            f"({session['url']})"
        )

    has_active = any(active_jules_task(issue) is not None for issue in issues) or started_any
    if not selected:
        print("No safe autonomous task is currently dispatchable this cycle.")
    return has_active, source_name


def schedule_dispatch_followup(repo: str) -> None:
    """Queue the next reconciliation pass before this watch window exits."""
    gh_run(
        "workflow", "run", "autonomous-dispatch.yml",
        "--repo", repo,
    )


def watch_jules_backlog(
    repo: str,
    api_key: str,
    *,
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    watch_seconds: int = DEFAULT_WATCH_SECONDS,
    run_cycle: Callable[[str, str, str | None], tuple[bool, str | None]] = run_dispatch_cycle,
    schedule_followup: Callable[[str], None] = schedule_dispatch_followup,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
) -> None:
    """Keep one workflow run alive long enough to promptly refill freed Jules slots."""
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")
    if watch_seconds < 0:
        raise ValueError("watch_seconds cannot be negative")

    deadline = monotonic_fn() + watch_seconds
    source_name: str | None = None

    while True:
        has_active, source_name = run_cycle(repo, api_key, source_name)
        if not has_active:
            return

        remaining = deadline - monotonic_fn()
        if remaining < poll_seconds:
            schedule_followup(repo)
            print(
                "Jules watch window ended with active sessions still running; "
                "queued a follow-up dispatcher run for continued reconciliation."
            )
            return

        print(
            f"Jules still has active backlog work; checking again in {poll_seconds} seconds."
        )
        sleep_fn(poll_seconds)


def main() -> int:
    repo = os.environ["REPOSITORY"]
    api_key = os.environ["JULES_API_KEY"]
    ensure_labels(repo)
    cleanup_merged_jules_sessions(repo, api_key)
    reconcile_historical_merged_jules_issues(repo)
    migrate_historical_no_pr_review_ready(repo)

    poll_seconds = int(os.environ.get("JULES_POLL_SECONDS", DEFAULT_POLL_SECONDS))
    watch_seconds = int(os.environ.get("JULES_WATCH_SECONDS", DEFAULT_WATCH_SECONDS))
    watch_jules_backlog(
        repo,
        api_key,
        poll_seconds=poll_seconds,
        watch_seconds=watch_seconds,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
