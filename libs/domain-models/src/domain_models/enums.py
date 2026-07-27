"""Domain enumerations for the Legislation RAG Platform."""

from enum import Enum


class ChunkingStrategy(str, Enum):
    """Available chunking strategies for document processing."""

    FIXED_SIZE = "fixed_size"
    RECURSIVE = "recursive"
    SEMANTIC = "semantic"
    LEGAL_HIERARCHICAL = "legal_hierarchical"


class LegalEntityType(str, Enum):
    """Types of legal entities extracted from legislative documents."""

    ACT = "Act"
    SECTION = "Section"
    REGULATION = "Regulation"
    DEFINITION = "Definition"
    OBLIGATION = "Obligation"
    AUTHORITY = "Authority"
    PENALTY = "Penalty"


class LegalRelationshipType(str, Enum):
    """Types of relationships between legal entities."""

    CONTAINS = "CONTAINS"
    DEFINES = "DEFINES"
    AMENDS = "AMENDS"
    REFERENCES = "REFERENCES"
    IMPLEMENTS = "IMPLEMENTS"
    IMPOSES = "IMPOSES"
    GRANTS_POWER = "GRANTS_POWER"
    PRESCRIBES_PENALTY = "PRESCRIBES_PENALTY"


class CircuitState(str, Enum):
    """Circuit breaker states for inter-service communication."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"
