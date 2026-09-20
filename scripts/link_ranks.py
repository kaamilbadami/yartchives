"""Shared constants for link precedence and ranking."""

LINK_KIND_RANKS = {"direct": 4, "employer_job": 3, "listing": 2, "source": 1}

def link_kind_rank(kind: str | None) -> int:
    return LINK_KIND_RANKS.get(str(kind), 0) if kind else 0
