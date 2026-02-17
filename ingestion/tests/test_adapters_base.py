"""Tests for app.adapters.base — RawItem and SourceAdapter ABC."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from app.adapters.base import RawItem, SourceAdapter


# =========================================================================
# RawItem creation
# =========================================================================

class TestRawItemCreation:
    """Verify that RawItem can be constructed with minimal and full data."""

    def test_minimal_fields(self, minimal_raw_item: RawItem) -> None:
        """RawItem with only required fields should have sensible defaults."""
        item = minimal_raw_item
        assert item.source_adapter == "test"
        assert item.external_id == "abc123"
        assert item.title == "Minimal Item"
        assert item.content is None
        assert item.summary is None
        assert item.authors == []
        assert item.published_at is None
        assert item.source_url is None
        assert item.metadata == {}

    def test_all_fields_populated(self, full_raw_item: RawItem) -> None:
        """RawItem with every field should preserve all values."""
        item = full_raw_item
        assert item.source_adapter == "rss"
        assert item.external_id == "full-item-001"
        assert item.title == "Full Article Title"
        assert item.content == "This is the full article content with details."
        assert item.summary == "A brief summary of the article."
        assert item.authors == ["Alice Smith", "Bob Jones"]
        assert item.published_at == datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert item.source_url == "https://example.com/article/1"
        assert "feed_url" in item.metadata
        assert "tags" in item.metadata

    def test_frozen_dataclass_is_immutable(self, minimal_raw_item: RawItem) -> None:
        """RawItem is frozen -- attribute assignment should raise."""
        with pytest.raises(AttributeError):
            minimal_raw_item.title = "changed"  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        """Two RawItems with identical fields should be equal."""
        a = RawItem(source_adapter="x", external_id="1", title="T")
        b = RawItem(source_adapter="x", external_id="1", title="T")
        assert a == b

    def test_inequality_different_external_id(self) -> None:
        a = RawItem(source_adapter="x", external_id="1", title="T")
        b = RawItem(source_adapter="x", external_id="2", title="T")
        assert a != b


# =========================================================================
# RawItem.to_dict() serialisation
# =========================================================================

class TestRawItemToDict:
    """Verify JSON-compatible serialisation."""

    def test_to_dict_minimal(self, minimal_raw_item: RawItem) -> None:
        d = minimal_raw_item.to_dict()
        assert isinstance(d, dict)
        assert d["source_adapter"] == "test"
        assert d["external_id"] == "abc123"
        assert d["title"] == "Minimal Item"
        assert d["content"] is None
        assert d["summary"] is None
        assert d["authors"] == []
        assert d["published_at"] is None
        assert d["source_url"] is None
        assert d["metadata"] == {}

    def test_to_dict_full(self, full_raw_item: RawItem) -> None:
        d = full_raw_item.to_dict()
        assert d["source_adapter"] == "rss"
        assert d["published_at"] == "2025-06-15T12:00:00+00:00"
        assert d["authors"] == ["Alice Smith", "Bob Jones"]
        assert d["metadata"]["tags"] == ["world", "politics"]

    def test_to_dict_published_at_isoformat(self) -> None:
        """published_at should be serialised to ISO 8601 when present."""
        dt = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        item = RawItem(source_adapter="s", external_id="e", title="t", published_at=dt)
        assert item.to_dict()["published_at"] == "2024-01-01T00:00:00+00:00"

    def test_to_dict_has_all_keys(self, full_raw_item: RawItem) -> None:
        """to_dict() must contain exactly the expected keys."""
        expected_keys = {
            "source_adapter",
            "external_id",
            "title",
            "content",
            "summary",
            "authors",
            "published_at",
            "source_url",
            "metadata",
        }
        assert set(full_raw_item.to_dict().keys()) == expected_keys


# =========================================================================
# SourceAdapter is abstract
# =========================================================================

class TestSourceAdapterABC:
    """SourceAdapter should not be directly instantiable."""

    def test_cannot_instantiate_directly(self) -> None:
        """Attempting to create a SourceAdapter should raise TypeError."""
        with pytest.raises(TypeError):
            SourceAdapter({})  # type: ignore[abstract]

    def test_concrete_subclass_works(self) -> None:
        """A subclass that implements all abstract methods should work."""

        class ConcreteAdapter(SourceAdapter):
            def get_name(self) -> str:
                return "concrete"

            async def fetch(self) -> list[RawItem]:
                return []

        adapter = ConcreteAdapter({"key": "val"})
        assert adapter.get_name() == "concrete"
        assert adapter.source_config == {"key": "val"}

    def test_partial_implementation_raises(self) -> None:
        """A subclass missing an abstract method should raise TypeError."""

        class Incomplete(SourceAdapter):
            def get_name(self) -> str:
                return "incomplete"
            # fetch() not implemented

        with pytest.raises(TypeError):
            Incomplete({})  # type: ignore[abstract]
