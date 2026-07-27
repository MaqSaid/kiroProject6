"""Embedding API route handlers (POST /embed, POST /embed/batch)."""

import time

import structlog
from fastapi import APIRouter, Request, Response

from domain_models import EmbedRequest, EmbedResponse, EmbedBatchRequest, EmbedBatchResponse, ErrorResponse
from src.infrastructure.bedrock_adapter import EmbeddingUnavailableError
from src.api.metrics import (
    EMBED_REQUESTS_TOTAL,
    EMBED_CACHE_HITS_TOTAL,
    EMBED_CACHE_MISSES_TOTAL,
    EMBED_LATENCY_SECONDS,
    TOKENS_USED_TOTAL,
)

router = APIRouter(tags=["embedding"])
logger = structlog.get_logger(__name__)


def _estimate_tokens(text: str) -> int:
    """Estimate token count as len(text) / 4."""
    return max(1, len(text) // 4)


@router.post("/embed", response_model=EmbedResponse)
async def embed_text(body: EmbedRequest, request: Request) -> Response:
    """Generate embedding for a single text.

    Computes SHA-256 hash, checks cache, calls Bedrock on miss,
    caches result, and returns vector + tokens_used.
    """
    start_time = time.perf_counter()
    EMBED_REQUESTS_TOTAL.inc()
    correlation_id = request.headers.get("x-correlation-id", "unknown")

    cache = request.app.state.embedding_cache
    adapter = request.app.state.bedrock_adapter
    settings = request.app.state.settings

    # Token budget enforcement
    estimated_tokens = _estimate_tokens(body.text)
    if estimated_tokens > settings.max_input_tokens:
        error = ErrorResponse(
            error_code="VALIDATION_ERROR",
            message=f"Text exceeds token budget of {settings.max_input_tokens} tokens (estimated: {estimated_tokens})",
            correlation_id=correlation_id,
        )
        return Response(
            content=error.model_dump_json(),
            status_code=422,
            media_type="application/json",
        )

    # Check cache
    cached = cache.get(body.text)
    if cached is not None:
        EMBED_CACHE_HITS_TOTAL.inc()
        logger.info("embed.cache_hit", correlation_id=correlation_id)
        duration = time.perf_counter() - start_time
        EMBED_LATENCY_SECONDS.observe(duration)
        TOKENS_USED_TOTAL.inc(cached.tokens_used)
        response_data = EmbedResponse(vector=cached.vector, tokens_used=cached.tokens_used)
        return Response(
            content=response_data.model_dump_json(),
            status_code=200,
            media_type="application/json",
        )

    # Cache miss — call Bedrock
    EMBED_CACHE_MISSES_TOTAL.inc()
    try:
        vector, tokens_used = await adapter.embed_text(body.text)
    except EmbeddingUnavailableError as e:
        logger.error("embed.bedrock_unavailable", error=str(e), correlation_id=correlation_id)
        error = ErrorResponse(
            error_code="BEDROCK_UNAVAILABLE",
            message="AWS Bedrock embedding API is unreachable",
            correlation_id=correlation_id,
        )
        return Response(
            content=error.model_dump_json(),
            status_code=503,
            media_type="application/json",
        )

    # Cache result
    cache.put(body.text, vector, tokens_used)
    logger.info("embed.cache_miss", tokens_used=tokens_used, correlation_id=correlation_id)

    duration = time.perf_counter() - start_time
    EMBED_LATENCY_SECONDS.observe(duration)
    TOKENS_USED_TOTAL.inc(tokens_used)

    response_data = EmbedResponse(vector=vector, tokens_used=tokens_used)
    return Response(
        content=response_data.model_dump_json(),
        status_code=200,
        media_type="application/json",
    )


@router.post("/embed/batch", response_model=EmbedBatchResponse)
async def embed_batch(body: EmbedBatchRequest, request: Request) -> Response:
    """Generate embeddings for multiple texts.

    Checks cache per item individually, calls Bedrock only for uncached texts,
    caches new results, and returns all vectors in original order.
    """
    start_time = time.perf_counter()
    EMBED_REQUESTS_TOTAL.inc()
    correlation_id = request.headers.get("x-correlation-id", "unknown")

    cache = request.app.state.embedding_cache
    adapter = request.app.state.bedrock_adapter
    settings = request.app.state.settings

    # Token budget enforcement for each text
    for i, text in enumerate(body.texts):
        estimated_tokens = _estimate_tokens(text)
        if estimated_tokens > settings.max_input_tokens:
            error = ErrorResponse(
                error_code="VALIDATION_ERROR",
                message=f"Text at index {i} exceeds token budget of {settings.max_input_tokens} tokens (estimated: {estimated_tokens})",
                correlation_id=correlation_id,
            )
            return Response(
                content=error.model_dump_json(),
                status_code=422,
                media_type="application/json",
            )

    # Check cache per item
    results: list[list[float] | None] = [None] * len(body.texts)
    uncached_indices: list[int] = []
    uncached_texts: list[str] = []
    total_tokens = 0

    for i, text in enumerate(body.texts):
        cached = cache.get(text)
        if cached is not None:
            results[i] = cached.vector
            total_tokens += cached.tokens_used
            EMBED_CACHE_HITS_TOTAL.inc()
        else:
            uncached_indices.append(i)
            uncached_texts.append(text)
            EMBED_CACHE_MISSES_TOTAL.inc()

    # Call Bedrock for uncached texts
    if uncached_texts:
        try:
            vectors, tokens_used = await adapter.embed_batch(uncached_texts)
        except EmbeddingUnavailableError as e:
            logger.error("embed_batch.bedrock_unavailable", error=str(e), correlation_id=correlation_id)
            error = ErrorResponse(
                error_code="BEDROCK_UNAVAILABLE",
                message="AWS Bedrock embedding API is unreachable",
                correlation_id=correlation_id,
            )
            return Response(
                content=error.model_dump_json(),
                status_code=503,
                media_type="application/json",
            )

        total_tokens += tokens_used

        # Cache new results and fill in the results list
        for idx, orig_idx in enumerate(uncached_indices):
            cache.put(uncached_texts[idx], vectors[idx], tokens_used // len(uncached_texts))
            results[orig_idx] = vectors[idx]

    logger.info(
        "embed_batch.completed",
        total=len(body.texts),
        cached=len(body.texts) - len(uncached_texts),
        uncached=len(uncached_texts),
        tokens_used=total_tokens,
        correlation_id=correlation_id,
    )

    duration = time.perf_counter() - start_time
    EMBED_LATENCY_SECONDS.observe(duration)
    TOKENS_USED_TOTAL.inc(total_tokens)

    # All results should be filled now
    final_vectors: list[list[float]] = [v for v in results if v is not None]
    response_data = EmbedBatchResponse(vectors=final_vectors, tokens_used=total_tokens)
    return Response(
        content=response_data.model_dump_json(),
        status_code=200,
        media_type="application/json",
    )
