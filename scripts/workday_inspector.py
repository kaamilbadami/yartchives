#!/usr/bin/env python3
"""Retrieve and conservatively normalize one public Workday job posting.

Workday career sites expose job details through a public CXS JSON endpoint.  This
module derives that endpoint from an authoritative ``myworkdayjobs.com`` job URL,
prefers its structured fields, and keeps requirement wording as evidence instead
of guessing facts the employer did not state.

The module deliberately does not score jobs.  It creates an inspection boundary
that Apply Next can consume in a later, separately reviewed scoring change.
"""

from __future__ import annotations

import argparse
import copy
import html
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import quote, unquote, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

TIMEOUT = 25
INTERFACE = "workday_cxs_json"
WORKDAY_HOST = re.compile(r"^[a-z0-9-]+\.wd\d+\.myworkdayjobs\.com$", re.I)
LOCALE = re.compile(r"^[a-z]{2}(?:-[A-Z]{2})?$")

# This vocabulary only annotates exact technology mentions in an already
# identified qualification statement.  It never creates a requirement by
# itself, and the original statement is always retained beside the annotation.
TECHNOLOGIES: tuple[tuple[str, str], ...] = (
    ("C++", r"(?<![A-Za-z0-9])C\+\+(?![A-Za-z0-9+])"),
    ("C#", r"(?<![A-Za-z0-9])C#(?![A-Za-z0-9#])"),
    ("C", r"(?<![A-Za-z0-9+#])C(?![A-Za-z0-9+#])"),
    ("Python", r"\bPython\b"),
    ("JavaScript", r"\bJavaScript\b"),
    ("TypeScript", r"\bTypeScript\b"),
    ("Java", r"\bJava\b"),
    ("SQL", r"\bSQL\b"),
    ("R", r"(?<![A-Za-z0-9])R(?![A-Za-z0-9])"),
    ("Git", r"\bGit\b"),
    ("Linux", r"\bLinux\b"),
    ("Microsoft Office", r"\b(?:Microsoft|MS) Office\b"),
    ("Excel", r"\bExcel\b"),
    ("SolidWorks", r"\bSolidWorks\b"),
    ("CAD", r"\bCAD\b"),
    ("MATLAB", r"\bMATLAB\b"),
    ("AWS", r"\bAWS\b|\bAmazon Web Services\b"),
    ("Azure", r"\bAzure\b"),
    ("Docker", r"\bDocker\b"),
    ("Kubernetes", r"\bKubernetes\b"),
)

REQUIREMENT_FIELDS = (
    "education",
    "graduation",
    "student_status",
    "major_fields",
    "citizenship",
    "work_authorization",
    "skills",
    "other_eligibility",
)

REQUIRED_HEADING = re.compile(
    r"\b(?:qualifications? (?:you )?must have|required qualifications?|"
    r"minimum qualifications?|basic qualifications?|what (?:is )?a must have|"
    r"requirements?)\b",
    re.I,
)
PREFERRED_HEADING = re.compile(
    r"\b(?:preferred qualifications?|qualifications? we prefer|ideal candidate|"
    r"nice to have|desired qualifications?|what sets you apart|bonus points?)\b",
    re.I,
)
UNSPECIFIED_HEADING = re.compile(
    r"\b(?:qualifications?|candidate profile|this job might be for you if|"
    r"what you bring(?: to the table)?|skills and abilities|education)\b",
    re.I,
)
RESET_HEADING = re.compile(
    r"\b(?:what you will do|responsibilities|duties|about (?:us|the role)|"
    r"what we offer|benefits|compensation|salary|employment practices|"
    r"location information|who are we|job category|target openings|"
    r"what is the opportunity|what you will learn|learn more)\b",
    re.I,
)


