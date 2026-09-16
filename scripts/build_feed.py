#!/usr/bin/env python3
"""Build the static Yartchives opportunity feed.

The browser never scrapes source repositories directly. This script runs in
GitHub Actions, normalizes public feeds, deduplicates them, and writes one JSON
file for the frontend.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT = Path(__file__).resolve().parents[1]
SOURCES_PATH = ROOT / "sources.json"
OUTPUT_PATH = ROOT / "data" / "listings.json"

USER_AGENT = "Yartchives/1.0 (public opportunity aggregator)"
TIMEOUT = 25

AGGREGATOR_HOSTS = {
    "simplify.jobs",
    "www.simplify.jobs",
    "zapply.jobs",
    "www.zapply.jobs",
    "jobright.ai",
    "www.jobright.ai",
    "applyguy.com",
    "www.applyguy.com",
    "fromcampustocareer.com",
    "www.fromcampustocareer.com",
}
TRACKING_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "source", "ref", "referrer", "gh_src", "lever-source", "src",
}

STATE_NAMES = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "district of columbia": "DC", "washington dc": "DC", "washington, dc": "DC",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN", "mississippi": "MS",
    "missouri": "MO", "montana": "MT", "nebraska": "NE", "nevada": "NV",
    "new hampshire": "NH", "new jersey": "NJ", "new mexico": "NM", "new york": "NY",
    "north carolina": "NC", "north dakota": "ND", "ohio": "OH", "oklahoma": "OK",
    "oregon": "OR", "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA", "west virginia": "WV",
    "wisconsin": "WI", "wyoming": "WY",
}
STATE_ABBRS = set(STATE_NAMES.values())

PROFILE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "cs": (
        "software engineer", "software developer", "software intern", "computer science",
        "machine learning", "ml engineer", "artificial intelligence", " ai intern",
        "data scientist", "cybersecurity", "security engineer", "devops", "cloud engineer",
        "backend", "front end", "frontend", "full stack", "fullstack", "site reliability",
        "sre intern", "computer vision", "distributed systems", "platform engineer",
    ),
    "tech-business": (
        "product manager", "product management", "product analyst", "product operations",
        "technical program manager", "technical program management", "program manager",
        "business analyst", "business systems analyst", "systems analyst", "data analyst",
        "business intelligence", "bi analyst", "analytics intern", "strategy & analytics",
        "strategy and analytics", "solutions engineer", "sales engineer", "solution consultant",
        "technical consultant", "technology consultant", "implementation consultant",
        "implementation intern", "technology strategy", "digital transformation",
        "information systems", "information technology", "technology analyst",
        "operations analyst", "business operations", "revenue operations", "go-to-market", "commercial analytics",
        "strategy intern", "consulting intern", "consultant intern", "product strategy", "technical account",
    ),
    "finance-econ": (
        "finance", "financial", "accounting", "audit", "tax intern", "actuarial", "banking",
        "investment", "credit", "treasury", "wealth management", "risk intern", "risk analyst",
        "underwriting", "economics", "economist", "capital markets", "insurance intern",
        "private equity", "asset management", "commercial banking", "quantitative finance",
    ),
    "mechanical": (
        "mechanical engineer", "mechanical engineering", "manufacturing engineer",
        "manufacturing engineering", "cad intern", "solidworks", "thermal engineer",
        "materials engineer", "industrial engineer", "test engineer", "quality engineer",
    ),
    "aero": (
        "aerospace", "aeronautical", "propulsion", "flight sciences", "flight test",
        "space systems", "spacecraft", "orbital", "avionics", "rocket", "satellite",
    ),
    "electrical": (
        "electrical engineer", "electrical engineering", "electronics engineer", "hardware engineer",
        "embedded", "firmware", "fpga", "rf engineer", "semiconductor", "asic", "pcb",
        "power systems", "controls engineer", "signal processing",
    ),
    "policy": (
        "public policy", "policy intern", "policy analyst", "government affairs", "public affairs",
        "legislative", "political", "advocacy", "civic engagement", "government relations",
        "international relations", "public sector", "urban government", "economic policy",
        "research and policy", "mayor", "city clerk", "congress", "senate", "campaign",
    ),
    "health": (
        "clinical", "healthcare", "health care", "public health", "medical", "biomedical",
        "patient", "laboratory", "lab intern", "research assistant", "clinical research",
        "pharmacy", "pre-med", "premed", "life sciences", "biology intern",
    ),
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if dt else None


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.7,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def fetch_text(s: requests.Session, url: str, headers: dict[str, str] | None = None) -> str:
    response = s.get(url, headers=headers, timeout=TIMEOUT)
    response.raise_for_status()
    return response.text


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    value = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", value)
    value = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", value)
    value = re.sub(r"<br\s*/?>", " / ", value, flags=re.I)
    value = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip(" |\t\r\n")
    return value


def extract_links(value: str | None) -> list[str]:
    if not value:
        return []
    links = re.findall(r"\[[^\]]*\]\((https?://[^)\s]+)", value)
    links += re.findall(r"href=[\"'](https?://[^\"']+)", value, flags=re.I)
    links += re.findall(r"(?<![\w\"'=])(https?://[^\s<>)\]]+)", value)
    # preserve order
    return list(dict.fromkeys(x.rstrip(".,;") for x in links))


def choose_apply_url(urls: Iterable[str]) -> str | None:
    candidates = [u for u in dict.fromkeys(urls) if u.startswith("http")]
    if not candidates:
        return None
    for u in candidates:
        host = urlparse(u).netloc.lower()
        if host not in AGGREGATOR_HOSTS and "github.com" not in host and "raw.githubusercontent.com" not in host:
            return u
    return candidates[0]


def canonical_url(url: str | None) -> str:
    if not url:
        return ""
    try:
        p = urlparse(url)
        clean_query = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                       if k.lower() not in TRACKING_KEYS and not k.lower().startswith("utm_")]
        path = re.sub(r"/+", "/", p.path).rstrip("/") or "/"
        return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "", urlencode(clean_query), ""))
    except Exception:
        return url


def norm(value: str | None) -> str:
    value = (value or "").lower()
    value = re.sub(r"&amp;", " and ", value)
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_relative_date(raw: str | None, reference: datetime) -> datetime | None:
    if not raw:
        return None
    text = clean_text(raw).lower().strip()
    if not text or text in {"unknown", "date unknown", "—", "-"}:
        return None
    if "today" in text or "just now" in text:
        return reference
    m = re.fullmatch(r"(\d+)\s*(m|min|mins|minute|minutes)", text)
    if m:
        return reference - timedelta(minutes=int(m.group(1)))
    m = re.fullmatch(r"(\d)\s*(h|hr|hrs|hour|hours)", text)
    if m:
        return reference - timedelta(hours=int(m.group(1)))
    m = re.fullmatch(r"(\d+)\s*(d|day|days)", text)
    if m:
        return reference.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=int(m.group(1)))
    m = re.fullmatch(r"(\d+)\s*(w|wk|wks|week|weeks)", text)
    if m:
        return reference.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(weeks=int(m.group(1)))
    m = re.fullmatch(r"(\d+)\s*(mo|mos|month|months)", text)
    if m:
        return reference.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=30 * int(m.group(1)))
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%b %d, %Y", "%B %d, %Y", "%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(text.title(), fmt).replace(tzinfo=timezone.utc)
            if "%Y" not in fmt:
                parsed = parsed.replace(year=reference.year)
                if parsed > reference + timedelta(days=30):
                    parsed = parsed.replace(year=reference.year - 1)
            return parsed
        except ValueError:
            pass
    # ISO timestamps
    try:
        return datetime.fromisoformat(text.replace("z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def extract_states(location: str) -> list[str]:
    loc = location or ""
    low = loc.lower()
    states: set[str] = set()
    if "remote" in low:
        states.add("Remote")
    if re.search(r"\b(united states|usa|u\.s\.)\b", low):
        states.add("US")
    for abbr in STATE_ABBRS:
        if re.search(rf"(?:^|[\s,/(-]){abbr}(?:$|[\s,/)])", loc, flags=re.I):
            states.add(abbr)
    for name, abbr in STATE_NAMES.items():
        if name == "washington" and "DC" in states:
            continue
        if re.search(rf"\b{re.escape(name)}\b", low):
            states.add(abbr)
    return sorted(states)


def classify_profiles(job: dict[str, Any], hints: Iterable[str] = ()) -> list[str]:
    blob = " ".join([
        job.get("title", ""), job.get("company", ""), job.get("section", ""),
        job.get("function_primary", ""), job.get("source_name", ""),
    ]).lower()
    tags = set(hints)
    for profile, keywords in PROFILE_KEYWORDS.items():
        if any(keyword in blob for keyword in keywords):
            tags.add(profile)

    # Data/analytics is intentionally shared between CS-adjacent and business-facing paths.
    if any(x in blob for x in ("data analyst", "business intelligence", "analytics intern", "analytics &", "analytics and")):
        tags.add("tech-business")
    if any(x in blob for x in ("product manager", "product management", "technical program manager")):
        tags.add("tech-business")
    if any(x in blob for x in ("data scientist", "machine learning", "software")):
        tags.add("cs")
    if not tags:
        tags.add("general")
    return sorted(tags)


def parse_term(title: str, section: str = "") -> str | None:
    text = f"{title} {section}".lower()
    for season in ("summer", "spring", "fall", "winter"):
        m = re.search(rf"\b{season}\s+(20\d{{2}})\b", text)
        if m:
            return f"{season.title()} {m.group(1)}"
    m = re.search(r"\b(20\d{2})\b", text)
    return m.group(1) if m else None


def base_job(*, company: str, title: str, location: str, url: str | None, posted_raw: str | None,
             source: dict[str, Any], section: str = "", function_primary: str = "",
             posted_at: datetime | None = None) -> dict[str, Any] | None:
    company = clean_text(company)
    title = clean_text(title)
    location = clean_text(location) or "Location not listed"
    if not title or len(title) < 3 or title.lower() in {"role", "job title", "position"}:
        return None
    if company in {"↳", "", "—", "-"}:
        company = "Company not listed"
    job = {
        "company": company,
        "title": title,
        "location": location,
        "url": canonical_url(url),
        "posted_raw": clean_text(posted_raw),
        "posted_at": iso(posted_at),
        "section": clean_text(section),
        "function_primary": clean_text(function_primary),
        "source_key": source["key"],
        "source_name": source["name"],
        "source_url": source.get("homepage", source.get("url", "")),
        "states": extract_states(location),
        "term": parse_term(title, section),
    }
    job["profiles"] = classify_profiles(job, source.get("profile_hint", []))
    return job


def parse_dreamwork(payload: dict[str, Any], source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    out = []
    for item in payload.get("listings", []):
        posted = parse_relative_date(item.get("postedAt"), reference)
        job = base_job(
            company=item.get("company") or "Company not listed",
            title=item.get("title") or "",
            location=item.get("location") or "Location not listed",
            url=item.get("url"),
            posted_raw = item.get("postedAt") or item.get("firstIndexedAt"),
            source=source,
            section=item.get("functionPrimary") or "",
            function_primary=item.get("functionPrimary") or "",
            posted_at=posted,
        )
        if job:
            salary_min = item.get("salaryMin")
            salary_max = item.get("salaryMax")
            if salary_min is not None or salary_max is not None:
                job["salary_min"] = salary_min
                job["salary_max"] = salary_max
                job["salary_period"] = item.get("salaryPeriod")
            job["remote_type"] = item.get("remoteType")
            out.append(job)
    return out


def split_markdown_row(line: str) -> list[str]:
    line = line.strip().strip("|")
    return [part.replace("\\|", "|").strip() for part in re.split(r"(?<!\\)\|", line)]


def header_index(headers: list[str], *names: str) -> int | None:
    lowered = [norm(x) for x in headers]
    for name in names:
        target = norm(name)
        for i, h in enumerate(lowered):
            if h == target or target in h:
                return i
    return None


def row_to_job(headers: list[str], cells: list[str], source: dict[str, Any], reference: datetime,
               section: str, previous_company: str) -> tuple[dict[str, Any] | None, str]:
    if len(cells) < 2:
        return None, previous_company
    company_i = header_index(headers, "company", "organization", "employer")
    title_i = header_index(headers, "role", "job title", "position", "opportunity", "title")
    location_i = header_index(headers, "location", "locations")
    posted_i = header_index(headers, "posted", "date posted", "age", "added", "date")
    apply_i = header_index(headers, "apply", "application", "link")

    def cell(i: int | None) -> str:
        return cells[i] if i is not None and i < len(cells) else ""

    company = clean_text(cell(company_i)) if company_i is not None else ""
    if company in {"↳", "", "—", "-"}:
        company = previous_company
    elif company:
        previous_company = company

    title_raw = cell(title_i) if title_i is not None else (cells[1] if len(cells) > 1 else "")
    title = clean_text(title_raw)
    location = clean_text(cell(location_i)) if location_i is not None else "Location not listed"
    posted_raw = cell(posted_i)

    if not company or not title:
        return None, previous_company
    if any(x in title.lower() for x in ("closed", "no longer accepting")):
        return None, previous_company

    links: list[str] = []
    if apply_i is not None:
        links.extend(extract_links(cell(apply_i)))
    links.extend(extract_links(title_raw))
    url = choose_apply_url(links)
    posted = parse_relative_date(posted_raw, reference)

    return base_job(
        company=company,
        title=title,
        location=location,
        url=url,
        posted_raw = posted_raw,
        source=source,
        section=section,
        posted_at=posted,
    ), previous_company


def parse_markdown_tables(text: str, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    section = ""
    headers: list[str] | None = None
    previous_company = ""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#"):
            section = clean_text(re.sub(r"^#+\s*", "", line))
        if "|" in line:
            maybe_headers = split_markdown_row(line)
            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
            is_separator = bool(re.match(r"^\s*\|?\s*:?-{3,}", next_line)) and "|" in next_line
            header_blob = " ".join(norm(x) for x in maybe_headers)
            if is_separator and ("company" in header_blob or "organization" in header_blob) and (
                "role" in header_blob or "title" in header_blob or "position" in header_blob or "opportunity" in header_blob
            ):
                headers = maybe_headers
                previous_company = ""
                i += 2
                while i < len(lines) and "|" in lines[i]:
                    row_line = lines[i].strip()
                    if not row_line or re.match(r"^\s*\|?\s*:?-{2}", row_line):
                        i += 1
                        continue
                    cells = split_markdown_row(row_line)
                    job, previous_company = row_to_job(headers, cells, source, reference, section, previous_company)
                    if job:
                        out.append(job)
                    i += 1
                continue
        i += 1
    return out


def parse_html_tables(text: str, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    soup = BeautifulSoup(text, "html.parser")
    out: list[dict[str, Any]] = []
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        header_cells = rows[0].find_all(["th", "td"])
        headers = [clean_text(str(c)) for c in header_cells]
        blob = " ".join(norm(x) for x in headers)
        if not ("company" in blob or "organization" in blob) or not any(x in blob for x in ("role", "title", "position", "opportunity")):
            continue
        previous_company = ""
        heading = table.find_previous(["h1", "h2", "h3", "h4"])
        section = clean_text(str(heading)) if heading else ""
        for row in rows[1:]:
            tds = row.find_all("td")
            if not tds:
                continue
            cells = [str(td) for td in tds]
            job, previous_company = row_to_job(headers, cells, source, reference, section, previous_company)
            if job:
                out.append(job)
    return out


def parse_markdown(text: str, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    jobs = parse_markdown_tables(text, source, reference)
    jobs.extend(parse_html_tables(text, source, reference))
    return jobs


def fetch_source(s: requests.Session, source: dict[str, Any], reference: datetime) -> list[dict[str, Any]]:
    text = fetch_text(s, source["url"])
    if source["kind"] == "dreamwork_json":
        return parse_dreamwork(json.loads(text), source, reference)
    if source["kind"] == "markdown":
        return parse_markdown(text, source, reference)
    raise ValueError(f"Unsupported source kind: {source['kind']}")


def fetch_usajobs(s: requests.Session, reference: datetime) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    api_key = os.getenv("USAJOBS_API_KEY", "").strip()
    email = os.getenv("USAJOBS_EMAIL", "").strip()
    source = {
        "key": "usajobs",
        "name": "USAJOBS",
        "homepage": "https://www.usajobs.gov/Search/Results?k=intern",
    }
    if not api_key or not email:
        return [], {"ok": True, "configured": False, "count": 0, "note": "API credentials not configured"}

    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": email,
        "Authorization-Key": api_key,
    }
    page = 1
    out: list[dict[str, Any]] = []
    while page <= 10:
        params = {
            "HiringPath": "student",
            "DatePosted": 60,
            "ResultsPerPage": 500,
            "Page": page,
            "Fields": "Full",
        }
        response = s.get("https://data.usajobs.gov/api/Search", params=params, headers=headers, timeout=TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        result = payload.get("SearchResult", {})
        for wrapper in result.get("SearchResultItems", []):
            item = wrapper.get("MatchedObjectDescriptor", {})
            details = item.get("UserArea", {}).get("Details", {})
            locations = item.get("PositionLocation") or []
            if isinstance(locations, dict):
                locations = [locations]
            location = " / ".join(
                x.get("LocationName") or ", ".join(filter(None, [x.get("CityName"), x.get("CountrySubDivisionCode")]))
                for x in locations if isinstance(x, dict)
            ) or "United States"
            apply_uri = item.get("ApplyURI") or []
            if isinstance(apply_uri, str):
                apply_uri = [apply_uri]
            url = choose_apply_url(apply_uri) or item.get("PositionURI")
            title = item.get("PositionTitle") or ""
            summary = clean_text(details.get("JobSummary") or "")
            searchable = f"{title} {summary}".lower()
            # Student hiring path contains some non-intern jobs. Keep explicit student/intern opportunities.
            if not any(k in searchable for k in ("intern", "student trainee", "pathways", "student program")):
                continue
            posted = parse_relative_date(item.get("PublicationStartDate") or item.get("PositionStartDate"), reference)
            job = base_job(
                company=item.get("OrganizationName") or details.get("SubAgencyName") or "U.S. Federal Government",
                title=title,
                location=location,
                url=url,
                posted_raw=item.get("PublicationStartDate"),
                source=source,
                section="Federal student opportunity",
                posted_at=posted,
            )
            if job:
                job["federal"] = True
                out.append(job)
        pages = int(result.get("UserArea", {}).get("NumberOfPages") or 1)
        if page >= pages:
            break
        page += 1
    return out, {"ok": True, "configured": True, "count": len(out)}


def merge_job(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    target["source_keys"] = sorted(set(target.get("source_keys", [])) | {incoming["source_key"]})
    target["source_names"] = sorted(set(target.get("source_names", [])) | {incoming["source_name"]})
    target["source_urls"] = sorted(set(target.get("source_urls", [])) | {incoming["source_url"]})
    target["profiles"] = sorted(set(target.get("profiles", [])) | set(incoming.get("profiles", [])))
    target["states"] = sorted(set(target.get("states", [])) | set(incoming.get("states", [])))
    if not target.get("url") and incoming.get("url"):
        target["url"] = incoming["url"]
    elif incoming.get("url"):
        old_host = urlparse(target.get("url", "")).netloc.lower()
        new_host = urlparse(incoming["url"]).netloc.lower()
        if old_host in AGGREGATOR_HOSTS and new_host not in AGGREGATOR_HOSTS:
            target["url"] = incoming["url"]
    # Prefer the newest explicit posting timestamp.
    if incoming.get("posted_at") and (not target.get("posted_at") or incoming["posted_at"] > target["posted_at"]):
        target["posted_at"] = incoming["posted_at"]
        target["posted_raw"] = incoming.get("posted_raw", "")
    for key in ("salary_min", "salary_max", "salary_period", "remote_type", "term"):
        if not target.get(key) and incoming.get(key) is not None:
            target[key] = incoming.get(key)


def dedupe(jobs: list[dict[str, Any]], old_jobs: dict[str, dict[str, Any]], reference: datetime) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    by_url: dict[str, int] = {}
    by_sig: dict[str, int] = {}

    for job in jobs:
        url_key = canonical_url(job.get("url"))
        sig = "|".join((norm(job.get("company")), norm(job.get("title")), norm(job.get("location"))))
        idx = by_url.get(url_key) if url_key else None
        if idx is None:
            idx = by_sig.get(sig)
        if idx is None:
            row = dict(job)
            row["source_keys"] = [job["source_key"]]
            row["source_names"] = [job["source_name"]]
            row["source_urls"] = [job["source_url"]]
            for k in ("source_key", "source_name", "source_url", "section", "function_primary"):
                row.pop(k, None)
            merged.append(row)
            idx = len(merged) - 1
            if url_key:
                by_url[url_key] = idx
            by_sig[sig] = idx
        else:
            merge_job(merged[idx], job)
            if url_key:
                by_url[url_key] = idx

    for job in merged:
        stable_basis = "|".join((norm(job.get("company")), norm(job.get("title")), norm(job.get("location"))))
        job_id = hashlib.sha1(stable_basis.encode("utf-8")).hexdigest()[:16]
        job["id"] = job_id
        prior = old_jobs.get(job_id)
        job["first_seen"] = prior.get("first_seen") if prior else iso(reference)
        job["last_seen"] = iso(reference)

    def sort_key(job: dict[str, Any]) -> tuple[str, str]:
        return (job.get("posted_at") or job.get("first_seen") or "", job.get("id") or "")

    merged.sort(key=sort_key, reverse=True)
    return merged


def content_hash(jobs: list[dict[str, Any]], sources: dict[str, Any]) -> str:
    # Ignore volatile build timestamps so an unchanged feed does not create an hourly commit.
    source_shape = {
        k: {"ok": v.get("ok"), "configured": v.get("configured", True), "count": v.get("count", 0)}
        for k, v in sources.items()
    }
    stable_jobs = []
    for job in jobs:
        copy = dict(job)
        copy.pop("last_seen", None)
        stable_jobs.append(copy)
    raw = json.dumps({"jobs": stable_jobs, "sources": source_shape}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> int:
    reference = now_utc()
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    old_doc: dict[str, Any] = {}
    if OUTPUT_PATH.exists():
        try:
            old_doc = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            old_doc = {}
    old_jobs_list = old_doc.get("jobs", []) if isinstance(old_doc, dict) else []
    old_jobs_by_id = {j.get("id"): j for j in old_jobs_list if isinstance(j, dict) and j.get("id")}

    s = session()
    all_jobs: list[dict[str, Any]] = []
    health: dict[str, Any] = {}
    failed_keys: set[str] = set()

    for source in sources:
        try:
            jobs = fetch_source(s, source, reference)
            all_jobs.extend(jobs)
            health[source["key"]] = {"ok": True, "configured": True, "count": len(jobs), "name": source["name"]}
            print(f"{source['name']}: {len(jobs)}")
        except Exception as exc:
            failed_keys.add(source["key"])
            health[source["key"]] = {
                "ok": False,
                "configured": True,
                "count": 0,
                "name": source["name"],
                "error": f"{type(exc).__name__}: {exc}",
            }
            print(f"{source['name']}: FAILED: {exc}", file=sys.stderr)

    try:
        federal_jobs, federal_health = fetch_usajobs(s, reference)
        all_jobs.extend(federal_jobs)
        federal_health["name"] = "USAJOBS"
        health["usajobs"] = federal_health
        print(f"USAJOBS: {len(federal_jobs)}" + ("" if federal_health.get("configured") else " (not configured)"))
    except Exception as exc:
        failed_keys.add("usajobs")
        health["usajobs"] = {"ok": False, "configured": True, "count": 0, "name": "USAJOBS", "error": f"{type(exc).__name__}: {exc}"}
        print(f"USAJOBS: FAILED: {exc}", file=sys.stderr)

    # If a source is temporarily down, carry its previously generated listings forward.
    if failed_keys:
        for old in old_jobs_list:
            if failed_keys.intersection(old.get("source_keys", [])):
                carry = dict(old)
                source_keys = carry.get("source_keys", [])
                # Rehydrate a minimal pre-dedupe shape for the first failed source attached to the listing.
                key = next((k for k in source_keys if k in failed_keys), None)
                if not key:
                    continue
                carry["source_key"] = key
                carry["source_name"] = next(iter(carry.get("source_names", [])), key)
                carry["source_url"] = next(iter(carry.get("source_urls", [])), "")
                all_jobs.append(carry)

    final_jobs = dedupe(all_jobs, old_jobs_by_id, reference)
    new_hash = content_hash(final_jobs, health)
    if old_doc.get("content_hash") == new_hash:
        print("No feed changes; leaving listings.json untouched.")
        return 0

    out = {
        "generated_at": iso(reference),
        "content_hash": new_hash,
        "jobs": final_jobs,
        "sources": health,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(final_jobs)} deduplicated listings to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
