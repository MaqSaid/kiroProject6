from enum import Enum

from pydantic import BaseModel


class DocumentFormat(str, Enum):
    MARKDOWN = "markdown"
    PLAINTEXT = "plaintext"
    HTML = "html"
    PDF = "pdf"


class ChunkingStrategy(str, Enum):
    FIXED_SIZE = "fixed_size"
    RECURSIVE = "recursive"
    SEMANTIC = "semantic"


class UserRole(str, Enum):
    READER = "reader"
    EDITOR = "editor"
    ADMIN = "admin"


class RRFWeights(BaseModel):
    dense: float = 0.5
    sparse: float = 0.2
    graph: float = 0.3

    def validate_sum(self) -> bool:
        """Verify weights sum to 1.0 within floating point tolerance."""
        return abs(self.dense + self.sparse + self.graph - 1.0) < 0.001
