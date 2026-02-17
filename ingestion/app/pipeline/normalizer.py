"""Entity normalisation and deduplication.

Provides deterministic name normalisation (whitespace, unicode, casing)
and cross-document entity deduplication using simple string similarity.
"""

from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from app.pipeline.extractor import ExtractedEntity

logger = logging.getLogger(__name__)

# Two entity names with a similarity ratio above this threshold are
# considered to be the same entity.
_DEFAULT_SIMILARITY_THRESHOLD = 0.85


@dataclass
class NormalisedEntity:
    """An entity after normalisation and possible merging."""

    name: str
    type: str
    occurrences: int = 1
    source_spans: list[tuple[int, int]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class EntityNormalizer:
    """Normalise and deduplicate extracted entities."""

    def __init__(self, similarity_threshold: float = _DEFAULT_SIMILARITY_THRESHOLD) -> None:
        self._threshold = similarity_threshold

    # ── public API ───────────────────────────────────────────────────
    @staticmethod
    def normalize_name(name: str) -> str:
        """Produce a canonical form of an entity name.

        Steps:
          1. Strip leading/trailing whitespace.
          2. Normalise unicode to NFC form (compose diacritics).
          3. Collapse internal whitespace.
          4. Title-case the result.
        """
        if not name:
            return ""
        # Unicode NFC normalisation
        text = unicodedata.normalize("NFC", name)
        # Strip and collapse whitespace
        text = " ".join(text.split())
        # Title case
        return text.title()

    def deduplicate_entities(
        self, entities: list[ExtractedEntity]
    ) -> list[NormalisedEntity]:
        """Merge entities that refer to the same real-world thing.

        Uses normalised name comparison with fuzzy string similarity to
        catch minor spelling variations.
        """
        merged: list[NormalisedEntity] = []

        for ent in entities:
            norm_name = self.normalize_name(ent.name)
            match = self._find_match(norm_name, ent.type, merged)

            if match is not None:
                self.merge_entity(match, ent)
            else:
                merged.append(
                    NormalisedEntity(
                        name=norm_name,
                        type=ent.type,
                        occurrences=1,
                        source_spans=[(ent.span_start, ent.span_end)],
                    )
                )

        return merged

    @staticmethod
    def merge_entity(existing: NormalisedEntity, new: ExtractedEntity) -> None:
        """Fold a new detection into an existing normalised entity.

        Increments the occurrence counter and records the source span.
        If the new detection has a longer (presumably more complete) name,
        adopt it as the canonical name.
        """
        existing.occurrences += 1
        existing.source_spans.append((new.span_start, new.span_end))

        # Prefer longer names (e.g. "United Nations" over "UN")
        norm_new = EntityNormalizer.normalize_name(new.name)
        if len(norm_new) > len(existing.name):
            existing.name = norm_new

    # ── internals ────────────────────────────────────────────────────
    def _find_match(
        self,
        norm_name: str,
        entity_type: str,
        candidates: list[NormalisedEntity],
    ) -> NormalisedEntity | None:
        """Find an existing entity that is similar enough to merge with."""
        for candidate in candidates:
            if candidate.type != entity_type:
                continue
            ratio = self._similarity(norm_name, candidate.name)
            if ratio >= self._threshold:
                return candidate
        return None

    @staticmethod
    def _similarity(a: str, b: str) -> float:
        """Compute a normalised string-similarity ratio in [0, 1]."""
        if not a or not b:
            return 0.0
        return SequenceMatcher(None, a.lower(), b.lower()).ratio()
