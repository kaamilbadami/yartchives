from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from employer_seed_from_benchmark import build_seed  # noqa: E402


def test_build_seed_groups_employers_and_keeps_authoritative_domains():
    benchmark = {
        "name": "regional benchmark",
        "collected_at": "2026-09-17T15:30:00Z",
        "scope": {"states": ["CT", "NY"]},
        "discoveries": [
            {
                "company": "Acme Corp",
                "expected_state": "CT",
                "url_kind": "authoritative",
                "url": "https://acme.wd1.myworkdayjobs.com/jobs/job/123",
            },
            {
                "company": "Acme Corp",
                "expected_state": "NY",
                "url_kind": "discovery_surface",
                "url": "https://www.linkedin.com/jobs/view/123",
            },
            {
                "company": "Beta Labs",
                "expected_state": "NY",
                "url_kind": "authoritative",
                "url": "https://job-boards.greenhouse.io/betalabs/jobs/456",
            },
        ],
    }

    seed = build_seed(benchmark)

    assert seed["source"] == {
        "key": "coverage-benchmark-2026-09-17",
        "kind": "coverage_benchmark",
        "name": "regional benchmark",
        "collected_at": "2026-09-17T15:30:00Z",
        "states": ["CT", "NY"],
    }
    assert seed["employers"] == [
        {
            "name": "Acme Corp",
            "states": ["CT", "NY"],
            "evidence_count": 2,
            "authoritative_evidence_count": 1,
            "domain_hints": ["acme.wd1.myworkdayjobs.com"],
        },
        {
            "name": "Beta Labs",
            "states": ["NY"],
            "evidence_count": 1,
            "authoritative_evidence_count": 1,
            "domain_hints": ["job-boards.greenhouse.io"],
        },
    ]


def test_build_seed_is_deterministic_and_ignores_discovery_hosts():
    rows = [
        {
            "company": "Example Inc.",
            "expected_state": "MD",
            "url_kind": "authoritative",
            "url": "https://www.linkedin.com/jobs/view/1",
        },
        {
            "company": "Example Inc.",
            "expected_state": "MD",
            "url_kind": "authoritative",
            "url": "https://careers.example.com/jobs/1",
        },
    ]
    benchmark = {"scope": {"states": ["MD"]}, "discoveries": rows}

    first = build_seed(benchmark, source_key="benchmark-md")
    second = build_seed({**benchmark, "discoveries": list(reversed(rows))}, source_key="benchmark-md")

    assert first == second
    assert first["employers"][0]["domain_hints"] == ["careers.example.com"]


def test_build_seed_rejects_missing_discovery_list():
    try:
        build_seed({"discoveries": None})
    except ValueError as exc:
        assert str(exc) == "benchmark discoveries must be a list"
    else:
        raise AssertionError("expected ValueError")
