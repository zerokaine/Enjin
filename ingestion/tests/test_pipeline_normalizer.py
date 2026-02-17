"""Tests for app.pipeline.normalizer — EntityNormalizer.

No external services are required.
"""

from __future__ import annotations

import pytest

from app.pipeline.extractor import ExtractedEntity
from app.pipeline.normalizer import EntityNormalizer, NormalisedEntity


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def normalizer() -> EntityNormalizer:
    """Default normalizer with default similarity threshold (0.85)."""
    return EntityNormalizer()


@pytest.fixture
def strict_normalizer() -> EntityNormalizer:
    """Normalizer with a high (strict) similarity threshold."""
    return EntityNormalizer(similarity_threshold=0.99)


@pytest.fixture
def loose_normalizer() -> EntityNormalizer:
    """Normalizer with a low (loose) similarity threshold."""
    return EntityNormalizer(similarity_threshold=0.50)


# =========================================================================
# normalize_name()
# =========================================================================

class TestNormalizeName:

    def test_strips_whitespace(self) -> None:
        assert EntityNormalizer.normalize_name("  Alice Smith  ") == "Alice Smith"

    def test_collapses_internal_whitespace(self) -> None:
        assert EntityNormalizer.normalize_name("Alice    Smith") == "Alice Smith"

    def test_title_cases(self) -> None:
        assert EntityNormalizer.normalize_name("alice smith") == "Alice Smith"

    def test_mixed_case(self) -> None:
        assert EntityNormalizer.normalize_name("aLiCe sMiTh") == "Alice Smith"

    def test_all_caps(self) -> None:
        assert EntityNormalizer.normalize_name("ALICE SMITH") == "Alice Smith"

    def test_unicode_normalisation(self) -> None:
        """NFC normalisation should compose diacritics."""
        # U+0065 (e) + U+0301 (combining acute accent) -> U+00E9 (e with acute)
        decomposed = "caf\u0065\u0301"
        result = EntityNormalizer.normalize_name(decomposed)
        assert "\u00e9" in result.lower()  # should be composed form

    def test_unicode_accented_characters(self) -> None:
        assert EntityNormalizer.normalize_name("  jOrgen  hAnsen  ") == "Jorgen Hansen"

    def test_empty_string(self) -> None:
        assert EntityNormalizer.normalize_name("") == ""

    def test_newlines_and_tabs(self) -> None:
        assert EntityNormalizer.normalize_name("Alice\n\tSmith") == "Alice Smith"

    def test_single_word(self) -> None:
        assert EntityNormalizer.normalize_name("denmark") == "Denmark"


# =========================================================================
# deduplicate_entities()
# =========================================================================

class TestDeduplicateEntities:

    def test_identical_entities_merged(self, normalizer: EntityNormalizer) -> None:
        """Two entities with the same name and type should be merged."""
        entities = [
            ExtractedEntity(name="Apple", type="org", span_start=0, span_end=5),
            ExtractedEntity(name="Apple", type="org", span_start=50, span_end=55),
        ]
        result = normalizer.deduplicate_entities(entities)
        assert len(result) == 1
        assert result[0].occurrences == 2

    def test_fuzzy_match_merges_similar_names(self, normalizer: EntityNormalizer) -> None:
        """Entities with slightly different spelling should be merged."""
        entities = [
            ExtractedEntity(name="United Nations", type="org", span_start=0, span_end=14),
            ExtractedEntity(name="United Nation", type="org", span_start=50, span_end=63),
        ]
        result = normalizer.deduplicate_entities(entities)
        # 'United Nations' vs 'United Nation' similarity should be above 0.85
        assert len(result) == 1
        assert result[0].occurrences == 2

    def test_different_types_not_merged(self, normalizer: EntityNormalizer) -> None:
        """Entities with the same name but different types must NOT be merged."""
        entities = [
            ExtractedEntity(name="Jordan", type="person", span_start=0, span_end=6),
            ExtractedEntity(name="Jordan", type="location", span_start=20, span_end=26),
        ]
        result = normalizer.deduplicate_entities(entities)
        assert len(result) == 2
        types = {e.type for e in result}
        assert types == {"person", "location"}

    def test_very_different_names_not_merged(self, normalizer: EntityNormalizer) -> None:
        """Entities with very different names should stay separate."""
        entities = [
            ExtractedEntity(name="Apple", type="org", span_start=0, span_end=5),
            ExtractedEntity(name="Microsoft", type="org", span_start=20, span_end=29),
        ]
        result = normalizer.deduplicate_entities(entities)
        assert len(result) == 2

    def test_empty_list_returns_empty(self, normalizer: EntityNormalizer) -> None:
        result = normalizer.deduplicate_entities([])
        assert result == []

    def test_single_entity_returns_one(self, normalizer: EntityNormalizer) -> None:
        entities = [
            ExtractedEntity(name="Google", type="org", span_start=0, span_end=6),
        ]
        result = normalizer.deduplicate_entities(entities)
        assert len(result) == 1
        assert result[0].occurrences == 1

    def test_source_spans_accumulated(self, normalizer: EntityNormalizer) -> None:
        """Merged entities should accumulate all source spans."""
        entities = [
            ExtractedEntity(name="Apple", type="org", span_start=0, span_end=5),
            ExtractedEntity(name="Apple", type="org", span_start=50, span_end=55),
            ExtractedEntity(name="Apple", type="org", span_start=100, span_end=105),
        ]
        result = normalizer.deduplicate_entities(entities)
        assert len(result) == 1
        assert len(result[0].source_spans) == 3
        assert result[0].occurrences == 3


