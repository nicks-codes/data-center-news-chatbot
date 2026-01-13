"""
Heuristics for keeping the corpus focused on "data center stuff".

This is intentionally lightweight (no ML dependency):
- assigns a relevance score based on keyword matches
- extracts simple topic tags for filtering and UI
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple
import re


@dataclass(frozen=True)
class RelevanceResult:
    score: float
    tags: List[str]


# Phrase-level signals (strong)
STRONG_PHRASES: Tuple[str, ...] = (
    "data center",
    "data-centre",
    "data centre",
    "datacenter",
    "colocation",
    "colo facility",
    "hyperscale",
    "edge data center",
    "edge datacenter",
)

# Keyword signals (medium)
KEYWORDS: Tuple[Tuple[str, str], ...] = (
    # (tag, keyword)
    ("power", "ups"),
    ("power", "generator"),
    ("power", "substation"),
    ("power", "transformer"),
    ("power", "grid"),
    ("power", "power purchase agreement"),
    ("power", "ppa"),
    ("cooling", "cooling"),
    ("cooling", "chiller"),
    ("cooling", "hvac"),
    ("cooling", "liquid cooling"),
    ("cooling", "immersion"),
    ("cooling", "heat reuse"),
    ("design", "tier iii"),
    ("design", "tier iv"),
    ("design", "uPtime institute"),
    ("design", "n+1"),
    ("design", "2n"),
    ("operations", "outage"),
    ("operations", "downtime"),
    ("operations", "incident"),
    ("operations", "maintenance"),
    ("sustainability", "pue"),
    ("sustainability", "renewable"),
    ("sustainability", "water"),
    ("sustainability", "carbon"),
    ("sustainability", "sustainab"),
    ("hardware", "rack"),
    ("hardware", "server"),
    ("hardware", "gpu"),
    ("hardware", "nvidia"),
    ("hardware", "amd"),
    ("networking", "fiber"),
    ("networking", "interconnect"),
    ("networking", "ix"),
    ("real-estate", "campus"),
    ("real-estate", "land"),
    ("real-estate", "permitting"),
    ("real-estate", "zoning"),
    ("cloud", "availability zone"),
    ("cloud", "region"),
)


def _tokenize(text: str) -> str:
    # Normalize whitespace and lowercase for matching.
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _merge_tags(existing: Optional[str], new_tags: Iterable[str]) -> Optional[str]:
    existing_tags: List[str] = []
    if existing:
        existing_tags = [t.strip() for t in existing.split(",") if t.strip()]

    combined: List[str] = []
    seen: Set[str] = set()

    for t in existing_tags + list(new_tags):
        key = t.lower()
        if not key or key in seen:
            continue
        seen.add(key)
        combined.append(t)

    return ", ".join(combined) if combined else None


def score_and_tag_article(
    title: str,
    content: str,
    existing_tags: Optional[str] = None,
) -> RelevanceResult:
    """
    Compute a relevance score and topic tags.

    Scoring is intentionally simple and stable:
    - strong phrases: +6 in title, +3 in content
    - keywords: +2 in title, +1 in content (tag assigned by mapping)
    """
    t = _tokenize(title)
    c = _tokenize(content)

    score = 0.0
    tags: List[str] = []

    # Strong phrases
    for phrase in STRONG_PHRASES:
        p = phrase.lower()
        if p and p in t:
            score += 6
        if p and p in c:
            score += 3
            if "data center" in p or "datacenter" in p or "data centre" in p:
                tags.append("data-center")

    # Keywords
    for tag, kw in KEYWORDS:
        k = kw.lower()
        if not k:
            continue
        if k in t:
            score += 2
            tags.append(tag)
        if k in c:
            score += 1
            tags.append(tag)

    # Cap score so it stays comparable across sources.
    score = min(score, 25.0)

    # Merge with any upstream tags.
    merged = _merge_tags(existing_tags, tags)
    merged_list = [x.strip() for x in merged.split(",")] if merged else []

    return RelevanceResult(score=score, tags=merged_list)

