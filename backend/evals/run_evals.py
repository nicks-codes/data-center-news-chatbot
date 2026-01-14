"""
Tiny eval harness for the chatbot.

Runs prompts and reports:
- citation coverage
- clarifying question count
- average sources used
- guardrails: when sources are 0, answer should avoid heavy factual claims
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.database.db import init_db
from backend.services.chat_service import ChatService


PROMPTS_PATH = Path(__file__).parent / "prompts.json"


def _has_clarifier(text: str) -> bool:
    t = (text or "").lower()
    return "quick clarifier" in t or t.strip().startswith("clarifier:")


def _extract_bullets(text: str) -> List[str]:
    lines = [ln.strip() for ln in (text or "").splitlines()]
    bullets = []
    for ln in lines:
        if ln.startswith("- "):
            bullets.append(ln[2:].strip())
    return bullets


def _citation_coverage(text: str) -> Tuple[int, int]:
    """
    Return (bullets_with_citations, total_bullets) over '-' bullets.
    """
    bullets = _extract_bullets(text)
    if not bullets:
        return 0, 0
    with_cite = 0
    for b in bullets:
        if re.search(r"\\[\\d+\\]", b):
            with_cite += 1
    return with_cite, len(bullets)


def _hallucination_guardrail(answer: str, sources_count: int) -> bool:
    """
    Heuristic: if there are zero sources, the answer should:
    - explicitly mention weak coverage / missing sources, OR
    - be mostly generic guidance (few citations, few concrete claims)
    """
    a = (answer or "").strip()
    if sources_count > 0:
        return True
    if re.search(r"not seeing strong coverage|couldn't find|no recent articles|missing", a.lower()):
        return True
    # If there are no sources and the model is still making a lot of bullet claims, fail.
    bullets = _extract_bullets(a)
    return len(bullets) <= 6


@dataclass
class EvalRow:
    id: str
    prompt: str
    audience: str
    sources_used: int
    asked_clarifier: bool
    bullet_cite_hits: int
    bullet_total: int
    guardrail_ok: bool


def run() -> int:
    init_db()
    service = ChatService()

    data = json.loads(PROMPTS_PATH.read_text())
    rows: List[EvalRow] = []

    for item in data:
        pid = item.get("id")
        prompt = item.get("prompt")
        audience = item.get("audience") or "Exec"

        # Use a stable conversation_id per prompt to exercise memory paths a bit.
        conversation_id = f"eval_{pid}"
        out = service.chat(prompt, audience=audience, conversation_id=conversation_id)

        answer = out.get("answer") or ""
        sources = out.get("sources") or []
        asked = _has_clarifier(answer)
        c_hits, c_total = _citation_coverage(answer)
        guard_ok = _hallucination_guardrail(answer, len(sources))

        rows.append(EvalRow(
            id=pid,
            prompt=prompt,
            audience=audience,
            sources_used=len(sources),
            asked_clarifier=asked,
            bullet_cite_hits=c_hits,
            bullet_total=c_total,
            guardrail_ok=guard_ok,
        ))

    # Aggregate metrics
    avg_sources = sum(r.sources_used for r in rows) / max(1, len(rows))
    clarifiers = sum(1 for r in rows if r.asked_clarifier)
    cite_hits = sum(r.bullet_cite_hits for r in rows)
    cite_total = sum(r.bullet_total for r in rows)
    cite_cov = (cite_hits / cite_total) if cite_total else 0.0
    guard_ok = sum(1 for r in rows if r.guardrail_ok)

    print("== Eval summary ==")
    print(f"prompts: {len(rows)}")
    print(f"avg_sources_used: {avg_sources:.2f}")
    print(f"clarifying_questions: {clarifiers}")
    print(f"citation_coverage_over_bullets: {cite_cov:.2%} ({cite_hits}/{cite_total})")
    print(f"guardrail_ok: {guard_ok}/{len(rows)}")
    print("")

    # Per-prompt table (compact)
    for r in rows:
        cov = (r.bullet_cite_hits / r.bullet_total) if r.bullet_total else 0.0
        print(f"{r.id} | src={r.sources_used:02d} | clarifier={'Y' if r.asked_clarifier else 'N'} | cite={cov:.0%} | guard={'OK' if r.guardrail_ok else 'FAIL'} | {r.prompt}")

    # Non-zero exit if guardrails fail badly
    if guard_ok < len(rows):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(run())

