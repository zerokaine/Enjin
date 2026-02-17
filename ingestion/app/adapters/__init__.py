"""Source adapter registry.

Import all concrete adapters and expose them through ``ADAPTER_REGISTRY``
so the task layer can instantiate them by name.
"""

from __future__ import annotations

from typing import Any

from app.adapters.base import RawItem, SourceAdapter
from app.adapters.cvr import CVRAdapter
from app.adapters.gdelt import GDELTAdapter
from app.adapters.rss import RSSAdapter

__all__ = [
    "ADAPTER_REGISTRY",
    "CVRAdapter",
    "GDELTAdapter",
    "RSSAdapter",
    "RawItem",
    "SourceAdapter",
    "get_adapter",
]

ADAPTER_REGISTRY: dict[str, type[SourceAdapter]] = {
    "rss": RSSAdapter,
    "gdelt": GDELTAdapter,
    "cvr": CVRAdapter,
}


def get_adapter(name: str, source_config: dict[str, Any] | None = None) -> SourceAdapter:
    """Instantiate an adapter by its registry name.

    Raises ``KeyError`` if the adapter name is not registered.
    """
    cls = ADAPTER_REGISTRY[name]
    return cls(source_config or {})
