"""GDELT 2.0 adapter.

Fetches events from the GDELT Global Knowledge Graph / event export and
maps them into ``RawItem`` objects.  GDELT uses CAMEO codes for event
classification -- this module provides a lightweight mapping to Enjin's
own event categories.

Reference: https://www.gdeltproject.org/data.html#rawdatafiles
"""

from __future__ import annotations

import csv
import hashlib
import io
import logging
from datetime import UTC, datetime

import httpx

from app.adapters.base import RawItem, SourceAdapter
from app.config import settings

logger = logging.getLogger(__name__)

# ── CAMEO root-code to Enjin category mapping ───────────────────────
CAMEO_CATEGORY_MAP: dict[str, str] = {
    "01": "public_statement",
    "02": "appeal",
    "03": "cooperation",
    "04": "consultation",
    "05": "diplomacy",
    "06": "material_cooperation",
    "07": "aid",
    "08": "concession",
    "09": "investigation",
    "10": "demand",
    "11": "disapproval",
    "12": "rejection",
    "13": "threat",
    "14": "protest",
    "15": "force_posture",
    "16": "reduce_relations",
    "17": "coercion",
    "18": "assault",
    "19": "fight",
    "20": "mass_violence",
}

# GDELT event export column indices (v2, 58-column format)
# Subset of the most useful columns:
COL_GLOBAL_EVENT_ID = 0
COL_DATE = 1                    # YYYYMMDD
COL_ACTOR1_NAME = 6
COL_ACTOR1_COUNTRY = 7
COL_ACTOR2_NAME = 16
COL_ACTOR2_COUNTRY = 17
COL_EVENT_ROOT_CODE = 26
COL_EVENT_CODE = 27
COL_QUAD_CLASS = 29
COL_GOLDSTEIN = 30
COL_NUM_MENTIONS = 31
COL_AVG_TONE = 34
COL_ACTOR1_GEO_LAT = 39
COL_ACTOR1_GEO_LONG = 40
COL_ACTOR2_GEO_LAT = 44
COL_ACTOR2_GEO_LONG = 45
COL_ACTION_GEO_FULLNAME = 49
COL_ACTION_GEO_LAT = 53
COL_ACTION_GEO_LONG = 54
COL_SOURCE_URL = 57


