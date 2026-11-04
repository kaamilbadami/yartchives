"""Conservative risk tiers for autonomous merge admission.

Classification is not authorization: only trusted-main verification and the
merge controller can permit a merge. Unknown and renamed paths fail closed.
"""
from __future__ import annotations

from fnmatch import fnmatch
from typing import Iterable, Mapping

TRUST_BOUNDARIES = (
    ".github/workflows/*", ".github/actions/**",
    ".github/CODEOWNERS", ".github/dependabot.yml",
    "scripts/auto_merge_agent_prs.py", "scripts/ready_copilot_prs.py",
    "scripts/merge_risk_policy.py", "scripts/dispatch_autonomous_issues.py",
    "scripts/dispatch_copilot_pilot.py", "scripts/guard_jules_redispatch.py",
    "scripts/reconcile_merged_pr_issues.py",
    "scripts/triage_workflow_failures.py",
    "scripts/run_quality_checks.sh", "scripts/quality_scope.sh",
    "scripts/targeted_frontend_preflight.py", "requirements.txt",
    ".github/**", "scripts/*copilot*controller*.py", "scripts/*automerge*.py",
)
ROUTINE_AUTOMATION = (
    "scripts/queue_coverage_gap.py", "scripts/triage_source_quarantines.py",
    "tests/test_queue_coverage_gap.py", "tests/test_triage_source_quarantines.py",
)
# Test changes can change CI assertions, but not the required workflow itself.
ORDINARY = (
    "tests/**", "docs/**", "data/**", "audit/**",
    "*.md", "*.js", "*.css", "*.html",
    "scripts/build_*.py", "scripts/validate_*.py",
)


def classify_merge_risk(files: Iterable[Mapping[str, object]]) -> tuple[int, str]:
    """Return risk 1/2/3, conservatively escalating mixed or ambiguous diffs.

    Paths must be actual GitHub changed-file records. No PR-prose inference.
    """
    rows = list(files)
    if not rows:
        return 3, "missing changed-file evidence"
    level = 1
    for row in rows:
        path = row.get("filename")
        previous = row.get("previous_filename")
        status = row.get("status")
        if (not isinstance(path, str) or not path
                or status == "renamed" or previous
                or status not in {"added", "modified", "removed", "changed"}):
            return 3, "unverifiable path, rename, or change status"
        if any(part in {".", ".."} or not part for part in path.split("/")):
            return 3, "unsafe path"
        if any(fnmatch(path, pattern) for pattern in TRUST_BOUNDARIES):
            return 3, "trust-boundary file"
        if any(fnmatch(path, pattern) for pattern in ROUTINE_AUTOMATION):
            level = max(level, 2)
        elif not any(fnmatch(path, pattern) for pattern in ORDINARY):
            return 3, "unknown file scope"
    return level, "routine automation" if level == 2 else "ordinary change"
