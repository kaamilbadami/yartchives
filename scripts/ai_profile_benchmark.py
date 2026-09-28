#!/usr/bin/env python3
"""Offline AI profile-classification benchmark for Yartchives.

This tool is intentionally audit-only. It never mutates data/listings.json and
never publishes AI classifications into the production feed.

The first provider is Gemini, but the benchmark depends on the provider-neutral
ProfileClassifier interface so production code is not coupled to one vendor.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FEED = ROOT / "data" / "listings.json"
DEFAULT_GOLD = ROOT / "tests" / "fixtures" / "ai-profile-gold.json"
DEFAULT_OUTPUT = ROOT / "audit" / "ai-profile-benchmark.json"
DEFAULT_MODEL = "gemini-3.5-flash-lite"

ALLOWED_LABELS = (
    "cs",
    "tech-business",
    "finance-econ",
    "engineering",
    "mechanical",
    "aero",
    "electrical",
    "policy",
    "health",
    "general",
)

SYSTEM_INSTRUCTION = """You classify internship/co-op roles into the Yartchives career taxonomy.
Use only the supplied role evidence. Return one or more labels only when the role/function clearly belongs there.
Do not classify a role as CS merely because it mentions AI, automation, data, applications, or technology in a nontechnical context.
Do not classify a role as Engineering merely because the employer is an engineering company.
Specialized engineering roles may receive both the discipline label and engineering.
If the evidence is too broad or ambiguous, return general.
Keep evidence phrases short and copied or closely paraphrased from the supplied role evidence."""

RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "labels": {
            "type": "ARRAY",
            "items": {"type": "STRING", "enum": list(ALLOWED_LABELS)},
            "minItems": 1,
        },
        "confidence": {"type": "NUMBER", "minimum": 0, "maximum": 1},
        "evidence": {
            "type": "ARRAY",
            "items": {"type": "STRING"},
            "maxItems": 3,
        },
    },
    "required": ["labels", "confidence", "evidence"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Classification:
    labels: tuple[str, ...]
    confidence: float
    evidence: tuple[str, ...]


class ProfileClassifier(Protocol):
    name: str

    def classify(self, job: dict[str, Any]) -> Classification:
        ...


class GeminiProfileClassifier:
    name = "gemini"

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 30.0):
        if not api_key:
            raise ValueError("Gemini API key is required")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def classify(self, job: dict[str, Any]) -> Classification:
        payload = compact_job_evidence(job)
        prompt = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        request_body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": RESPONSE_SCHEMA,
                "temperature": 0,
            },
        }

        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = requests.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": self.api_key,
                    },
                    json=request_body,
                    timeout=self.timeout,
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise RuntimeError(f"Gemini transient HTTP {response.status_code}")
                response.raise_for_status()
                body = response.json()
                text = body["candidates"][0]["content"]["parts"][0]["text"]
                return validate_classification(json.loads(text))
            except (requests.RequestException, RuntimeError, KeyError, IndexError, json.JSONDecodeError, ValueError) as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(2**attempt)
        raise RuntimeError(f"Gemini classification failed after retries: {last_error}")


def validate_classification(raw: dict[str, Any]) -> Classification:
    if not isinstance(raw, dict):
        raise ValueError("classification must be an object")
    labels_raw = raw.get("labels")
    if not isinstance(labels_raw, list) or not labels_raw:
        raise ValueError("classification labels must be a non-empty list")
    labels: list[str] = []
    for label in labels_raw:
        if label not in ALLOWED_LABELS:
            raise ValueError(f"unsupported classification label: {label!r}")
        if label not in labels:
            labels.append(label)
    if "general" in labels and len(labels) > 1:
        raise ValueError("general cannot be combined with specialized labels")

    confidence = float(raw.get("confidence"))
    if not 0 <= confidence <= 1:
        raise ValueError("confidence must be between 0 and 1")

    evidence_raw = raw.get("evidence")
    if not isinstance(evidence_raw, list):
        raise ValueError("evidence must be a list")
    evidence = tuple(str(item).strip()[:160] for item in evidence_raw if str(item).strip())[:3]
    return Classification(tuple(sorted(labels)), confidence, evidence)


def compact_job_evidence(job: dict[str, Any]) -> dict[str, Any]:
    """Return public job evidence only; never include user/profile state."""
    fields = (
        "company",
        "title",
        "function_primary",
        "section",
        "location",
        "term",
        "opportunity_type",
        "education_level",
    )
    out = {
        key: job.get(key)
        for key in fields
        if job.get(key) not in (None, "", [], {})
    }

    requirements = job.get("requirements")
    if isinstance(requirements, dict):
        compact_requirements: dict[str, Any] = {}
        for key in ("education", "major_fields", "skills", "other_eligibility"):
            value = requirements.get(key)
            if not isinstance(value, dict):
                continue
            facts: list[str] = []
            for level in ("required", "preferred", "unspecified"):
                rows = value.get(level)
                if not isinstance(rows, list):
                    continue
                for row in rows[:4]:
                    if isinstance(row, dict) and row.get("statement"):
                        facts.append(str(row["statement"])[:240])
            if facts:
                compact_requirements[key] = facts[:6]
        if compact_requirements:
            out["requirements"] = compact_requirements
    return out


def stable_general_sample(jobs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    general = [
        job for job in jobs
        if isinstance(job, dict) and set(job.get("profiles") or []) == {"general"}
    ]
    general.sort(
        key=lambda job: hashlib.sha256(
            str(job.get("id") or f"{job.get('company','')}|{job.get('title','')}").encode("utf-8")
        ).hexdigest()
    )
    return general[: max(0, limit)]


def score_gold(expected: list[set[str]], predicted: list[set[str]]) -> dict[str, Any]:
    if len(expected) != len(predicted):
        raise ValueError("expected/predicted lengths differ")
    total = len(expected)
    exact = sum(1 for exp, pred in zip(expected, predicted) if exp == pred)
    tp = sum(len(exp & pred) for exp, pred in zip(expected, predicted))
    fp = sum(len(pred - exp) for exp, pred in zip(expected, predicted))
    fn = sum(len(exp - pred) for exp, pred in zip(expected, predicted))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return {
        "cases": total,
        "exact_set_accuracy": exact / total if total else 0.0,
        "micro_precision": precision,
        "micro_recall": recall,
    }


def run_gold(provider: ProfileClassifier, gold_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = json.loads(gold_path.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []
    expected: list[set[str]] = []
    predicted: list[set[str]] = []
    for case in cases:
        classification = provider.classify(case)
        exp = set(case["expected_labels"])
        pred = set(classification.labels)
        expected.append(exp)
        predicted.append(pred)
        results.append({
            "company": case.get("company"),
            "title": case.get("title"),
            "expected_labels": sorted(exp),
            "predicted_labels": sorted(pred),
            "confidence": classification.confidence,
            "evidence": list(classification.evidence),
            "exact": exp == pred,
        })
    return score_gold(expected, predicted), results


def run_live_sample(
    provider: ProfileClassifier,
    feed_path: Path,
    limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = json.loads(feed_path.read_text(encoding="utf-8"))
    jobs = doc.get("jobs") or []
    sample = stable_general_sample(jobs, limit)
    rows: list[dict[str, Any]] = []
    label_counts = {label: 0 for label in ALLOWED_LABELS}
    high_confidence_non_general = 0
    for job in sample:
        classification = provider.classify(job)
        for label in classification.labels:
            label_counts[label] += 1
        if classification.confidence >= 0.95 and classification.labels != ("general",):
            high_confidence_non_general += 1
        rows.append({
            "job_id": job.get("id"),
            "company": job.get("company"),
            "title": job.get("title"),
            "labels": list(classification.labels),
            "confidence": classification.confidence,
            "evidence": list(classification.evidence),
        })
    summary = {
        "feed_jobs": len(jobs),
        "general_jobs": sum(
            1 for job in jobs
            if isinstance(job, dict) and set(job.get("profiles") or []) == {"general"}
        ),
        "sample_size": len(sample),
        "high_confidence_non_general": high_confidence_non_general,
        "label_counts": label_counts,
    }
    return summary, rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--feed", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--gold", type=Path, default=DEFAULT_GOLD)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--api-key-env", default="GEMINI_API_KEY")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    api_key = os.getenv(args.api_key_env, "")
    if not api_key:
        raise SystemExit(
            f"{args.api_key_env} is not set; benchmark is audit-only and requires an explicit API key"
        )

    provider = GeminiProfileClassifier(api_key=api_key, model=args.model)
    gold_summary, gold_rows = run_gold(provider, args.gold)
    live_summary, live_rows = run_live_sample(provider, args.feed, args.limit)

    report = {
        "schema": "yartchives-ai-profile-benchmark-v1",
        "provider": provider.name,
        "model": args.model,
        "production_mutation": False,
        "gold": {"summary": gold_summary, "rows": gold_rows},
        "live_general_sample": {"summary": live_summary, "rows": live_rows},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "model": args.model,
        "gold": gold_summary,
        "live_general_sample": live_summary,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
