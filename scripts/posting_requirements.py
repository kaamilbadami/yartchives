#!/usr/bin/env python3
"""Provider-neutral normalization and deterministic requirement extraction.

ATS adapters should retrieve authoritative posting content and pass it through
this module. The extractor only records facts stated by the employer, preserves
normalized evidence text, and never assigns semantic confidence scores.
"""

from __future__ import annotations

import html
import re
from typing import Any, Iterable

from bs4 import BeautifulSoup

# This vocabulary only annotates exact technology mentions in an already
# identified qualification statement. It never creates a requirement by itself,
# and the original statement is always retained beside the annotation.
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
    r"preferred but not required|nice to have|desired qualifications?|"
    r"what sets you apart|bonus points?)\b",
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


def clean_line(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip(" \t\r\n\u200b")


def _decode_description(raw_html: str | None) -> str:
    # Some providers double-encode newline entities in posting descriptions.
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
    if re.search(
        r"\bnot required\b|\bisn['’]?t required\b|"
        r"\b(?:do|does|did|will) not require\b|"
        r"\bno\b[^,.;:]{0,60}\brequired\b",
        lower,
    ):
        return "not_required"
    if re.search(
        r"\b(?:must|requires?|required to|required qualification|must be authorized|"
        r"does not sponsor|will not sponsor|unable to sponsor)\b",
        lower,
    ):
        return "required"
    if re.search(r"\b(?:preferred|ideally|desired|a plus|nice to have|suggested)\b", lower):
        return "preferred"
    if re.search(r"\b(?:minimum of|at least)\b", lower):
        return "preferred" if section_level == "preferred" else "required"
    return section_level


def _sentences(lines: Iterable[str]) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    section_level: str | None = None
    for line in lines:
        is_heading, new_level = _heading_level(line)
        if is_heading:
            section_level = new_level
            continue
        # Do not split common initialisms such as "U.S." into fragments.
        pieces = re.split(r"(?<![A-Z]\.)(?<=[.!?])\s+(?=[A-Z])", line)
        for piece in pieces:
            statement = clean_line(piece)
            if statement:
                out.append((statement, _explicit_level(statement, section_level)))
    return out


def empty_requirement_field() -> dict[str, Any]:
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

    result = {key: empty_requirement_field() for key in REQUIREMENT_FIELDS}
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