class UnsupportedWorkdayUrl(ValueError):
    """Raised when a URL cannot identify a public Workday CXS job endpoint."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_line(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\r\n\u200b")


def derive_cxs_endpoint(job_url: str) -> dict[str, str]:
    """Return tenant/site/job metadata derived from a public Workday URL."""

    parsed = urlparse(job_url or "")
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https" or not WORKDAY_HOST.fullmatch(host):
        raise UnsupportedWorkdayUrl("expected an HTTPS *.wdN.myworkdayjobs.com job URL")

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if parts and parts[0].lower() == "wday":
        # Accept a CXS URL as input, but still validate its tenant/site/job shape.
        if len(parts) < 7 or parts[1].lower() != "cxs" or parts[4].lower() != "job":
            raise UnsupportedWorkdayUrl("Workday CXS URL does not contain a job path")
        tenant, site = parts[2], parts[3]
        job_parts = parts[4:]
    else:
        if parts and LOCALE.fullmatch(parts[0]):
            parts = parts[1:]
        try:
            job_index = next(i for i, part in enumerate(parts) if part.lower() == "job")
        except StopIteration as exc:
            raise UnsupportedWorkdayUrl("Workday URL does not contain a /job/ path") from exc
        if job_index != 1 or len(parts) < 4:
            raise UnsupportedWorkdayUrl("Workday job URL must identify one career site and job")
        tenant = host.split(".", 1)[0]
        site = parts[0]
        job_parts = parts[job_index:]

    encoded = [quote(part, safe="-._~") for part in (tenant, site, *job_parts)]
    endpoint_path = "/wday/cxs/" + "/".join(encoded)
    endpoint = urlunparse(("https", host, endpoint_path, "", "", ""))
    canonical_job_path = "/" + "/".join(quote(part, safe="-._~") for part in (site, *job_parts))
    canonical_job_url = urlunparse(("https", host, canonical_job_path, "", "", ""))
    return {
        "tenant": tenant,
        "site": site,
        "job_path": "/" + "/".join(job_parts),
        "endpoint_url": endpoint,
        "canonical_job_url": canonical_job_url,
    }


def _decode_description(raw_html: str | None) -> str:
    # Some tenants double-encode Workday's newline entity as &amp;#xa;.
    decoded = html.unescape(html.unescape(raw_html or ""))
    decoded = decoded.replace("&#xa;", "\n").replace("\u00a0", " ")
    return decoded


def normalize_description(raw_html: str | None) -> tuple[str, list[str]]:
    """Return plain posting text plus stable block-level lines for extraction."""

    soup = BeautifulSoup(_decode_description(raw_html), "html.parser")
    for br in soup.find_all("br"):
        br.replace_with("\n")
    lines = [clean_line(line) for line in soup.get_text("\n").splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines), lines


def _heading_level(line: str) -> tuple[bool, str | None]:
    candidate = line.rstrip(":").strip()
    # Headings are short labels, not prose that happens to mention qualifications.
    if not candidate or len(candidate) > 100 or len(candidate.split()) > 14:
        return False, None
    if PREFERRED_HEADING.search(candidate):
        return True, "preferred"
    if REQUIRED_HEADING.search(candidate):
        return True, "required"
    if UNSPECIFIED_HEADING.search(candidate):
        return True, "unspecified"
    if RESET_HEADING.search(candidate):
        return True, None
    return False, None


def _explicit_level(statement: str, section_level: str | None) -> str | None:
    lower = statement.lower()
    # Polarity overrides section headings. For example, a statement under
    # "Required Qualifications" that says citizenship is not required must not
    # become positive required evidence merely because of its section.
    if re.search(
        r"\bnot required\b|\bisn['’]?t required\b|"
        r"\b(?:do|does|did|will) not require\b|"
        r"\bno\b[^,.;:]{0,60}\brequired\b",
        lower,
    ):
        return "not_required"
    if re.search(
        r"\b(?:must|requires?|required to|required qualification|minimum of|at least|"
        r"must be authorized|does not sponsor|will not sponsor|unable to sponsor)\b",
        lower,
    ):
        return "required"
    if re.search(r"\b(?:preferred|ideally|desired|a plus|nice to have|suggested)\b", lower):
        return "preferred"
    return section_level


def _sentences(lines: Iterable[str]) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    section_level: str | None = None
    for line in lines:
        is_heading, new_level = _heading_level(line)
        if is_heading:
            section_level = new_level
            continue
        # Split prose so one explicit authorization sentence does not pull in an
        # entire employer-description paragraph. List items normally stay whole.
        # Do not split common initialisms such as "U.S." into fragments; a
        # fragmented status statement could otherwise be missed or mislabelled.
        pieces = re.split(r"(?<![A-Z]\.)(?<=[.!?])\s+(?=[A-Z])", line)
        for piece in pieces:
            statement = clean_line(piece)
            if statement:
                out.append((statement, _explicit_level(statement, section_level)))
    return out


def _empty_field() -> dict[str, Any]:
    return {
        "classification": "unknown",
        "required": [],
        "preferred": [],
        "unspecified": [],
        "not_required": [],
    }


def _finalize_field(field: dict[str, Any]) -> None:
    present = [
        level
        for level in ("required", "preferred", "unspecified", "not_required")
        if field[level]
    ]
    if not present:
        field["classification"] = "unknown"
    elif len(present) == 1:
        field["classification"] = present[0]
    else:
        field["classification"] = "mixed"


def _add(field: dict[str, Any], level: str | None, statement: str, **extra: Any) -> None:
    bucket = level if level in {"required", "preferred", "not_required"} else "unspecified"
    fact: dict[str, Any] = {
        "statement": statement,
        "requirement_state": bucket,
        "negated": bucket == "not_required",
    }
    fact.update({key: value for key, value in extra.items() if value})
    if fact not in field[bucket]:
        field[bucket].append(fact)


def _technology_mentions(statement: str) -> list[str]:
    return [name for name, pattern in TECHNOLOGIES if re.search(pattern, statement, flags=re.I)]


def extract_requirements(lines: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Extract only stated facts, retaining their exact normalized evidence."""

    result = {key: _empty_field() for key in REQUIREMENT_FIELDS}
    for statement, level in _sentences(lines):
        lower = statement.lower()
        qualification_context = level is not None
        matched = False

        if re.search(
            r"\b(?:degree|bachelor(?:'s|s)?|master(?:'s|s)?|ph\.?d\.?|doctorate|"
            r"associate(?:'s|s)?|B\.?S\.?|B\.?A\.?|M\.?S\.?)\b",
            statement,
            flags=re.I,
        ):
            _add(result["education"], level, statement)
            matched = True

        if re.search(r"\b(?:graduat(?:e|ing|ion)|class of)\b", lower) and re.search(
            r"\b(?:20\d{2}|spring|summer|fall|winter|between|before|after|by)\b", lower
        ):
            _add(result["graduation"], level, statement)
            matched = True

        if re.search(
            r"\b(?:current(?:ly)? (?:a )?student|actively enrolled|enrolled (?:in|through|at)|"
            r"pursuing (?:a |an )?(?:degree|bachelor|master|BS|BA|MS)|returning to school)\b",
            statement,
            flags=re.I,
        ):
            _add(result["student_status"], level, statement)
            matched = True

        if re.search(
            r"\b(?:major(?:s|ing)?|degree in|discipline|field of study|academic field|related field)\b",
            lower,
        ):
            _add(result["major_fields"], level, statement)
            matched = True

        if re.search(
            r"\b(?:u\.?s\.?|united states) (?:citizen|citizenship|person|national|permanent resident)\b|"
            r"\b(?:lawful permanent resident|refugee or asylee|asylee status)\b",
            lower,
        ) and not re.search(r"without regard to .*\b(?:citizenship|national origin)\b", lower):
            _add(result["citizenship"], level, statement)
            matched = True

        if re.search(
            r"\b(?:authoriz(?:ed|ation) to work|work authoriz(?:ation|ed)|sponsor(?:ship|ed|ing)?|"
            r"h-?1b|stem opt|opt\b|i-983|work visa|employment eligibility)\b",
            lower,
        ):
            _add(result["work_authorization"], level, statement)
            matched = True

        technologies = _technology_mentions(statement)
        skill_language = re.search(
            r"\b(?:experience|knowledge|proficien(?:cy|t)|skills?|ability to|familiar(?:ity)?|"
            r"expertise|competency|using|communication|problem[- ]solving)\b",
            lower,
        )
        if qualification_context and (technologies or skill_language):
            _add(result["skills"], level, statement, technologies=technologies)
            matched = True

        hard_eligibility = re.search(
            r"\b(?:gpa|credit hours?|credits? by|background check|drug test|driver'?s license|"
            r"security clearance|at least \d+ years? old|minimum age|able to work|available to work|"
            r"work (?:part|full)[- ]time|travel up to|onsite|on-site)\b",
            lower,
        )
        if hard_eligibility or (qualification_context and not matched):
            _add(result["other_eligibility"], level, statement)

    for field in result.values():
        _finalize_field(field)
    return result


