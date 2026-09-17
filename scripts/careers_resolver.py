#!/usr/bin/env python3
"""Resolve employer-universe entries to official careers landing pages.

The resolver inspects employer-owned pages and their recruiting-platform
handoffs. It resolves sites only: it never calls job-search APIs and rejects
individual opening URLs before requesting them.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qs, urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from provider_fingerprint import fingerprint_provider  # noqa: E402

TIMEOUT = 15
MAX_PAGES = 12
USER_AGENT = "Yartchives/1.0 careers-resolver (+https://github.com/kaamilbadami/yartchives)"
CAREER_WORDS = re.compile(r"\b(careers?|jobs?|join us|work with us|opportunities|employment)\b", re.I)


class Candidate:
    def __init__(self, url: str, source: str, linked_from: str | None = None, anchor_text: str = ""):
        self.url = url
        self.source = source
        self.linked_from = linked_from
        self.anchor_text = anchor_text


def http_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text.lstrip("/")
    try:
        parsed = urlparse(text)
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", "", parsed.query, ""))


def entry_hints(entry: dict[str, Any]) -> list[str]:
    """Accept domain hints from seed, universe, and ordinary registry records."""
    values: list[Any] = []
    for key in (
        "domain", "domains", "domain_hint", "domain_hints", "website",
        "homepage", "url_hint", "url_hints", "careers_url",
    ):
        value = entry.get(key)
        values.extend(value if isinstance(value, list) else [value])
    return list(dict.fromkeys(url for value in values if (url := http_url(value))))


def host_matches(host: str | None, domain: str | None) -> bool:
    host = (host or "").lower().split(":", 1)[0]
    domain = (domain or "").lower().split(":", 1)[0]
    return bool(host and domain and (host == domain or host.endswith("." + domain) or domain.endswith("." + host)))


def provider_for(url: str, html: str = "") -> dict[str, Any]:
    return fingerprint_provider(url, html=html or None)


def platform_for(url: str, html: str = "") -> str:
    provider = provider_for(url, html)
    return provider["family"] if provider["status"] == "resolved" else "company-branded"


def has_provider_tenant_identity(url: str, family: str | None = None) -> bool:
    """Return false for shared ATS roots that do not identify an employer."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    family = family or provider_for(url)["family"]
    if host in {"greenhouse.com", "www.greenhouse.com"}:
        family = "greenhouse"
    parts = [part for part in parsed.path.split("/") if part]
    query = parse_qs(parsed.query.lower())
    if family == "greenhouse":
        return bool(parts and parts[0] not in {"jobs", "careers"})
    if family in {"ashby", "lever", "smartrecruiters"}:
        return bool(parts)
    if family == "successfactors":
        return bool(query.get("company"))
    if family == "oracle":
        return "sites" in [part.lower() for part in parts] or bool((parsed.hostname or "").split(".")[0])
    return True


def is_job_detail(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.lower()
    query = parse_qs(parsed.query.lower())
    family = provider_for(url)["family"]
    if family == "workday":
        return "/job/" in path or "/jobs/" in path
    if family == "oracle":
        return bool(re.search(r"/job/[^/]+", path)) or "jobid" in query
    if family == "successfactors":
        return query.get("career_ns") == ["job_listing"] or "career_job_req_id" in query or "/job/" in path
    if family == "greenhouse":
        return bool(re.search(r"/jobs?/\d+(?:/|$)", path))
    if family in {"ashby", "lever"}:
        return len([part for part in path.split("/") if part]) > 1
    if family == "icims":
        return bool(re.search(r"/jobs/\d+(?:/|$)", path))
    if family == "smartrecruiters":
        return len([part for part in path.split("/") if part]) > 1
    return bool(re.search(r"/(?:jobs?|careers?)/(?:[^/?#]+/)*\d{3,}(?:/|$)", path))


def is_company_landing_path(url: str) -> bool:
    path = urlparse(url).path.lower().rstrip("/")
    return bool(re.search(
        r"/(?:careers?|jobs?|join-us|work-with-us|employment|opportunities)"
        r"(?:/(?:home|search|openings|positions))?$",
        path,
    ))


def normalized_landing_url(url: str, platform: str) -> str:
    parsed = urlparse(url)
    query = parsed.query
    if platform == "successfactors":
        values = parse_qs(query, keep_blank_values=True)
        query = "&".join(
            f"{key}={value}"
            for key in ("company", "lang")
            for value in values.get(key, [])
        )
    elif platform != "oracle":
        query = ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/") or "/", "", query, ""))


def redirect_chain(response: requests.Response, requested: str) -> list[dict[str, Any]]:
    return [
        {"url": item.url or requested, "status": item.status_code}
        for item in [*getattr(response, "history", []), response]
    ]


def page_score(candidate: Candidate, final_url: str, html: str, official_domains: set[str]) -> tuple[int, list[str]]:
    platform = platform_for(final_url, html)
    parsed = urlparse(final_url)
    text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)[:12000] if html else ""
    signals: list[str] = []
    score = 0
    direct_provider = provider_for(final_url)
    if direct_provider["status"] == "resolved" and not has_provider_tenant_identity(final_url):
        return -50, ["shared provider host lacks employer tenant identity"]
    if platform != "company-branded":
        score += 5
        signals.append(f"{platform} provider fingerprint")
    if CAREER_WORDS.search(parsed.path.replace("-", " ")):
        score += 3
        signals.append("careers path")
    if CAREER_WORDS.search(candidate.anchor_text):
        score += 3
        signals.append("careers link text")
    if CAREER_WORDS.search(text[:4000]):
        score += 2
        signals.append("careers page content")
    if any(host_matches(parsed.hostname, domain) for domain in official_domains):
        score += 2
        signals.append("employer domain")
    if candidate.linked_from:
        score += 4
        signals.append("linked from employer site")
    if is_job_detail(final_url):
        return -100, ["job detail URL rejected"]
    return score, signals


