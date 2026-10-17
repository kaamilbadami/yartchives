"""Generic ATS-family compensation normalization and text parsing utilities.

Supports min/max, currency, period (hour, week, month, year, stipend),
raw text, provenance, and conservative guardrails.
"""

from typing import Any, Optional, Dict
import re

VALID_PERIODS = {"hour", "week", "month", "year", "stipend"}

UNIT_TO_PERIOD = {
    "hr": "hour",
    "hour": "hour",
    "h": "hour",
    "hourly": "hour",
    "per hour": "hour",
    "wk": "week",
    "week": "week",
    "weekly": "week",
    "per week": "week",
    "mo": "month",
    "month": "month",
    "monthly": "month",
    "per month": "month",
    "yr": "year",
    "year": "year",
    "yearly": "year",
    "annual": "year",
    "annually": "year",
    "per year": "year",
    "stipend": "stipend",
    "fixed stipend": "stipend",
}

PERIOD_MAP = {
    "hour": "hour",
    "hourly": "hour",
    "hr": "hour",
    "per hour": "hour",
    "h": "hour",
    "week": "week",
    "weekly": "week",
    "wk": "week",
    "per week": "week",
    "month": "month",
    "monthly": "month",
    "mo": "month",
    "per month": "month",
    "year": "year",
    "yearly": "year",
    "annual": "year",
    "annually": "year",
    "yr": "year",
    "per year": "year",
    "stipend": "stipend",
    "fixed": "stipend",
    "total": "stipend",
}

CURRENCY_MAP = {
    "$": "USD",
    "USD": "USD",
    "US$": "USD",
    "CAD": "CAD",
    "CA$": "CAD",
    "EUR": "EUR",
    "€": "EUR",
    "GBP": "GBP",
    "£": "GBP",
}

def parse_number(val_str: Optional[str]) -> Optional[float]:
    if not val_str:
        return None
    val_str = val_str.strip().lower()
    mult = 1.0
    if val_str.endswith("k"):
        mult = 1000.0
        val_str = val_str[:-1].strip()
    val_str = val_str.replace(",", "")
    try:
        val = float(val_str)
        return val * mult
    except ValueError:
        return None


def _resolve_currency(raw_curr: Optional[str]) -> str:
    if not raw_curr:
        return "USD"
    curr_str = raw_curr.strip().upper()
    return CURRENCY_MAP.get(curr_str, CURRENCY_MAP.get(raw_curr.strip(), "USD"))


# Unified pattern for pay parsing
_C = r"(?:USD|CAD|EUR|GBP|US\$|CA\$|\$|€|£)"
_N = r"(?:\d+(?:\.\d+)?k|\d{1,3}(?:,\d{3})*(?:\.\d+)?|\d+(?:\.\d+)?)"
_SEP = r"(?:\s*(?:-|–|—|to)\s*)"
_UNITS = r"(?:per\s+(?:hour|week|month|year)|hourly|weekly|monthly|annually|yearly|\bhr\b|\bhour\b|\bwk\b|\bweek\b|\bmo\b|\bmonth\b|\byr\b|\byear\b|\bannual\b|fixed\s+stipend|stipend)"

_PAY_PATTERN = re.compile(
    r"(?P<currency>" + _C + r")?\s*(?P<min>" + _N + r")"
    r"(?:" + _SEP + r"(?P<currency2>" + _C + r")?\s*(?P<max>" + _N + r"))?"
    r"\s*(?:/|per\s+)?\s*(?P<unit>" + _UNITS + r")",
    re.IGNORECASE,
)

_STIPEND_PREFIX_PATTERN = re.compile(
    r"stipend\s+(?:of\s+)?(?P<currency>" + _C + r")?\s*(?P<min>" + _N + r")",
    re.IGNORECASE,
)


