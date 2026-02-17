"""Tests for app.pipeline.geocoder — Geocoder (Nominatim).

All HTTP calls are mocked.  No real network requests are made.
"""

from __future__ import annotations

import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.pipeline.geocoder import Geocoder, GeoResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _nominatim_json(
    display_name: str = "Copenhagen, Denmark",
    lat: str = "55.6761",
    lon: str = "12.5683",
    country: str = "Denmark",
    state: str | None = "Capital Region",
) -> list[dict[str, Any]]:
    """Build a Nominatim JSON response list."""
    address: dict[str, Any] = {"country": country}
    if state:
        address["state"] = state
    return [
        {
            "display_name": display_name,
            "lat": lat,
            "lon": lon,
            "address": address,
        }
    ]


def _make_nominatim_response(
    data: list[dict[str, Any]] | None = None,
    status_code: int = 200,
) -> httpx.Response:
    """Build an httpx.Response for Nominatim."""
    payload = data if data is not None else []
    return httpx.Response(
        status_code=status_code,
        content=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://nominatim.openstreetmap.org/search"),
    )


def _mock_async_client(response: httpx.Response) -> MagicMock:
    """Build a mock httpx.AsyncClient that returns *response* for every GET."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# =========================================================================
# Basic geocoding
# =========================================================================

class TestGeocoder:

    @pytest.mark.asyncio
    async def test_geocode_success(self) -> None:
        """A successful Nominatim response should return a GeoResult."""
        data = _nominatim_json()
        resp = _make_nominatim_response(data)
        client = _mock_async_client(resp)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            result = await geocoder.geocode("Copenhagen, Denmark")

        assert result is not None
        assert isinstance(result, GeoResult)
        assert result.latitude == pytest.approx(55.6761, abs=0.001)
        assert result.longitude == pytest.approx(12.5683, abs=0.001)
        assert result.country == "Denmark"
        assert result.region == "Capital Region"

    @pytest.mark.asyncio
    async def test_geocode_empty_results(self) -> None:
        """If Nominatim returns no results, geocode() should return None."""
        resp = _make_nominatim_response([])
        client = _mock_async_client(resp)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            result = await geocoder.geocode("Nonexistent Place XYZ")

        assert result is None

    @pytest.mark.asyncio
    async def test_geocode_empty_string_returns_none(self) -> None:
        """An empty location name should return None without making a request."""
        geocoder = Geocoder(rate_limit=0.0)
        result = await geocoder.geocode("")
        assert result is None

    @pytest.mark.asyncio
    async def test_geocode_whitespace_only_returns_none(self) -> None:
        geocoder = Geocoder(rate_limit=0.0)
        result = await geocoder.geocode("   ")
        assert result is None


# =========================================================================
# Cache behaviour
# =========================================================================

class TestGeocoderCache:

    @pytest.mark.asyncio
    async def test_second_call_uses_cache(self) -> None:
        """After a successful geocode, the second call should not make an HTTP request."""
        data = _nominatim_json()
        resp = _make_nominatim_response(data)
        client = _mock_async_client(resp)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            result1 = await geocoder.geocode("Copenhagen")
            result2 = await geocoder.geocode("Copenhagen")

        # Both results should be identical
        assert result1 == result2
        # The HTTP client should have been created only once (for the first call)
        # We verify by checking the mock was entered once
        assert client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_is_case_insensitive(self) -> None:
        """Cache keys should be lowercased so 'BERLIN' and 'berlin' hit the same entry."""
        data = _nominatim_json(display_name="Berlin, Germany", lat="52.52", lon="13.405")
        resp = _make_nominatim_response(data)
        client = _mock_async_client(resp)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            await geocoder.geocode("BERLIN")
            await geocoder.geocode("berlin")
            await geocoder.geocode("Berlin")

        assert client.get.await_count == 1

    @pytest.mark.asyncio
    async def test_cache_eviction(self) -> None:
        """When cache reaches maxsize, the oldest entry should be evicted."""
        data = _nominatim_json()
        resp = _make_nominatim_response(data)
        client = _mock_async_client(resp)

        geocoder = Geocoder(rate_limit=0.0, cache_maxsize=2)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            await geocoder.geocode("City A")
            await geocoder.geocode("City B")
            await geocoder.geocode("City C")  # should evict "City A"

        assert "city a" not in geocoder._cache
        assert "city b" in geocoder._cache
        assert "city c" in geocoder._cache

    @pytest.mark.asyncio
    async def test_none_result_is_cached(self) -> None:
        """A None result (no matches) should also be cached to avoid repeat lookups."""
        resp = _make_nominatim_response([])
        client = _mock_async_client(resp)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            result1 = await geocoder.geocode("Nowhere Land")
            result2 = await geocoder.geocode("Nowhere Land")

        assert result1 is None
        assert result2 is None
        assert client.get.await_count == 1


# =========================================================================
# Rate limiting
# =========================================================================

class TestGeocoderRateLimit:

    @pytest.mark.asyncio
    async def test_rate_limiting_enforced(self) -> None:
        """Consecutive requests should be spaced by at least rate_limit seconds."""
        data = _nominatim_json()
        resp = _make_nominatim_response(data)
        client = _mock_async_client(resp)

        rate_limit = 0.1  # 100 ms -- fast enough for tests
        geocoder = Geocoder(rate_limit=rate_limit)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            t0 = time.monotonic()
            await geocoder.geocode("Place A")
            await geocoder.geocode("Place B")  # different key, so no cache hit
            t1 = time.monotonic()

        # The second request should have waited ~rate_limit seconds
        elapsed = t1 - t0
        assert elapsed >= rate_limit * 0.9  # allow small timing margin

    @pytest.mark.asyncio
    async def test_zero_rate_limit_no_delay(self) -> None:
        """With rate_limit=0, there should be no artificial delay."""
        data = _nominatim_json()
        resp = _make_nominatim_response(data)
        client = _mock_async_client(resp)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            t0 = time.monotonic()
            await geocoder.geocode("Fast A")
            await geocoder.geocode("Fast B")
            t1 = time.monotonic()

        assert t1 - t0 < 0.5  # should be very fast


# =========================================================================
# Error handling
# =========================================================================

class TestGeocoderErrors:

    @pytest.mark.asyncio
    async def test_http_status_error_returns_none(self) -> None:
        """A 4xx/5xx HTTP error should return None, not raise."""
        error_resp = httpx.Response(
            429,
            content=b"Rate limited",
            request=httpx.Request("GET", "https://nominatim.openstreetmap.org/search"),
        )

        async def mock_get(*args: Any, **kwargs: Any) -> httpx.Response:
            raise httpx.HTTPStatusError(
                "Rate limited",
                request=httpx.Request("GET", "https://nominatim.openstreetmap.org/search"),
                response=error_resp,
            )

        client = AsyncMock()
        client.get = mock_get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            result = await geocoder.geocode("Some Place")

        assert result is None

    @pytest.mark.asyncio
    async def test_network_timeout_returns_none(self) -> None:
        """A network timeout should return None."""
        async def mock_get(*args: Any, **kwargs: Any) -> httpx.Response:
            raise httpx.ReadTimeout("Timed out")

        client = AsyncMock()
        client.get = mock_get
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            result = await geocoder.geocode("Timeout City")

        assert result is None

    @pytest.mark.asyncio
    async def test_malformed_json_returns_none(self) -> None:
        """If Nominatim returns non-JSON, geocode should return None."""
        resp = httpx.Response(
            200,
            content=b"this is not json",
            request=httpx.Request("GET", "https://nominatim.openstreetmap.org/search"),
        )
        client = _mock_async_client(resp)

        geocoder = Geocoder(rate_limit=0.0)

        with patch("app.pipeline.geocoder.httpx.AsyncClient", return_value=client):
            result = await geocoder.geocode("Bad JSON City")

        assert result is None


# =========================================================================
# GeoResult dataclass
# =========================================================================

class TestGeoResult:

    def test_creation(self) -> None:
        r = GeoResult(name="Berlin", latitude=52.52, longitude=13.405, country="Germany")
        assert r.name == "Berlin"
        assert r.latitude == 52.52
        assert r.longitude == 13.405
        assert r.country == "Germany"
        assert r.region is None

    def test_frozen(self) -> None:
        r = GeoResult(name="Berlin", latitude=52.52, longitude=13.405)
        with pytest.raises(AttributeError):
            r.name = "changed"  # type: ignore[misc]

    def test_equality(self) -> None:
        a = GeoResult(name="Berlin", latitude=52.52, longitude=13.405)
        b = GeoResult(name="Berlin", latitude=52.52, longitude=13.405)
        assert a == b
