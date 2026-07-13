# Implementation Plan: Production RAG Pipeline with Hybrid Search

## Overview

This plan breaks down the production RAG pipeline into incremental coding tasks following a foundations-first approach. We build core domain models and ports, then implement services layer by layer (ingestion → retrieval → generation → confidence), wire up the API, add security/observability, build the frontend, and finally set up infrastructure and CI/CD. Property-based tests validate the 20 correctness properties defined in the design document using Hypothesis.

## Tasks

- [x] 1. Project scaffolding, configuration, and core domain models
  - [x] 1.1 Initialize Python project with pyproject.toml, dependency groups (core, dev, test), and directory structure following hexagonal architecture
    - Create top-level directories: `src/domain/`, `src/application/`, `src/infrastructure/`, `src/api/`, `src/ports/`, `tests/unit/`, `tests/property/`, `tests/integration/`, `frontend/`
    - Configure pytest, Hypothesis, mypy, ruff, and pre-commit hooks
    - _Requirements: 16.1, 18.1_

  - [x] 1.2 Implement core domain enums and value objects
    - `DocumentFormat`, `ChunkingStrategy`, `UserRole` enums
    - `RRFWeights` value object with `validate_sum()` method
    - _Requirements: 1.1, 2.1, 4.3, 10.2_

  - [x] 1.3 Implement core domain entities (Pydantic models)
    - `RawDocument`, `NormalizedDocument`, `Section`, `DocumentMetadata`
    - `Chunk`, `ScoredChunk`, `EmbeddingRecord`
    - `ExtractedEntity`, `ExtractedRelationship`
    - `Query`, `Citation`, `ConfidenceScore`, `GenerationResult`, `FallbackInfo`
    - _Requirements: 1.2, 2.7, 4.5, 5.2, 6.1_

  - [x] 1.4 Implement API request/response models
    - `AskRequest`, `AskResponse`, `SourceReference`
    - `IngestResponse`, `ErrorResponse`
    - `DocumentIngestedEvent`
    - _Requirements: 8.1, 8.2, 8.3, 8.8_

  - [x] 1.5 Define all port interfaces (Protocol classes)
    - `VectorStorePort`, `SparseIndexPort`, `GraphStorePort`
    - `EmbeddingPort`, `LLMPort`, `DocumentStorePort`
    - `RerankerPort`, `CachePort`
    - _Requirements: 3.1, 3.2, 4.1, 4.2, 4.10_

  - [x] 1.6 Implement domain events and event bus interface
    - `DocumentIngestedEvent` with document_id, format, size, timestamp, chunk_count, entity_count
    - `EventBus` protocol with `publish()` method
    - In-memory event bus implementation for local dev
    - _Requirements: 1.6_

