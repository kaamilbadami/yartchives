#!/usr/bin/env python3
"""Run grounded external discovery for trust-benchmark personas.

This is audit-only. It uses Azure OpenAI Responses API web search to discover
current opportunities independently of the Yartchives feed, validates that
selected URLs are authoritative employer/ATS destinations, and writes the draft
CSV consumed by external_discovery_benchmark.py.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
DISCOVERY_HOSTS = {
    "linkedin.com", "www.linkedin.com", "indeed.com", "www.indeed.com",
    "handshake.com", "joinhandshake.com", "glassdoor.com", "www.glassdoor.com",
    "ziprecruiter.com", "www.ziprecruiter.com",
}
FIELDS = [
    "persona_id", "company", "title", "location", "url", "source",
    "discovery_url", "discovery_query", "expected_state",
]


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower()


def _response_text(payload: dict[str, Any]) -> str:
    pieces: list[str] = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                pieces.append(str(part.get("text") or ""))
    return "\n".join(pieces).strip()


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^\\s*```(?:json)?\\s*", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\\s*```\\s*$", "", cleaned)
    value = json.loads(cleaned)
    if not isinstance(value, dict):
        raise ValueError("discovery response must be a JSON object")
    return value


def _validate_authoritative_url(url: str, timeout: float) -> bool:
    if not url.startswith(("https://", "http://")):
        return False
    if _host(url) in DISCOVERY_HOSTS:
        return False
    try:
        response = requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 YartchivesBenchmark/1.0"},
        )
    except requests.RequestException:
        return False
    return response.status_code < 500 and response.status_code not in {404, 410}


def discover(
    persona: dict[str, Any],
    *,
    endpoint: str,
    api_key: str,
    deployment: str,
    max_results: int,
    timeout: float,
) -> list[dict[str, str]]:
    prompt = f"""You are building an independent internship benchmark for Yartchives.
Do not use or infer anything from the Yartchives feed.

Search the current public web for strong Summer 2027 undergraduate internship/co-op
opportunities for this sanitized student persona:
{json.dumps(persona, ensure_ascii=False, sort_keys=True)}

Rules:
- Use web search extensively and tailor results to the whole profile: academics,
  experience, skills, role intent, graduation timing, and preferences.
- Graduation timing is the canonical eligibility signal.
- Discovery surfaces such as LinkedIn, Indeed, Handshake, Glassdoor, and
  ZipRecruiter may help find roles, but every included result MUST use a current
  authoritative employer or ATS posting URL in "url".
- Exclude stale, closed, graduate-only, full-time, or clearly ineligible roles.
- Return at most {max_results} high-confidence opportunities.
- Do not include Yartchives URLs.
- Return ONLY valid JSON with this shape:
{{
  "discoveries": [
    {{
      "company": "...",
      "title": "...",
      "location": "...",
      "url": "https://authoritative-employer-or-ats/...",
      "source": "web_search",
      "discovery_url": "https://page-that-led-to-the-role/...",
      "discovery_query": "brief query used",
      "expected_state": "two-letter US state or empty"
    }}
  ]
}}
"""
    base = endpoint.rstrip("/")
    if not base.endswith("/openai/v1"):
        base = base + "/openai/v1"
    response = requests.post(
        base + "/responses",
        headers={"Content-Type": "application/json", "api-key": api_key},
        json={
            "model": deployment,
            "tools": [{"type": "web_search"}],
            "tool_choice": "auto",
            "input": prompt,
        },
        timeout=timeout,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Azure OpenAI HTTP {response.status_code}: {response.text[:1000]}")
    payload = response.json()
    if not any(
        isinstance(item, dict) and item.get("type") == "web_search_call"
        for item in payload.get("output") or []
    ):
        raise RuntimeError("Azure response did not perform web search")
    parsed = _parse_json_text(_response_text(payload))
    rows = parsed.get("discoveries")
    if not isinstance(rows, list):
        raise ValueError("discovery response missing discoveries list")

    approved: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for row in rows[:max_results]:
        if not isinstance(row, dict):
            continue
        company = str(row.get("company") or "").strip()
        title = str(row.get("title") or "").strip()
        url = str(row.get("url") or "").strip()
        if not company or not title or not _validate_authoritative_url(url, timeout=min(timeout, 15)):
            continue
        key = (company.lower(), title.lower(), url.lower())
        if key in seen:
            continue
        seen.add(key)
        approved.append({
            "persona_id": str(persona["id"]),
            "company": company,
            "title": title,
            "location": str(row.get("location") or "").strip(),
            "url": url,
            "source": str(row.get("source") or "web_search").strip(),
            "discovery_url": str(row.get("discovery_url") or "").strip(),
            "discovery_query": str(row.get("discovery_query") or "").strip(),
            "expected_state": str(row.get("expected_state") or "").strip().upper()[:2],
        })
    return approved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--personas", type=Path, default=ROOT / "audit/personas/trust-benchmark-personas.json")
    parser.add_argument("--persona", default="KB", help="Persona ID or 'all'")
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--max-results", type=int, default=12)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()
    missing = [
        name for name, value in (
            ("AZURE_OPENAI_API_KEY", api_key),
            ("AZURE_OPENAI_ENDPOINT", endpoint),
            ("AZURE_OPENAI_DEPLOYMENT", deployment),
        ) if not value
    ]
    if missing:
        raise SystemExit("Missing required environment variables: " + ", ".join(missing))

    document = json.loads(args.personas.read_text(encoding="utf-8"))
    personas = [p for p in document.get("personas", []) if isinstance(p, dict) and p.get("id")]
    if args.persona != "all":
        personas = [p for p in personas if p.get("id") == args.persona]
        if not personas:
            raise SystemExit(f"Unknown persona: {args.persona}")

    rows: list[dict[str, str]] = []
    for persona in personas:
        rows.extend(discover(
            persona,
            endpoint=endpoint,
            api_key=api_key,
            deployment=deployment,
            max_results=args.max_results,
            timeout=args.timeout,
        ))

    if not rows:
        raise SystemExit("No authoritative discoveries survived validation")

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    with args.output_csv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"personas": [p["id"] for p in personas], "discoveries": len(rows), "output": str(args.output_csv)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
