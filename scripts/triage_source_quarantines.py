#!/usr/bin/env python3
"""Escalate persistent source quarantines into deduplicated Jules repair issues."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

ISSUE_LABEL = "source-quarantine"
AGENT_LABEL = "agent-ready"
BACKLOG_LABEL = "autonomous-backlog"
AUTONOMOUS_MARKER = "<!-- autonomous-task -->"
SIGNATURE_PREFIX = "<!-- source-quarantine-signature: "
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
NUMBER_RE = re.compile(r"\b\d+\b")
ERROR_CLASS_RE = re.compile(r"\b([A-Za-z][A-Za-z0-9_]*(?:Error|Exception))\b")


def source_status(source: dict[str, Any]) -> str:
    status = source.get("status")
    return str(status).strip().casefold() if isinstance(status, str) else ""


def quarantined_sources(feed: dict[str, Any]) -> dict[str, dict[str, Any]]:
    sources = feed.get("sources")
    if not isinstance(sources, dict):
        return {}
    return {
        str(key): value
        for key, value in sources.items()
        if isinstance(value, dict) and source_status(value) == "quarantined"
    }


def source_family(key: str, source: dict[str, Any]) -> str:
    haystack = " ".join(
        str(value)
        for value in (
            key,
            source.get("name"),
            source.get("provider"),
            source.get("error"),
        )
        if value
    ).casefold()
    for family in ("workday", "icims", "greenhouse", "oracle", "lever", "ashby"):
        if family in haystack:
            return family
    if source.get("auto_discovered"):
        return "auto-discovered"
    return "source"


def normalized_cause(source: dict[str, Any]) -> str:
    error = str(source.get("error") or "structural quarantine").strip()
    match = ERROR_CLASS_RE.search(error)
    error_class = match.group(1) if match else "StructuralQuarantine"
    detail = error
    if ":" in detail:
        detail = detail.split(":", 1)[1]
    detail = URL_RE.sub("<url>", detail)
    detail = NUMBER_RE.sub("<n>", detail)
    detail = re.sub(r"\s+", " ", detail).strip().casefold()
    if len(detail) > 140:
        detail = detail[:140].rstrip()
    return f"{error_class}:{detail or 'unspecified'}"


def group_signature(family: str, cause: str) -> str:
    digest = hashlib.sha256(f"{family}\0{cause}".encode("utf-8")).hexdigest()[:16]
    return f"{family}:{digest}"


def persistent_groups(
    previous_feed: dict[str, Any],
    current_feed: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    previous = quarantined_sources(previous_feed)
    current = quarantined_sources(current_feed)
    persistent_keys = sorted(set(previous) & set(current))
    grouped: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = defaultdict(list)

    for key in persistent_keys:
        source = current[key]
        family = source_family(key, source)
        cause = normalized_cause(source)
        grouped[(family, cause)].append((key, source))

    result: dict[str, dict[str, Any]] = {}
    for (family, cause), entries in grouped.items():
        signature = group_signature(family, cause)
        result[signature] = {
            "family": family,
            "cause": cause,
            "sources": entries,
        }
    return result


def label_names(issue: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for label in issue.get("labels", []):
        if isinstance(label, str):
            names.add(label)
        elif isinstance(label, dict) and label.get("name"):
            names.add(str(label["name"]))
    return names


def signature_marker(signature: str) -> str:
    return f"{SIGNATURE_PREFIX}{signature} -->"


def issue_signature(issue: dict[str, Any]) -> str | None:
    body = str(issue.get("body") or "")
    match = re.search(r"<!--\s*source-quarantine-signature:\s*([^\s>]+)\s*-->", body)
    return match.group(1) if match else None


def render_source_line(key: str, source: dict[str, Any]) -> str:
    name = str(source.get("name") or key)
    error = str(source.get("error") or "structural quarantine").strip()
    return f"- `{key}` — {name}: {error}"


def render_issue_body(signature: str, group: dict[str, Any]) -> str:
    family = group["family"]
    cause = group["cause"]
    source_lines = "\n".join(render_source_line(key, source) for key, source in group["sources"])
    return f"""priority: P1
area: coverage
resources: coverage, source-collection
autonomous: true

{AUTONOMOUS_MARKER}
{signature_marker(signature)}

Persistent source quarantine detected across two consecutive published-feed generations.

- Source family: **{family}**
- Root-cause signature: `{cause}`
- Affected sources: **{len(group["sources"])}**

## Current affected sources

{source_lines}

## Agent guidance