def extract_locations(info: dict[str, Any]) -> dict[str, Any]:
    values: list[str] = []

    def append(value: Any) -> None:
        if isinstance(value, dict):
            value = value.get("descriptor") or value.get("name")
        if not isinstance(value, str):
            return
        cleaned = clean_line(value)
        if cleaned and cleaned.casefold() not in {item.casefold() for item in values}:
            values.append(cleaned)

    append(info.get("location"))
    append(info.get("jobRequisitionLocation"))
    additional = info.get("additionalLocations") or info.get("locations") or []
    if isinstance(additional, (str, dict)):
        additional = [additional]
    if isinstance(additional, list):
        for location in additional:
            append(location)
    return {
        "status": "authoritative" if values else "unknown",
        "values": values,
    }


def normalize_payload(payload: Any) -> dict[str, Any]:
    """Normalize one Workday CXS response or raise on a changed response shape."""

    if not isinstance(payload, dict) or not isinstance(payload.get("jobPostingInfo"), dict):
        raise ValueError("Workday response did not contain jobPostingInfo")
    info = payload["jobPostingInfo"]
    if not any(info.get(key) for key in ("title", "jobDescription", "jobReqId", "location")):
        raise ValueError("Workday jobPostingInfo did not contain recognizable job fields")

    description, lines = normalize_description(info.get("jobDescription"))
    requisition_id = clean_line(info.get("jobReqId")) or None
    posting_id = clean_line(info.get("jobPostingId")) or None
    can_apply = info.get("canApply") if isinstance(info.get("canApply"), bool) else None
    posted = info.get("posted") if isinstance(info.get("posted"), bool) else None
    if can_apply is False or posted is False:
        application_status = "unavailable"
    elif can_apply is True and posted is True:
        application_status = "available"
    else:
        application_status = "unknown"
    return {
        "posting": {
            "title": clean_line(info.get("title")) or None,
            "description": description or None,
            "requisition_id": requisition_id,
            "posting_id": posting_id,
            "locations": extract_locations(info),
            "can_apply": can_apply,
            "posted": posted,
            "application_status": application_status,
        },
        "requirements": extract_requirements(lines),
    }


