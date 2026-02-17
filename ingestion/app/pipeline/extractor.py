"""Named Entity Recognition via spaCy.

Loads the ``en_core_web_sm`` model (configurable) and extracts PERSON,
ORG, GPE, and LOC entities from free text.  Provides basic intra-document
deduplication so the same entity name is not emitted twice.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import spacy
from spacy.language import Language

from app.config import settings

logger = logging.getLogger(__name__)

# Map spaCy entity labels to Enjin's canonical types
_SPACY_LABEL_MAP: dict[str, str] = {
    "PERSON": "person",
    "ORG": "org",
    "GPE": "location",    # geo-political entity (countries, cities, states)
    "LOC": "location",    # non-GPE locations (mountain ranges, water bodies)
}


@dataclass(frozen=True, slots=True)
class ExtractedEntity:
    """A single named entity extracted from text."""

    name: str
    type: str               # person | org | location
    span_start: int
    span_end: int
    confidence: float = 1.0  # spaCy sm models don't provide probabilities; default 1.0


class EntityExtractor:
    """Extract named entities from text using spaCy NER.

    Usage::

        extractor = EntityExtractor()
        entities = extractor.extract_entities("Apple Inc. CEO Tim Cook visited Berlin.")
    """

    _nlp: Language | None = None  # class-level singleton to avoid reloading the model

    def __init__(self) -> None:
        if EntityExtractor._nlp is None:
            model_name = settings.spacy_model
            logger.info("EntityExtractor: loading spaCy model '%s'...", model_name)
            EntityExtractor._nlp = spacy.load(model_name)
            logger.info("EntityExtractor: model loaded successfully")

    @property
    def nlp(self) -> Language:
        assert self._nlp is not None
        return self._nlp

    def extract_entities(self, text: str) -> list[ExtractedEntity]:
        """Run NER on *text* and return deduplicated entities.

        Only entities whose spaCy label maps to one of the Enjin types
        (person, org, location) are returned.
        """
        if not text or not text.strip():
            return []

        doc = self.nlp(text)

        raw_entities: list[ExtractedEntity] = []
        for ent in doc.ents:
            enjin_type = _SPACY_LABEL_MAP.get(ent.label_)
            if enjin_type is None:
                continue
            raw_entities.append(
                ExtractedEntity(
                    name=ent.text.strip(),
                    type=enjin_type,
                    span_start=ent.start_char,
                    span_end=ent.end_char,
                )
            )

        return self._deduplicate(raw_entities)

    # ── deduplication ────────────────────────────────────────────────
    @staticmethod
    def _deduplicate(entities: list[ExtractedEntity]) -> list[ExtractedEntity]:
        """Merge entities that share the same normalised name and type.

        Keeps the *first* occurrence's span offsets.
        """
        seen: dict[tuple[str, str], ExtractedEntity] = {}
        for ent in entities:
            key = (ent.name.lower().strip(), ent.type)
            if key not in seen:
                seen[key] = ent
        return list(seen.values())
