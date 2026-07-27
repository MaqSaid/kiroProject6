"""Entity extraction from text chunks for knowledge graph population.

Sits after chunking in the ingestion pipeline:
validate → normalize → chunk → extract_entities → deduplicate → index → emit_event
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable
from uuid import UUID, uuid5

import structlog
from pydantic import BaseModel

from src.domain.models.entities import Chunk, ExtractedEntity, ExtractedRelationship

logger = structlog.get_logger(__name__)

# Namespace UUID for deterministic entity ID generation
_ENTITY_NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# Legislation-specific entity types
LEGISLATION_ENTITY_TYPES: list[str] = [
    "Act",
    "Section",
    "Regulation",
    "Agency",
    "Penalty",
    "Definition",
    "Jurisdiction",
]

# Legislation-specific relationship types
LEGISLATION_RELATIONSHIP_TYPES: list[str] = [
    "AMENDS",
    "REFERENCES",
    "DELEGATES_TO",
    "DEFINES",
    "APPLIES_TO",
    "SUPERSEDES",
    "PART_OF",
]

ENTITY_EXTRACTION_PROMPT = """\
You are a legal document entity extractor. Analyze the following text chunk from \
legislation and extract all named entities and their relationships.

## Entity Types to Extract
- Act: Named legislation (e.g., "Privacy Act 1988")
- Section: Specific sections/clauses (e.g., "Section 15")
- Regulation: Subordinate legislation or rules
- Agency: Government bodies or regulatory authorities
- Penalty: Fines, imprisonment terms, or other sanctions
- Definition: Legally defined terms
- Jurisdiction: Geographic or legal jurisdictions

## Relationship Types to Extract
- AMENDS: One act/section modifies another
- REFERENCES: One entity refers to another
- DELEGATES_TO: Power delegated from one entity to another
- DEFINES: A definition defines a term
- APPLIES_TO: A rule/penalty applies to a jurisdiction or entity
- SUPERSEDES: One provision replaces another
- PART_OF: Hierarchical containment (section part of act)

## Input Text
{text}

## Output Format
Return a JSON object with two arrays:
{{
  "entities": [
    {{
      "name": "exact entity name",
      "entity_type": "one of the entity types above",
      "description": "brief description of this entity in context",
      "properties": {{}}
    }}
  ],
  "relationships": [
    {{
      "source_entity_name": "name of source entity",
      "target_entity_name": "name of target entity",
      "relationship_type": "one of the relationship types above",
      "description": "brief description of this relationship"
    }}
  ]
}}

