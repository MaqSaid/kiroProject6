# Adapter Verification Skill

## Purpose
Verify that an infrastructure adapter correctly implements its port protocol, follows project conventions, and has proper logging/error handling.

## Steps

1. **Read the adapter file** from `src/infrastructure/<adapter_name>.py`
2. **Read the corresponding port** from `src/ports/<port_name>.py`
3. **Verify protocol compliance**:
   - All methods from the port Protocol are implemented
   - All methods are `async def`
   - Return types match the Protocol
   - Method signatures match (parameter names and types)
4. **Verify structured logging**:
   - `structlog.get_logger(__name__)` at module level
   - `.start` log at beginning of each operation
   - `.success` log with `duration_ms` on success
   - `.failed` log with `error=str(e)` on failure
5. **Verify error handling**:
   - Try/except around external calls
   - Typed exception raised (not bare Exception)
   - Error logged before re-raising
6. **Verify no domain service imports**:
   - Only imports from `src/ports/`, `src/domain/models/`, and stdlib
   - Never imports from `src/domain/services/` or `src/api/`
7. **Check for timeout configuration** on external calls
8. **Run ruff check** on the file
9. **Mark task complete** if all checks pass

## Port-to-Adapter Mapping

| Port | Adapter | File |
|------|---------|------|
| `VectorStorePort` | `ChromaDBVectorStoreAdapter` | `chromadb_vector_store.py` |
| `SparseIndexPort` | `BM25SparseIndexAdapter` | `bm25_sparse_index.py` |
| `GraphStorePort` | `InMemoryGraphStore` | `in_memory_graph_store.py` |
| `EmbeddingPort` | `BedrockEmbeddingAdapter` | `bedrock_embedding.py` |
| `RerankerPort` | `CrossEncoderRerankerAdapter` | `cross_encoder_reranker.py` |
| `CachePort` | `InMemoryCache` | `in_memory_cache.py` |
| `DocumentStorePort` | `LocalDocumentStore` | `local_document_store.py` |
