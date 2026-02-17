"""Tests for Pydantic models in ``app.models.entities`` and ``app.models.events``."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.entities import (
    Asset,
    EntityBase,
    EntityResponse,
    Location,
    Organization,
    Person,
)
from app.models.events import (
    EventCategory,
    EventCreate,
    EventFeed,
    EventResponse,
)


# ========================================================================
# Entity models
# ========================================================================


class TestPerson:
    """Tests for the Person entity model."""

    def test_create_with_all_fields(self, sample_person_data: dict) -> None:
        person = Person(**sample_person_data)
        assert person.id == "person-001"
        assert person.name == "Jane Doe"
        assert person.type == "person"
        assert person.role == "CEO"
        assert person.nationality == "US"
        assert person.aliases == ["J. Doe"]
        assert person.metadata == {"source": "test"}

    def test_create_minimal(self) -> None:
        person = Person(id="p1", name="Alice")
        assert person.type == "person"
        assert person.role is None
        assert person.nationality is None
        assert person.aliases == []
        assert person.metadata == {}

    def test_default_type_is_person(self) -> None:
        person = Person(id="p1", name="Bob")
        assert person.type == "person"

    def test_name_min_length_rejected(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Person(id="p1", name="")
        errors = exc_info.value.errors()
        assert any(e["type"] == "string_too_short" for e in errors)


class TestOrganization:
    """Tests for the Organization entity model."""

    def test_create_with_all_fields(self, sample_organization_data: dict) -> None:
        org = Organization(**sample_organization_data)
        assert org.id == "org-001"
        assert org.name == "Acme Corp"
        assert org.type == "organization"
        assert org.org_type == "company"
        assert org.country == "US"
        assert org.aliases == ["Acme"]

    def test_create_minimal(self) -> None:
        org = Organization(id="o1", name="Initech")
        assert org.type == "organization"
        assert org.org_type is None
        assert org.country is None
        assert org.aliases == []

    def test_default_type_is_organization(self) -> None:
        org = Organization(id="o1", name="Globex")
        assert org.type == "organization"


class TestLocation:
    """Tests for the Location entity model."""

    def test_create_with_coordinates(self, sample_location_data: dict) -> None:
        loc = Location(**sample_location_data)
        assert loc.id == "loc-001"
        assert loc.name == "New York City"
        assert loc.type == "location"
        assert loc.latitude == pytest.approx(40.7128)
        assert loc.longitude == pytest.approx(-74.0060)
        assert loc.country == "US"
        assert loc.region == "New York"

    def test_create_without_coordinates(self) -> None:
        loc = Location(id="l1", name="Unknown Place")
        assert loc.latitude is None
        assert loc.longitude is None

    @pytest.mark.parametrize(
        "lat,lon",
        [
            (-90, -180),
            (90, 180),
            (0, 0),
        ],
        ids=["south-west-extreme", "north-east-extreme", "equator-prime-meridian"],
    )
    def test_valid_coordinate_bounds(self, lat: float, lon: float) -> None:
        loc = Location(id="l1", name="Test", latitude=lat, longitude=lon)
        assert loc.latitude == lat
        assert loc.longitude == lon

    @pytest.mark.parametrize(
        "lat,lon",
        [
            (-91, 0),
            (91, 0),
            (0, -181),
            (0, 181),
        ],
        ids=["lat-too-low", "lat-too-high", "lon-too-low", "lon-too-high"],
    )
    def test_invalid_coordinate_bounds(self, lat: float, lon: float) -> None:
        with pytest.raises(ValidationError):
            Location(id="l1", name="Bad", latitude=lat, longitude=lon)


class TestAsset:
    """Tests for the Asset entity model."""

    def test_create_with_all_fields(self, sample_asset_data: dict) -> None:
        asset = Asset(**sample_asset_data)
        assert asset.id == "asset-001"
        assert asset.name == "Luxury Yacht Oceania"
        assert asset.type == "asset"
        assert asset.asset_type == "vessel"
        assert asset.value == 5_000_000.0
        assert asset.currency == "USD"
        assert asset.owner_id == "person-001"

    def test_create_minimal(self) -> None:
        asset = Asset(id="a1", name="Misc Item")
        assert asset.type == "asset"
        assert asset.asset_type is None
        assert asset.value is None
        assert asset.currency is None
        assert asset.owner_id is None


class TestEntityResponse:
    """Tests for the EntityResponse wrapper."""

    def test_with_empty_relationships_and_events(self) -> None:
        entity = EntityBase(id="e1", name="Test Entity", type="person")
        resp = EntityResponse(entity=entity)
        assert resp.entity.id == "e1"
        assert resp.relationships == []
        assert resp.events == []

    def test_with_nested_data(self) -> None:
        entity = EntityBase(id="e1", name="Test", type="person")
        rels = [{"target": {"id": "e2", "name": "Other"}, "edges": []}]
        evts = [{"event": {"id": "ev1"}, "relationship": "INVOLVED_IN"}]
        resp = EntityResponse(entity=entity, relationships=rels, events=evts)
        assert len(resp.relationships) == 1
        assert resp.relationships[0]["target"]["id"] == "e2"
        assert len(resp.events) == 1
        assert resp.events[0]["relationship"] == "INVOLVED_IN"

    def test_serialization_roundtrip(self) -> None:
        entity = EntityBase(id="e1", name="X", type="person", metadata={"k": "v"})
        resp = EntityResponse(entity=entity, relationships=[], events=[])
        data = resp.model_dump()
        assert data["entity"]["id"] == "e1"
        assert data["entity"]["metadata"] == {"k": "v"}
        restored = EntityResponse(**data)
        assert restored.entity.id == "e1"


# ========================================================================
# Event models
# ========================================================================


class TestEventCategory:
    """Tests for the EventCategory enum."""

    def test_all_values(self) -> None:
        expected = {"political", "economic", "social", "legal", "security", "technology"}
        actual = {c.value for c in EventCategory}
        assert actual == expected

    @pytest.mark.parametrize("value", ["political", "economic", "social", "legal", "security", "technology"])
    def test_valid_category(self, value: str) -> None:
        assert EventCategory(value).value == value

    def test_invalid_category(self) -> None:
        with pytest.raises(ValueError):
            EventCategory("invalid_category")


class TestEventCreate:
    """Tests for the EventCreate request schema."""

    def test_create_with_all_fields(self, sample_event_create_data: dict) -> None:
        event = EventCreate(**sample_event_create_data)
        assert event.title == "Trade Agreement Signed"
        assert event.summary == "Major trade agreement signed between nations."
        assert event.category == EventCategory.economic
        assert event.location_name == "Geneva"
        assert event.latitude == pytest.approx(46.2044)
        assert event.longitude == pytest.approx(6.1432)
        assert event.source_url == "https://example.com/news/1"
        assert event.metadata == {"confidence": "high"}

    def test_create_minimal(self) -> None:
        event = EventCreate(title="Something happened")
        assert event.title == "Something happened"
        assert event.summary is None
        assert event.category is None
        assert event.occurred_at is None
        assert event.location_name is None
        assert event.latitude is None
        assert event.longitude is None
        assert event.source_url is None
        assert event.metadata == {}

    def test_title_cannot_be_empty(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            EventCreate(title="")
        errors = exc_info.value.errors()
        assert any(e["type"] == "string_too_short" for e in errors)

    def test_title_max_length(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            EventCreate(title="X" * 501)
        errors = exc_info.value.errors()
        assert any(e["type"] == "string_too_long" for e in errors)

    def test_invalid_category_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EventCreate(title="Test", category="not_a_category")

    @pytest.mark.parametrize(
        "lat,lon",
        [(-91, 0), (91, 0), (0, -181), (0, 181)],
        ids=["lat-low", "lat-high", "lon-low", "lon-high"],
    )
    def test_invalid_coordinates_rejected(self, lat: float, lon: float) -> None:
        with pytest.raises(ValidationError):
            EventCreate(title="Test", latitude=lat, longitude=lon)


class TestEventResponse:
    """Tests for the EventResponse schema."""

    def test_serialization(self) -> None:
        now = datetime(2025, 6, 15, 12, 0, tzinfo=timezone.utc)
        resp = EventResponse(
            id="event-1",
            title="Test Event",
            summary="A summary",
            category="economic",
            occurred_at=datetime(2025, 6, 15, 10, 30, tzinfo=timezone.utc),
            location_name="Geneva",
            latitude=46.2044,
            longitude=6.1432,
            source_url="https://example.com",
            created_at=now,
            connections=[{"entity": {"id": "e1"}, "relationship": "MENTIONS"}],
        )
        data = resp.model_dump()
        assert data["id"] == "event-1"
        assert data["title"] == "Test Event"
        assert data["category"] == "economic"
        assert len(data["connections"]) == 1

    def test_optional_fields_default_to_none(self) -> None:
        now = datetime.now(tz=timezone.utc)
        resp = EventResponse(id="ev1", title="Bare Event", created_at=now)
        assert resp.summary is None
        assert resp.category is None
        assert resp.occurred_at is None
        assert resp.location_name is None
        assert resp.latitude is None
        assert resp.longitude is None
        assert resp.source_url is None
        assert resp.connections == []


class TestEventFeed:
    """Tests for the EventFeed paginated response."""

    def test_pagination_fields(self) -> None:
        now = datetime.now(tz=timezone.utc)
        events = [
            EventResponse(id=f"ev{i}", title=f"Event {i}", created_at=now)
            for i in range(3)
        ]
        feed = EventFeed(events=events, total=50, page=2, per_page=20)
        assert len(feed.events) == 3
        assert feed.total == 50
        assert feed.page == 2
        assert feed.per_page == 20

    def test_empty_feed(self) -> None:
        feed = EventFeed(events=[], total=0, page=1, per_page=20)
        assert feed.events == []
        assert feed.total == 0

    def test_serialization_roundtrip(self) -> None:
        now = datetime.now(tz=timezone.utc)
        feed = EventFeed(
            events=[EventResponse(id="ev1", title="E", created_at=now)],
            total=1,
            page=1,
            per_page=20,
        )
        data = feed.model_dump()
        restored = EventFeed(**data)
        assert len(restored.events) == 1
        assert restored.total == 1
