#!/usr/bin/env python3
"""Make one real Azure OpenAI profile-classification request as a smoke test."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from ai_profile_providers import AzureOpenAIProfileClassifier


SMOKE_JOB = {
    "company": "Yartchives Smoke Test",
    "title": "Software Engineering Intern",
    "description": "Build and test software systems using Python and APIs.",
}


def main() -> int:
    api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "")

    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_API_KEY", api_key),
            ("AZURE_OPENAI_ENDPOINT", endpoint),
            ("AZURE_OPENAI_DEPLOYMENT", deployment),
        )
        if not value
    ]
    if missing:
        raise SystemExit("Missing required Azure OpenAI configuration: " + ", ".join(missing))

    provider = AzureOpenAIProfileClassifier(
        api_key=api_key,
        endpoint=endpoint,
        deployment=deployment,
        timeout=45,
        batch_size=1,
    )
    outcome = provider.classify_many([SMOKE_JOB])[0]
    classification = outcome.classification
    if classification is None:
        raise SystemExit(f"Azure OpenAI returned an invalid classification: {outcome.error}")

    print(json.dumps({
        "provider": provider.name,
        "model": provider.model,
        "labels": list(classification.labels),
        "confidence": classification.confidence,
        "evidence_count": len(classification.evidence),
        "structured_output_valid": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