Extract only entities and relationships explicitly mentioned or clearly implied in the text. \
Do not infer entities that are not present."""


class RawExtractedEntity(BaseModel):
    """Raw entity as returned by the LLM before ID assignment."""

    name: str
    entity_type: str
    description: str
    properties: dict[str, Any] = {}


class RawExtractedRelationship(BaseModel):
    """Raw relationship as returned by the LLM before ID resolution."""

    source_entity_name: str
    target_entity_name: str
    relationship_type: str
    description: str


class RawExtractionResponse(BaseModel):
    """Schema for the LLM extraction response."""

    entities: list[RawExtractedEntity] = []
    relationships: list[RawExtractedRelationship] = []


class ExtractionResult(BaseModel):
    """Result of entity extraction from a single chunk."""

    entities: list[ExtractedEntity] = []
    relationships: list[ExtractedRelationship] = []


@runtime_checkable
class LLMExtractionPort(Protocol):
    """Port for LLM-based entity extraction.

    Implementations can use any LLM provider (Bedrock, OpenAI, etc.)
    to extract structured entities from text.
    """

    async def extract_entities(
        self,
        prompt: str,
        correlation_id: str,
    ) -> RawExtractionResponse:
        """Send extraction prompt to LLM and return structured response.

        Args:
            prompt: The formatted extraction prompt with text embedded.
            correlation_id: Request correlation ID for tracing.

        Returns:
            Parsed extraction response with raw entities and relationships.

        Raises:
            Any exception on LLM failure — caller handles gracefully.
        """
        ...


def _normalize_entity_name(name: str) -> str:
    """Normalize entity name for deduplication.

    Lowercases, strips whitespace, and collapses internal whitespace.
    """
    return " ".join(name.strip().lower().split())


def _generate_entity_id(entity_name: str, chunk_id: UUID) -> UUID:
    """Generate deterministic UUID for an entity based on name + chunk.

    Uses uuid5 so the same entity extracted from the same chunk
    always produces the same ID, enabling idempotent re-processing.
    """
    normalized = _normalize_entity_name(entity_name)
    seed = f"{normalized}:{chunk_id}"
    return uuid5(_ENTITY_NAMESPACE, seed)


def _generate_relationship_id(
    source_entity_id: UUID,
    target_entity_id: UUID,
    relationship_type: str,
    chunk_id: UUID,
) -> UUID:
    """Generate deterministic UUID for a relationship."""
    seed = f"{source_entity_id}:{target_entity_id}:{relationship_type}:{chunk_id}"
    return uuid5(_ENTITY_NAMESPACE, seed)


class EntityExtractor:
    """Extracts named entities and relationships from text chunks.

    Uses an LLM via the LLMExtractionPort to identify legislation-specific
    entities and their relationships, then deduplicates and assigns
    deterministic IDs for idempotent knowledge graph population.
    """

    def __init__(self, llm_port: LLMExtractionPort) -> None:
        self._llm_port = llm_port

    async def extract(
        self,
        chunk: Chunk,
        correlation_id: str,
    ) -> ExtractionResult:
        """Extract entities and relationships from a text chunk.

        Args:
            chunk: The text chunk to extract entities from.
            correlation_id: Request correlation ID for tracing.

        Returns:
            ExtractionResult with deduplicated entities and resolved relationships.
            Returns empty result on LLM failure.
        """
        log = logger.bind(
            correlation_id=correlation_id,
            chunk_id=str(chunk.id),
            document_id=str(chunk.document_id),
        )

        log.info(
            "entity_extractor.extract.started",
            chunk_index=chunk.index,
            char_count=chunk.char_count,
        )

        prompt = ENTITY_EXTRACTION_PROMPT.format(text=chunk.text)

        try:
            raw_response = await self._llm_port.extract_entities(
                prompt=prompt,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            log.warning(
                "entity_extractor.extract.llm_failed",
                error=str(exc),
                error_type=type(exc).__name__,
            )
            return ExtractionResult()

        entities = self._deduplicate_and_assign_ids(
            raw_entities=raw_response.entities,
            chunk_id=chunk.id,
        )

        # Build name→entity lookup for relationship resolution
        entity_lookup: dict[str, ExtractedEntity] = {
            _normalize_entity_name(e.name): e for e in entities
        }

        relationships = self._resolve_relationships(
            raw_relationships=raw_response.relationships,
            entity_lookup=entity_lookup,
            chunk_id=chunk.id,
            log=log,
        )

        log.info(
            "entity_extractor.extract.completed",
            entity_count=len(entities),
            relationship_count=len(relationships),
        )

        return ExtractionResult(entities=entities, relationships=relationships)

    def _deduplicate_and_assign_ids(
        self,
        raw_entities: list[RawExtractedEntity],
        chunk_id: UUID,
    ) -> list[ExtractedEntity]:
        """Deduplicate entities by normalized name and assign deterministic IDs."""
        seen: dict[str, ExtractedEntity] = {}

        for raw in raw_entities:
            normalized_name = _normalize_entity_name(raw.name)
            if normalized_name in seen:
                # Skip duplicate — keep first occurrence
                continue

            entity_id = _generate_entity_id(raw.name, chunk_id)
            entity = ExtractedEntity(
                id=entity_id,
                name=raw.name,
                entity_type=raw.entity_type,
                description=raw.description,
                source_chunk_id=chunk_id,
                properties=raw.properties,
            )
            seen[normalized_name] = entity

        return list(seen.values())

    def _resolve_relationships(
        self,
        raw_relationships: list[RawExtractedRelationship],
        entity_lookup: dict[str, ExtractedEntity],
        chunk_id: UUID,
        log: Any,
    ) -> list[ExtractedRelationship]:
        """Resolve relationship entity references and assign deterministic IDs.

        Skips relationships where source or target entity cannot be resolved.
        """
        relationships: list[ExtractedRelationship] = []

        for raw in raw_relationships:
            source_key = _normalize_entity_name(raw.source_entity_name)
            target_key = _normalize_entity_name(raw.target_entity_name)

            source_entity = entity_lookup.get(source_key)
            target_entity = entity_lookup.get(target_key)

            if source_entity is None or target_entity is None:
                log.debug(
                    "entity_extractor.relationship.unresolved",
                    source=raw.source_entity_name,
                    target=raw.target_entity_name,
                    source_found=source_entity is not None,
                    target_found=target_entity is not None,
                )
                continue

            rel_id = _generate_relationship_id(
                source_entity_id=source_entity.id,
                target_entity_id=target_entity.id,
                relationship_type=raw.relationship_type,
                chunk_id=chunk_id,
            )

            relationship = ExtractedRelationship(
                id=rel_id,
                source_entity_id=source_entity.id,
                target_entity_id=target_entity.id,
                relationship_type=raw.relationship_type,
                description=raw.description,
                source_chunk_id=chunk_id,
            )
            relationships.append(relationship)

        return relationships
