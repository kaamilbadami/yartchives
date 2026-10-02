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
import ai_profile_providers as provider_adapters

DEFAULT_FEED = SCRIPT_DIR.parent / "data" / "listings.json"
DEFAULT_MODEL = ai.DEFAULT_MODEL
DEFAULT_THRESHOLD = 0.95
DEFAULT_BATCH_SIZE = 20
DEFAULT_MAX_BATCHES = 10
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
    models: set[str],
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
    if str(metadata.get("model")) not in models:
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
    max_batches: int | None = DEFAULT_MAX_BATCHES,
    cache_models: set[str] | None = None,
) -> dict[str, int]:
    jobs = doc.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Feed does not contain a jobs list")
    if not 0 <= threshold <= 1:
        raise ValueError("threshold must be between 0 and 1")
    if request_batch_size < 1:
        raise ValueError("request_batch_size must be positive")
    if max_batches is not None and max_batches < 1:
        raise ValueError("max_batches must be positive when provided")

    accepted_cache_models = set(cache_models or {model})
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
            models=accepted_cache_models,
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
    attempted = 0
    stopped_after_failure = 0

    for batch_index, start in enumerate(range(0, len(candidates), request_batch_size)):
        if max_batches is not None and batch_index >= max_batches:
            break
        batch = candidates[start:start + request_batch_size]
        attempted += len(batch)
        try:
            outcomes = provider.classify_many(batch)
        except Exception as exc:
            failed += len(batch)
            stopped_after_failure = 1
            print(
                f"AI profile fallback stopped after provider failure for {len(batch)} jobs: "
                f"{type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            break

        effective_provider = str(
            getattr(provider, "last_provider_name", getattr(provider, "name", "unknown"))
        )
        effective_model = str(getattr(provider, "last_model", model))

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
                provider=effective_provider,
                model=effective_model,
                fingerprint=fingerprint,
            )
            accepted += 1

    return {
        "eligible_general": reused + len(candidates),
        "cache_reused": reused,
        "model_attempted": attempted,
        "budget_deferred": max(0, len(candidates) - attempted),
        "accepted": accepted,
        "kept_general": kept_general,
        "failed": failed,
        "stopped_after_failure": stopped_after_failure,
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
    parser.add_argument("--max-batches", type=int, default=DEFAULT_MAX_BATCHES)
    parser.add_argument("--api-key-env", default="GEMINI_API_KEY")
    parser.add_argument("--azure-api-key-env", default="AZURE_OPENAI_API_KEY")
    parser.add_argument("--azure-endpoint-env", default="AZURE_OPENAI_ENDPOINT")
    parser.add_argument("--azure-deployment-env", default="AZURE_OPENAI_DEPLOYMENT")
    args = parser.parse_args()

    gemini_api_key = os.getenv(args.api_key_env, "")
    azure_api_key = os.getenv(args.azure_api_key_env, "")
    azure_endpoint = os.getenv(args.azure_endpoint_env, "")
    azure_deployment = os.getenv(args.azure_deployment_env, "")

    configured_providers: list[ai.ProfileClassifier] = []
    if gemini_api_key:
        configured_providers.append(
            ai.GeminiProfileClassifier(
                api_key=gemini_api_key,
                model=args.model,
                batch_size=args.batch_size,
            )
        )
    if azure_api_key and azure_endpoint and azure_deployment:
        configured_providers.append(
            provider_adapters.AzureOpenAIProfileClassifier(
                api_key=azure_api_key,
                endpoint=azure_endpoint,
                deployment=azure_deployment,
                batch_size=args.batch_size,
            )
        )
    elif any((azure_api_key, azure_endpoint, azure_deployment)):
        print(
            "Azure OpenAI fallback is partially configured; endpoint, key, and deployment "
            "are all required. Continuing without Azure.",
            file=sys.stderr,
        )

    if not configured_providers:
        print(
            "AI profile fallback skipped: no configured provider; "
            "deterministic career areas remain unchanged."
        )
        return 0

    doc = _load_json(args.feed)
    if doc is None:
        raise SystemExit(f"Feed does not exist: {args.feed}")
    cache_doc = _load_json(args.cache_feed)

    provider = provider_adapters.FailoverProfileClassifier(configured_providers)
    primary_model = str(getattr(configured_providers[0], "model", configured_providers[0].name))
    stats = apply_ai_fallback(
        doc,
        provider,
        model=primary_model,
        threshold=args.threshold,
        cache_doc=cache_doc,
        request_batch_size=args.batch_size,
        max_batches=args.max_batches,
        cache_models=provider.cache_models,
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
