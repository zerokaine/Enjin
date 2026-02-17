"""Tests for app.adapters.gdelt — GDELTAdapter.

All HTTP calls are mocked via unittest.mock.patch on httpx.AsyncClient.
"""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.base import RawItem
from app.adapters.gdelt import (
    CAMEO_CATEGORY_MAP,
    COL_GLOBAL_EVENT_ID,
    GDELTAdapter,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_gdelt_row(**overrides: str) -> list[str]:
    """Build a 58-column GDELT row.  Default values for key columns."""
    defaults = {
        "event_id": "1234567890",
        "date": "20250115",
        "actor1_name": "DENMARK",
        "actor1_country": "DA",
        "actor2_name": "UNITED STATES",
        "actor2_country": "US",
        "event_root_code": "03",
        "event_code": "030",
        "quad_class": "1",
        "goldstein": "5.0",
        "num_mentions": "10",
        "avg_tone": "2.5",
        "action_geo_fullname": "Copenhagen, Denmark",
        "action_geo_lat": "55.6761",
        "action_geo_long": "12.5683",
        "source_url": "https://example.com/story",
    }
    defaults.update(overrides)
    row = [""] * 58
    row[0] = defaults["event_id"]
    row[1] = defaults["date"]
    row[6] = defaults["actor1_name"]
    row[7] = defaults["actor1_country"]
    row[16] = defaults["actor2_name"]
    row[17] = defaults["actor2_country"]
    row[26] = defaults["event_root_code"]
    row[27] = defaults["event_code"]
    row[29] = defaults["quad_class"]
    row[30] = defaults["goldstein"]
    row[31] = defaults["num_mentions"]
    row[34] = defaults["avg_tone"]
    row[49] = defaults["action_geo_fullname"]
    row[53] = defaults["action_geo_lat"]
    row[54] = defaults["action_geo_long"]
    row[57] = defaults["source_url"]
    return row


def _rows_to_csv_text(rows: list[list[str]]) -> str:
    """Convert rows to tab-separated CSV text (GDELT format)."""
    return "\n".join("\t".join(r) for r in rows)


def _csv_text_to_zip(csv_text: str, csv_filename: str = "export.CSV") -> bytes:
    """Create an in-memory zip containing a single CSV file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(csv_filename, csv_text)
    return buf.getvalue()


def _make_lastupdate_response() -> str:
    """Fake lastupdate.txt content."""
    return (
        "123456 abcdef http://data.gdeltproject.org/gdeltv2/20250115120000.export.CSV.zip\n"
        "789012 ghijkl http://data.gdeltproject.org/gdeltv2/20250115120000.mentions.CSV.zip\n"
        "345678 mnopqr http://data.gdeltproject.org/gdeltv2/20250115120000.gkg.csv.zip\n"
    )


# ---------------------------------------------------------------------------
# Mock httpx.AsyncClient context manager
# ---------------------------------------------------------------------------

def _mock_async_client(responses: dict[str, httpx.Response]) -> MagicMock:
    """Create a mock httpx.AsyncClient that returns different responses per URL.

    ``responses`` maps URL substrings to httpx.Response objects.
    """

    async def mock_get(url: str, **kwargs: Any) -> httpx.Response:
        for pattern, resp in responses.items():
            if pattern in url:
                return resp
        raise httpx.HTTPStatusError(
            "Not found",
            request=httpx.Request("GET", url),
            response=httpx.Response(404),
        )

    client = AsyncMock()
    client.get = mock_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# =========================================================================
# CAMEO code mapping
# =========================================================================

class TestCAMEOMapping:
    """Verify the CAMEO root-code to Enjin category map."""

    def test_all_20_codes_present(self) -> None:
        assert len(CAMEO_CATEGORY_MAP) == 20

    @pytest.mark.parametrize(
        "code,expected",
        [
            ("01", "public_statement"),
            ("03", "cooperation"),
            ("14", "protest"),
            ("18", "assault"),
            ("20", "mass_violence"),
        ],
    )
    def test_specific_codes(self, code: str, expected: str) -> None:
        assert CAMEO_CATEGORY_MAP[code] == expected

    def test_unknown_code_not_in_map(self) -> None:
        assert "99" not in CAMEO_CATEGORY_MAP


# =========================================================================
# CSV parsing
# =========================================================================

class TestGDELTCSVParsing:
    """Test the static _parse_csv method."""

    def test_parse_csv_single_row(self) -> None:
        row = _build_gdelt_row()
        csv_text = "\t".join(row)
        adapter = GDELTAdapter({})
        rows = adapter._parse_csv(csv_text)
        assert len(rows) == 1
        assert rows[0][COL_GLOBAL_EVENT_ID] == "1234567890"

    def test_parse_csv_multiple_rows(self) -> None:
        rows = [
            _build_gdelt_row(event_id="111"),
            _build_gdelt_row(event_id="222"),
        ]
        csv_text = _rows_to_csv_text(rows)
        adapter = GDELTAdapter({})
        parsed = adapter._parse_csv(csv_text)
        assert len(parsed) == 2
        assert parsed[0][COL_GLOBAL_EVENT_ID] == "111"
        assert parsed[1][COL_GLOBAL_EVENT_ID] == "222"

    def test_parse_csv_empty_text(self) -> None:
        adapter = GDELTAdapter({})
        parsed = adapter._parse_csv("")
        # csv.reader on empty string yields one empty-ish row or nothing
        assert all(len(r) <= 1 for r in parsed)


# =========================================================================
# _row_to_raw_item
# =========================================================================

class TestRowToRawItem:
    """Test conversion of a single GDELT CSV row to RawItem."""

    def test_valid_row_returns_raw_item(self) -> None:
        adapter = GDELTAdapter({})
        row = _build_gdelt_row()
        item = adapter._row_to_raw_item(row)
        assert item is not None
        assert isinstance(item, RawItem)
        assert item.source_adapter == "gdelt"
        assert "cooperation" in item.title.lower() or "DENMARK" in item.title

    def test_short_row_returns_none(self) -> None:
        adapter = GDELTAdapter({})
        short_row = ["col1", "col2"]  # far fewer than 58 columns
        assert adapter._row_to_raw_item(short_row) is None

    def test_empty_event_id_returns_none(self) -> None:
        adapter = GDELTAdapter({})
        row = _build_gdelt_row(event_id="")
        assert adapter._row_to_raw_item(row) is None

    def test_metadata_fields(self) -> None:
        adapter = GDELTAdapter({})
        row = _build_gdelt_row(
            event_root_code="14",
            event_code="140",
            goldstein="-3.5",
            avg_tone="-1.2",
            num_mentions="25",
        )
        item = adapter._row_to_raw_item(row)
        assert item is not None
        assert item.metadata["cameo_root"] == "14"
        assert item.metadata["cameo_code"] == "140"
        assert item.metadata["category"] == "protest"
        assert item.metadata["goldstein_scale"] == -3.5
        assert item.metadata["avg_tone"] == -1.2
        assert item.metadata["num_mentions"] == 25

    def test_gdelt_date_parsing(self) -> None:
        adapter = GDELTAdapter({})
        row = _build_gdelt_row(date="20250601")
        item = adapter._row_to_raw_item(row)
        assert item is not None
        assert item.published_at == datetime(2025, 6, 1, tzinfo=UTC)

    def test_invalid_date_returns_none_published_at(self) -> None:
        adapter = GDELTAdapter({})
        row = _build_gdelt_row(date="BADDATE")
        item = adapter._row_to_raw_item(row)
        assert item is not None
        assert item.published_at is None

    def test_unknown_cameo_code_maps_to_unknown(self) -> None:
        adapter = GDELTAdapter({})
        row = _build_gdelt_row(event_root_code="99")
        item = adapter._row_to_raw_item(row)
        assert item is not None
        assert item.metadata["category"] == "unknown"


# =========================================================================
# Country filtering
# =========================================================================

class TestCountryFiltering:
    """Test that the country filter in fetch() correctly limits results."""

    @pytest.mark.asyncio
    async def test_focus_countries_filter_keeps_matching_rows(self) -> None:
        """Rows with actor countries in focus_countries should pass."""
        rows = [
            _build_gdelt_row(event_id="111", actor1_country="DA", actor2_country="US"),
        ]
        csv_text = _rows_to_csv_text(rows)
        zip_bytes = _csv_text_to_zip(csv_text)

        lastupdate_resp = httpx.Response(
            200,
            content=_make_lastupdate_response().encode(),
            request=httpx.Request("GET", "http://example.com"),
        )
        csv_zip_resp = httpx.Response(
            200,
            content=zip_bytes,
            request=httpx.Request("GET", "http://example.com"),
        )

        client = _mock_async_client({
            "lastupdate": lastupdate_resp,
            "export.CSV.zip": csv_zip_resp,
        })

        adapter = GDELTAdapter({"focus_countries": ["DA", "US"]})

        with patch("app.adapters.gdelt.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()

        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_focus_countries_filter_excludes_non_matching_rows(self) -> None:
        """Rows whose actor countries are NOT in focus_countries should be excluded."""
        rows = [
            _build_gdelt_row(event_id="111", actor1_country="ZZ", actor2_country="YY"),
        ]
        csv_text = _rows_to_csv_text(rows)
        zip_bytes = _csv_text_to_zip(csv_text)

        lastupdate_resp = httpx.Response(
            200,
            content=_make_lastupdate_response().encode(),
            request=httpx.Request("GET", "http://example.com"),
        )
        csv_zip_resp = httpx.Response(
            200,
            content=zip_bytes,
            request=httpx.Request("GET", "http://example.com"),
        )

        client = _mock_async_client({
            "lastupdate": lastupdate_resp,
            "export.CSV.zip": csv_zip_resp,
        })

        adapter = GDELTAdapter({"focus_countries": ["DA", "US"]})

        with patch("app.adapters.gdelt.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()

        assert len(items) == 0

    @pytest.mark.asyncio
    async def test_empty_focus_countries_returns_all(self) -> None:
        """With an empty focus_countries list, all rows should be included."""
        rows = [
            _build_gdelt_row(event_id="111", actor1_country="ZZ", actor2_country="YY"),
            _build_gdelt_row(event_id="222", actor1_country="XX", actor2_country="WW"),
        ]
        csv_text = _rows_to_csv_text(rows)
        zip_bytes = _csv_text_to_zip(csv_text)

        lastupdate_resp = httpx.Response(
            200,
            content=_make_lastupdate_response().encode(),
            request=httpx.Request("GET", "http://example.com"),
        )
        csv_zip_resp = httpx.Response(
            200,
            content=zip_bytes,
            request=httpx.Request("GET", "http://example.com"),
        )

        client = _mock_async_client({
            "lastupdate": lastupdate_resp,
            "export.CSV.zip": csv_zip_resp,
        })

        adapter = GDELTAdapter({"focus_countries": []})

        with patch("app.adapters.gdelt.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()

        assert len(items) == 2


# =========================================================================
# Full fetch() flow
# =========================================================================

class TestGDELTAdapterFetch:
    """Test the full async fetch() with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_fetch_success(self) -> None:
        """Successful fetch should return parsed RawItems."""
        rows = [
            _build_gdelt_row(event_id="111", actor1_country="DA"),
            _build_gdelt_row(event_id="222", actor1_country="US"),
        ]
        csv_text = _rows_to_csv_text(rows)
        zip_bytes = _csv_text_to_zip(csv_text)

        lastupdate_resp = httpx.Response(
            200,
            content=_make_lastupdate_response().encode(),
            request=httpx.Request("GET", "http://example.com"),
        )
        csv_zip_resp = httpx.Response(
            200,
            content=zip_bytes,
            request=httpx.Request("GET", "http://example.com"),
        )

        client = _mock_async_client({
            "lastupdate": lastupdate_resp,
            "export.CSV.zip": csv_zip_resp,
        })

        adapter = GDELTAdapter({"focus_countries": ["DA", "US"]})

        with patch("app.adapters.gdelt.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()

        assert len(items) == 2
        assert all(isinstance(i, RawItem) for i in items)

    @pytest.mark.asyncio
    async def test_fetch_http_error_returns_empty(self) -> None:
        """An HTTP error during fetch should return an empty list."""
        async def mock_get(url: str, **kwargs: Any) -> httpx.Response:
            raise httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("GET", url),
                response=httpx.Response(500),
            )

        client = AsyncMock()
        client.get = mock_get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        adapter = GDELTAdapter({"focus_countries": ["DA"]})

        with patch("app.adapters.gdelt.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()

        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_no_export_url_in_lastupdate(self) -> None:
        """If lastupdate.txt has no export URL, fetch should return empty."""
        bad_lastupdate = "some random text with no csv zip urls\n"
        lastupdate_resp = httpx.Response(
            200,
            content=bad_lastupdate.encode(),
            request=httpx.Request("GET", "http://example.com"),
        )

        client = _mock_async_client({"lastupdate": lastupdate_resp})
        adapter = GDELTAdapter({"focus_countries": ["DA"]})

        with patch("app.adapters.gdelt.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()

        assert items == []


# =========================================================================
# Helper methods
# =========================================================================

class TestGDELTHelpers:

    def test_safe_col_valid_index(self) -> None:
        row = ["a", " b ", "c"]
        assert GDELTAdapter._safe_col(row, 1) == "b"

    def test_safe_col_out_of_range(self) -> None:
        row = ["a"]
        assert GDELTAdapter._safe_col(row, 5) == ""

    def test_safe_float_valid(self) -> None:
        row = ["", "3.14"]
        assert GDELTAdapter._safe_float(row, 1) == 3.14

    def test_safe_float_empty(self) -> None:
        row = ["", ""]
        assert GDELTAdapter._safe_float(row, 1) is None

    def test_safe_float_out_of_range(self) -> None:
        assert GDELTAdapter._safe_float([], 0) is None

    def test_safe_int_valid(self) -> None:
        row = ["42"]
        assert GDELTAdapter._safe_int(row, 0) == 42

    def test_safe_int_invalid_string(self) -> None:
        row = ["abc"]
        assert GDELTAdapter._safe_int(row, 0) is None

    def test_parse_gdelt_date_valid(self) -> None:
        assert GDELTAdapter._parse_gdelt_date("20250115") == datetime(
            2025, 1, 15, tzinfo=UTC
        )

    def test_parse_gdelt_date_empty(self) -> None:
        assert GDELTAdapter._parse_gdelt_date("") is None

    def test_parse_gdelt_date_short(self) -> None:
        assert GDELTAdapter._parse_gdelt_date("2025") is None

    def test_parse_gdelt_date_invalid(self) -> None:
        assert GDELTAdapter._parse_gdelt_date("XXXXXXXX") is None

    def test_get_name(self) -> None:
        adapter = GDELTAdapter({})
        assert adapter.get_name() == "gdelt"