def career_links(html: str, base_url: str, official_domains: set[str]) -> Iterable[Candidate]:
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        text = " ".join(anchor.get_text(" ", strip=True).split())
        absolute = http_url(urljoin(base_url, str(anchor.get("href") or "")))
        if not absolute or is_job_detail(absolute):
            continue
        host = urlparse(absolute).hostname
        recognized_ats = provider_for(absolute)["status"] == "resolved"
        same_employer = any(host_matches(host, domain) for domain in official_domains)
        career_signal = bool(CAREER_WORDS.search(text))
        if recognized_ats or (career_signal and same_employer and is_company_landing_path(absolute)):
            yield Candidate(absolute, "employer-link", linked_from=base_url, anchor_text=text)


def resolve_employer(entry: dict[str, Any], session: requests.Session | None = None, *, timeout: int = TIMEOUT, max_pages: int = MAX_PAGES) -> dict[str, Any]:
    hints = entry_hints(entry)
    if not hints:
        return {"status": "unresolved", "url": None, "platform": None, "provider": None, "evidence": [{"type": "input", "detail": "no valid domain hints"}]}
    client = session or requests.Session()
    official_domains = {(urlparse(url).hostname or "").lower().removeprefix("www.") for url in hints}
    queue: list[Candidate] = []
    for hint in hints:
        parsed = urlparse(hint)
        origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
        queue.append(Candidate(hint, "input-hint"))
        if parsed.path in {"", "/"}:
            queue.extend(Candidate(origin + suffix, "conventional-path") for suffix in ("/careers", "/jobs"))
    evidence: list[dict[str, Any]] = []
    scored: list[tuple[int, int, str, str, dict[str, Any]]] = []
    seen: set[str] = set()
    order = 0
    while queue and len(seen) < max_pages:
        candidate = queue.pop(0)
        if candidate.url in seen or is_job_detail(candidate.url):
            continue
        seen.add(candidate.url)
        record: dict[str, Any] = {"type": "http", "source": candidate.source, "requested_url": candidate.url}
        if candidate.linked_from:
            record["linked_from"] = candidate.linked_from
        try:
            response = client.get(candidate.url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}, timeout=timeout, allow_redirects=True)
            final_url = http_url(response.url or candidate.url) or candidate.url
            record.update({"redirect_chain": redirect_chain(response, candidate.url), "final_url": final_url, "status": response.status_code})
            content_type = (response.headers.get("Content-Type", "") if hasattr(response, "headers") else "").lower()
            html = response.text if response.status_code < 400 and ("html" in content_type or not content_type) else ""
            score, signals = page_score(candidate, final_url, html, official_domains)
            record.update({"signals": signals, "score": score})
            if response.status_code < 400 and score >= 5:
                provider = provider_for(final_url, html)
                platform = provider["family"] if provider["status"] == "resolved" else "company-branded"
                scored.append((score, -order, normalized_landing_url(final_url, platform), platform, provider))
            final_host = urlparse(final_url).hostname
            if html and any(host_matches(final_host, domain) for domain in official_domains):
                queue.extend(link for link in career_links(html, final_url, official_domains) if link.url not in seen)
        except requests.RequestException as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        evidence.append(record)
        order += 1
    if not scored:
        return {"status": "unresolved", "url": None, "platform": None, "provider": None, "evidence": evidence}
    _, _, url, platform, provider = max(scored, key=lambda item: (item[0], item[1]))
    return {"status": "resolved", "url": url, "platform": platform, "provider": provider, "evidence": evidence}


def resolve_registry(entries: list[dict[str, Any]], session: requests.Session | None = None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for entry in entries:
        row = dict(entry)
        resolution = resolve_employer(entry, session)
        row["careers_resolution"] = resolution
        if resolution["status"] == "resolved":
            row["careers_url"] = resolution["url"]
            row["careers_platform"] = resolution["platform"]
            row["provider"] = resolution["provider"]
        output.append(row)
    return output


def registry_entries(payload: Any) -> tuple[list[dict[str, Any]], str | None]:
    if isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
        return payload, None
    if isinstance(payload, dict) and isinstance(payload.get("employers"), list):
        return payload["employers"], "employers"
    raise ValueError("registry must be a JSON list or an object with an employers list")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("registry", type=Path, help="registry, seed, or employer-universe JSON")
    parser.add_argument("--output", type=Path, help="write enriched JSON here (stdout by default)")
    args = parser.parse_args()
    payload = json.loads(args.registry.read_text(encoding="utf-8"))
    try:
        entries, container_key = registry_entries(payload)
    except ValueError as exc:
        parser.error(str(exc))
    resolved = resolve_registry(entries)
    if container_key:
        result = dict(payload)
        result[container_key] = resolved
    else:
        result = resolved
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
