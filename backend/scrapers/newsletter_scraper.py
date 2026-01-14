"""
Newsletter ingestion helpers.

Supports:
- Manual upload (HTML or plaintext)
- Basic link extraction
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup


@dataclass
class NewsletterIngestResult:
    title: str
    content_text: str
    extracted_links: List[str]
    detected_date: Optional[datetime]


class NewsletterScraper:
    """Utility class for parsing newsletter HTML/plaintext into a storable item."""

    def parse(self, *, title: str, raw_content: str, content_type: str = "auto") -> NewsletterIngestResult:
        title = (title or "").strip() or "Newsletter issue"
        raw = (raw_content or "").strip()
        ctype = (content_type or "auto").lower().strip()

        detected_date = self._detect_date(title, raw)

        if ctype in {"html", "text/html"} or (ctype == "auto" and ("<html" in raw.lower() or "<body" in raw.lower() or "<a " in raw.lower())):
            text, links = self._parse_html(raw)
        else:
            text, links = self._parse_text(raw)

        # Normalize whitespace
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return NewsletterIngestResult(
            title=title,
            content_text=text,
            extracted_links=links,
            detected_date=detected_date,
        )

    def _parse_html(self, html: str) -> tuple[str, List[str]]:
        soup = BeautifulSoup(html, "html.parser")
        # Extract links first
        links: List[str] = []
        for a in soup.find_all("a"):
            href = (a.get("href") or "").strip()
            if href.startswith("http://") or href.startswith("https://"):
                links.append(href)

        # Remove script/style
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text("\n")
        return text, self._dedupe_links(links)

    def _parse_text(self, text: str) -> tuple[str, List[str]]:
        links = re.findall(r"https?://\\S+", text or "")
        return (text or "").strip(), self._dedupe_links(links)

    def _dedupe_links(self, links: List[str]) -> List[str]:
        out: List[str] = []
        seen = set()
        for u in links:
            u = u.strip().rstrip(").,;")
            if not u or u in seen:
                continue
            seen.add(u)
            out.append(u)
        return out[:200]

    def _detect_date(self, title: str, raw: str) -> Optional[datetime]:
        # Very lightweight date detection for things like "Rundown Jan 13 2026"
        blob = f"{title}\n{raw[:500]}"
        m = re.search(r"\\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\\s+(\\d{1,2}),?\\s+(\\d{4})\\b", blob, re.IGNORECASE)
        if not m:
            return None
        month = m.group(1).lower()[:3]
        day = int(m.group(2))
        year = int(m.group(3))
        month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
        mm = month_map.get(month)
        if not mm:
            return None
        try:
            return datetime(year, mm, day)
        except Exception:
            return None

