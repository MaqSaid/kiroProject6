from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from src.domain.models.enums import DocumentFormat


class DocumentIngestedEvent(BaseModel):
    document_id: UUID
    format: DocumentFormat
    size_bytes: int
    timestamp: datetime
    chunk_count: int
    entity_count: int
