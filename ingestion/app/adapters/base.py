"""Abstract base class and shared data structures for source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class RawItem:
    """Normalised representation of a single item fetched from any source."""

    source_adapter: str
    external_id: str
    title: str
    content: str | None = None
    summary: str | None = None
    authors: list[str] = field(default_factory=list)
    published_at: datetime | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-compatible dictionary."""
        return {
            "source_adapter": self.source_adapter,
            "external_id": self.external_id,
            "title": self.title,
            "content": self.content,
            "summary": self.summary,
            "authors": self.authors,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "source_url": self.source_url,
            "metadata": self.metadata,
        }


class SourceAdapter(ABC):
    """Base class that every ingestion source adapter must implement.

    Subclasses are expected to:
      1. Accept a *source_config* dict that carries adapter-specific parameters
         (feed URL, API key, country filter, etc.).
      2. Implement ``fetch()`` which returns a list of ``RawItem`` objects.
      3. Implement ``get_name()`` returning a stable human-readable identifier.
    """

    def __init__(self, source_config: dict[str, Any]) -> None:
        self.source_config = source_config

    @abstractmethod
    async def fetch(self) -> list[RawItem]:
        """Fetch new items from the upstream source.

        Returns a list of ``RawItem`` instances ready for pipeline processing.
        """

    @abstractmethod
    def get_name(self) -> str:
        """Return a unique, stable name for this adapter (e.g. ``'rss'``)."""
