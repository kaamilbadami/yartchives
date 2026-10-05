#!/usr/bin/env python3
"""Validate sanitized trust-benchmark persona fixtures."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

REQUIRED_FIELDS = {
    "id",
    "source_kind",
    "student_stage",
    "graduation_options",
    "primary_area",
    "role_intent",
    "evidence",
    "negative_preferences",
    "location",
}
FORBIDDEN_KEYS = {
    "name",
    "full_name",
    "email",
    "phone",
    "contact",
    "contact_info",
    "raw_resume",
    "resume_text",
    "raw_profile",
    "linkedin",
    "linkedin_url",
    "citizenship",
    "work_authorization",
}
ALLOWED_SOURCE_KINDS = {"real_derived", "reference", "synthetic"}
ALLOWED_PRIMARY_AREAS = {"computer_science", "engineering", "business", "finance"}
GRADUATION_RE = re.compile(r"^May 20\d{2}$")
ID_RE = re.compile(r"^[A-Z]{2,4}$")
EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?:\+?1[ .-]?)?(?:\(?\d{3}\)?[ .-]?)\d{3}[ .-]?\d{4}")


def _walk(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            yield path, str(key), item
            yield from _walk(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")


def validate_document(document: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    personas = document.get("personas")
    if document.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if document.get("target_term") != "Summer 2027":
        errors.append("target_term must be Summer 2027 for trust-benchmark-v1")
    if not isinstance(personas, list):
        return errors + ["personas must be a list"]

    ids: list[str] = []
    area_counts: Counter[str] = Counter()
    real_derived = 0

    for index, persona in enumerate(personas):
        prefix = f"personas[{index}]"
        if not isinstance(persona, dict):
            errors.append(f"{prefix} must be an object")
            continue

        missing = sorted(REQUIRED_FIELDS - set(persona))
        if missing:
            errors.append(f"{prefix} missing required fields: {', '.join(missing)}")

        persona_id = str(persona.get("id") or "")
        if not ID_RE.fullmatch(persona_id):
            errors.append(f"{prefix}.id must be 2-4 uppercase letters")
        ids.append(persona_id)

        source_kind = persona.get("source_kind")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            errors.append(f"{prefix}.source_kind is unsupported")
        if source_kind == "real_derived":
            real_derived += 1

        primary_area = persona.get("primary_area")
        if primary_area not in ALLOWED_PRIMARY_AREAS:
            errors.append(f"{prefix}.primary_area is unsupported")
        else:
            area_counts[primary_area] += 1

        graduations = persona.get("graduation_options")
        if not isinstance(graduations, list) or not graduations:
            errors.append(f"{prefix}.graduation_options must be a non-empty list")
        else:
            for value in graduations:
                if not isinstance(value, str) or not GRADUATION_RE.fullmatch(value):
                    errors.append(f"{prefix}.graduation_options contains invalid value: {value!r}")

        for key in ("role_intent", "evidence", "negative_preferences"):
            value = persona.get(key)
            if not isinstance(value, list):
                errors.append(f"{prefix}.{key} must be a list")

        location = persona.get("location")
        if not isinstance(location, dict):
            errors.append(f"{prefix}.location must be an object")
        else:
            for key in ("home_region", "preference_mode", "preferred_regions", "relocation_allowed"):
                if key not in location:
                    errors.append(f"{prefix}.location missing {key}")
            if location.get("relocation_allowed") is not True:
                errors.append(f"{prefix}.location.relocation_allowed must be true for this reviewed cohort")

        for path, key, value in _walk(persona, prefix):
            if key.casefold() in FORBIDDEN_KEYS:
                errors.append(f"{path}.{key} is forbidden in sanitized fixtures")
            if isinstance(value, str):
                if EMAIL_RE.search(value):
                    errors.append(f"{path}.{key} contains an email-like value")
                if PHONE_RE.search(value):
                    errors.append(f"{path}.{key} contains a phone-like value")

    duplicates = sorted(value for value, count in Counter(ids).items() if value and count > 1)
    if duplicates:
        errors.append(f"duplicate persona ids: {', '.join(duplicates)}")

    if real_derived < 8:
        errors.append(f"need at least 8 real-derived personas; found {real_derived}")

    for required_area in ("computer_science", "engineering", "finance"):
        if area_counts[required_area] < 1:
            errors.append(f"benchmark coverage missing primary area: {required_area}")

    bm = next((row for row in personas if isinstance(row, dict) and row.get("id") == "BM"), None)
    if bm and bm.get("graduation_options") != ["May 2029"]:
        errors.append("BM graduation_options must remain ['May 2029']")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        nargs="?",
        default="audit/personas/trust-benchmark-personas.json",
    )
    args = parser.parse_args()
    document = json.loads(Path(args.path).read_text(encoding="utf-8"))
    errors = validate_document(document)
    if errors:
        print("Trust benchmark persona validation: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Trust benchmark persona validation: PASS ({len(document['personas'])} personas)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
