"""Tests for app.pipeline.extractor — EntityExtractor (spaCy NER).

If the ``en_core_web_sm`` spaCy model is not installed, these tests are
skipped gracefully.
"""

from __future__ import annotations

import pytest

# Gracefully skip the entire module if spaCy or the model is unavailable.
spacy = pytest.importorskip("spacy", reason="spaCy is required for extractor tests")

try:
    spacy.load("en_core_web_sm")
    _MODEL_AVAILABLE = True
except OSError:
    _MODEL_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _MODEL_AVAILABLE,
    reason="en_core_web_sm model not installed",
)

from app.pipeline.extractor import EntityExtractor, ExtractedEntity  # noqa: E402

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def extractor() -> EntityExtractor:
    """Create a single EntityExtractor for the entire test module (model load is expensive)."""
    # Reset the class-level singleton so we get a fresh load (useful if other
    # test modules have been mucking with the class attribute).
    EntityExtractor._nlp = None
    return EntityExtractor()


# =========================================================================
# Basic extraction
# =========================================================================

class TestExtractEntities:

    def test_extracts_person(self, extractor: EntityExtractor) -> None:
        """PERSON entities should be found."""
        entities = extractor.extract_entities("Tim Cook is the CEO of Apple Inc.")
        names = [e.name for e in entities]
        types = [e.type for e in entities]
        assert "person" in types or any("Tim" in n for n in names)

    def test_extracts_org(self, extractor: EntityExtractor) -> None:
        """ORG entities should be found."""
        entities = extractor.extract_entities(
            "Apple Inc. announced a partnership with Google."
        )
        org_names = [e.name for e in entities if e.type == "org"]
        assert len(org_names) >= 1

    def test_extracts_gpe_as_location(self, extractor: EntityExtractor) -> None:
        """GPE entities should be mapped to 'location' type."""
        entities = extractor.extract_entities(
            "The summit was held in Berlin, Germany."
        )
        location_names = [e.name for e in entities if e.type == "location"]
        assert len(location_names) >= 1

    def test_extracts_multiple_types(self, extractor: EntityExtractor) -> None:
        """A single text can yield PERSON, ORG, and location entities."""
        text = "Angela Merkel met with officials from the United Nations in Paris."
        entities = extractor.extract_entities(text)
        types_found = {e.type for e in entities}
        # We expect at least person and location; ORG depends on model confidence
        assert "person" in types_found or "location" in types_found

    def test_span_offsets_are_reasonable(self, extractor: EntityExtractor) -> None:
        """Span start and end should be within the text bounds."""
        text = "Microsoft was founded by Bill Gates."
        entities = extractor.extract_entities(text)
        for ent in entities:
            assert 0 <= ent.span_start < ent.span_end <= len(text)


# =========================================================================
# Deduplication
# =========================================================================

class TestDeduplication:

    def test_duplicate_names_are_merged(self, extractor: EntityExtractor) -> None:
        """If the same entity appears twice, only one should be returned."""
        text = "Apple released a new product. Apple also reported earnings."
        entities = extractor.extract_entities(text)
        apple_ents = [e for e in entities if "apple" in e.name.lower()]
        # After dedup, there should be at most one
        assert len(apple_ents) <= 1

    def test_different_types_are_not_merged(self, extractor: EntityExtractor) -> None:
        """Entities with the same name but different types should remain separate."""
        # This is a contrived test; the dedup key is (name.lower(), type)
        from app.pipeline.extractor import ExtractedEntity

        ent_person = ExtractedEntity(name="Jordan", type="person", span_start=0, span_end=6)
        ent_location = ExtractedEntity(name="Jordan", type="location", span_start=20, span_end=26)
        result = EntityExtractor._deduplicate([ent_person, ent_location])
        assert len(result) == 2

    def test_case_insensitive_dedup(self, extractor: EntityExtractor) -> None:
        """Dedup should treat 'Apple' and 'apple' as the same entity."""
        ent1 = ExtractedEntity(name="Apple", type="org", span_start=0, span_end=5)
        ent2 = ExtractedEntity(name="apple", type="org", span_start=20, span_end=25)
        result = EntityExtractor._deduplicate([ent1, ent2])
        assert len(result) == 1


# =========================================================================
# Edge cases
# =========================================================================

class TestExtractorEdgeCases:

    def test_empty_text_returns_empty_list(self, extractor: EntityExtractor) -> None:
        assert extractor.extract_entities("") == []

    def test_whitespace_only_returns_empty_list(self, extractor: EntityExtractor) -> None:
        assert extractor.extract_entities("   \n\t  ") == []

    def test_text_with_no_entities(self, extractor: EntityExtractor) -> None:
        """Purely generic text with no proper nouns should yield few/no entities."""
        entities = extractor.extract_entities("The quick brown fox jumps over the lazy dog.")
        # This might still find entities depending on the model, but it should not crash
        assert isinstance(entities, list)

    def test_entity_is_extracted_entity_dataclass(self, extractor: EntityExtractor) -> None:
        entities = extractor.extract_entities("Google headquarters is in Mountain View.")
        for ent in entities:
            assert isinstance(ent, ExtractedEntity)
            assert isinstance(ent.name, str)
            assert ent.type in ("person", "org", "location")
            assert isinstance(ent.span_start, int)
            assert isinstance(ent.span_end, int)
