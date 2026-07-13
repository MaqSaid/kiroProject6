from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import uuid4

from src.domain.models.entities import (
    DocumentMetadata,
    NormalizedDocument,
    RawDocument,
    Section,
)
from src.domain.models.enums import DocumentFormat


class NormalizedContent:
    """Result of format-specific normalization."""

    def __init__(self, plaintext: str, sections: list[Section], page_count: int | None = None):
        self.plaintext = plaintext
        self.sections = sections
        self.page_count = page_count


class FormatNormalizer(Protocol):
    """Protocol for format-specific document normalizers."""

    def normalize(self, content: bytes) -> NormalizedContent: ...


class DocumentNormalizer:
    """Orchestrates normalization by dispatching to format-specific normalizers."""

    def __init__(self) -> None:
        self._normalizers: dict[DocumentFormat, FormatNormalizer] = {}

    def register(self, fmt: DocumentFormat, normalizer: FormatNormalizer) -> None:
        self._normalizers[fmt] = normalizer

    def normalize(self, raw: RawDocument) -> NormalizedDocument:
        normalizer = self._normalizers.get(raw.format)
        if normalizer is None:
            raise ValueError(
                f"Unsupported format: {raw.format}. "
                f"Supported: {list(self._normalizers.keys())}"
            )

        result = normalizer.normalize(raw.content)

        return NormalizedDocument(
            id=uuid4(),
            source_document_id=raw.id,
            plaintext=result.plaintext,
            sections=result.sections,
            metadata=DocumentMetadata(
                source_path=raw.filename,
                format=raw.format,
                page_count=result.page_count,
                ingested_at=datetime.utcnow(),
            ),
        )
