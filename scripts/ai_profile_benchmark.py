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
import re
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
DEFAULT_BATCH_SIZE = 20

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
Use only the supplied role evidence. Return one result for every supplied key, with the same key.
Return one or more labels only when the role/function clearly belongs there.
Do not classify a role as CS merely because it mentions AI, automation, data, applications, or technology in a nontechnical context.
Do not classify a role as Engineering merely because the employer is an engineering company.
Specialized engineering roles may receive both the discipline label and engineering.
If the evidence is too broad or ambiguous, return general.
Keep evidence phrases short and copied or closely paraphrased from the supplied role evidence."""

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "labels": {
            "type": "array",
            "items": {"type": "string", "enum": list(ALLOWED_LABELS)},
            "minItems": 1,
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 3,
        },
    },
    "required": ["labels", "confidence", "evidence"],
    "additionalProperties": False,
}

BATCH_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    **CLASSIFICATION_SCHEMA["properties"],
                },
                "required": ["key", *CLASSIFICATION_SCHEMA["required"]],
                "additionalProperties": False,
            },
        },
    },
    "required": ["results"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Classification:
    labels: tuple[str, ...]
    confidence: float
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class ClassificationOutcome:
    classification: Classification | None
    error: str | None = None
    raw_labels: tuple[str, ...] = ()


class ProfileClassifier(Protocol):
    name: str

    def classify(self, job: dict[str, Any]) -> Classification:
        ...

    def classify_many(self, jobs: list[dict[str, Any]]) -> list[ClassificationOutcome]:
        ...


def _chunks(values: list[Any], size: int):
    for start in range(0, len(values), size):
        yield values[start:start + size]


def _retry_delay_seconds(response: requests.Response, attempt: int) -> float:
    header = response.headers.get("Retry-After")
    if header:
        try:
            return max(1.0, float(header))
        except ValueError:
            pass
    match = re.search(r"retry in\s+([0-9.]+)s", response.text, flags=re.I)
    if match:
        return max(1.0, float(match.group(1)) + 1.0)
    return float(min(30, 2 ** (attempt + 1)))


class GeminiProfileClassifier:
    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ):
        if not api_key:
            raise ValueError("Gemini API key is required")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.batch_size = batch_size

    def classify(self, job: dict[str, Any]) -> Classification:
        outcome = self.classify_many([job])[0]
        if outcome.classification is None:
            raise ValueError(outcome.error or "Gemini returned an invalid classification")
        return outcome.classification

    def classify_many(self, jobs: list[dict[str, Any]]) -> list[ClassificationOutcome]:
        if not jobs:
            return []
        all_results: list[ClassificationOutcome] = []
        for batch in _chunks(jobs, self.batch_size):
            all_results.extend(self._classify_batch(batch))
        return all_results

    def _classify_batch(self, jobs: list[dict[str, Any]]) -> list[ClassificationOutcome]:
        keyed_jobs = [
            {"key": str(index), "job": compact_job_evidence(job)}
            for index, job in enumerate(jobs)
        ]
        prompt = json.dumps({"jobs": keyed_jobs}, ensure_ascii=False, sort_keys=True)
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        request_body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": BATCH_RESPONSE_SCHEMA,
                "temperature": 0,
            },
        }

        last_error: Exception | None = None
        for attempt in range(5):
            response: requests.Response | None = None
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
                if response.status_code == 429:
                    detail = response.text[:1000].strip()
                    if attempt < 4:
                        time.sleep(_retry_delay_seconds(response, attempt))
                        continue
                    raise RuntimeError(f"Gemini HTTP 429 after retries: {detail}")
                if response.status_code >= 500:
                    detail = response.text[:1000].strip()
                    if attempt < 4:
                        time.sleep(_retry_delay_seconds(response, attempt))
                        continue
                    raise RuntimeError(
                        f"Gemini transient HTTP {response.status_code}: {detail}"
                    )
                if response.status_code >= 400:
                    detail = response.text[:1000].strip()
                    raise ValueError(
                        f"Gemini HTTP {response.status_code}: {detail}"
                    )

                body = response.json()
                text = body["candidates"][0]["content"]["parts"][0]["text"]
                raw = json.loads(text)
                rows = raw.get("results")
                if not isinstance(rows, list):
                    raise ValueError("Gemini batch response is missing results")

                by_key: dict[str, ClassificationOutcome] = {}
                for row in rows:
                    if not isinstance(row, dict):
                        raise ValueError("Gemini batch result must be an object")
                    key = str(row.get("key", ""))
                    if key in by_key:
                        raise ValueError(f"Gemini returned duplicate key {key!r}")
                    raw_labels = tuple(
                        str(label) for label in row.get("labels", [])
                        if isinstance(label, str)
                    )
                    try:
                        classification = validate_classification(row)
                        by_key[key] = ClassificationOutcome(
                            classification=classification,
                            raw_labels=raw_labels,
                        )
                    except ValueError as exc:
                        by_key[key] = ClassificationOutcome(
                            classification=None,
                            error=str(exc),
                            raw_labels=raw_labels,
                        )

                expected_keys = {str(index) for index in range(len(jobs))}
                if set(by_key) != expected_keys:
                    missing = sorted(expected_keys - set(by_key))
                    extra = sorted(set(by_key) - expected_keys)
                    raise ValueError(
                        f"Gemini batch keys mismatch; missing={missing}, extra={extra}"
                    )
                return [by_key[str(index)] for index in range(len(jobs))]
            except (
                requests.RequestException,
                RuntimeError,
                KeyError,
                IndexError,
                json.JSONDecodeError,
                ValueError,
            ) as exc:
                last_error = exc
                if response is not None and response.status_code == 429:
                    continue
                if attempt < 4 and isinstance(exc, requests.RequestException):
                    time.sleep(float(min(30, 2 ** (attempt + 1))))
                    continue
                break
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
    outcomes = provider.classify_many(cases)
    results: list[dict[str, Any]] = []
    expected: list[set[str]] = []
    predicted: list[set[str]] = []
    error_count = 0
    for case, outcome in zip(cases, outcomes):
        exp = set(case["expected_labels"])
        if outcome.classification is None:
            error_count += 1
            results.append({
                "company": case.get("company"),
                "title": case.get("title"),
                "expected_labels": sorted(exp),
                "predicted_labels": list(outcome.raw_labels),
                "error": outcome.error,
                "exact": False,
            })
            continue

        classification = outcome.classification
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

    summary = score_gold(expected, predicted)
    summary.update({
        "attempted_cases": len(cases),
        "valid_cases": len(expected),
        "validation_errors": error_count,
        "validation_error_rate": error_count / len(cases) if cases else 0.0,
    })
    return summary, results


def run_live_sample(
    provider: ProfileClassifier,
    feed_path: Path,
    limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = json.loads(feed_path.read_text(encoding="utf-8"))
    jobs = doc.get("jobs") or []
    sample = stable_general_sample(jobs, limit)
    outcomes = provider.classify_many(sample)
    rows: list[dict[str, Any]] = []
    label_counts = {label: 0 for label in ALLOWED_LABELS}
    high_confidence_non_general = 0
    validation_errors = 0
    for job, outcome in zip(sample, outcomes):
        if outcome.classification is None:
            validation_errors += 1
            rows.append({
                "job_id": job.get("id"),
                "company": job.get("company"),
                "title": job.get("title"),
                "labels": list(outcome.raw_labels),
                "error": outcome.error,
            })
            continue

        classification = outcome.classification
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
        "valid_results": len(sample) - validation_errors,
        "validation_errors": validation_errors,
        "validation_error_rate": validation_errors / len(sample) if sample else 0.0,
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
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
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

    provider = GeminiProfileClassifier(
        api_key=api_key,
        model=args.model,
        batch_size=args.batch_size,
    )
    gold_summary, gold_rows = run_gold(provider, args.gold)
    live_summary, live_rows = run_live_sample(provider, args.feed, args.limit)

    report = {
        "schema": "yartchives-ai-profile-benchmark-v2",
        "provider": provider.name,
        "model": args.model,
        "batch_size": args.batch_size,
        "production_mutation": False,
        "gold": {"summary": gold_summary, "rows": gold_rows},
        "live_general_sample": {"summary": live_summary, "rows": live_rows},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "model": args.model,
        "batch_size": args.batch_size,
        "gold": gold_summary,
        "live_general_sample": live_summary,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
