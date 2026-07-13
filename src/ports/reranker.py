from typing import Protocol

from src.domain.models.entities import ScoredChunk


class RerankerPort(Protocol):
    async def rerank(
        self, query: str, candidates: list[ScoredChunk], top_n: int
    ) -> list[ScoredChunk]: ...