# =========================================================================
# merge_entity()
# =========================================================================

class TestMergeEntity:

    def test_increments_occurrences(self) -> None:
        existing = NormalisedEntity(
            name="Apple",
            type="org",
            occurrences=2,
            source_spans=[(0, 5), (20, 25)],
        )
        new = ExtractedEntity(name="Apple", type="org", span_start=50, span_end=55)
        EntityNormalizer.merge_entity(existing, new)
        assert existing.occurrences == 3
        assert len(existing.source_spans) == 3
        assert (50, 55) in existing.source_spans

    def test_adopts_longer_name(self) -> None:
        """If the new entity has a longer normalized name, it becomes canonical."""
        existing = NormalisedEntity(
            name="Un",
            type="org",
            occurrences=1,
            source_spans=[(0, 2)],
        )
        new = ExtractedEntity(
            name="United Nations",
            type="org",
            span_start=10,
            span_end=24,
        )
        EntityNormalizer.merge_entity(existing, new)
        assert existing.name == "United Nations"

    def test_keeps_existing_if_shorter_new(self) -> None:
        """If the existing name is already longer, it should be kept."""
        existing = NormalisedEntity(
            name="United Nations",
            type="org",
            occurrences=1,
            source_spans=[(0, 14)],
        )
        new = ExtractedEntity(name="UN", type="org", span_start=50, span_end=52)
        EntityNormalizer.merge_entity(existing, new)
        assert existing.name == "United Nations"


# =========================================================================
# Fuzzy matching threshold
# =========================================================================

class TestFuzzyMatchingThreshold:

    def test_strict_threshold_prevents_merge(self, strict_normalizer: EntityNormalizer) -> None:
        """With threshold=0.99, even small differences prevent merging."""
        entities = [
            ExtractedEntity(name="United Nations", type="org", span_start=0, span_end=14),
            ExtractedEntity(name="United Nation", type="org", span_start=50, span_end=63),
        ]
        result = strict_normalizer.deduplicate_entities(entities)
        # These are similar but not 99% identical
        assert len(result) == 2

    def test_loose_threshold_merges_different_names(
        self, loose_normalizer: EntityNormalizer
    ) -> None:
        """With threshold=0.50, loosely similar names should merge."""
        entities = [
            ExtractedEntity(name="Apple Inc", type="org", span_start=0, span_end=9),
            ExtractedEntity(name="Apple Corp", type="org", span_start=30, span_end=40),
        ]
        result = loose_normalizer.deduplicate_entities(entities)
        # 'Apple Inc' vs 'Apple Corp' should be above 0.50 similarity
        assert len(result) == 1

    def test_default_threshold_is_085(self) -> None:
        normalizer = EntityNormalizer()
        assert normalizer._threshold == 0.85


# =========================================================================
# Similarity function
# =========================================================================

class TestSimilarity:

    def test_identical_strings(self) -> None:
        assert EntityNormalizer._similarity("hello", "hello") == 1.0

    def test_completely_different(self) -> None:
        ratio = EntityNormalizer._similarity("abc", "xyz")
        assert ratio < 0.5

    def test_empty_string_returns_zero(self) -> None:
        assert EntityNormalizer._similarity("", "hello") == 0.0
        assert EntityNormalizer._similarity("hello", "") == 0.0
        assert EntityNormalizer._similarity("", "") == 0.0

    def test_case_insensitive(self) -> None:
        """Similarity should be case-insensitive."""
        assert EntityNormalizer._similarity("Apple", "apple") == 1.0

    def test_partial_match(self) -> None:
        ratio = EntityNormalizer._similarity("United Nations", "United Nation")
        assert 0.85 < ratio < 1.0


# =========================================================================
# NormalisedEntity dataclass
# =========================================================================

class TestNormalisedEntity:

    def test_defaults(self) -> None:
        ent = NormalisedEntity(name="Test", type="org")
        assert ent.occurrences == 1
        assert ent.source_spans == []
        assert ent.metadata == {}

    def test_mutable(self) -> None:
        """NormalisedEntity is NOT frozen, so mutations should work."""
        ent = NormalisedEntity(name="Test", type="org")
        ent.name = "Changed"
        assert ent.name == "Changed"
