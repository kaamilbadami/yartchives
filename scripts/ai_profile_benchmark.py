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
import importlib.util
import json
import os
import re
import sys
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
DEFAULT_REFERENCE_LIMIT = 300

LEGACY_ENGINEERING_LABELS = {"mechanical", "aero", "electrical"}

ALLOWED_LABELS = (
    "cs",
    "tech-business",
    "finance-econ",
    "engineering",
    "policy",
    "health",
    "general",
)

SYSTEM_INSTRUCTION = """You classify internship/co-op roles into the Yartchives career taxonomy.
Use only the supplied role evidence. Return one result for every supplied key, with the same key.

Taxonomy contract:
- cs: software/computing roles, data science/engineering, ML/AI technical roles, cybersecurity, cloud/platform/DevOps, databases, networking, IT, test automation, and programming-heavy roles.
- tech-business: product management, business/systems/data analysts, analytics/BI, technology consulting/strategy, digital transformation, implementation, and business/product operations.
- finance-econ: finance, accounting, audit, tax, actuarial, banking, investments, markets, trading, economics, risk, underwriting, quantitative finance/research/trading.
- engineering: physical engineering roles, including mechanical/manufacturing/industrial/materials/thermal/CAD, aerospace/aeronautical/spacecraft/propulsion/aerodynamics/GNC/flight/avionics, electrical/electronics/hardware/computer engineering, embedded systems/firmware, FPGA/RF/semiconductors/IC/VLSI/PCB/signal/power, and broad physical/general engineering. Mechanical, aerospace, and electrical are sub-disciplines, not separate career-area labels.
- policy: public policy, government/public affairs, legislative, advocacy, government relations, and policy research.
- health: clinical/healthcare/public-health/medical/biomedical/patient/pharmacy/life-science roles.
- general: use only when none of the specialized labels clearly apply. general is mutually exclusive with every specialized label.

Boundary rules that matter in Yartchives:
- Software engineering is cs, not engineering merely because the title contains "engineer".
- Security, cloud, data, platform, DevOps, site-reliability, software, sales, solutions, support, and consulting roles do not receive engineering solely because "engineer" appears in the title.
- Firmware, embedded systems, computer-engineering, and hardware roles are engineering. Add cs only when the title/function independently indicates software, programming, computer science, data science/engineering, ML/AI engineering, or another cs role family. Do not add cs merely because firmware or embedded work involves code.
- Avionics, aerospace, mechanical/manufacturing, and electrical/hardware roles all receive engineering; do not emit discipline names as labels.
- Data analyst, business intelligence, analytics, technology operations, product management, and digital-transformation roles are tech-business unless the role evidence clearly says software engineering, data engineering, data science, ML/AI engineering, or another cs role family. Generic "data", "technology", or "analytics" wording alone does not add cs.
- Finance/econ roles do not receive cs merely because they mention data, analytics, technology, or quantitative work. Add cs only for an independently explicit computing role such as quantitative developer, software, data engineering/science, or programming.
- Generic physical-engineering titles such as Engineering Intern, Systems Engineering Intern, Design Engineer, Test Engineer, or Product Development Engineering receive engineering when the role evidence is genuinely physical/technical engineering.
- Mechanical/manufacturing, aerospace, and electrical/hardware distinctions are discipline metadata handled separately from this career-area classification.
- AI in business strategy, product marketing, people/HR transformation, policy, or other nontechnical contexts is not cs.
- A role whose own title/function explicitly says medical, clinical, healthcare, biomedical, pharmacy, public health, or life sciences receives health even when it also has a cs or tech-business function. Do not infer health merely from the employer's industry or company name.
- Do not infer finance, policy, or engineering from the employer's industry alone; classify the role itself.
- Prefer coverage over omission when multiple specialized labels are independently supported by the role evidence. Extra plausible supported labels are less harmful than missing a relevant label.
- Do not add unrelated labels "just in case"; every label still needs visible role evidence.

Return one or more labels only when the role/function clearly belongs there.
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




def _load_enrich_feed_module():
    path = ROOT / "scripts" / "enrich_feed.py"
    spec = importlib.util.spec_from_file_location("yartchives_enrich_feed", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load deterministic classifier from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ENRICH_FEED = _load_enrich_feed_module()

def canonicalize_profile_labels(labels: Any) -> set[str]:
    """Collapse legacy engineering discipline labels into the Engineering career area."""
    values = {str(label) for label in (labels or [])}
    if values & LEGACY_ENGINEERING_LABELS:
        values.add("engineering")
    values -= LEGACY_ENGINEERING_LABELS
    return values


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
                    retry_delay = _retry_delay_seconds(response, attempt)
                    if retry_delay > 30:
                        raise RuntimeError(
                            f"Gemini quota unavailable for {retry_delay:.1f}s: {detail}"
                        )
                    if attempt < 4:
                        time.sleep(retry_delay)
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
                    if attempt < 4 and _retry_delay_seconds(response, attempt) <= 30:
                        continue
                    break
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



def _stable_job_key(job: dict[str, Any]) -> str:
    return hashlib.sha256(
        str(job.get("id") or f"{job.get('company','')}|{job.get('title','')}").encode("utf-8")
    ).hexdigest()


def rule_backed_reference_candidates(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return non-General jobs whose labels are reproduced from visible role evidence.

    Source-key-only classifications are excluded by recomputing after source_keys are
    removed. This keeps the reference set grounded in evidence Gemini can actually see.
    """
    candidates: list[dict[str, Any]] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        stored = canonicalize_profile_labels(job.get("profiles"))
        if not stored or "general" in stored:
            continue
        if not stored.issubset(ALLOWED_LABELS):
            continue

        visible_job = dict(job)
        visible_job["source_keys"] = []
        recomputed = set(ENRICH_FEED.classify_profiles(visible_job))
        if recomputed != stored:
            continue

        # Generic engineering fallback titles (for example "Systems Engineering"
        # or "Product Engineering") are intentionally broad in production, but
        # they are not strong enough to serve as benchmark truth by themselves.
        # Keep Engineering in the rule-backed reference only when a concrete
        # engineering discipline is visible in the role evidence.
        if (
            "engineering" in stored
            and not ENRICH_FEED.classify_engineering_disciplines(visible_job)
        ):
            continue

        candidates.append(job)
    return candidates