def _base_result(job_url: str, inspected_at: datetime) -> dict[str, Any]:
    return {
        "provider": "workday",
        "status": "failed",
        "retrieval_confidence": "none",
        "error": None,
        "posting": None,
        "requirements": {key: _empty_field() for key in REQUIREMENT_FIELDS},
        "provenance": {
            "provider": "workday",
            "interface": INTERFACE,
            "source_url": job_url,
            "endpoint_url": None,
            "inspected_at": iso(inspected_at),
        },
    }


def inspect_workday_url(
    job_url: str,
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    """Inspect a URL without raising; failures remain explicit structured data."""

    inspected_at = now()
    result = _base_result(job_url, inspected_at)
    try:
        endpoint = derive_cxs_endpoint(job_url)
    except UnsupportedWorkdayUrl as exc:
        result["status"] = "unsupported_url"
        result["error"] = str(exc)
        return result

    result["provenance"].update(
        {
            "endpoint_url": endpoint["endpoint_url"],
            "tenant": endpoint["tenant"],
            "site": endpoint["site"],
            "canonical_job_url": endpoint["canonical_job_url"],
        }
    )
    client = session or requests.Session()
    try:
        response = client.get(
            endpoint["endpoint_url"],
            headers={"Accept": "application/json", "User-Agent": "Yartchives/1.0 (+public job inspection)"},
            timeout=timeout,
        )
        if response.status_code in {404, 410}:
            result["status"] = "unavailable"
            result["error"] = f"Workday returned HTTP {response.status_code}"
            return result
        response.raise_for_status()
        normalized = normalize_payload(response.json())
    except requests.RequestException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    except (ValueError, json.JSONDecodeError) as exc:
        result["status"] = "changed_response"
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result.update(normalized)
    result["status"] = "inspected"
    # This describes CXS retrieval completeness only. It is deliberately not a
    # semantic confidence score for the deterministic requirement extraction.
    result["retrieval_confidence"] = (
        "high" if normalized["posting"].get("description") else "medium"
    )
    result["error"] = None
    return result


def inspect_listing(
    listing: dict[str, Any],
    *,
    session: requests.Session | None = None,
    timeout: int = TIMEOUT,
    now: Callable[[], datetime] = utc_now,
) -> dict[str, Any]:
    """Return a copied listing with inspection attached, even when it fails."""

    preserved = copy.deepcopy(listing)
    preserved["inspection"] = inspect_workday_url(
        str(listing.get("url") or ""), session=session, timeout=timeout, now=now
    )
    return preserved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="Authoritative public Workday job URL")
    args = parser.parse_args()
    result = inspect_workday_url(args.url)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "inspected" else 1


if __name__ == "__main__":
    raise SystemExit(main())
