from typing import Any, Protocol

from pydantic import BaseModel

from src.domain.models.entities import DocumentMetadata, RawDocument


class DocumentFilters(BaseModel):
    format: str | None = None
    uploaded_by: str | None = None


class DocumentStorePort(Protocol):
    async def store(self, document: RawDocument) -> str: ...
    async def retrieve(self, document_id: str) -> RawDocument: ...
    async def list_documents(self, filters: Any = None) -> list[DocumentMetadata]: ...
    async def delete(self, document_id: str) -> None: ...
