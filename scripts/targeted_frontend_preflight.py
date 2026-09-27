#!/usr/bin/env python3
"""Run only frontend checks affected by a branch diff.

This is a fast PR preflight, not a replacement for the full Quality checks job.
It intentionally uses only the Python standard library plus Node already present
on GitHub-hosted runners.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]

ALL_FRONTEND_TESTS = (
    "tests/analytics.test.cjs",
    "tests/deploy-assets.test.cjs",
    "tests/frontend-utils.test.cjs",
    "tests/location-display.test.cjs",
    "tests/apply-next.test.cjs",
    "tests/apply-next-readiness.test.cjs",
    "tests/apply-next-competition.test.cjs",
    "tests/apply-next-location.test.cjs",
    "tests/apply-next-location-preferences.test.cjs",
    "tests/apply-next-location-profile-ui.test.cjs",
    "tests/apply-next-dimensions.test.cjs",
    "tests/apply-next-presentation.test.cjs",
    "tests/apply-next-presentation-browser.test.cjs",
    "tests/apply-next-ui.test.cjs",
    "tests/apply-next-profile-setup.test.cjs",
)

APPLY_NEXT_CORE_TESTS = (
    "tests/apply-next.test.cjs",
    "tests/apply-next-readiness.test.cjs",
    "tests/apply-next-competition.test.cjs",
    "tests/apply-next-location.test.cjs",
    "tests/apply-next-location-preferences.test.cjs",
    "tests/apply-next-dimensions.test.cjs",
    "tests/apply-next-presentation.test.cjs",
    "tests/apply-next-presentation-browser.test.cjs",
    "tests/apply-next-ui.test.cjs",
)

DEPENDENT_TESTS = {
    "analytics.js": ("tests/analytics.test.cjs",),
    "frontend-utils.js": (
        "tests/frontend-utils.test.cjs",
        "tests/apply-next-presentation.test.cjs",
        "tests/apply-next-presentation-browser.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "location-display.js": ("tests/location-display.test.cjs",),
    "apply-next.js": APPLY_NEXT_CORE_TESTS,
    "apply-next-readiness.js": (
        "tests/apply-next-readiness.test.cjs",
        "tests/apply-next-competition.test.cjs",
        "tests/apply-next-location.test.cjs",
        "tests/apply-next-location-preferences.test.cjs",
        "tests/apply-next-dimensions.test.cjs",
        "tests/apply-next-presentation.test.cjs",
        "tests/apply-next-presentation-browser.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "apply-next-competition.js": (
        "tests/apply-next-competition.test.cjs",
        "tests/apply-next-location.test.cjs",
        "tests/apply-next-location-preferences.test.cjs",
        "tests/apply-next-dimensions.test.cjs",
        "tests/apply-next-presentation.test.cjs",
        "tests/apply-next-presentation-browser.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "apply-next-location.js": (
        "tests/apply-next-location.test.cjs",
        "tests/apply-next-location-preferences.test.cjs",
        "tests/apply-next-dimensions.test.cjs",
        "tests/apply-next-presentation.test.cjs",
        "tests/apply-next-presentation-browser.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "apply-next-location-preferences.js": (
        "tests/apply-next-location-preferences.test.cjs",
        "tests/apply-next-presentation.test.cjs",
        "tests/apply-next-presentation-browser.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "apply-next-location-profile-ui.js": (
        "tests/apply-next-location-profile-ui.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "apply-next-dimensions.js": (
        "tests/apply-next-dimensions.test.cjs",
        "tests/apply-next-presentation.test.cjs",
        "tests/apply-next-presentation-browser.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "apply-next-presentation.js": (
        "tests/apply-next-presentation.test.cjs",
        "tests/apply-next-presentation-browser.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "apply-next-ui.js": ("tests/apply-next-ui.test.cjs",),
    "apply-next-profile-setup.js": (
        "tests/apply-next-profile-setup.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "apply-next-profile-setup.css": (
        "tests/apply-next-profile-setup.test.cjs",
        "tests/apply-next-ui.test.cjs",
    ),
    "index.html": ("tests/deploy-assets.test.cjs", "tests/apply-next-ui.test.cjs"),
    "styles.css": ("tests/deploy-assets.test.cjs", "tests/apply-next-ui.test.cjs"),
    "location.css": ("tests/location-display.test.cjs",),
    "ui.css": ("tests/deploy-assets.test.cjs",),
    "ux.css": ("tests/deploy-assets.test.cjs",),
    ".github/workflows/deploy-pages.yml": ("tests/deploy-assets.test.cjs",),
}

ROOT_FRONTEND_SUFFIXES = (".js", ".css", ".html")


def _is_frontend_path(path: str) -> bool:
    if path.startswith("tests/") and path.endswith(".cjs"):
        return True
    if "/" not in path and path.endswith(ROOT_FRONTEND_SUFFIXES):
        return True
    if path in {".github/workflows/deploy-pages.yml"}:
        return True
    return False


def plan_for_paths(paths: Iterable[str]) -> dict[str, list[str]]:
    normalized = sorted({str(path).strip() for path in paths if str(path).strip()})
    syntax_checks: set[str] = set()
    tests: set[str] = set()
    unknown_frontend = False

    for path in normalized:
        if path.startswith("tests/") and path.endswith(".cjs"):
            tests.add(path)
            continue

        if "/" not in path and path.endswith(".js"):
            syntax_checks.add(path)

        mapped = DEPENDENT_TESTS.get(path)
        if mapped:
            tests.update(mapped)
        elif _is_frontend_path(path):
            unknown_frontend = True

    if unknown_frontend:
        tests.update(ALL_FRONTEND_TESTS)

    return {
        "syntax_checks": sorted(syntax_checks),
        "tests": sorted(tests),
    }


def changed_paths(base: str, head: str) -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        cwd=ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def run_plan(plan: dict[str, list[str]]) -> None:
    syntax_checks = plan["syntax_checks"]
    tests = plan["tests"]

    if not syntax_checks and not tests:
        print("Targeted frontend preflight: no affected frontend checks.")
        return

    print(
        "Targeted frontend preflight: "
        f"{len(syntax_checks)} syntax check(s), {len(tests)} test file(s)."
    )

    for path in syntax_checks:
        if not (ROOT / path).exists():
            print(f"Skipping deleted JavaScript file: {path}")
            continue
        print(f"+ node --check {path}", flush=True)
        subprocess.run(["node", "--check", path], cwd=ROOT, check=True)

    for test in tests:
        if not (ROOT / test).exists():
            raise FileNotFoundError(f"Mapped frontend test does not exist: {test}")
        print(f"+ node {test}", flush=True)
        subprocess.run(["node", test], cwd=ROOT, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base", help="Base Git ref/SHA, e.g. origin/main")
    parser.add_argument("head", nargs="?", default="HEAD", help="Head Git ref/SHA")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="Print the selected checks without executing them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    paths = changed_paths(args.base, args.head)
    plan = plan_for_paths(paths)

    print("Changed paths:")
    for path in paths:
        print(f"  {path}")
    print("Selected syntax checks:")
    for path in plan["syntax_checks"]:
        print(f"  {path}")
    print("Selected frontend tests:")
    for path in plan["tests"]:
        print(f"  {path}")

    if not args.plan_only:
        run_plan(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
