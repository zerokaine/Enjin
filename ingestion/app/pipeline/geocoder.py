"""Geocoding via OpenStreetMap Nominatim.

Resolves location names (cities, countries, addresses) to geographic
coordinates using the Nominatim free-text search endpoint.  An in-memory
LRU cache and a per-request rate limiter ensure we respect the OSM
usage policy (max 1 request per second, valid User-Agent).

Reference: https://operations.osmfoundation.org/policies/nominatim/
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from functools import lru_cache

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"


@dataclass(frozen=True, slots=True)
class GeoResult:
    """Geocoding result for a single location."""

    name: str
    latitude: float
    longitude: float
    country: str | None = None
    region: str | None = None


class Geocoder:
    """Geocode location names via Nominatim with caching and rate limiting.

    Usage::

        geocoder = Geocoder()
        result = await geocoder.geocode("Copenhagen, Denmark")
    """

    def __init__(
        self,
        user_agent: str | None = None,
        rate_limit: float | None = None,
        cache_maxsize: int = 2048,
    ) -> None:
        self._user_agent = user_agent or settings.geocoder_user_agent
        self._rate_limit = rate_limit if rate_limit is not None else settings.geocoder_rate_limit
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

        # Build a simple LRU cache closure keyed on normalised location name.
        # We wrap the lru_cache in a sync function and call it from the async
        # method after the network request.
        self._cache: dict[str, GeoResult | None] = {}
        self._cache_maxsize = cache_maxsize

    async def geocode(self, location_name: str) -> GeoResult | None:
        """Resolve *location_name* to coordinates.

        Returns ``None`` if the location cannot be resolved or if the
        Nominatim API returns no results.
        """
        if not location_name or not location_name.strip():
            return None

        cache_key = location_name.strip().lower()

        # Check cache first
        if cache_key in self._cache:
            logger.debug("Geocoder: cache hit for '%s'", location_name)
            return self._cache[cache_key]

        # Rate-limit: ensure at least ``_rate_limit`` seconds between requests
        async with self._lock:
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < self._rate_limit:
                await asyncio.sleep(self._rate_limit - elapsed)

            result = await self._nominatim_search(location_name)
            self._last_request_time = time.monotonic()

        # Store in cache (evict oldest if at capacity)
        if len(self._cache) >= self._cache_maxsize:
            # Pop the first (oldest) entry
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]
        self._cache[cache_key] = result

        return result

    async def _nominatim_search(self, query: str) -> GeoResult | None:
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": "1",
            "addressdetails": "1",
        }
        headers = {"User-Agent": self._user_agent}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    _NOMINATIM_SEARCH_URL,
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()

            results = resp.json()
            if not results:
                logger.debug("Geocoder: no results for '%s'", query)
                return None

            top = results[0]
            address = top.get("address", {})

            return GeoResult(
                name=top.get("display_name", query),
                latitude=float(top["lat"]),
                longitude=float(top["lon"]),
                country=address.get("country"),
                region=address.get("state") or address.get("region"),
            )

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "Geocoder: Nominatim returned %d for '%s'",
                exc.response.status_code,
                query,
            )
            return None
        except Exception:
            logger.exception("Geocoder: unexpected error geocoding '%s'", query)
            return None
