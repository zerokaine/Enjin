"""Danish Central Business Registry (CVR) adapter.

Queries the public CVR API (https://cvrapi.dk) to retrieve company
information -- name, registration number, directors, address, and
industry classification -- and normalises it into ``RawItem`` objects.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.adapters.base import RawItem, SourceAdapter
from app.config import settings

logger = logging.getLogger(__name__)


class CVRAdapter(SourceAdapter):
    """Fetch company data from the Danish CVR public API."""

    def get_name(self) -> str:
        return "cvr"

    async def fetch(self) -> list[RawItem]:
        """Query CVR for each configured search term and return RawItems.

        ``source_config`` keys:
          - ``search_terms`` (list[str]): company names or CVR numbers to look up.
          - ``country`` (str): ISO country code, defaults to ``"dk"``.
        """
        search_terms: list[str] = self.source_config.get("search_terms", [])
        country = self.source_config.get("country", "dk")

        if not search_terms:
            logger.warning("CVRAdapter: no search_terms configured -- nothing to fetch")
            return []

        items: list[RawItem] = []
        for term in search_terms:
            try:
                result = await self._query_cvr(term, country)
                if result is not None:
                    items.append(result)
            except Exception:
                logger.exception("CVRAdapter: failed to query CVR for '%s'", term)

        logger.info("CVRAdapter: fetched %d company records", len(items))
        return items

    # ── network ──────────────────────────────────────────────────────
    async def _query_cvr(self, search_term: str, country: str) -> RawItem | None:
        api_url = self.source_config.get("api_url", settings.cvr_api_url)

        headers: dict[str, str] = {
            "User-Agent": "enjin-osint/0.1 (contact@enjin.dev)",
        }
        if settings.cvr_api_key:
            headers["Authorization"] = f"Bearer {settings.cvr_api_key}"

        params: dict[str, str] = {
            "search": search_term,
            "country": country,
        }

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(api_url, params=params, headers=headers)
            resp.raise_for_status()

        data: dict[str, Any] = resp.json()
        return self._response_to_raw_item(data)

    # ── mapping ──────────────────────────────────────────────────────
    def _response_to_raw_item(self, data: dict[str, Any]) -> RawItem | None:
        cvr_number = str(data.get("vat", "")).strip()
        company_name = (data.get("name") or "").strip()

        if not cvr_number and not company_name:
            return None

        external_id = hashlib.sha256(f"cvr:{cvr_number}".encode()).hexdigest()[:32]

        # Directors / owners (the API returns them under "owners" or "participants")
        owners_raw = data.get("owners") or []
        directors: list[str] = [o.get("name", "") for o in owners_raw if o.get("name")]

        # Address
        address_parts = [
            data.get("address", ""),
            data.get("zipcode", ""),
            data.get("city", ""),
        ]
        address = ", ".join(p for p in address_parts if p)

        # Industry
        industry_code = data.get("industrydesc", "")
        industry_code_raw = data.get("industrycode")

        # Build a human-readable title
        title = f"{company_name} (CVR: {cvr_number})" if cvr_number else company_name

        # Company start date
        start_date = self._parse_date(data.get("startdate"))

        return RawItem(
            source_adapter=self.get_name(),
            external_id=external_id,
            title=title,
            content=None,
            summary=f"Danish company: {company_name}. Industry: {industry_code}.",
            authors=directors,
            published_at=start_date,
            source_url=f"https://datacvr.virk.dk/enhed/virksomhed/{cvr_number}"
            if cvr_number
            else None,
            metadata={
                "cvr_number": cvr_number,
                "company_name": company_name,
                "directors": directors,
                "address": address,
                "industry_code": industry_code_raw,
                "industry_description": industry_code,
                "company_type": data.get("companydesc", ""),
                "email": data.get("email", ""),
                "phone": data.get("phone", ""),
                "country": data.get("country", "dk"),
                "status": data.get("status", ""),
            },
        )

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _parse_date(date_str: Any) -> datetime | None:
        if not date_str:
            return None
        for fmt in ("%d/%m - %Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(str(date_str), fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None
