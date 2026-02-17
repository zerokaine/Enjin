"""RSS / Atom feed adapter.

Uses ``feedparser`` to consume any standard RSS 2.0 or Atom feed and
normalise its entries into ``RawItem`` objects.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
from bs4 import BeautifulSoup

from app.adapters.base import RawItem, SourceAdapter

logger = logging.getLogger(__name__)


class RSSAdapter(SourceAdapter):
    """Fetch and parse RSS/Atom feeds into RawItem objects."""

    def get_name(self) -> str:
        return "rss"

    # ── public API ───────────────────────────────────────────────────
    async def fetch(self) -> list[RawItem]:
        """Parse every configured feed URL and return a flat list of items."""
        urls: list[str] = self.source_config.get("feed_urls", [])
        if not urls:
            logger.warning("RSSAdapter: no feed_urls configured -- nothing to fetch")
            return []

        items: list[RawItem] = []
        for url in urls:
            try:
                feed_items = self._parse_feed(url)
                items.extend(feed_items)
                logger.info("RSSAdapter: fetched %d items from %s", len(feed_items), url)
            except Exception:
                logger.exception("RSSAdapter: failed to parse feed %s", url)
        return items

    # ── internals ────────────────────────────────────────────────────
    def _parse_feed(self, url: str) -> list[RawItem]:
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            logger.warning("RSSAdapter: feed %s is malformed: %s", url, feed.bozo_exception)
            return []

        return [self._entry_to_raw_item(entry, url) for entry in feed.entries]

    def _entry_to_raw_item(self, entry: Any, feed_url: str) -> RawItem:
        title = entry.get("title", "")
        link = entry.get("link", feed_url)

        # Build a deterministic external id from source + link
        external_id = hashlib.sha256(f"rss:{link}".encode()).hexdigest()[:32]

        # Extract and clean summary / content
        raw_summary = entry.get("summary") or entry.get("description") or ""
        summary = self._strip_html(raw_summary)

        content_detail = entry.get("content")
        content: str | None = None
        if content_detail and isinstance(content_detail, list):
            content = self._strip_html(content_detail[0].get("value", ""))

        # Authors
        author = entry.get("author", "")
        authors = [a.strip() for a in author.split(",") if a.strip()] if author else []

        # Published date -- try several common formats
        published_at = self._parse_date(entry)

        return RawItem(
            source_adapter=self.get_name(),
            external_id=external_id,
            title=title,
            content=content,
            summary=summary,
            authors=authors,
            published_at=published_at,
            source_url=link,
            metadata={
                "feed_url": feed_url,
                "tags": [t.get("term", "") for t in entry.get("tags", [])],
            },
        )

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _strip_html(html: str) -> str:
        """Remove HTML tags and collapse whitespace."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "lxml")
        text = soup.get_text(separator=" ", strip=True)
        return " ".join(text.split())

    @staticmethod
    def _parse_date(entry: Any) -> datetime | None:
        """Extract a timezone-aware datetime from a feed entry.

        Tries ``published_parsed``, ``updated_parsed`` (struct_time) first,
        then falls back to parsing the raw string with ``email.utils``.
        """
        # feedparser already parses many formats into struct_time
        for attr in ("published_parsed", "updated_parsed"):
            struct = entry.get(attr)
            if struct:
                try:
                    from time import mktime

                    return datetime.fromtimestamp(mktime(struct), tz=UTC)
                except (OverflowError, OSError, ValueError):
                    continue

        # Fallback: raw string (RFC 2822 style)
        for attr in ("published", "updated"):
            raw = entry.get(attr)
            if raw:
                try:
                    return parsedate_to_datetime(raw).replace(tzinfo=UTC)
                except (ValueError, TypeError):
                    continue

        return None