- [x] 2. Document normalizers
  - [x] 2.1 Implement `FormatNormalizer` base protocol and `DocumentNormalizer` orchestrator
    - Define `FormatNormalizer` protocol with `normalize(content: bytes) -> NormalizedContent`
    - `DocumentNormalizer` dispatches to format-specific normalizers based on `DocumentFormat`
    - _Requirements: 1.2_

  - [x] 2.2 Implement `MarkdownNormalizer`
    - Strip Markdown syntax, preserve section headings (# levels), produce plaintext with section offsets
    - _Requirements: 1.1, 1.2_

  - [x] 2.3 Implement `HTMLNormalizer`
    - Strip HTML tags using BeautifulSoup, preserve heading hierarchy, extract plaintext
    - _Requirements: 1.1, 1.2_

  - [x] 2.4 Implement `PDFNormalizer`
    - Extract text using PyMuPDF/pdfplumber, preserve page numbers and section headings
    - _Requirements: 1.1, 1.2_

  - [x] 2.5 Implement `PlaintextNormalizer`
    - Pass-through with basic section detection (lines matching heading patterns)
    - _Requirements: 1.1, 1.2_

  - [ ]* 2.6 Write property test: Normalization preserves document metadata
    - **Property 1: Normalization preserves document metadata**
    - Generate arbitrary documents with known section headings and page numbers; verify normalization output contains all of them
    - **Validates: Requirements 1.2**

  - [ ]* 2.7 Write unit tests for each normalizer format
    - Known Markdown → plaintext conversions, HTML edge cases, PDF multi-page, empty documents
    - _Requirements: 1.1, 1.2, 1.4, 1.5_

- [ ] 3. Chunking strategies
  - [x] 3.1 Implement `ChunkerFactory` and `Chunker` protocol
    - Factory dispatches to strategy-specific chunker based on `ChunkingStrategy` enum
    - All chunkers produce `list[Chunk]` with required metadata fields populated
    - _Requirements: 2.1, 2.2, 2.7_

  - [x] 3.2 Implement `FixedSizeChunker`
    - Split text into chunks of configurable `chunk_size` with configurable `overlap`
    - Attach metadata: source_document_id, chunk_index, section_heading, strategy name, char_count
    - Handle edge case: chunk exceeding embedding model token limit → split further and log warning
    - _Requirements: 2.3, 2.7, 2.8_

  - [x] 3.3 Implement `RecursiveChunker`
    - Split by section headers respecting document hierarchy from `NormalizedDocument.sections`
    - Each chunk contained within a single section or subsection
    - _Requirements: 2.4, 2.7_

  - [x] 3.4 Implement `SemanticChunker`
    - Compute pairwise embedding similarity between consecutive sentences
    - Split at boundaries where similarity drops below configurable threshold
    - Uses `EmbeddingPort` for sentence embeddings
    - _Requirements: 2.5, 2.7_

  - [ ]* 3.5 Write property test: Fixed-size chunker size and overlap invariants
    - **Property 4: Fixed-size chunker size and overlap invariants**
    - For any text and valid config, verify: no chunk exceeds chunk_size, consecutive chunks overlap exactly, non-overlapping concatenation reconstructs original
    - **Validates: Requirements 2.3**

  - [ ]* 3.6 Write property test: Recursive chunker respects section boundaries
    - **Property 5: Recursive chunker respects section boundaries**
    - For any document with sections, verify no chunk spans across a section boundary
    - **Validates: Requirements 2.4**

  - [ ]* 3.7 Write property test: Semantic chunker splits at similarity threshold
    - **Property 6: Semantic chunker splits at similarity threshold**
    - For any sentence sequence with known similarities, verify splits only occur where similarity < threshold
    - **Validates: Requirements 2.5**

  - [ ]* 3.8 Write property test: All chunks carry required metadata
    - **Property 7: All chunks carry required metadata**
    - For any document processed by any strategy, verify every chunk has source_document_id, chunk_index, section_heading, strategy name, char_count == len(text)
    - **Validates: Requirements 2.2, 2.7**

- [~] 4. Checkpoint — Core processing layer
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Infrastructure adapters — storage layer
  - [~] 5.1 Implement `LocalDocumentStore` adapter (DocumentStorePort)
    - Store/retrieve raw documents on local filesystem for dev; S3 adapter as alternate
    - _Requirements: 1.3_

  - [ ]* 5.2 Write property test: Raw document storage round-trip
    - **Property 2: Raw document storage round-trip**
    - For any valid document, store then retrieve SHALL produce byte-identical content
    - **Validates: Requirements 1.3**

  - [~] 5.3 Implement `ChromaDBVectorStore` adapter (VectorStorePort)
    - store(), search(), delete_by_document(), find_similar() using ChromaDB client
    - Collection schema: 1536-dimension cosine similarity
    - _Requirements: 3.1, 3.4_

  - [~] 5.4 Implement `BM25SparseIndex` adapter (SparseIndexPort)
    - In-memory BM25 index using rank_bm25 library
    - index(), search(), delete_by_document()
    - _Requirements: 3.2_

  - [~] 5.5 Implement `Neo4jGraphStore` adapter (GraphStorePort)
    - store_entities(), store_relationships(), traverse(), delete_by_document()
    - Cypher queries for multi-hop traversal
    - _Requirements: 1.10, 3.9, 4.10_

  - [~] 5.6 Implement `OpenAIEmbedding` adapter (EmbeddingPort)
    - embed() and embed_single() using text-embedding-3-small
    - Batch embedding with rate limit handling
    - _Requirements: 3.1_

  - [~] 5.7 Implement `OpenAILLM` adapter (LLMPort) and `AnthropicLLM` fallback adapter
    - generate() and generate_structured() for GPT-4o primary
    - Fallback adapter for Claude Sonnet
    - _Requirements: 5.1_

  - [~] 5.8 Implement `CrossEncoderReranker` adapter (RerankerPort)
    - Load cross-encoder/ms-marco-MiniLM-L-12-v2 locally
    - rerank() scores query-passage pairs and returns top_n by descending score
    - _Requirements: 4.4_

  - [~] 5.9 Implement `RedisCache` adapter (CachePort)
    - get(), set() with TTL, invalidate() by pattern
    - _Requirements: 15.11_

- [ ] 6. Indexing service with deduplication
  - [~] 6.1 Implement `IndexingService`
    - Coordinate writes to vector store, sparse index, and graph store
    - Transactional: if any write fails, roll back all successful writes
    - `index_chunks()`, `remove_document_entries()`, `check_duplicate()`
    - _Requirements: 3.1, 3.2, 3.3, 3.9_

  - [~] 6.2 Implement deduplication logic
    - Compute cosine similarity against existing chunks before indexing
    - Reject/flag chunks with similarity > 0.95, log duplicate source and similarity score
    - _Requirements: 3.4, 3.5_

  - [~] 6.3 Implement re-indexing flow
    - Remove all prior chunks from all indexes for a document, then re-index with new strategy
    - _Requirements: 3.6_

  - [ ]* 6.4 Write property test: Deduplication rejects near-duplicate chunks
    - **Property 9: Deduplication rejects near-duplicate chunks**
    - For any two chunks with cosine similarity > 0.95, indexing service rejects the second; similarity ≤ 0.95, both accepted
    - **Validates: Requirements 3.4**

  - [ ]* 6.5 Write property test: Re-chunking produces valid output from stored content
    - **Property 8: Re-chunking produces valid output from stored content**
    - For any previously ingested document, re-chunking with a different strategy covers the same content
    - **Validates: Requirements 2.6**

- [ ] 7. Entity extraction via Instructor
  - [~] 7.1 Implement `EntityExtractor` with Instructor + Pydantic schemas
    - Define `ExtractionResult` Pydantic model with `entities` and `relationships` fields
    - Use `instructor.Instructor` client with system prompt for extraction
    - Extract typed entities (Person, Concept, Technology) and relationships (USES, DEPENDS_ON, PART_OF)
    - _Requirements: 1.9, 1.10_

  - [ ]* 7.2 Write unit tests for entity extraction
    - Test with known text snippets containing entities and relationships
    - Mock LLM responses to verify schema parsing and validation
    - _Requirements: 1.9, 1.10_

- [ ] 8. Ingestion service (orchestrator)
  - [~] 8.1 Implement `IngestionService`
    - Orchestrate: validate → normalize → chunk → extract entities → index → emit event
    - `ingest()` and `reindex()` methods
    - Validate file format, reject unsupported with descriptive error
    - Store raw document before processing
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

  - [ ]* 8.2 Write property test: Successful ingestion produces correct domain event
    - **Property 3: Successful ingestion produces correct domain event**
    - For any valid document, ingestion emits event with correct document_id, format, size, and timestamp within request window
    - **Validates: Requirements 1.1, 1.6**

  - [ ]* 8.3 Write unit tests for ingestion error paths
    - Unsupported format rejection, corrupted file handling, path traversal detection
    - _Requirements: 1.4, 1.5, 1.7_

- [~] 9. Checkpoint — Ingestion pipeline complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Retrieval service with RRF fusion and reranking
  - [~] 10.1 Implement `RetrievalService` with three-way parallel retrieval
    - Execute dense vector search, BM25 sparse search, and graph traversal in parallel
    - Handle degraded modes: BM25 unavailable → dense+graph; Graph unavailable → dense+sparse
    - Respect configurable timeout (default 5s), return partial results or timeout error
    - _Requirements: 4.1, 4.2, 4.7, 4.8, 4.9, 4.10, 4.11_

  - [~] 10.2 Implement `reciprocal_rank_fusion()` function
    - Three-way weighted RRF: score(d) = Σ(weight_i / (k + rank_i))
    - Support configurable weights (default 0.5/0.2/0.3) and per-request override
    - Output sorted by descending RRF score, include all unique items from all lists
    - _Requirements: 4.3, 4.6_

  - [~] 10.3 Implement reranking step
    - Apply cross-encoder over top-20 fused candidates, select top-5 for context window
    - Attach retrieval metadata (source_document, section_heading, relevance_score, retrieval_method)
    - _Requirements: 4.4, 4.5_

  - [ ]* 10.4 Write property test: RRF fusion with configurable weights
    - **Property 10: RRF fusion with configurable weights**
    - For any three non-empty ranked lists and valid weights summing to 1.0, verify: all unique items included, scores use correct formula, output sorted descending
    - **Validates: Requirements 4.3, 4.6**

  - [ ]* 10.5 Write property test: Reranker selection maintains ordering
    - **Property 11: Reranker selection maintains ordering**
    - For any list of N>=5 candidates scored by reranker, top-5 are the 5 highest-scored in descending order
    - **Validates: Requirements 4.4**

  - [ ]* 10.6 Write property test: Retrieval results include required metadata
    - **Property 12: Retrieval results include required metadata**
    - For any retrieval result, every scored chunk has source_document, section_heading, relevance_score >= 0, retrieval_method in valid set
    - **Validates: Requirements 4.5**

- [ ] 11. Generation service with citation verification
  - [~] 11.1 Implement `GenerationService`
    - Generate grounded answers from query + context using primary LLM (GPT-4o)
    - Enforce bracketed citation format [1], [2], etc. linking claims to source chunks
    - Detect insufficient context → return explicit "insufficient context" response
    - Implement fallback to Anthropic Claude when primary unavailable
    - Enforce maximum token budget per request
    - _Requirements: 5.1, 5.2, 5.3, 5.6, 5.7, 5.8_

  - [~] 11.2 Implement `CitationVerifier` (LLM-as-judge)
    - Parse citations from generated answer
    - For each citation-claim pair, send to LLM judge to verify semantic entailment
    - Compute citation_coverage = verified_count / total_citations
    - Flag unsupported citations in response metadata
    - _Requirements: 5.4, 5.5_

  - [ ]* 11.3 Write property test: Citation format correctness
    - **Property 13: Citation format correctness**
    - For any generated answer with citations, all references match [N] pattern and N maps to a valid chunk in the context window
    - **Validates: Requirements 5.2**

  - [ ]* 11.4 Write property test: Citation verification and scoring
    - **Property 14: Citation verification and scoring**
    - For any answer with citations, verifier correctly identifies supported/unsupported citations and coverage = verified_count / total
    - **Validates: Requirements 5.4, 5.5**

  - [ ]* 11.5 Write property test: Token budget enforcement
    - **Property 15: Token budget enforcement**
    - For any generation request, total tokens consumed SHALL NOT exceed the configured maximum
    - **Validates: Requirements 5.8**

- [ ] 12. Confidence scoring and fallback
  - [~] 12.1 Implement `ConfidenceService`
    - Compute three dimensions: retrieval_confidence, citation_coverage, answer_completeness
    - Compute composite = weighted sum using configurable weights (default 0.35/0.4/0.25)
    - All scores clamped to [0, 1]
    - `should_fallback()` returns true when retrieval_confidence < threshold
    - _Requirements: 6.1, 6.2, 6.5, 6.6_

  - [~] 12.2 Implement fallback response generation
    - When confidence below threshold, produce structured fallback with: what was found, what was not found, suggested documents for manual review
    - Never present zero-confidence as a confident answer
    - _Requirements: 6.3, 6.4, 6.5_

  - [ ]* 12.3 Write property test: Confidence score structure and validity
    - **Property 17: Confidence score structure and validity**
    - For any computed result, retrieval_confidence, citation_coverage, answer_completeness all in [0,1], composite = weighted sum
    - **Validates: Requirements 6.1, 6.2, 6.6**

  - [ ]* 12.4 Write property test: Low confidence triggers fallback
    - **Property 18: Low confidence triggers fallback**
    - For any response where retrieval_confidence < threshold (including zero), system triggers fallback with structured info
    - **Validates: Requirements 6.3, 6.5**

- [~] 13. Checkpoint — Core pipeline services complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 14. Security service
  - [~] 14.1 Implement `SecurityService` — prompt injection detection
    - Compile pattern set for direct injection (system prompt override, instruction injection, role-play attacks)
    - `scan_query()` returns pass/reject with reason
    - _Requirements: 5.9, 11.1_

  - [~] 14.2 Implement document content scanning
    - `scan_document()` detects indirect injection payloads in document content
    - Flag or quarantine affected documents for manual review
    - _Requirements: 11.2, 11.8_

  - [~] 14.3 Implement input validation (filename, path traversal, injection)
    - `validate_filename()` rejects path traversal characters (../, ..\)
    - Input validation for SQL/NoSQL/command injection patterns
    - _Requirements: 1.7, 10.11_

  - [~] 14.4 Implement PII detection and handling policy
    - Detect PII in ingested documents, apply configured policy (flag/quarantine)
    - _Requirements: 1.8_

  - [~] 14.5 Implement token budget management
    - `TokenBudget` class: per-request max, per-user daily, system-wide daily limits
    - `check_budget()` before LLM calls, `record_usage()` after
    - Alert at configurable threshold (default 80%)
    - _Requirements: 11.6, 11.7, 15.12_

  - [~] 14.6 Implement output sanitization
    - Sanitize generated output to prevent insecure rendering (strip HTML/JS injection)
    - _Requirements: 11.4_

  - [ ]* 14.7 Write property test: Prompt injection detection
    - **Property 16: Prompt injection detection**
    - For any string matching known injection patterns, service rejects; for any benign query, service accepts
    - **Validates: Requirements 5.9, 11.1**

- [ ] 15. API layer (FastAPI routes, middleware, error handling)
  - [~] 15.1 Create OpenAPI 3.1 specification (openapi.yaml)
    - Define all endpoints, request/response schemas, error codes, auth requirements
    - This spec is authored before implementation per Requirement 8.5
    - _Requirements: 8.5_

  - [~] 15.2 Implement FastAPI application scaffold and dependency injection
    - App factory, lifespan events, DI container for services
    - CORS, trusted hosts configuration
    - _Requirements: 8.1_

  - [~] 15.3 Implement `POST /v1/ask` endpoint
    - Accept query, orchestrate security scan → retrieval → generation → citation verify → confidence
    - Return answer, citations, confidence, sources, correlation_id, degraded_mode
    - _Requirements: 8.1_

  - [~] 15.4 Implement `POST /v1/ingest` endpoint
    - Accept file upload with strategy parameter
    - Orchestrate ingestion pipeline, return document_id, chunk_count, entity_count, status
    - _Requirements: 8.3_

  - [~] 15.5 Implement `GET /v1/documents` endpoint
    - Return paginated list of ingested documents with metadata
    - _Requirements: 8.2_

  - [~] 15.6 Implement `GET /health` and `GET /ready` endpoints
    - Liveness: return 200 if process running
    - Readiness: check vector store, graph store, embedding provider connectivity
    - _Requirements: 8.4_

  - [~] 15.7 Implement correlation ID middleware
    - Generate UUID correlation_id for each request, propagate through all service calls
    - Include in all responses and log entries
    - _Requirements: 8.10, 14.1_

  - [~] 15.8 Implement global error handler middleware
    - Catch all exceptions, map to structured `ErrorResponse` with error_code, message, correlation_id
    - Log full stack trace with correlation_id
    - _Requirements: 8.8, 14.7_

  - [~] 15.9 Implement request validation middleware
    - Validate all inputs against OpenAPI schema, return 422 for invalid requests
    - _Requirements: 8.7_

  - [~] 15.10 Implement rate limiting middleware
    - Configurable limits per role and per user
    - Return 429 Too Many Requests with Retry-After header
    - _Requirements: 8.9, 15.7_

  - [ ]* 15.11 Write property test: API input validation rejects invalid requests
    - **Property 19: API input validation rejects invalid requests**
    - For any request violating schema constraints, API returns 422 with structured error indicating which rules violated
    - **Validates: Requirements 8.7**

  - [ ]* 15.12 Write property test: Error responses contain required structure
    - **Property 20: Error response structure**
    - For any error response (4xx/5xx), body contains error_code (non-empty), message (human-readable), correlation_id (UUID format)
    - **Validates: Requirements 8.8, 8.10**

- [~] 16. Checkpoint — API layer complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 17. Authentication and RBAC
  - [~] 17.1 Implement OAuth2/OIDC authentication middleware
    - Validate JWT tokens, extract user identity and roles
    - Exempt /health and /ready from auth requirements
    - _Requirements: 10.1_

  - [~] 17.2 Implement RBAC enforcement
    - Define three roles: reader (query), editor (ingest), admin (full access)
    - Dependency injection for role checking on each endpoint
    - Return 403 Forbidden for unauthorized access (do not disclose resource existence)
    - _Requirements: 10.2, 10.8_

  - [~] 17.3 Implement audit logging
    - Log all ingestion, query, and admin actions with actor identity, timestamp, action, outcome
    - _Requirements: 10.7_

  - [~] 17.4 Implement brute-force protection
    - Detect repeated failed auth attempts from single source
    - Apply progressive rate limiting, alert security team
    - _Requirements: 10.9_

  - [ ]* 17.5 Write unit tests for auth and RBAC
    - Test role enforcement per endpoint, token validation, 403 behavior, audit log entries
    - _Requirements: 10.1, 10.2, 10.8_

- [ ] 18. Resilience layer (circuit breakers, retries, degradation)
  - [~] 18.1 Implement `CircuitBreaker` class
    - States: CLOSED → OPEN → HALF_OPEN → CLOSED
    - Configurable failure_threshold, recovery_timeout, success_threshold
    - Apply to all external provider calls (LLM, embedding, vector store)
    - _Requirements: 15.2_

  - [~] 18.2 Implement retry with exponential backoff and jitter
    - `RetryConfig` with max_retries, base_delay, max_delay, jitter
    - Apply to all retriable external calls
    - _Requirements: 15.3_

  - [~] 18.3 Wire circuit breakers into adapters
    - Wrap VectorStore, EmbeddingPort, LLMPort, GraphStore adapter calls with circuit breakers
    - Emit degraded-state alerts when circuits open
    - _Requirements: 3.7, 3.8, 15.2_

  - [ ]* 18.4 Write integration tests for degraded mode behavior
    - Simulate BM25 unavailable → verify dense+graph fallback
    - Simulate graph store unavailable → verify dense+sparse fallback
    - Simulate LLM unavailable → verify retrieval-only response
    - _Requirements: 4.7, 4.8, 4.11, 5.7, 15.5, 15.6_

- [ ] 19. Observability
  - [~] 19.1 Implement structured JSON logging with correlation IDs
    - Configure Python logging to output structured JSON
    - Inject correlation_id into all log records
    - _Requirements: 14.1_

  - [~] 19.2 Implement OpenTelemetry instrumentation
    - Distributed tracing across ingestion and query paths
    - Auto-instrument FastAPI, httpx, database clients
    - _Requirements: 14.3_

  - [~] 19.3 Implement Prometheus metrics
    - Expose metrics: retrieval_latency, rerank_latency, generation_latency, token_usage, cost_per_query, confidence_distribution, citation_failure_rate
    - _Requirements: 14.2_

  - [~] 19.4 Implement token usage and cost tracking
    - Track tokens per LLM/embedding call, aggregate by user, endpoint, time period
    - Alert when approaching budget thresholds
    - _Requirements: 14.8, 11.7_

  - [~] 19.5 Create Grafana dashboard definitions (JSON/YAML)
    - System health, RAG-specific metrics, cost tracking panels
    - _Requirements: 14.4_

  - [~] 19.6 Define SLOs, SLIs, and error budgets
    - API availability, query latency (p50/p95/p99), ingestion throughput, retrieval accuracy
    - Alert when error budget at risk of exhaustion
    - _Requirements: 14.5, 14.6_

  - [~] 19.7 Implement telemetry export to Parquet/Iceberg
    - Export observability data, cost logs, and metrics on configurable schedule
    - _Requirements: 14.9_

- [~] 20. Checkpoint — Backend services fully integrated
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 21. Evaluation framework
  - [~] 21.1 Create golden dataset structure and initial Q&A pairs
    - Versioned JSON/YAML file with 50+ hand-written Q&A pairs
    - Categories: simple_lookup, multi_hop, no_answer, ambiguous
    - Support adding new pairs without code changes
    - _Requirements: 7.1, 7.6_

  - [~] 21.2 Implement evaluation harness
    - Run pipeline against golden dataset for each chunking strategy
    - Compute metrics: answer correctness (LLM-as-judge), faithfulness, retrieval relevance, citation accuracy
    - Produce chunking-strategy comparison report
    - _Requirements: 7.2, 7.4_

  - [~] 21.3 Implement regression detection and CI integration
    - Compare current metrics against baseline, fail if regression exceeds tolerance
    - Report which metrics regressed and by how much
    - _Requirements: 7.3, 7.5_

  - [~] 21.4 Implement evaluation result storage and export
    - Store results with timestamps and pipeline version for historical trend tracking
    - Export to Parquet/Iceberg format
    - _Requirements: 7.7, 7.8_

- [ ] 22. Web UI — React + TypeScript dashboard
  - [~] 22.1 Initialize React + TypeScript project
    - Vite, React 18, TypeScript, Tailwind CSS, react-query for API calls
    - Configure accessibility linting (eslint-plugin-jsx-a11y)
    - _Requirements: 9.1_

  - [~] 22.2 Implement query interface page
    - Question input, submit button, display generated answer with clickable citation references
    - Link citations to source chunk details
    - _Requirements: 9.1_

  - [~] 22.3 Implement search results panel
    - Display retrieved chunks ranked by relevance alongside answer
    - Toggle: hybrid search vs dense-only side-by-side comparison
    - _Requirements: 9.2, 9.4_

  - [~] 22.4 Implement confidence score display
    - Show breakdown: retrieval_confidence, citation_coverage, answer_completeness, composite
    - Visually distinguish flagged/unsupported citations from verified ones
    - _Requirements: 9.3, 9.5_

  - [~] 22.5 Implement accessibility compliance
    - Semantic HTML with ARIA attributes where needed
    - Full keyboard operability, visible focus indicators, no keyboard traps
    - Contrast ratio: 4.5:1 normal text, 3:1 large text
    - Text resize 200% without loss, touch targets 44x44px
    - Respect prefers-reduced-motion, no auto-play
    - _Requirements: 9.6, 9.7, 9.8, 9.9, 9.10, 9.11, 9.14_

  - [~] 22.6 Implement error states and mobile responsiveness
    - Accessible error messages associated with controls, announced to screen readers
    - API unavailable state with clear messaging
    - Mobile-first responsive design (360px minimum viewport)
    - _Requirements: 9.12, 9.13, 9.10_

  - [ ]* 22.7 Write unit tests for React components
    - Test citation linking, confidence display, error states, accessibility attributes
    - _Requirements: 9.1, 9.3, 9.5, 9.12_

- [~] 23. Checkpoint — Frontend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 24. Infrastructure as Code (Terraform)
  - [~] 24.1 Set up Terraform project structure
    - Remote state with S3 backend and DynamoDB lock table
    - Per-environment workspaces (dev, stage, prod)
    - Reusable modules directory
    - _Requirements: 17.1, 17.2_

  - [~] 24.2 Implement networking module
    - VPC, subnets, security groups, NAT gateway
    - _Requirements: 17.5_

  - [~] 24.3 Implement compute module
    - ECS Fargate for stateless API containers behind ALB
    - Horizontal autoscaling policies
    - _Requirements: 15.1, 17.6_

  - [~] 24.4 Implement data stores module
    - Qdrant cluster (or managed service), Neptune/Neo4j instance, Redis, S3 buckets
    - Encryption at rest (AES-256), TLS 1.2+ in transit
    - _Requirements: 10.3, 10.4, 17.5_

  - [~] 24.5 Implement secrets management
    - AWS Secrets Manager for API keys, DB credentials, provider tokens
    - IAM policies with least-privilege access
    - _Requirements: 10.5, 10.6_

  - [~] 24.6 Implement observability infrastructure
    - OpenTelemetry Collector, Prometheus, Grafana provisioning
    - CloudWatch log groups, alarm definitions
    - _Requirements: 14.2, 14.3, 14.4_

  - [~] 24.7 Implement WAF and security infrastructure
    - ALB with WAF rules, rate limiting at edge
    - _Requirements: 10.3, 15.7_

- [ ] 25. Containerized delivery (Docker + docker-compose)
  - [~] 25.1 Create Dockerfiles
    - API service: multi-stage build, non-root user, health check
    - Frontend: Nginx with React build artifacts
    - _Requirements: 18.1_

  - [~] 25.2 Create docker-compose.yml for local development
    - API, ChromaDB, Neo4j, Redis, frontend — correct networking and dependencies
    - Environment variable documentation
    - _Requirements: 18.2, 18.5_

  - [~] 25.3 Create seed script
    - Index a sample documentation corpus so system is immediately usable
    - Complete within 5 minutes on standard dev machine
    - _Requirements: 18.3, 18.4_

- [ ] 26. CI/CD pipeline (GitLab CI)
  - [~] 26.1 Implement CI pipeline stages as reusable templates
    - Build → unit test → SAST/SCA/secrets → contract test → integration → DAST → E2E → eval → perf → accessibility → package → deploy
    - _Requirements: 16.1, 16.2_

  - [~] 26.2 Implement security scanning stages
    - SAST (Semgrep/Bandit), SCA with SBOM generation, secret detection, container scanning (Trivy), IaC scanning (Checkov)
    - Block merge on critical/high findings
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.10_

  - [~] 26.3 Implement contract testing stage
    - Validate API implementation against OpenAPI spec (Schemathesis)
    - Fail on divergence
    - _Requirements: 8.6_

  - [~] 26.4 Implement DAST and API security testing stage
    - OWASP ZAP against running API and UI
    - API security tests for OWASP API Security Top 10
    - Fuzzing: malicious PDFs/HTML, oversized payloads, path traversal, injection
    - _Requirements: 12.6, 12.7, 12.8_

  - [~] 26.5 Implement evaluation and performance stages
    - Run eval suite, fail on metric regression beyond tolerance
    - k6 load tests validating latency SLOs
    - _Requirements: 7.3, 7.5, 15.10_

  - [~] 26.6 Implement deployment and rollback
    - Environment promotion: dev → stage → prod with manual gates
    - Terraform plan/apply stage with review
    - Automated rollback on post-deploy verification failure
    - Signed container images, semantic versioning
    - _Requirements: 16.4, 16.5, 16.6, 16.8, 17.3_

  - [~] 26.7 Implement branch protection and notifications
    - Mandatory code review before merge to protected branches
    - Block progression on any stage failure, notify team
    - _Requirements: 16.3, 16.7_

  - [~] 26.8 Implement E2E UI tests stage (Playwright)
    - Desktop and mobile viewport tests
    - _Requirements: 16.9_

- [ ] 27. GRC artifacts and compliance mapping
  - [~] 27.1 Create ISO 27001 control matrix
    - Map system controls to relevant Annex A controls: access control, cryptography, operations security, supplier management, logging, incident management, business continuity
    - _Requirements: 13.1_

  - [~] 27.2 Create ISO 42001 AI control matrix
    - Map to: AI policy, risk assessment, impact assessment, human oversight, transparency, model lifecycle, data governance, continuous monitoring
    - Map citations/confidence as transparency controls, eval suite as continuous monitoring
    - _Requirements: 13.2, 13.3, 13.4_

  - [~] 27.3 Create GRC artifacts
    - Risk register, statement of applicability, AI impact assessment, incident response runbook, audit-evidence checklist
    - _Requirements: 13.5_

  - [~] 27.4 Implement data retention and deletion capability
    - Configurable retention periods
    - Delete documents and all derived data (chunks, embeddings, index entries) upon request
    - _Requirements: 10.10_

- [~] 28. Final checkpoint — Full system integration
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation at logical milestones
- Property-based tests use Hypothesis with `@settings(max_examples=100)` minimum
- Property tests are tagged: `# Feature: production-rag-pipeline-hybrid-search, Property N: <title>`
- The project uses Python 3.11+ with FastAPI (backend) and React 18 + TypeScript (frontend)
- Local development uses ChromaDB + Neo4j; production targets Qdrant + Neptune via port/adapter swaps
- All adapters implement port Protocol interfaces for testability and swappability

## Task Dependency Graph

```json
{
  "waves": [
    {
      "name": "Wave 1: Foundations",
      "tasks": [1],
      "description": "Project scaffolding, domain models, ports, and event bus"
    },
    {
      "name": "Wave 2: Processing Layer",
      "tasks": [2, 3, 5],
      "description": "Document normalizers, chunking strategies, and infrastructure adapters (parallel)"
    },
    {
      "name": "Wave 3: Ingestion Pipeline",
      "tasks": [4, 6, 7, 8, 9],
      "description": "Indexing service, entity extraction, and ingestion orchestrator"
    },
    {
      "name": "Wave 4: Query Pipeline",
      "tasks": [10, 11, 12, 13],
      "description": "Retrieval with RRF, generation with citations, confidence scoring"
    },
    {
      "name": "Wave 5: API & Security",
      "tasks": [14, 15, 16, 17, 18],
      "description": "Security service, API layer, auth/RBAC, resilience"
    },
    {
      "name": "Wave 6: Observability & Evaluation",
      "tasks": [19, 20, 21],
      "description": "Logging, tracing, metrics, SLOs, evaluation framework"
    },
    {
      "name": "Wave 7: Frontend",
      "tasks": [22, 23],
      "description": "React + TypeScript dashboard with accessibility"
    },
    {
      "name": "Wave 8: Infrastructure & Delivery",
      "tasks": [24, 25, 26, 27, 28],
      "description": "Terraform IaC, Docker, CI/CD, GRC artifacts, final integration"
    }
  ]
}
```
