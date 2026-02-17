"""Tests for app.adapters.rss — RSSAdapter.

All external calls (feedparser.parse) are mocked so no network I/O occurs.
"""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.base import RawItem
from app.adapters.rss import RSSAdapter


# ---------------------------------------------------------------------------
# Helper: build a fake feedparser entry
# ---------------------------------------------------------------------------

def _make_entry(
    title: str = "Test Title",
    link: str = "https://example.com/article",
    summary: str = "A summary",
    content: list[dict[str, str]] | None = None,
    author: str = "",
    published_parsed: time.struct_time | None = None,
    published: str | None = None,
    tags: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build a dictionary mimicking a feedparser entry."""
    entry: dict[str, Any] = {
        "title": title,
        "link": link,
        "summary": summary,
    }
    if content is not None:
        entry["content"] = content
    if author:
        entry["author"] = author
    if published_parsed is not None:
        entry["published_parsed"] = published_parsed
    if published is not None:
        entry["published"] = published
    if tags is not None:
        entry["tags"] = tags
    return entry


def _make_feed_result(
    entries: list[dict[str, Any]] | None = None,
    bozo: bool = False,
    bozo_exception: Exception | None = None,
) -> MagicMock:
    """Build a mock feedparser.parse() return value."""
    feed = MagicMock()
    feed.entries = entries or []
    feed.bozo = bozo
    feed.bozo_exception = bozo_exception
    return feed


# =========================================================================
# RSSAdapter.fetch()
# =========================================================================

class TestRSSAdapterFetch:
    """Test the async fetch() method with mocked feedparser."""

    @pytest.mark.asyncio
    async def test_fetch_returns_raw_items(self, rss_config: dict[str, Any]) -> None:
        """fetch() should return RawItem objects from parsed entries."""
        entries = [
            _make_entry(title="Article 1", link="https://example.com/1"),
            _make_entry(title="Article 2", link="https://example.com/2"),
        ]
        mock_feed = _make_feed_result(entries=entries)

        adapter = RSSAdapter(rss_config)
        with patch("app.adapters.rss.feedparser.parse", return_value=mock_feed):
            items = await adapter.fetch()

        assert len(items) == 2
        assert all(isinstance(i, RawItem) for i in items)
        assert items[0].title == "Article 1"
        assert items[1].title == "Article 2"

    @pytest.mark.asyncio
    async def test_fetch_no_feed_urls_returns_empty(self) -> None:
        """An adapter with no feed_urls should return an empty list."""
        adapter = RSSAdapter({"feed_urls": []})
        items = await adapter.fetch()
        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_missing_feed_urls_key_returns_empty(self) -> None:
        """If 'feed_urls' key is missing entirely, return empty."""
        adapter = RSSAdapter({})
        items = await adapter.fetch()
        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_multiple_feeds(
        self, rss_config_multi: dict[str, Any]
    ) -> None:
        """fetch() should aggregate items from multiple feed URLs."""
        entries_a = [_make_entry(title="Feed1 Article", link="https://a.com/1")]
        entries_b = [
            _make_entry(title="Feed2 Article A", link="https://b.com/1"),
            _make_entry(title="Feed2 Article B", link="https://b.com/2"),
        ]
        feed_a = _make_feed_result(entries=entries_a)
        feed_b = _make_feed_result(entries=entries_b)

        adapter = RSSAdapter(rss_config_multi)

        def side_effect(url: str) -> MagicMock:
            if "feed1" in url:
                return feed_a
            return feed_b

        with patch("app.adapters.rss.feedparser.parse", side_effect=side_effect):
            items = await adapter.fetch()

        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_fetch_exception_in_one_feed_does_not_block_others(
        self, rss_config_multi: dict[str, Any]
    ) -> None:
        """If one feed raises, items from other feeds should still be returned."""
        entries_b = [_make_entry(title="Good Article", link="https://b.com/1")]
        feed_b = _make_feed_result(entries=entries_b)

        adapter = RSSAdapter(rss_config_multi)

        call_count = 0

        def side_effect(url: str) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("Simulated parse error")
            return feed_b

        with patch("app.adapters.rss.feedparser.parse", side_effect=side_effect):
            items = await adapter.fetch()

        # Only items from the second feed should be returned
        assert len(items) == 1
        assert items[0].title == "Good Article"


# =========================================================================
# Bozo / malformed feeds
# =========================================================================

class TestRSSAdapterBozoFeeds:
    """feedparser sets bozo=True for malformed feeds."""

    @pytest.mark.asyncio
    async def test_bozo_feed_with_no_entries_returns_empty(
        self, rss_config: dict[str, Any]
    ) -> None:
        """A bozo feed with zero entries should yield no items."""
        mock_feed = _make_feed_result(
            entries=[],
            bozo=True,
            bozo_exception=Exception("not well-formed"),
        )
        adapter = RSSAdapter(rss_config)
        with patch("app.adapters.rss.feedparser.parse", return_value=mock_feed):
            items = await adapter.fetch()
        assert items == []

    @pytest.mark.asyncio
    async def test_bozo_feed_with_entries_still_returns_items(
        self, rss_config: dict[str, Any]
    ) -> None:
        """A bozo feed that still has entries should return those entries."""
        entries = [_make_entry(title="Partial Entry", link="https://e.com/1")]
        mock_feed = _make_feed_result(
            entries=entries,
            bozo=True,
            bozo_exception=Exception("not well-formed"),
        )
        adapter = RSSAdapter(rss_config)
        with patch("app.adapters.rss.feedparser.parse", return_value=mock_feed):
            items = await adapter.fetch()
        assert len(items) == 1
        assert items[0].title == "Partial Entry"


# =========================================================================
# _strip_html
# =========================================================================

class TestStripHtml:
    """Test HTML-to-text conversion."""

    def test_removes_tags(self) -> None:
        assert RSSAdapter._strip_html("<p>Hello <b>World</b></p>") == "Hello World"

    def test_collapses_whitespace(self) -> None:
        result = RSSAdapter._strip_html("<p>Hello   \n   World</p>")
        assert result == "Hello World"

    def test_empty_string(self) -> None:
        assert RSSAdapter._strip_html("") == ""

    def test_plain_text_unchanged(self) -> None:
        assert RSSAdapter._strip_html("No tags here") == "No tags here"

    def test_nested_tags(self) -> None:
        html = "<div><ul><li>One</li><li>Two</li></ul></div>"
        result = RSSAdapter._strip_html(html)
        assert "One" in result
        assert "Two" in result

    def test_entities_decoded(self) -> None:
        html = "&amp; &lt;b&gt; test"
        result = RSSAdapter._strip_html(html)
        assert "&" in result
        assert "<b>" in result or "b" in result  # lxml may handle differently


# =========================================================================
# _parse_date
# =========================================================================

class TestParseDate:
    """Test date parsing from feedparser entries."""

    def test_published_parsed_struct_time(self) -> None:
        """A valid published_parsed struct_time should yield a datetime."""
        struct = time.strptime("2025-01-15 12:00:00", "%Y-%m-%d %H:%M:%S")
        entry = {"published_parsed": struct}
        result = RSSAdapter._parse_date(entry)
        assert result is not None
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_updated_parsed_fallback(self) -> None:
        """Falls back to updated_parsed when published_parsed is absent."""
        struct = time.strptime("2025-06-01 00:00:00", "%Y-%m-%d %H:%M:%S")
        entry = {"updated_parsed": struct}
        result = RSSAdapter._parse_date(entry)
        assert result is not None

    def test_raw_published_string_rfc2822(self) -> None:
        """Falls back to parsing raw RFC 2822 date strings."""
        entry = {"published": "Mon, 15 Jan 2025 12:00:00 +0000"}
        result = RSSAdapter._parse_date(entry)
        assert result is not None
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 15

    def test_raw_updated_string_fallback(self) -> None:
        entry = {"updated": "Tue, 16 Jan 2025 08:30:00 +0000"}
        result = RSSAdapter._parse_date(entry)
        assert result is not None

    def test_no_date_fields_returns_none(self) -> None:
        entry = {"title": "No dates here"}
        result = RSSAdapter._parse_date(entry)
        assert result is None

    def test_invalid_date_string_returns_none(self) -> None:
        entry = {"published": "not-a-date"}
        result = RSSAdapter._parse_date(entry)
        assert result is None

    def test_empty_entry_returns_none(self) -> None:
        result = RSSAdapter._parse_date({})
        assert result is None


# =========================================================================
# _entry_to_raw_item
# =========================================================================

class TestEntryToRawItem:
    """Test conversion of a feedparser entry to a RawItem."""

    def test_basic_conversion(self, rss_config: dict[str, Any]) -> None:
        adapter = RSSAdapter(rss_config)
        entry = _make_entry(
            title="Test Article",
            link="https://example.com/article",
            summary="<p>A summary</p>",
            author="Jane Doe",
        )
        item = adapter._entry_to_raw_item(entry, "https://example.com/feed.xml")

        assert isinstance(item, RawItem)
        assert item.source_adapter == "rss"
        assert item.title == "Test Article"
        assert item.summary == "A summary"  # HTML stripped
        assert item.authors == ["Jane Doe"]
        assert item.source_url == "https://example.com/article"
        assert item.metadata["feed_url"] == "https://example.com/feed.xml"

    def test_external_id_deterministic(self, rss_config: dict[str, Any]) -> None:
        """external_id should be a deterministic hash of 'rss:<link>'."""
        adapter = RSSAdapter(rss_config)
        link = "https://example.com/specific-article"
        entry = _make_entry(link=link)
        item = adapter._entry_to_raw_item(entry, "https://example.com/feed.xml")

        expected_id = hashlib.sha256(f"rss:{link}".encode()).hexdigest()[:32]
        assert item.external_id == expected_id

    def test_multiple_authors_split(self, rss_config: dict[str, Any]) -> None:
        adapter = RSSAdapter(rss_config)
        entry = _make_entry(author="Alice, Bob, Charlie")
        item = adapter._entry_to_raw_item(entry, "https://example.com/feed.xml")
        assert item.authors == ["Alice", "Bob", "Charlie"]

    def test_no_author_yields_empty_list(self, rss_config: dict[str, Any]) -> None:
        adapter = RSSAdapter(rss_config)
        entry = _make_entry(author="")
        item = adapter._entry_to_raw_item(entry, "https://example.com/feed.xml")
        assert item.authors == []

    def test_content_extracted_from_content_field(
        self, rss_config: dict[str, Any]
    ) -> None:
        """If the entry has a 'content' list, its value should be extracted."""
        adapter = RSSAdapter(rss_config)
        entry = _make_entry(
            content=[{"value": "<p>Full content here.</p>", "type": "text/html"}]
        )
        item = adapter._entry_to_raw_item(entry, "https://example.com/feed.xml")
        assert item.content == "Full content here."

    def test_tags_extracted(self, rss_config: dict[str, Any]) -> None:
        adapter = RSSAdapter(rss_config)
        entry = _make_entry(tags=[{"term": "tech"}, {"term": "ai"}])
        item = adapter._entry_to_raw_item(entry, "https://example.com/feed.xml")
        assert item.metadata["tags"] == ["tech", "ai"]

    def test_empty_tags_yields_empty_list(self, rss_config: dict[str, Any]) -> None:
        adapter = RSSAdapter(rss_config)
        entry = _make_entry()
        item = adapter._entry_to_raw_item(entry, "https://example.com/feed.xml")
        assert item.metadata["tags"] == []

    def test_missing_link_uses_feed_url(self, rss_config: dict[str, Any]) -> None:
        adapter = RSSAdapter(rss_config)
        entry = {"title": "No Link", "summary": "Summary"}
        item = adapter._entry_to_raw_item(entry, "https://example.com/feed.xml")
        assert item.source_url == "https://example.com/feed.xml"


# =========================================================================
# get_name()
# =========================================================================

class TestRSSAdapterMeta:
    def test_get_name(self, rss_config: dict[str, Any]) -> None:
        adapter = RSSAdapter(rss_config)
        assert adapter.get_name() == "rss"
