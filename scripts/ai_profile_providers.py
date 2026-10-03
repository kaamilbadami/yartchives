#!/usr/bin/env python3
"""Provider adapters and failover policy for AI profile classification."""

from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlsplit

import requests

import ai_profile_benchmark as ai

MAX_RETRY_DELAY_SECONDS = 30.0


def _parse_batch_results(raw: dict[str, Any], jobs: list[dict[str, Any]], provider: str) -> list[ai.ClassificationOutcome]:
    rows = raw.get("results")
    if not isinstance(rows, list):
        raise ValueError(f"{provider} batch response is missing results")

    by_key: dict[str, ai.ClassificationOutcome] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError(f"{provider} batch result must be an object")
        key = str(row.get("key", ""))
        if key in by_key:
            raise ValueError(f"{provider} returned duplicate key {key!r}")
        raw_labels = tuple(
            str(label) for label in row.get("labels", [])
            if isinstance(label, str)
        )
        try:
            classification = ai.validate_classification(row)
            by_key[key] = ai.ClassificationOutcome(
                classification=classification,
                raw_labels=raw_labels,
            )
        except ValueError as exc:
            by_key[key] = ai.ClassificationOutcome(
                classification=None,
                error=str(exc),
                raw_labels=raw_labels,
            )

    expected_keys = {str(index) for index in range(len(jobs))}
    if set(by_key) != expected_keys:
        missing = sorted(expected_keys - set(by_key))
        extra = sorted(set(by_key) - expected_keys)
        raise ValueError(
            f"{provider} batch keys mismatch; missing={missing}, extra={extra}"
        )
    return [by_key[str(index)] for index in range(len(jobs))]


class AzureOpenAIProfileClassifier:
    """Azure OpenAI chat-completions adapter using structured outputs."""

    name = "azure-openai"

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        deployment: str,
        *,
        timeout: float = 45.0,
        batch_size: int = ai.DEFAULT_BATCH_SIZE,
    ):
        if not api_key:
            raise ValueError("Azure OpenAI API key is required")
        if not deployment:
            raise ValueError("Azure OpenAI deployment name is required")
        parsed = urlsplit(endpoint.strip())
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("Azure OpenAI endpoint must be an absolute HTTPS URL without credentials")
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        self.api_key = api_key
        self.endpoint = f"{parsed.scheme}://{parsed.netloc}"
        self.model = deployment
        self.timeout = timeout
        self.batch_size = batch_size

    def classify(self, job: dict[str, Any]) -> ai.Classification:
        outcome = self.classify_many([job])[0]
        if outcome.classification is None:
            raise ValueError(outcome.error or "Azure OpenAI returned an invalid classification")
        return outcome.classification

    def classify_many(self, jobs: list[dict[str, Any]]) -> list[ai.ClassificationOutcome]:
        if not jobs:
            return []
        results: list[ai.ClassificationOutcome] = []
        for start in range(0, len(jobs), self.batch_size):
            results.extend(self._classify_batch(jobs[start:start + self.batch_size]))
        return results

    def _classify_batch(self, jobs: list[dict[str, Any]]) -> list[ai.ClassificationOutcome]:
        keyed_jobs = [
            {"key": str(index), "job": ai.compact_job_evidence(job)}
            for index, job in enumerate(jobs)
        ]
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": ai.SYSTEM_INSTRUCTION},
                {
                    "role": "user",
                    "content": json.dumps({"jobs": keyed_jobs}, ensure_ascii=False, sort_keys=True),
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "yartchives_profile_batch",
                    "strict": True,
                    "schema": ai.BATCH_RESPONSE_SCHEMA,
                },
            },
        }
        url = f"{self.endpoint}/openai/v1/chat/completions"
        last_error: Exception | None = None

        for attempt in range(3):
            response: requests.Response | None = None
            try:
                response = requests.post(
                    url,
                    headers={
                        "Content-Type": "application/json",
                        "api-key": self.api_key,
                    },
                    json=payload,
                    timeout=self.timeout,
                )
                if response.status_code == 429:
                    detail = response.text[:1000].strip()
                    delay = ai._retry_delay_seconds(response, attempt)
                    if delay > MAX_RETRY_DELAY_SECONDS:
                        raise RuntimeError(
                            f"Azure OpenAI quota unavailable for {delay:.1f}s: {detail}"
                        )
                    if attempt < 2:
                        time.sleep(delay)
                        continue
                    raise RuntimeError(f"Azure OpenAI HTTP 429 after retries: {detail}")
                if response.status_code >= 500:
                    detail = response.text[:1000].strip()
                    if attempt < 2:
                        time.sleep(min(MAX_RETRY_DELAY_SECONDS, 2 ** (attempt + 1)))
                        continue
                    raise RuntimeError(
                        f"Azure OpenAI transient HTTP {response.status_code}: {detail}"
                    )
                if response.status_code >= 400:
                    raise ValueError(
                        f"Azure OpenAI HTTP {response.status_code}: "
                        f"{response.text[:1000].strip()}"
                    )

                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    raise ValueError("Azure OpenAI response content is not text")
                return _parse_batch_results(json.loads(content), jobs, "Azure OpenAI")
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
                    if attempt < 2 and ai._retry_delay_seconds(response, attempt) <= MAX_RETRY_DELAY_SECONDS:
                        continue
                    break
                if attempt < 2 and isinstance(exc, requests.RequestException):
                    time.sleep(min(MAX_RETRY_DELAY_SECONDS, 2 ** (attempt + 1)))
                    continue
                break
        raise RuntimeError(f"Azure OpenAI classification failed after retries: {last_error}")


class FailoverProfileClassifier:
    """Try providers in order; a provider outage/quota error falls through."""

    name = "failover"

    def __init__(self, providers: list[ai.ProfileClassifier]):
        if not providers:
            raise ValueError("At least one AI profile provider is required")
        self.providers = list(providers)
        self.last_provider_name = providers[0].name
        self.last_model = str(getattr(providers[0], "model", providers[0].name))

    @property
    def cache_models(self) -> set[str]:
        return {
            str(getattr(provider, "model", provider.name))
            for provider in self.providers
        }

    def classify(self, job: dict[str, Any]) -> ai.Classification:
        outcome = self.classify_many([job])[0]
        if outcome.classification is None:
            raise ValueError(outcome.error or "AI providers returned an invalid classification")
        return outcome.classification

    def classify_many(self, jobs: list[dict[str, Any]]) -> list[ai.ClassificationOutcome]:
        errors: list[str] = []
        for provider in self.providers:
            try:
                outcomes = provider.classify_many(jobs)
                self.last_provider_name = provider.name
                self.last_model = str(getattr(provider, "model", provider.name))
                return outcomes
            except Exception as exc:
                errors.append(f"{provider.name}: {type(exc).__name__}: {exc}")
        raise RuntimeError("All AI profile providers failed: " + " | ".join(errors))
