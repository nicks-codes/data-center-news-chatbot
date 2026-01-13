"""
Small utilities for splitting article text into embedding-friendly chunks.

We keep this dependency-free (no tokenizer) and rely on conservative char limits + overlap.
"""

from __future__ import annotations

import re
from typing import List


def chunk_text(text: str, *, max_chars: int = 1200, overlap_chars: int = 200, max_chunks: int = 8) -> List[str]:
    """
    Split text into overlapping chunks.

    Notes:
    - This is intentionally simple and robust without external tokenizers.
    - For MiniLM-class embedding models, ~1k chars is usually enough context per chunk.
    """
    if not text:
        return []

    # Normalize whitespace early to make char counts meaningful.
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []

    max_chars = max(200, int(max_chars or 1200))
    overlap_chars = max(0, int(overlap_chars or 0))
    if overlap_chars >= max_chars:
        overlap_chars = max_chars // 4
    max_chunks = max(1, int(max_chunks or 1))

    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    start = 0
    n = len(text)

    while start < n and len(chunks) < max_chunks:
        end = min(n, start + max_chars)

        # Try to end on a sentence boundary if possible.
        if end < n:
            window_start = max(start + 200, end - 250)
            window = text[window_start:end]
            last_period = window.rfind(". ")
            last_space = window.rfind(" ")
            cut = max(last_period, last_space)
            if cut > 0:
                end = window_start + cut + (2 if cut == last_period else 1)

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= n:
            break

        # Advance with overlap
        start = max(0, end - overlap_chars)
        if start == 0 and end < n:
            # Safety: ensure forward progress if something goes weird.
            start = end

    return chunks

