"""
Scraper for The Data Center Rundown issue pages.
"""
import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dateutil import parser as date_parser

from .base_scraper import BaseScraper
from ..database.db import SessionLocal
from ..database.models import Article

logger = logging.getLogger(__name__)


class DCRundownScraper(BaseScraper):
    def __init__(self):
        super().__init__("DC Rundown")
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; DCNewsBot/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        self.timeout = 15

    def ingest_issue(self, url: str) -> Dict[str, object]:
        html = self._fetch(url)
        if not html:
            raise RuntimeError("Could not fetch issue page")

        parsed = self._parse_issue(html, url)
        db = SessionLocal()
        try:
            existing = db.query(Article).filter(Article.url == parsed["canonical_url"]).first()
            if existing:
                return {
                    "article_id": existing.id,
                    "title": existing.title,
                    "stored": False,
                    "links_found": len(parsed["outbound_links"]),
                }

            article = Article(
                title=parsed["title"],
                content=parsed["content"],
                url=parsed["canonical_url"],
                source="The Data Center Rundown",
                source_type="newsletter",
                published_date=parsed.get("published_date"),
                author=None,
                tags=parsed.get("tags_json"),
                has_embedding=False,
            )
            db.add(article)
            db.commit()
            db.refresh(article)
            return {
                "article_id": article.id,
                "title": article.title,
                "stored": True,
                "links_found": len(parsed["outbound_links"]),
            }
        finally:
            db.close()

    def _fetch(self, url: str) -> Optional[str]:
        try:
            resp = requests.get(url, headers=self.headers, timeout=self.timeout)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error(f"Failed to fetch DC Rundown issue: {e}")
            return None

    def _parse_issue(self, html: str, issue_url: str) -> Dict[str, object]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript", "iframe"]):
            tag.decompose()

        title = self._extract_title(soup)
        published_date = self._extract_date(soup, title)

        content = self._extract_visible_text(soup)
        content = self.clean_text(content)[:8000]

        outbound_links = self._extract_outbound_links(soup, issue_url)
        tags_json = self._build_tags(issue_url, outbound_links)

        canonical_url = self._issue_canonical_url(issue_url, published_date)

        return {
            "title": title or "DC Rundown Issue",
            "published_date": published_date,
            "content": content,
            "outbound_links": outbound_links,
            "tags_json": tags_json,
            "canonical_url": canonical_url,
        }

    def _extract_title(self, soup: BeautifulSoup) -> str:
        h1 = soup.find("h1")
        if h1 and h1.get_text(strip=True):
            return h1.get_text(strip=True)
        if soup.title and soup.title.get_text(strip=True):
            return soup.title.get_text(strip=True)
        return ""

    def _extract_visible_text(self, soup: BeautifulSoup) -> str:
        main = soup.find("article") or soup.find("main") or soup.body
        if not main:
            return soup.get_text(separator=" ", strip=True)
        paragraphs = main.find_all(["p", "li"])
        if paragraphs:
            return " ".join(p.get_text(" ", strip=True) for p in paragraphs)
        return main.get_text(" ", strip=True)

    def _extract_outbound_links(self, soup: BeautifulSoup, issue_url: str) -> List[str]:
        issue_host = urlparse(issue_url).netloc.lower()
        links = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href.startswith(("http://", "https://")):
                continue
            parsed = urlparse(href)
            if parsed.netloc.lower().endswith(issue_host):
                continue
            canon = self.canonicalize_url(href)
            if canon and canon not in seen:
                seen.add(canon)
                links.append(canon)
        return links

    def _extract_date(self, soup: BeautifulSoup, title: str) -> Optional[datetime]:
        # Try meta tags first
        meta = soup.find("meta", attrs={"property": "article:published_time"}) or soup.find("meta", attrs={"name": "date"})
        if meta and meta.get("content"):
            try:
                return date_parser.parse(meta["content"])
            except Exception:
                pass

        # Try title-based date pattern
        patterns = [
            r"([A-Z][a-z]+\\s+\\d{1,2},\\s+\\d{4})",
            r"(\\d{4}-\\d{2}-\\d{2})",
        ]
        for pat in patterns:
            m = re.search(pat, title or "")
            if m:
                try:
                    return date_parser.parse(m.group(1))
                except Exception:
                    pass
        return None

    def _issue_canonical_url(self, issue_url: str, published_date: Optional[datetime]) -> str:
        slug = urlparse(issue_url).path.rstrip("/").split("/")[-1] or "issue"
        date_part = (published_date.date().isoformat() if published_date else datetime.utcnow().date().isoformat())
        return f"dcrundown://{date_part}/{slug}"

    def _build_tags(self, issue_url: str, outbound_links: List[str]) -> str:
        links = outbound_links[:25]
        payload = {"issue_url": issue_url, "outbound_links": links}
        raw = json.dumps(payload)
        if len(raw) <= 480:
            return raw
        # If too long, trim links until it fits
        while links and len(raw) > 480:
            links = links[:-1]
            payload["outbound_links"] = links
            raw = json.dumps(payload)
        return raw
