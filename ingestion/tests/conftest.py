"""Shared fixtures for the Enjin ingestion test suite.

Provides sample data objects, mock HTTP responses, and adapter configurations
that are reused across multiple test modules.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from app.adapters.base import RawItem

# ---------------------------------------------------------------------------
# RawItem fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def minimal_raw_item() -> RawItem:
    """A RawItem with only required fields populated."""
    return RawItem(
        source_adapter="test",
        external_id="abc123",
        title="Minimal Item",
    )


@pytest.fixture
def full_raw_item() -> RawItem:
    """A RawItem with every field populated."""
    return RawItem(
        source_adapter="rss",
        external_id="full-item-001",
        title="Full Article Title",
        content="This is the full article content with details.",
        summary="A brief summary of the article.",
        authors=["Alice Smith", "Bob Jones"],
        published_at=datetime(2025, 6, 15, 12, 0, 0, tzinfo=UTC),
        source_url="https://example.com/article/1",
        metadata={
            "feed_url": "https://example.com/feed.xml",
            "tags": ["world", "politics"],
        },
    )


# ---------------------------------------------------------------------------
# RSS feed XML fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_rss_xml() -> str:
    """A minimal valid RSS 2.0 feed as an XML string."""
    return """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <link>https://example.com</link>
    <description>A test RSS feed</description>
    <item>
      <title>First Article</title>
      <link>https://example.com/first</link>
      <description>&lt;p&gt;Summary of the first article.&lt;/p&gt;</description>
      <author>Alice Smith</author>
      <pubDate>Mon, 15 Jan 2025 12:00:00 GMT</pubDate>
      <category>world</category>
    </item>
    <item>
      <title>Second Article</title>
      <link>https://example.com/second</link>
      <description>Summary of the second article.</description>
      <author>Bob Jones, Charlie Brown</author>
      <pubDate>Tue, 16 Jan 2025 08:30:00 GMT</pubDate>
    </item>
  </channel>
</rss>"""


@pytest.fixture
def empty_rss_xml() -> str:
    """An RSS feed with no items."""
    return """\
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Empty Feed</title>
    <link>https://example.com</link>
    <description>This feed has no items</description>
  </channel>
</rss>"""


@pytest.fixture
def malformed_rss_xml() -> str:
    """Malformed/incomplete XML that feedparser would flag as bozo."""
    return "<rss><channel><title>Broken"


# ---------------------------------------------------------------------------
# GDELT CSV fixtures
# ---------------------------------------------------------------------------

def _build_gdelt_row(
    event_id: str = "1234567890",
    date: str = "20250115",
    actor1_name: str = "DENMARK",
    actor1_country: str = "DA",
    actor2_name: str = "UNITED STATES",
    actor2_country: str = "US",
    event_root_code: str = "03",
    event_code: str = "030",
    quad_class: str = "1",
    goldstein: str = "5.0",
    num_mentions: str = "10",
    avg_tone: str = "2.5",
    action_geo_fullname: str = "Copenhagen, Denmark",
    action_geo_lat: str = "55.6761",
    action_geo_long: str = "12.5683",
    source_url: str = "https://example.com/story",
) -> list[str]:
    """Build a 58-column GDELT event row with specified values.

    Columns not explicitly listed are filled with empty strings.
    """
    row = [""] * 58
    row[0] = event_id
    row[1] = date
    row[6] = actor1_name
    row[7] = actor1_country
    row[16] = actor2_name
    row[17] = actor2_country
    row[26] = event_root_code
    row[27] = event_code
    row[29] = quad_class
    row[30] = goldstein
    row[31] = num_mentions
    row[34] = avg_tone
    row[49] = action_geo_fullname
    row[53] = action_geo_lat
    row[54] = action_geo_long
    row[57] = source_url
    return row


@pytest.fixture
def gdelt_csv_row() -> list[str]:
    """A single valid 58-column GDELT event row."""
    return _build_gdelt_row()


@pytest.fixture
def gdelt_csv_text() -> str:
    """Tab-separated GDELT CSV text with two event rows."""
    row1 = _build_gdelt_row(
        event_id="1111111111",
        actor1_country="DA",
        actor2_country="US",
    )
    row2 = _build_gdelt_row(
        event_id="2222222222",
        actor1_country="GB",
        actor2_country="FR",
    )
    lines = ["\t".join(row1), "\t".join(row2)]
    return "\n".join(lines)


@pytest.fixture
def gdelt_csv_text_non_focus() -> str:
    """GDELT CSV text with rows that do NOT match the default focus countries."""
    row = _build_gdelt_row(
        event_id="9999999999",
        actor1_country="ZZ",
        actor2_country="YY",
    )
    return "\t".join(row)


# ---------------------------------------------------------------------------
# Adapter configuration fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rss_config() -> dict[str, Any]:
    """Source config for the RSS adapter."""
    return {"feed_urls": ["https://example.com/feed.xml"]}


@pytest.fixture
def rss_config_multi() -> dict[str, Any]:
    """Source config for the RSS adapter with multiple feeds."""
    return {
        "feed_urls": [
            "https://example.com/feed1.xml",
            "https://example.com/feed2.xml",
        ]
    }


@pytest.fixture
def gdelt_config() -> dict[str, Any]:
    """Source config for the GDELT adapter."""
    return {
        "base_url": "http://data.gdeltproject.org/api/v2",
        "focus_countries": ["DA", "US", "GB"],
    }


@pytest.fixture
def cvr_config() -> dict[str, Any]:
    """Source config for the CVR adapter."""
    return {
        "api_url": "https://cvrapi.dk/api",
        "search_terms": ["Novo Nordisk"],
        "country": "dk",
    }


@pytest.fixture
def cvr_config_empty() -> dict[str, Any]:
    """Source config for the CVR adapter with no search terms."""
    return {
        "api_url": "https://cvrapi.dk/api",
        "search_terms": [],
        "country": "dk",
    }


# ---------------------------------------------------------------------------
# Mock HTTP response helper
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_httpx_response():
    """Factory fixture that creates a mock httpx.Response.

    Usage::

        resp = mock_httpx_response(
            status_code=200,
            json_data={"key": "value"},
        )
    """

    def _factory(
        status_code: int = 200,
        json_data: Any = None,
        text: str = "",
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        resp = httpx.Response(
            status_code=status_code,
            headers=headers or {},
            content=(
                json.dumps(json_data).encode()
                if json_data is not None
                else content or text.encode()
            ),
            request=httpx.Request("GET", "https://mocked.example.com"),
        )
        return resp

    return _factory


# ---------------------------------------------------------------------------
# Sample CVR API response data
# ---------------------------------------------------------------------------

@pytest.fixture
def cvr_api_response_data() -> dict[str, Any]:
    """Sample JSON response from the CVR API."""
    return {
        "vat": 10150817,
        "name": "NOVO NORDISK A/S",
        "address": "Novo Alle 1",
        "zipcode": "2880",
        "city": "Bagsvaerd",
        "country": "dk",
        "companydesc": "Aktieselskab",
        "industrydesc": "Manufacture of pharmaceutical preparations",
        "industrycode": 21200,
        "startdate": "01/02 - 1989",
        "status": "NORMAL",
        "email": "info@novonordisk.com",
        "phone": "+4544448888",
        "owners": [
            {"name": "Novo Holdings A/S"},
            {"name": "Lars Fruergaard Jorgensen"},
        ],
    }
