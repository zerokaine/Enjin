"""Tests for app.adapters.cvr — CVRAdapter.

All HTTP calls to the CVR API are mocked.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.adapters.base import RawItem
from app.adapters.cvr import CVRAdapter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_async_client_for_cvr(response: httpx.Response) -> MagicMock:
    """Create a mock httpx.AsyncClient that always returns *response*."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def _make_cvr_response(data: dict[str, Any], status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response carrying JSON data."""
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(data).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://cvrapi.dk/api"),
    )


# =========================================================================
# fetch() with mocked HTTP
# =========================================================================

class TestCVRAdapterFetch:

    @pytest.mark.asyncio
    async def test_fetch_returns_raw_items(
        self,
        cvr_config: dict[str, Any],
        cvr_api_response_data: dict[str, Any],
    ) -> None:
        """Successful fetch should return a list of RawItem objects."""
        resp = _make_cvr_response(cvr_api_response_data)
        client = _mock_async_client_for_cvr(resp)

        adapter = CVRAdapter(cvr_config)

        with patch("app.adapters.cvr.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()

        assert len(items) == 1
        item = items[0]
        assert isinstance(item, RawItem)
        assert item.source_adapter == "cvr"
        assert "NOVO NORDISK" in item.title

    @pytest.mark.asyncio
    async def test_fetch_no_search_terms_returns_empty(
        self, cvr_config_empty: dict[str, Any]
    ) -> None:
        """With no search_terms configured, fetch() should return empty."""
        adapter = CVRAdapter(cvr_config_empty)
        items = await adapter.fetch()
        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_http_error_returns_empty(
        self, cvr_config: dict[str, Any]
    ) -> None:
        """An HTTP error should be caught and logged; result is empty list."""
        error_resp = httpx.Response(
            500,
            content=b"Internal Server Error",
            request=httpx.Request("GET", "https://cvrapi.dk/api"),
        )

        async def mock_get(*args: Any, **kwargs: Any) -> httpx.Response:
            raise httpx.HTTPStatusError(
                "Server Error",
                request=httpx.Request("GET", "https://cvrapi.dk/api"),
                response=error_resp,
            )

        client = AsyncMock()
        client.get = mock_get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        adapter = CVRAdapter(cvr_config)
        with patch("app.adapters.cvr.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()
        assert items == []

    @pytest.mark.asyncio
    async def test_fetch_multiple_search_terms(
        self, cvr_api_response_data: dict[str, Any]
    ) -> None:
        """Each search term should produce one query and potentially one item."""
        config = {
            "api_url": "https://cvrapi.dk/api",
            "search_terms": ["Novo Nordisk", "Maersk"],
            "country": "dk",
        }
        resp = _make_cvr_response(cvr_api_response_data)
        client = _mock_async_client_for_cvr(resp)

        adapter = CVRAdapter(config)
        with patch("app.adapters.cvr.httpx.AsyncClient", return_value=client):
            items = await adapter.fetch()

        assert len(items) == 2


# =========================================================================
# Company data extraction (_response_to_raw_item)
# =========================================================================

class TestResponseToRawItem:

    def test_full_response(self, cvr_api_response_data: dict[str, Any]) -> None:
        adapter = CVRAdapter({})
        item = adapter._response_to_raw_item(cvr_api_response_data)

        assert item is not None
        assert item.source_adapter == "cvr"
        assert "NOVO NORDISK" in item.title
        assert "10150817" in item.title  # CVR number in title
        assert item.metadata["cvr_number"] == "10150817"
        assert item.metadata["company_name"] == "NOVO NORDISK A/S"
        assert "Novo Alle 1" in item.metadata["address"]
        assert "2880" in item.metadata["address"]
        assert "Bagsvaerd" in item.metadata["address"]

    def test_directors_extracted(self, cvr_api_response_data: dict[str, Any]) -> None:
        adapter = CVRAdapter({})
        item = adapter._response_to_raw_item(cvr_api_response_data)
        assert item is not None
        assert "Novo Holdings A/S" in item.authors
        assert "Lars Fruergaard Jorgensen" in item.authors

    def test_industry_in_summary(self, cvr_api_response_data: dict[str, Any]) -> None:
        adapter = CVRAdapter({})
        item = adapter._response_to_raw_item(cvr_api_response_data)
        assert item is not None
        assert "pharmaceutical" in item.summary.lower()

    def test_source_url_links_to_datacvr(
        self, cvr_api_response_data: dict[str, Any]
    ) -> None:
        adapter = CVRAdapter({})
        item = adapter._response_to_raw_item(cvr_api_response_data)
        assert item is not None
        assert "datacvr.virk.dk" in item.source_url
        assert "10150817" in item.source_url

    def test_empty_response_returns_none(self) -> None:
        adapter = CVRAdapter({})
        item = adapter._response_to_raw_item({})
        assert item is None

    def test_response_with_only_name(self) -> None:
        adapter = CVRAdapter({})
        data = {"name": "Unnamed Company"}
        item = adapter._response_to_raw_item(data)
        assert item is not None
        assert item.metadata["company_name"] == "Unnamed Company"

    def test_response_with_no_owners(self) -> None:
        adapter = CVRAdapter({})
        data = {"vat": 12345678, "name": "Empty Owners Co"}
        item = adapter._response_to_raw_item(data)
        assert item is not None
        assert item.authors == []

    def test_metadata_contains_expected_keys(
        self, cvr_api_response_data: dict[str, Any]
    ) -> None:
        adapter = CVRAdapter({})
        item = adapter._response_to_raw_item(cvr_api_response_data)
        assert item is not None
        expected_keys = {
            "cvr_number",
            "company_name",
            "directors",
            "address",
            "industry_code",
            "industry_description",
            "company_type",
            "email",
            "phone",
            "country",
            "status",
        }
        assert set(item.metadata.keys()) == expected_keys


# =========================================================================
# Date parsing
# =========================================================================

class TestCVRDateParsing:

    def test_danish_format(self) -> None:
        """CVR dates like '01/02 - 1989' should be parsed."""
        result = CVRAdapter._parse_date("01/02 - 1989")
        assert result is not None
        assert result.year == 1989
        assert result.month == 2
        assert result.day == 1
        assert result.tzinfo == timezone.utc

    def test_iso_format(self) -> None:
        result = CVRAdapter._parse_date("2020-03-15")
        assert result is not None
        assert result.year == 2020
        assert result.month == 3
        assert result.day == 15

    def test_european_format(self) -> None:
        result = CVRAdapter._parse_date("15-03-2020")
        assert result is not None
        assert result.year == 2020

    def test_none_returns_none(self) -> None:
        assert CVRAdapter._parse_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert CVRAdapter._parse_date("") is None

    def test_invalid_date_returns_none(self) -> None:
        assert CVRAdapter._parse_date("not-a-date-at-all") is None


# =========================================================================
# get_name()
# =========================================================================

class TestCVRAdapterMeta:

    def test_get_name(self) -> None:
        adapter = CVRAdapter({})
        assert adapter.get_name() == "cvr"