def parse_pay_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Deterministically parse pay ranges or amounts from raw text."""
    if not text or not isinstance(text, str):
        return None

    cleaned = text.strip()
    if not cleaned:
        return None

    m = _PAY_PATTERN.search(cleaned)
    if m:
        gd = m.groupdict()
        min_val = parse_number(gd.get("min"))
        max_val = parse_number(gd.get("max")) if gd.get("max") else min_val
        if min_val is None:
            return None

        unit_str = (gd.get("unit") or "").lower().strip()
        period = UNIT_TO_PERIOD.get(unit_str)
        if not period:
            for u_k, u_v in UNIT_TO_PERIOD.items():
                if u_k in unit_str:
                    period = u_v
                    break

        if not period:
            return None

        curr = _resolve_currency(gd.get("currency") or gd.get("currency2"))

        if max_val is not None and min_val > max_val:
            min_val, max_val = max_val, min_val

        if period == "hour" and (min_val > 500 or (max_val and max_val > 500)):
            return None

        return {
            "salary_min": min_val,
            "salary_max": max_val if max_val is not None else min_val,
            "salary_period": period,
            "salary_currency": curr,
            "salary_raw": cleaned,
            "salary_provenance": "text_extraction",
        }

    m1 = _STIPEND_PREFIX_PATTERN.search(cleaned)
    if m1:
        gd = m1.groupdict()
        min_val = parse_number(gd.get("min"))
        curr = _resolve_currency(gd.get("currency"))
        if min_val is not None:
            return {
                "salary_min": min_val,
                "salary_max": min_val,
                "salary_period": "stipend",
                "salary_currency": curr,
                "salary_raw": cleaned,
                "salary_provenance": "text_extraction",
            }

    return None


def normalize_compensation(
    raw_input: Any,
    default_currency: str = "USD",
    provenance: str = "structured_ats"
) -> Optional[Dict[str, Any]]:
    """Normalize structured compensation dicts or text from ATS feeds into standard canonical fields."""
    if raw_input is None:
        return None

    if isinstance(raw_input, str):
        res = parse_pay_from_text(raw_input)
        if res and provenance != "text_extraction":
            res["salary_provenance"] = provenance
        return res

    if isinstance(raw_input, dict):
        min_val = raw_input.get("min") if raw_input.get("min") is not None else raw_input.get("salary_min")
        max_val = raw_input.get("max") if raw_input.get("max") is not None else raw_input.get("salary_max")

        if min_val is None and max_val is None:
            tier = raw_input.get("compensationTier") or raw_input.get("salaryRange") or raw_input.get("compensation")
            if isinstance(tier, dict):
                return normalize_compensation(tier, default_currency=default_currency, provenance=provenance)
            elif isinstance(tier, str):
                return parse_pay_from_text(tier)

        raw_text = raw_input.get("text") or raw_input.get("raw") or raw_input.get("summary") or raw_input.get("display")

        period_raw = raw_input.get("period") or raw_input.get("interval") or raw_input.get("salary_period") or raw_input.get("payPeriod")
        curr_raw = raw_input.get("currency") or raw_input.get("salary_currency")

        try:
            min_num = float(min_val) if min_val is not None else None
        except (ValueError, TypeError):
            min_num = None

        try:
            max_num = float(max_val) if max_val is not None else None
        except (ValueError, TypeError):
            max_num = None

        if min_num is None and max_num is None:
            if raw_text and isinstance(raw_text, str):
                return parse_pay_from_text(raw_text)
            return None

        if min_num is not None and max_num is None:
            max_num = min_num
        elif max_num is not None and min_num is None:
            min_num = max_num

        if min_num is not None and max_num is not None and min_num > max_num:
            min_num, max_num = max_num, min_num

        period = None
        if period_raw and isinstance(period_raw, str):
            p_clean = period_raw.strip().lower()
            period = PERIOD_MAP.get(p_clean)

        if not period and raw_text and isinstance(raw_text, str):
            text_parsed = parse_pay_from_text(raw_text)
            if text_parsed:
                period = text_parsed.get("salary_period")

        if not period:
            if min_num is not None:
                if 10.0 <= min_num <= 200.0:
                    period = "hour"
                elif 500.0 <= min_num <= 5000.0:
                    period = "month"
                elif min_num >= 15000.0:
                    period = "year"

        if not period:
            period = "hour" if (min_num and min_num < 200) else "year"

        currency = _resolve_currency(curr_raw) if curr_raw else default_currency

        return {
            "salary_min": min_num,
            "salary_max": max_num,
            "salary_period": period,
            "salary_currency": currency,
            "salary_raw": raw_text,
            "salary_provenance": provenance,
        }

    return None


def merge_salary_fields(target: dict, incoming: dict) -> None:
    """Merge incoming salary fields into target job dict while preserving better existing data."""
    if not incoming:
        return

    inc_min = incoming.get("salary_min")
    inc_max = incoming.get("salary_max")
    inc_period = incoming.get("salary_period")
    inc_currency = incoming.get("salary_currency")
    inc_raw = incoming.get("salary_raw")
    inc_prov = incoming.get("salary_provenance")

    has_inc_salary = (inc_min is not None) or (inc_max is not None)
    if not has_inc_salary:
        return

    tar_min = target.get("salary_min")
    tar_max = target.get("salary_max")
    has_tar_salary = (tar_min is not None) or (tar_max is not None)

    tar_prov = target.get("salary_provenance", "text_extraction")

    should_override = False
    if not has_tar_salary:
        should_override = True
    elif inc_prov == "structured_ats" and tar_prov != "structured_ats":
        should_override = True
    elif inc_prov == tar_prov:
        if tar_min == tar_max and inc_min != inc_max:
            should_override = True
        elif not target.get("salary_raw") and inc_raw:
            should_override = True

    if should_override:
        if inc_min is not None:
            target["salary_min"] = inc_min
        if inc_max is not None:
            target["salary_max"] = inc_max
        if inc_period:
            target["salary_period"] = inc_period
        if inc_currency:
            target["salary_currency"] = inc_currency
        if inc_raw:
            target["salary_raw"] = inc_raw
        if inc_prov:
            target["salary_provenance"] = inc_prov
    else:
        if target.get("salary_min") is None and inc_min is not None:
            target["salary_min"] = inc_min
        if target.get("salary_max") is None and inc_max is not None:
            target["salary_max"] = inc_max
        if not target.get("salary_period") and inc_period:
            target["salary_period"] = inc_period
        if not target.get("salary_currency") and inc_currency:
            target["salary_currency"] = inc_currency
        if not target.get("salary_raw") and inc_raw:
            target["salary_raw"] = inc_raw
        if not target.get("salary_provenance") and inc_prov:
            target["salary_provenance"] = inc_prov