def stable_rule_reference_sample(jobs: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Deterministically stratify rule-backed jobs across profile labels."""
    if limit <= 0:
        return []
    candidates = rule_backed_reference_candidates(jobs)
    labels = [label for label in ALLOWED_LABELS if label != "general"]
    buckets: dict[str, list[dict[str, Any]]] = {
        label: sorted(
            [job for job in candidates if label in canonicalize_profile_labels(job.get("profiles"))],
            key=_stable_job_key,
        )
        for label in labels
    }
    positions = {label: 0 for label in labels}
    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    while len(selected) < limit:
        progressed = False
        for label in labels:
            bucket = buckets[label]
            while positions[label] < len(bucket):
                job = bucket[positions[label]]
                positions[label] += 1
                key = _stable_job_key(job)
                if key in seen:
                    continue
                seen.add(key)
                selected.append(job)
                progressed = True
                break
            if len(selected) >= limit:
                break
        if not progressed:
            break
    return selected


def per_label_metrics(expected: list[set[str]], predicted: list[set[str]]) -> dict[str, dict[str, float | int]]:
    metrics: dict[str, dict[str, float | int]] = {}
    for label in ALLOWED_LABELS:
        if label == "general":
            continue
        tp = sum(1 for exp, pred in zip(expected, predicted) if label in exp and label in pred)
        fp = sum(1 for exp, pred in zip(expected, predicted) if label not in exp and label in pred)
        fn = sum(1 for exp, pred in zip(expected, predicted) if label in exp and label not in pred)
        support = sum(1 for exp in expected if label in exp)
        if not support and not tp and not fp and not fn:
            continue
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        beta = 2.0
        f2 = (
            (1 + beta * beta) * precision * recall
            / ((beta * beta * precision) + recall)
            if precision or recall
            else 0.0
        )
        metrics[label] = {
            "support": support,
            "precision": precision,
            "recall": recall,
            "f2": f2,
        }
    return metrics


def run_rule_reference(
    provider: ProfileClassifier,
    feed_path: Path,
    limit: int,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    doc = json.loads(feed_path.read_text(encoding="utf-8"))
    jobs = doc.get("jobs") or []
    candidates = rule_backed_reference_candidates(jobs)
    sample = stable_rule_reference_sample(jobs, limit)
    outcomes = provider.classify_many(sample)

    rows: list[dict[str, Any]] = []
    expected_valid: list[set[str]] = []
    predicted_valid: list[set[str]] = []
    validation_errors = 0
    disagreements = 0

    for job, outcome in zip(sample, outcomes):
        exp = canonicalize_profile_labels(job.get("profiles"))
        if outcome.classification is None:
            validation_errors += 1
            disagreements += 1
            rows.append({
                "job_id": job.get("id"),
                "company": job.get("company"),
                "title": job.get("title"),
                "expected_labels": sorted(exp),
                "predicted_labels": list(outcome.raw_labels),
                "error": outcome.error,
                "exact": False,
            })
            continue

        pred = set(outcome.classification.labels)
        expected_valid.append(exp)
        predicted_valid.append(pred)
        exact = exp == pred
        if not exact:
            disagreements += 1
        rows.append({
            "job_id": job.get("id"),
            "company": job.get("company"),
            "title": job.get("title"),
            "expected_labels": sorted(exp),
            "predicted_labels": sorted(pred),
            "confidence": outcome.classification.confidence,
            "evidence": list(outcome.classification.evidence),
            "exact": exact,
        })

    summary = score_gold(expected_valid, predicted_valid)
    summary.update({
        "candidate_pool": len(candidates),
        "sample_size": len(sample),
        "valid_results": len(expected_valid),
        "validation_errors": validation_errors,
        "validation_error_rate": validation_errors / len(sample) if sample else 0.0,
        "disagreements": disagreements,
        "agreement_rate_including_invalid": (
            (len(sample) - disagreements) / len(sample) if sample else 0.0
        ),
        "per_label": per_label_metrics(expected_valid, predicted_valid),
    })
    return summary, rows

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
    beta = 2.0
    f2 = (
        (1 + beta * beta) * precision * recall
        / ((beta * beta * precision) + recall)
        if precision or recall
        else 0.0
    )
    coverage_cases = sum(1 for exp, pred in zip(expected, predicted) if exp.issubset(pred))
    underclassified_cases = sum(1 for exp, pred in zip(expected, predicted) if exp - pred)
    overclassified_only_cases = sum(
        1 for exp, pred in zip(expected, predicted)
        if exp < pred
    )
    mixed_error_cases = sum(
        1 for exp, pred in zip(expected, predicted)
        if (exp - pred) and (pred - exp)
    )
    return {
        "cases": total,
        "exact_set_accuracy": exact / total if total else 0.0,
        "coverage_accuracy": coverage_cases / total if total else 0.0,
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f2": f2,
        "missed_label_count": fn,
        "extra_label_count": fp,
        "underclassified_cases": underclassified_cases,
        "overclassified_only_cases": overclassified_only_cases,
        "mixed_error_cases": mixed_error_cases,
    }


def run_gold(provider: ProfileClassifier, gold_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    cases = json.loads(gold_path.read_text(encoding="utf-8"))
    outcomes = provider.classify_many(cases)
    results: list[dict[str, Any]] = []
    expected: list[set[str]] = []
    predicted: list[set[str]] = []
    error_count = 0
    for case, outcome in zip(cases, outcomes):
        exp = canonicalize_profile_labels(case["expected_labels"])
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
    parser.add_argument("--reference-limit", type=int, default=DEFAULT_REFERENCE_LIMIT)
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
    reference_summary, reference_rows = run_rule_reference(
        provider, args.feed, args.reference_limit
    )

    report = {
        "schema": "yartchives-ai-profile-benchmark-v3",
        "provider": provider.name,
        "model": args.model,
        "batch_size": args.batch_size,
        "production_mutation": False,
        "gold": {"summary": gold_summary, "rows": gold_rows},
        "live_general_sample": {"summary": live_summary, "rows": live_rows},
        "rule_backed_reference": {"summary": reference_summary, "rows": reference_rows},
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({
        "model": args.model,
        "batch_size": args.batch_size,
        "gold": gold_summary,
        "live_general_sample": live_summary,
        "rule_backed_reference": reference_summary,
        "output": str(args.output),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
