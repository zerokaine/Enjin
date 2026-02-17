"""Tests for app.adapters.__init__ — ADAPTER_REGISTRY and get_adapter().

No external services required.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.adapters import (
    ADAPTER_REGISTRY,
    CVRAdapter,
    GDELTAdapter,
    RSSAdapter,
    SourceAdapter,
    get_adapter,
)

# =========================================================================
# ADAPTER_REGISTRY contents
# =========================================================================

class TestAdapterRegistry:

    def test_registry_contains_rss(self) -> None:
        assert "rss" in ADAPTER_REGISTRY

    def test_registry_contains_gdelt(self) -> None:
        assert "gdelt" in ADAPTER_REGISTRY

    def test_registry_contains_cvr(self) -> None:
        assert "cvr" in ADAPTER_REGISTRY

    def test_registry_has_exactly_three_entries(self) -> None:
        assert len(ADAPTER_REGISTRY) == 3

    def test_registry_values_are_source_adapter_subclasses(self) -> None:
        for name, cls in ADAPTER_REGISTRY.items():
            assert issubclass(cls, SourceAdapter), (
                f"ADAPTER_REGISTRY['{name}'] is not a SourceAdapter subclass"
            )

    def test_rss_maps_to_correct_class(self) -> None:
        assert ADAPTER_REGISTRY["rss"] is RSSAdapter

    def test_gdelt_maps_to_correct_class(self) -> None:
        assert ADAPTER_REGISTRY["gdelt"] is GDELTAdapter

    def test_cvr_maps_to_correct_class(self) -> None:
        assert ADAPTER_REGISTRY["cvr"] is CVRAdapter


# =========================================================================
# get_adapter()
# =========================================================================

class TestGetAdapter:

    def test_get_adapter_rss(self) -> None:
        adapter = get_adapter("rss", {"feed_urls": ["https://example.com/feed"]})
        assert isinstance(adapter, RSSAdapter)
        assert adapter.get_name() == "rss"

    def test_get_adapter_gdelt(self) -> None:
        adapter = get_adapter("gdelt")
        assert isinstance(adapter, GDELTAdapter)
        assert adapter.get_name() == "gdelt"

    def test_get_adapter_cvr(self) -> None:
        adapter = get_adapter("cvr")
        assert isinstance(adapter, CVRAdapter)
        assert adapter.get_name() == "cvr"

    def test_get_adapter_with_source_config(self) -> None:
        """source_config should be passed through to the adapter."""
        config: dict[str, Any] = {"feed_urls": ["https://my.feed/rss"]}
        adapter = get_adapter("rss", config)
        assert adapter.source_config == config

    def test_get_adapter_none_config_defaults_to_empty_dict(self) -> None:
        adapter = get_adapter("rss", None)
        assert adapter.source_config == {}

    def test_get_adapter_no_config_defaults_to_empty_dict(self) -> None:
        adapter = get_adapter("rss")
        assert adapter.source_config == {}

    def test_get_adapter_unknown_name_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            get_adapter("nonexistent_adapter")

    def test_get_adapter_empty_string_raises_key_error(self) -> None:
        with pytest.raises(KeyError):
            get_adapter("")

    def test_get_adapter_case_sensitive(self) -> None:
        """Registry keys are lowercase; upper-case should raise."""
        with pytest.raises(KeyError):
            get_adapter("RSS")

        with pytest.raises(KeyError):
            get_adapter("Gdelt")