Treat the current repository as the source of truth. Reproduce the structural failure before changing code. Prefer a generic ATS-family/parser/discovery fix over employer-by-employer exceptions. Add regression coverage for the failure mode. If an employer migrated ATS or the endpoint is permanently retired, update discovery/source lifecycle state explicitly rather than weakening validation.

Do not scrape LinkedIn or Handshake as production sources.

## Completion contract

The issue may be closed automatically once this quarantine signature is no longer persistent in the generated feed. A later regression should create a fresh issue.
"""


def issue_title(group: dict[str, Any]) -> str:
    family = str(group["family"]).replace("-", " ").title()
    return f"[source quarantine] Repair persistent {family} structural failures"


def ensure_labels(repo: str, run_gh: Callable[..., None]) -> None:
    labels = (
        (ISSUE_LABEL, "B60205", "Persistent source quarantine detected by the feed pipeline"),
        (AGENT_LABEL, "0E8A16", "Bounded task suitable for an automated coding agent"),
        (BACKLOG_LABEL, "1D76DB", "Approved backlog item eligible for autonomous dispatch"),
    )
    for name, color, description in labels:
        run_gh(
            "label", "create", name,
            "--repo", repo,
            "--color", color,
            "--description", description,
            "--force",
        )


def triage(
    repo: str,
    previous_feed: dict[str, Any],
    current_feed: dict[str, Any],
    *,
    load_open_issues: Callable[[], list[dict[str, Any]]],
    run_gh: Callable[..., None],
) -> dict[str, dict[str, Any]]:
    ensure_labels(repo, run_gh)
    groups = persistent_groups(previous_feed, current_feed)
    open_issues = [
        issue for issue in load_open_issues()
        if "pull_request" not in issue and ISSUE_LABEL in label_names(issue)
    ]
    by_signature = {
        signature: issue
        for issue in open_issues
        if (signature := issue_signature(issue))
    }

    for signature, group in groups.items():
        body = render_issue_body(signature, group)
        existing = by_signature.get(signature)
        if existing:
            number = str(existing["number"])
            labels = label_names(existing)
            edit_args = ["issue", "edit", number, "--repo", repo, "--body", body]
            if AGENT_LABEL not in labels:
                edit_args += ["--add-label", AGENT_LABEL]
            if BACKLOG_LABEL not in labels:
                edit_args += ["--add-label", BACKLOG_LABEL]
            run_gh(*edit_args)
            continue

        run_gh(
            "issue", "create",
            "--repo", repo,
            "--title", issue_title(group),
            "--body", body,
            "--label", ISSUE_LABEL,
            "--label", AGENT_LABEL,
            "--label", BACKLOG_LABEL,
        )

    active_signatures = set(groups)
    for issue in open_issues:
        signature = issue_signature(issue)
        if not signature or signature in active_signatures:
            continue
        number = str(issue["number"])
        labels = label_names(issue)
        edit_args = ["issue", "edit", number, "--repo", repo]
        for label in ("jules", "jules-session", AGENT_LABEL, BACKLOG_LABEL):
            if label in labels:
                edit_args += ["--remove-label", label]
        if len(edit_args) > 5:
            run_gh(*edit_args)
        run_gh(
            "issue", "comment", number, "--repo", repo,
            "--body",
            (
                "The source-quarantine signature is no longer persistent in the latest "
                "validated feed. Closing this repair cycle automatically. If it persists "
                "again across two future feed generations, triage will create a fresh issue."
            ),
        )
        run_gh("issue", "close", number, "--repo", repo)

    return groups


def gh_json(*args: str) -> Any:
    result = subprocess.run(["gh", *args], check=True, text=True, capture_output=True)
    return json.loads(result.stdout)


def gh_run(*args: str) -> None:
    subprocess.run(["gh", *args], check=True)


def load_open_issues(repo: str) -> list[dict[str, Any]]:
    result = gh_json(
        "api",
        "--paginate",
        f"repos/{repo}/issues?state=open&labels={ISSUE_LABEL}&per_page=100",
    )
    return result if isinstance(result, list) else []


def load_feed(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("current_feed")
    parser.add_argument("--previous-feed", required=True)
    parser.add_argument("--repo", required=True)
    args = parser.parse_args()

    groups = triage(
        args.repo,
        load_feed(args.previous_feed),
        load_feed(args.current_feed),
        load_open_issues=lambda: load_open_issues(args.repo),
        run_gh=gh_run,
    )
    affected = sum(len(group["sources"]) for group in groups.values())
    print(
        f"Persistent source quarantine groups: {len(groups)} "
        f"({affected} affected sources)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
