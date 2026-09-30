#!/usr/bin/env python3
"""Apply high-confidence AI career-area classifications to deterministic General roles.

Deterministic career-area rules remain authoritative. This pass only considers
jobs whose current profiles are exactly ["general"]. AI results are accepted
only above a conservative confidence threshold and are stored with provenance.

Prior accepted classifications can be reused from the previous published feed
when the public role evidence fingerprint is unchanged, avoiding repeated model
calls for stable listings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import ai_profile_benchmark as ai

DEFAULT_FEED = SCRIPT_DIR.parent / "data" / "listings.json"
DEFAULT_MODEL = ai.DEFAULT_MODEL
DEFAULT_THRESHOLD = 0.95
DEFAULT_BATCH_SIZE = 20
CLASSIFICATION_FIELD = "profile_classification"


def evidence_fingerprint(job: dict[str, Any]) -> str:
    payload = ai.compact_job_evidence(job)
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _accepted_metadata(
    classification: ai.Classification,
    *,
    provider: str,
    model: str,
    fingerprint: str,
) -> dict[str, Any]:
    return {
        "method": "ai-fallback",
        "provider": provider,
        "model": model,
        "confidence": classification.confidence,
        "evidence": list(classification.evidence),
        "input_fingerprint": fingerprint,
    }


def _cached_classification(
    cached_job: dict[str, Any] | None,
    *,
    model: str,
    threshold: float,
    fingerprint: str,
) -> ai.Classification | None:
    if not isinstance(cached_job, dict):
        return None
    metadata = cached_job.get(CLASSIFICATION_FIELD)
    if not isinstance(metadata, dict):
        return None
    if metadata.get("method") != "ai-fallback":
        return None
    if metadata.get("model") != model:
        return None
    if metadata.get("input_fingerprint") != fingerprint:
        return None

    labels = cached_job.get("profiles")
    if not isinstance(labels, list) or not labels or "general" in labels:
        return None
    try:
        confidence = float(metadata.get("confidence"))
    except (TypeError, ValueError):
        return None
    if confidence < threshold:
        return None
    if not set(labels).issubset(set(ai.ALLOWED_LABELS) - {"general"}):
        return None

    evidence = metadata.get("evidence")
    if not isinstance(evidence, list):
        evidence = []
    return ai.Classification(
        tuple(sorted(dict.fromkeys(str(label) for label in labels))),
        confidence,
        tuple(str(item) for item in evidence if str(item).strip())[:3],
    )


def _cache_by_id(cache_doc: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(cache_doc, dict):
        return {}
    jobs = cache_doc.get("jobs")
    if not isinstance(jobs, list):
        return {}
    return {
        str(job.get("id")): job
        for job in jobs
        if isinstance(job, dict) and job.get("id")
    }


def apply_ai_fallback(
    doc: dict[str, Any],
    provider: ai.ProfileClassifier,
    *,
    model: str,
    threshold: float = DEFAULT_THRESHOLD,
    cache_doc: dict[str, Any] | None = None,
    request_batch_size: int = DEFAULT_BATCH_SIZE,
) -> dict[str, int]:
    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Feed does not contain a jobs list")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    if request_batch_size < 1:
        raise ValueError("request_batch_size must be positive")

    cache = _cache_by_id(cache_doc)
    candidates: list[dict[str, Any]] = []
    fingerprints: dict[str, str] = {}
    reused = 0

    for job in jobs:
        if not isinstance(job, dict):
            continue
        if set(job.get("profiles") or []) != {"general"}:
            continue

        job.pop(CLASSIFICATION_FIELD, None)
        fingerprint = evidence_fingerprint(job)
        job_id = str(job.get("id") or "")
        fingerprints[job_id] = fingerprint

        cached = _cached_classification(
            cache.get(job_id),
            model=model,
            threshold=threshold,
            fingerprint=fingerprint,
        )
        if cached is not None:
            job["profiles"] = list(cached.labels)
            job[CLASSIFICATION_FIELD] = _accepted_metadata(
                cached,
                provider=getattr(provider, "name", "unknown"),
                model=model,
                fingerprint=fingerprint,
            )
            reused += 1
        else:
            candidates.append(job)

    accepted = 0
    kept_general = 0
    failed = 0

    for start in range(0, len(candidates), request_batch_size):
        batch = candidates[start:start + request_batch_size]
        try:
            outcomes = provider.classify_many(batch)
        except Exception as exc:
            failed += len(batch)
            print(
                f"AI profile fallback batch failed for {len(batch)} jobs: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            continue

        for job, outcome in zip(batch, outcomes):
            classification = outcome.classification
            if (
                classification is None
                or classification.confidence < threshold
                or classification.labels == ("general",)
                or "general" in classification.labels
            ):
                kept_general += 1
                continue

            job["profiles"] = list(classification.labels)
            fingerprint = fingerprints.get(str(job.get("id") or "")) or evidence_fingerprint(job)
            job[CLASSIFICATION_FIELD] = _accepted_metadata(
                classification,
                provider=getattr(provider, "name", "unknown"),
                model=model,
                fingerprint=fingerprint,
            )
            accepted += 1

    return {
        "eligible_general": reused + len(candidates),
        "cache_reused": reused,
        "model_attempted": len(candidates),
        "accepted": accepted,
        "kept_general": kept_general,
        "failed": failed,
    }


def _load_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("feed", nargs="?", type=Path, default=DEFAULT_FEED)
    parser.add_argument("--cache-feed", type=Path)
    parser.add_argument("--model", default=os.getenv("GEMINI_MODEL", DEFAULT_MODEL))
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--api-key-env", default="GEMINI_API_KEY")
    args = parser.parse_args()

    api_key = os.getenv(args.api_key_env, "")
    if not api_key:
        print(
            f"AI profile fallback skipped: {args.api_key_env} is not configured; "
            "deterministic career areas remain unchanged."
        )
        return 0

    doc = _load_json(args.feed)
    if doc is None:
        raise SystemExit(f"Feed does not exist: {args.feed}")
    cache_doc = _load_json(args.cache_feed)

    provider = ai.GeminiProfileClassifier(
        api_key=api_key,
        model=args.model,
        batch_size=args.batch_size,
    )
    stats = apply_ai_fallback(
        doc,
        provider,
        model=args.model,
        threshold=args.threshold,
        cache_doc=cache_doc,
        request_batch_size=args.batch_size,
    )

    args.feed.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(
        "AI profile fallback: "
        + ", ".join(f"{key}={value}" for key, value in stats.items())
        + f", threshold={args.threshold:.2f}, model={args.model}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