class GDELTAdapter(SourceAdapter):
    """Fetch and parse GDELT 2.0 event exports."""

    def get_name(self) -> str:
        return "gdelt"

    async def fetch(self) -> list[RawItem]:
        """Download the latest GDELT event CSV and convert to RawItems."""
        base_url = self.source_config.get("base_url", settings.gdelt_base_url)
        focus_countries = self.source_config.get(
            "focus_countries", settings.gdelt_focus_countries
        )

        try:
            last_update_url = await self._get_latest_export_url(base_url)
            if not last_update_url:
                return []

            csv_text = await self._download_csv(last_update_url)
            rows = self._parse_csv(csv_text)

            items: list[RawItem] = []
            for row in rows:
                item = self._row_to_raw_item(row)
                if item is None:
                    continue
                # Country filter
                country1 = self._safe_col(row, COL_ACTOR1_COUNTRY)
                country2 = self._safe_col(row, COL_ACTOR2_COUNTRY)
                if focus_countries and not (
                    country1 in focus_countries or country2 in focus_countries
                ):
                    continue
                items.append(item)

            logger.info(
                "GDELTAdapter: fetched %d items (%d after country filter)",
                len(rows),
                len(items),
            )
            return items

        except Exception:
            logger.exception("GDELTAdapter: fetch failed")
            return []

    # ── network helpers ──────────────────────────────────────────────
    async def _get_latest_export_url(self, base_url: str) -> str | None:
        """Query the GDELT last-update endpoint to discover the latest CSV URL."""
        # Use the well-known last-update file list to discover the latest CSV
        last_update_url = "http://data.gdeltproject.org/gdeltv2/lastupdate.txt"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(last_update_url)
            resp.raise_for_status()

        # lastupdate.txt has 3 lines; first line contains the export CSV zip URL
        for line in resp.text.strip().splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[2].endswith(".export.CSV.zip"):
                return parts[2]

        logger.warning("GDELTAdapter: could not find export URL in lastupdate.txt")
        return None

    async def _download_csv(self, url: str) -> str:
        """Download and decompress a GDELT export CSV zip."""
        import zipfile

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        buf = io.BytesIO(resp.content)
        with zipfile.ZipFile(buf) as zf:
            csv_name = [n for n in zf.namelist() if n.endswith(".CSV")][0]
            return zf.read(csv_name).decode("utf-8", errors="replace")

    # ── parsing ──────────────────────────────────────────────────────
    @staticmethod
    def _parse_csv(csv_text: str) -> list[list[str]]:
        reader = csv.reader(io.StringIO(csv_text), delimiter="\t")
        return list(reader)

    def _row_to_raw_item(self, row: list[str]) -> RawItem | None:
        if len(row) < 58:
            return None

        global_event_id = self._safe_col(row, COL_GLOBAL_EVENT_ID)
        if not global_event_id:
            return None

        external_id = hashlib.sha256(f"gdelt:{global_event_id}".encode()).hexdigest()[:32]

        actor1 = self._safe_col(row, COL_ACTOR1_NAME)
        actor2 = self._safe_col(row, COL_ACTOR2_NAME)
        event_code = self._safe_col(row, COL_EVENT_CODE)
        root_code = self._safe_col(row, COL_EVENT_ROOT_CODE)
        category = CAMEO_CATEGORY_MAP.get(root_code, "unknown")
        source_url = self._safe_col(row, COL_SOURCE_URL)

        title_parts = [p for p in [actor1, category.replace("_", " "), actor2] if p]
        title = " -- ".join(title_parts) or f"GDELT event {global_event_id}"

        published_at = self._parse_gdelt_date(self._safe_col(row, COL_DATE))

        tone = self._safe_float(row, COL_AVG_TONE)
        goldstein = self._safe_float(row, COL_GOLDSTEIN)
        location = self._safe_col(row, COL_ACTION_GEO_FULLNAME)
        lat = self._safe_float(row, COL_ACTION_GEO_LAT)
        lon = self._safe_float(row, COL_ACTION_GEO_LONG)

        actors = [a for a in [actor1, actor2] if a]

        return RawItem(
            source_adapter=self.get_name(),
            external_id=external_id,
            title=title,
            content=None,
            summary=f"CAMEO {event_code}: {category}",
            authors=actors,
            published_at=published_at,
            source_url=source_url or None,
            metadata={
                "gdelt_event_id": global_event_id,
                "cameo_code": event_code,
                "cameo_root": root_code,
                "category": category,
                "actor1": actor1,
                "actor1_country": self._safe_col(row, COL_ACTOR1_COUNTRY),
                "actor2": actor2,
                "actor2_country": self._safe_col(row, COL_ACTOR2_COUNTRY),
                "goldstein_scale": goldstein,
                "avg_tone": tone,
                "num_mentions": self._safe_int(row, COL_NUM_MENTIONS),
                "location": location,
                "latitude": lat,
                "longitude": lon,
            },
        )

    # ── helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _safe_col(row: list[str], idx: int) -> str:
        try:
            return row[idx].strip()
        except IndexError:
            return ""

    @staticmethod
    def _safe_float(row: list[str], idx: int) -> float | None:
        try:
            val = row[idx].strip()
            return float(val) if val else None
        except (IndexError, ValueError):
            return None

    @staticmethod
    def _safe_int(row: list[str], idx: int) -> int | None:
        try:
            val = row[idx].strip()
            return int(val) if val else None
        except (IndexError, ValueError):
            return None

    @staticmethod
    def _parse_gdelt_date(date_str: str) -> datetime | None:
        """Parse a GDELT YYYYMMDD date string."""
        if not date_str or len(date_str) < 8:
            return None
        try:
            return datetime.strptime(date_str[:8], "%Y%m%d").replace(tzinfo=UTC)
        except ValueError:
            return None
