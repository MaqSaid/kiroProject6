# Implementation Plan: Legislation RAG Platform (Microservices Architecture)

## Overview

This plan implements a microservices-based Legislation RAG Platform comprising 5 FastAPI services (API Gateway, Query Service, Ingestion Service, Graph Service, Embedding Service), shared libraries (domain-models, service-client), and a React 19 frontend. The implementation follows a sprint-based approach respecting service dependency order: shared libs first, then Graph/Embedding services, then Ingestion/Query services, then Gateway, then Frontend, then Testing, Observability, and Infrastructure/CI.

## Tasks

- [x] 1. Sprint 0: Project Scaffolding and Configuration

  - [x] 1.1 Create monorepo directory structure and root configuration
    - Create directories: services/gateway/, services/query-service/, services/ingestion-service/, services/graph-service/, services/embedding-service/, libs/domain-models/, libs/service-client/, frontend/, infrastructure/terraform/, infrastructure/docker/, data/sample_documents/, tests/e2e/, tests/contract/
    - Create root pyproject.toml with workspace configuration, ruff, mypy settings
    - Create .pre-commit-config.yaml with ruff, mypy, eslint, prettier hooks
    - Create root .gitignore covering Python, Node, Docker, IDE artifacts
    - _Requirements: 16.1, 16.5_

  - [x] 1.2 Implement shared domain-models library (libs/domain-models/)
    - Create libs/domain-models/pyproject.toml with Pydantic v2 dependency
    - Implement all enums: ChunkingStrategy, LegalEntityType, LegalRelationshipType, CircuitState
    - Implement core models: ExtractedEntity, ExtractedRelationship, ScoredChunk
    - Implement API models: AgentAskRequest, AgentAskResponse, CitationResponse, ConfidenceScoreResponse, SourceChunkResponse, FallbackInfoResponse, ErrorResponse
    - Implement inter-service models: EmbedRequest, EmbedResponse, EmbedBatchRequest, EmbedBatchResponse, TraverseRequest, TraverseResponse, StoreEntitiesRequest, StoreRelationshipsRequest
    - Implement health models: ServiceHealthStatus, AggregatedHealthResponse
    - Implement DDD base classes: DomainEvent, ValueObject (DocumentId, ChunkId, EntityId), AggregateRoot
    - _Requirements: 16.2, 7.3, 14.3, 15.1_

  - [x] 1.3 Implement shared service-client library (libs/service-client/)
    - Create libs/service-client/pyproject.toml with httpx, structlog dependencies
    - Implement CircuitBreaker class with CLOSED/OPEN/HALF_OPEN states, 5-failure threshold, 30s reset timeout
    - Implement RetryPolicy class with exponential backoff (base 1s, multiplier 2, max 3 attempts, jitter up to 500ms)
    - Implement ResilientClient class wrapping httpx AsyncClient with connection pooling (max_connections=100, max_keepalive_connections=20), circuit breaker, retry, and X-Correlation-ID propagation
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

  - [x] 1.4 Create Docker Compose orchestration
    - Create infrastructure/docker/docker-compose.yml defining all 5 services + Neo4j + ChromaDB
    - Configure health checks and dependency ordering: Graph_Service and Embedding_Service start before Query_Service and Ingestion_Service; all backend services start before API_Gateway
    - Configure shared network for DNS-based service discovery
    - Set up environment variables for inter-service URLs and Neo4j/ChromaDB connections
    - _Requirements: 16.3_

  - [x] 1.5 Create per-service pyproject.toml and Dockerfile templates
    - Create pyproject.toml for each service with service-specific dependencies and editable installs of libs/domain-models and libs/service-client
    - Create multi-stage Dockerfiles (builder + python:3.11-slim runtime) for each service targeting images under 500MB
    - Configure structlog JSON logging with consistent fields (timestamp, level, service_name, correlation_id, message)
    - _Requirements: 16.1, 16.5, 16.6_

  - [x] 1.6 Create OpenAPI specification for all service endpoints
    - Define OpenAPI 3.1 schemas for Graph Service (POST /entities, POST /relationships, POST /traverse, DELETE /documents/{id}, health endpoints)
    - Define OpenAPI 3.1 schemas for Embedding Service (POST /embed, POST /embed/batch, health endpoints)
    - Define OpenAPI 3.1 schemas for Ingestion Service (POST /v1/ingest, GET /v1/documents, health endpoints)
    - Define OpenAPI 3.1 schemas for Query Service (POST /v1/agents/ask, POST /v1/ask, health endpoints)
    - Define OpenAPI 3.1 schemas for API Gateway (all proxied paths + /health aggregate)
    - _Requirements: 14.1, 15.1, 7.1, 12.5_

  - [x] 1.7 Update steering files for microservices architecture
    - Update .kiro/steering/coding-standards.md: React 18 → React 19, add useActionState/useOptimistic/use() patterns, update component patterns for Suspense
    - Create .kiro/steering/legal-domain-guide.md with legal entity types, relationship types, legislative structure patterns
    - Create .kiro/steering/frontend-guide.md with React 19 patterns, WCAG 2.0 AA requirements, TailwindCSS conventions
    - Create .kiro/steering/neo4j-patterns.md with Cypher best practices, MERGE patterns, traversal query templates
    - Update .kiro/steering/project-context.md (or create) documenting microservices architecture, service boundaries, inter-service communication patterns
    - Create .kiro/steering/microservices-patterns.md with inter-service call patterns, ResilientClient usage, circuit breaker conventions, correlation ID propagation, service-client library API reference (conditional inclusion for services/**)
    - Create .kiro/steering/security-middleware-guide.md with fastapi-guard configuration, secure headers setup, HTTPBearer pattern, rate limiter implementation (conditional inclusion for services/gateway/**)
    - Create .kiro/steering/docker-compose-guide.md with service startup order, health check patterns, env var conventions, debugging across containers (conditional inclusion for infrastructure/docker/**)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 13.1, 12.9, 12.10, 16.3_

  - [x] 1.8 Create skills and hooks for task execution
    - Create .kiro/skills/react-component.md with React 19 component patterns (useActionState, use(), Suspense boundaries), WCAG 2.0 AA patterns, TailwindCSS conventions, Playwright test patterns (manual inclusion)
    - Create .kiro/skills/fastapi-service.md with per-service FastAPI app scaffold: lifespan events, health endpoints (/health, /health/ready, /health/live), /metrics endpoint, structlog setup, Pydantic request/response validation, Depends() injection (manual inclusion)
    - Create .kiro/skills/contract-test-writer.md with pattern for writing Pydantic schema contract tests between services, validating client expectations against server response schemas (manual inclusion)
    - Create .kiro/hooks/validate-openapi.kiro.hook: on fileEdited for *.yaml in specs, run OpenAPI schema validation
    - Create .kiro/hooks/docker-health-check.kiro.hook: postTaskExecution hook running docker compose ps to verify all services healthy after task completion
    - Update .kiro/hooks/test-after-task.kiro.hook to also run property tests (pytest tests/property/ alongside tests/unit/)
    - _Requirements: 16.4, 19.4_

- [x] 2. Sprint 0 Checkpoint
  - Ensure all shared libraries have passing unit tests, Docker Compose starts all containers, steering files are in place, skills are loadable, hooks trigger correctly, and linting/formatting is configured.
  - Ask the user if questions arise.

- [x] 3. Sprint 1: Graph Service and Embedding Service

  - [x] 3.1 Implement Graph Service FastAPI application (services/graph-service/)
    - Create services/graph-service/src/main.py with FastAPI app, lifespan event for Neo4j driver initialization
    - Implement GraphStorePort protocol interface in src/ports/graph_store_port.py
    - Implement Neo4jGraphStore adapter in src/infrastructure/neo4j_adapter.py with async driver, connection pool (10-50), per-query timeout (5s)
    - Create indexes on entity_type and source_chunk_id during initialization (CREATE INDEX IF NOT EXISTS)
    - Implement store_entities using MERGE by entity id with all properties
    - Implement store_relationships with MERGE by relationship id; skip relationships with missing endpoints and log warning
    - Implement traverse with variable-length Cypher path query, max_hops capped at 5, scoring by 1.0/(1+hop_distance)
    - Implement delete_by_document removing all nodes for a document_id and connected relationships in a single transaction
    - Raise GraphStoreUnavailableError on Neo4j unavailability or 5s timeout
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 14.1, 14.2, 14.3, 14.4_

  - [x] 3.2 Implement Graph Service REST endpoints and health checks
    - Implement POST /entities endpoint validating against StoreEntitiesRequest model, delegating to Neo4jGraphStore
    - Implement POST /relationships endpoint validating against StoreRelationshipsRequest model
    - Implement POST /traverse endpoint validating against TraverseRequest model, returning TraverseResponse
    - Implement DELETE /documents/{document_id} endpoint
    - Implement /health (Neo4j connectivity), /health/ready (pool + indexes), /health/live (always 200)
    - Implement /metrics endpoint for Prometheus-compatible metrics
    - Accept and log X-Correlation-ID header in all structured log entries
    - Return HTTP 422 with validation error details for invalid request bodies
    - _Requirements: 14.1, 14.3, 14.4, 14.5, 14.6, 14.7_

  - [x]* 3.3 Write property tests for Graph Service (Properties 1-5, 28)
    - **Property 1: Entity storage round-trip preserves all data** — For any list of valid ExtractedEntity objects, storing via POST /entities and traversing by name/entity_type returns results with all original properties
    - **Validates: Requirements 1.1, 1.9**
    - **Property 2: Relationship storage with deduplication** — Storing the same relationship id twice creates exactly one edge
    - **Validates: Requirements 1.2**
    - **Property 3: Referential integrity on relationship storage** — Relationships referencing non-existent entities are skipped
    - **Validates: Requirements 1.3**
    - **Property 4: Graph traversal scoring follows distance formula** — Score equals 1.0/(1+hop_distance), max_hops capped at 5
    - **Validates: Requirements 1.4, 14.4**
    - **Property 5: Document deletion removes exactly target document's data** — DELETE /documents/{id} removes only that document's entities and relationships
    - **Validates: Requirements 1.5**
    - **Property 28: Graph Service request body validation** — Malformed bodies receive HTTP 422 with validation details
    - **Validates: Requirements 14.3, 14.6**

  - [x] 3.4 Implement Embedding Service FastAPI application (services/embedding-service/)
    - Create services/embedding-service/src/main.py with FastAPI app, lifespan event for cache initialization and Bedrock client setup
    - Implement EmbeddingPort protocol interface in src/ports/embedding_port.py
    - Implement BedrockEmbeddingAdapter in src/infrastructure/bedrock_adapter.py
    - Implement SHA-256 embedding cache (in-memory dict keyed by hash of input text)
    - Implement POST /embed: compute SHA-256 hash, check cache, call Bedrock on miss, cache result, return vector + tokens_used
    - Implement POST /embed/batch: check cache per item, batch only uncached to Bedrock, cache new results, return vectors in original order + total tokens_used
    - Implement token budget enforcement: estimate token count of each input text before calling Bedrock; reject texts exceeding 8192 tokens with HTTP 422 response indicating text exceeds token budget (do not send oversized request to Bedrock)
    - Implement token usage tracking returned in every response
    - Implement /health (Bedrock connectivity), /health/ready (cache initialized + credentials valid), /health/live (always 200)
    - Implement /metrics endpoint for Prometheus-compatible metrics
    - Accept and log X-Correlation-ID header; return HTTP 503 on Bedrock unavailability
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9_

  - [x]* 3.5 Write property tests for Embedding Service (Properties 29-30)
    - **Property 29: Embedding cache round-trip** — First call computes hash and calls Bedrock; second call with same text returns identical vector from cache without Bedrock call; batch requests check each item individually
    - **Validates: Requirements 15.2, 15.3, 15.4**
    - **Property 30: Token usage tracking in responses** — Every response (single or batch) includes tokens_used as a non-negative integer
    - **Validates: Requirements 15.5**

- [x] 4. Sprint 1 Checkpoint
  - Ensure Graph Service and Embedding Service start correctly, pass all unit and property tests, and respond to health checks.
  - Ask the user if questions arise.

- [x] 5. Sprint 2: Ingestion Service

  - [x] 5.1 Implement Legal-Hierarchical Chunker (services/ingestion-service/)
    - Implement LegalHierarchicalChunker in src/domain/processing/legal_hierarchical_chunker.py
    - Detect Act title (H1 or pattern matching "<Title> Act <Year>"), Part/Division headings
    - Prepend Act title and Part/Division heading as contextual prefix separated by newline
    - Preserve section numbering hierarchy in chunk metadata under "hierarchy_path" key
    - Enforce max_chunk_size: prioritize prefix retention, reduce body text, ensure minimum 100 chars body
    - Set section_heading (non-empty) and parent_document_title (filename fallback) on every chunk
    - Log warning when no Act/Regulation title markers found
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [x] 5.2 Implement Chunker Registry (services/ingestion-service/)
    - Implement ChunkerRegistry in src/domain/processing/chunker_registry.py
    - Register fixed-size, recursive, semantic, and legal-hierarchical strategies during lifespan event
    - Implement auto-selection logic: legal_hierarchical for .pdf/.md with legislative keywords; recursive for .html or .pdf/.md without keywords; fixed_size for .txt or unrecognized extensions
    - Implement fallback to fixed_size when selected strategy is unavailable (log warning)
    - Implement explicit strategy selection by name; reject unrecognized names with error
    - Expose registered_strategies property returning name and availability status
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 5.3 Implement Ingestion Service FastAPI application (services/ingestion-service/)
    - Create services/ingestion-service/src/main.py with FastAPI app, lifespan event for ChromaDB, BM25 index, and Chunker Registry initialization
    - Implement POST /v1/ingest: accept multipart file, validate format (.txt, .md, .html, .pdf) and size (50MB max)
    - Implement ingestion pipeline: auto-select chunker, chunk document, extract entities/relationships (Ingestion Agent), call Embedding Service POST /embed/batch, store vectors in ChromaDB + tokens in BM25, call Graph Service POST /entities + POST /relationships
    - Use ResilientClient from libs/service-client for inter-service calls with circuit breaker and retry
    - Implement GET /v1/documents: list ingested documents with filename, format, ingestion_date sorted descending
    - Implement /health, /health/ready, /health/live, /metrics endpoints
    - Return 503 if Embedding Service unavailable (critical); complete without graph on Graph Service failure (degraded)
    - _Requirements: 3.2, 3.5, 7.1, 13.5, 13.6, 16.4_

  - [x]* 5.4 Write property tests for Ingestion Service (Properties 11-14)
    - **Property 11: Legal-hierarchical chunker metadata completeness** — Every output chunk has non-empty section_heading, parent_document_title, prefix with Act title and Part/Division heading, and hierarchy_path metadata
    - **Validates: Requirements 5.1, 5.2, 5.5, 5.6**
    - **Property 12: Legal-hierarchical chunker size constraints** — Every chunk does not exceed max_chunk_size; when prefix plus body exceeds limit, prefix is preserved and body is reduced to minimum 100 chars
    - **Validates: Requirements 5.3, 5.4**
    - **Property 13: Chunker Registry auto-selection correctness** — Auto-selection maps file extensions plus keywords to correct strategies; unavailable strategies fall back to fixed_size
    - **Validates: Requirements 6.2, 6.5**
    - **Property 14: Chunker Registry explicit strategy selection** — Registered names use that strategy; unregistered names are rejected with error
    - **Validates: Requirements 6.6, 6.7**

- [x] 6. Sprint 2 Checkpoint
  - Ensure Ingestion Service starts, inter-service calls to Graph and Embedding Service work, chunking produces correct metadata, and property tests pass.
  - Ask the user if questions arise.

- [x] 7. Sprint 3: Query Service

  - [x] 7.1 Implement Query Service FastAPI application with Orchestrator (services/query-service/)
    - Create services/query-service/src/main.py with FastAPI app, lifespan event creating RAGOrchestrator and storing in app.state
    - Implement RAGOrchestrator class coordinating Retrieval_Agent, Generation_Agent, Citation_Verification_Agent, Evaluation_Agent
    - Inject Orchestrator as FastAPI Depends dependency
    - Implement POST /v1/agents/ask: validate AgentAskRequest (1-2000 chars), route through Orchestrator, return AgentAskResponse within 30s
    - Implement POST /v1/ask: direct retrieval-only queries (existing behavior)
    - Implement output sanitization: strip HTML tags, JavaScript code, and control characters from generated answer text before including in API response, ensuring no executable content is returned to the client
    - Return HTTP 422 for missing/empty/oversized query; HTTP 500 with error_code, message, correlation_id on agent/service failures
    - Implement /health, /health/ready, /health/live, /metrics endpoints
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7_

  - [x] 7.2 Implement legal domain agent prompts and Strands Agent configuration
    - Configure Retrieval_Agent system prompt: recognize legal entity types, invoke graph traversal first on cross-reference keywords (AMENDS, REFERENCES, IMPLEMENTS, section numbers)
    - Configure Generation_Agent system prompt: cite specific sections using format Act/Regulation Title Section number(subsection), passive legislative phrasing, claims supported by source chunks only
    - Configure Citation_Verification_Agent system prompt: verify verbatim/paraphrase match, flag unsupported claims, confirm section_heading metadata match
    - Configure Ingestion_Agent system prompt: extract legal entities and relationships from text, minimum one entity per legislative section
    - Configure Evaluation_Agent system prompt: score legislative accuracy, section-level citation precision, obligation/authority completeness
    - Store prompts as configurable text strings loaded at initialization; raise ConfigurationError if empty/missing
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [x] 7.3 Implement hybrid search with RRF fusion in Retrieval Agent
    - Execute dense search (call Embedding Service for vector, query ChromaDB), sparse search (BM25), and graph search (call Graph Service /traverse) in parallel with 5s timeout each
    - Retrieve top 20 candidates from each method
    - Implement RRF fusion with k=60 and default weights: dense=0.5, sparse=0.2, graph=0.3
    - Implement weight renormalization when 1 or 2 methods are unavailable (preserve ratio, sum to 1.0)
    - Log degradation including which methods/services were unavailable
    - Use ResilientClient from libs/service-client for Graph and Embedding service calls
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [x] 7.4 Implement reranking, confidence scoring, and fallback logic
    - Implement cross-encoder reranker: rerank top 20 fused candidates, return top 5 (or fewer if less than 20 available)
    - Implement confidence scoring: composite = 0.35 x retrieval_confidence + 0.40 x citation_coverage + 0.25 x answer_completeness, rounded to 2 decimal places
    - Implement sub-score calculations: retrieval_confidence (max reranked score normalized), citation_coverage (verified citations / total factual statements), answer_completeness (addressed concepts / total query concepts)
    - Implement fallback trigger: composite less than 0.4 returns FallbackResponse with found_topics, not_found_topics, suggested_documents (up to 3)
    - Set all scores to 0.0 when no chunks retrieved or reranker returns zero results
    - _Requirements: 10.5, 11.1, 11.2, 11.3, 11.4, 11.5_

  - [x]* 7.5 Write property tests for Query Service (Properties 15-21)
    - **Property 15: API response completeness** — Every successful response contains answer, citations, confidence_scores (with all 4 sub-fields), source_chunks, and is_fallback
    - **Validates: Requirements 7.3**
    - **Property 16: Error response structure with correlation ID** — Agent/service failures return HTTP 500 with error_code, message, and correlation_id
    - **Validates: Requirements 7.4**
    - **Property 17: Query validation at Query Service** — Empty/missing/oversized queries return HTTP 422; valid queries (1-2000 chars) are processed
    - **Validates: Requirements 7.6**
    - **Property 18: RRF fusion with weight renormalization** — Weights renormalize proportionally when fewer than 3 methods available, preserving ratio and summing to 1.0
    - **Validates: Requirements 10.2, 10.4, 13.5**
    - **Property 19: Reranker output size invariant** — Returns min(5, N) results for N fused candidates where N is at most 20
    - **Validates: Requirements 10.5**
    - **Property 20: Confidence composite formula correctness** — Composite equals round(0.35 x retrieval + 0.40 x citation + 0.25 x completeness, 2) and is always in range 0.0 to 1.0
    - **Validates: Requirements 11.1**
    - **Property 21: Fallback response threshold** — is_fallback is true iff composite less than 0.4; true includes fallback info, false includes full answer with citations
    - **Validates: Requirements 11.2, 11.3**

- [x] 8. Sprint 3 Checkpoint
  - Ensure Query Service processes queries end-to-end through agent pipeline, hybrid search retrieves from all three methods, confidence scoring works, and property tests pass.
  - Ask the user if questions arise.

- [x] 9. Sprint 4: API Gateway

  - [x] 9.1 Implement API Gateway FastAPI application (services/gateway/)
    - Create services/gateway/src/main.py with FastAPI app and middleware stack
    - Implement CORS middleware: allow origins localhost:3000 and localhost:5173, methods GET/POST/DELETE, headers Content-Type/X-API-Key/X-Correlation-ID
    - Implement Correlation ID middleware: generate UUID v4, inject X-Correlation-ID on proxied requests, include in response
    - Implement API Key authentication middleware: validate X-API-Key against configured key set, return HTTP 401 if missing/invalid
    - Implement rate limiting middleware: in-memory token bucket, 60 requests per minute per API key, return HTTP 429 when exceeded
    - Implement request/response logging middleware: structlog JSON with method, path, status_code, duration_ms, correlation_id, key identifier (not full value)
    - Implement proxy routing: /v1/ask and /v1/agents/ask to Query Service (30s timeout), /v1/ingest and /v1/documents to Ingestion Service (60s timeout)
    - Return HTTP 504 on proxy timeout, HTTP 502 on downstream unreachable
    - Implement CSP headers: Content-Security-Policy restricting script-src to self
    - Implement security headers using the secure library: Strict-Transport-Security (max-age=31536000), X-Frame-Options (DENY), X-Content-Type-Options (nosniff), Referrer-Policy (no-referrer), X-XSS-Protection (1; mode=block)
    - Integrate fastapi-guard middleware for automated penetration detection: SQL injection, XSS payloads, path traversal, command injection patterns in paths/params/headers; return HTTP 403 on detection
    - Add fastapi-guard and secure to services/gateway/pyproject.toml dependencies
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.8, 12.9, 12.10, 17.5, 17.6_

  - [x] 9.2 Implement aggregated health endpoint
    - Implement /health endpoint checking connectivity to Query_Service, Ingestion_Service, Graph_Service, Embedding_Service (5s timeout per downstream)
    - Return HTTP 200 with individual service statuses when all healthy
    - Return HTTP 503 with failing service names when any downstream is unreachable
    - _Requirements: 12.7_

  - [x]* 9.3 Write property tests for API Gateway (Properties 22-25)
    - **Property 22: API Gateway authentication enforcement** — Missing/invalid API keys receive HTTP 401; valid keys are proxied to downstream
    - **Validates: Requirements 12.1**
    - **Property 23: Rate limiting token bucket** — At most 60 requests per minute per key; 61st request receives HTTP 429; requests allowed again after window reset
    - **Validates: Requirements 12.2**
    - **Property 24: Correlation ID generation and propagation** — Every request gets UUID v4 Correlation ID injected on downstream call and included in client response
    - **Validates: Requirements 12.3, 13.2, 14.7, 15.8**
    - **Property 25: API Gateway request routing correctness** — /v1/ask and /v1/agents/ask route to Query Service; /v1/ingest and /v1/documents route to Ingestion Service
    - **Validates: Requirements 12.5**

- [x] 10. Sprint 4 Checkpoint
  - Ensure API Gateway routes requests correctly, authentication and rate limiting work, correlation IDs propagate through the system, and property tests pass.
  - Ask the user if questions arise.

- [x] 11. Sprint 5: React Frontend (WCAG 2.0 AA)

  - [x] 11.1 Initialize React 19 frontend project (frontend/)
    - Initialize with Vite + React 19 + TypeScript strict mode
    - Configure TailwindCSS with custom theme (color tokens for confidence: green/amber/red)
    - Install dependencies: tanstack/react-query, eslint-plugin-jsx-a11y
    - Configure ESLint with jsx-a11y plugin, Prettier
    - Set up VITE_API_BASE_URL environment variable (default http://localhost:8080)
    - Configure API client with X-API-Key header on all requests
    - _Requirements: 2.9_

  - [x] 11.2 Implement chat interface with React 19 patterns
    - Implement ChatInput component: text field (max 1000 chars) with Send button, Enter to submit
    - Implement submission logic using useActionState: disable input, POST to /v1/agents/ask, show loading indicator (30s timeout)
    - Implement whitespace-only input rejection (no request sent, input unchanged)
    - Implement ConversationHistory: scrollable session history, cleared on page reload
    - Implement MessageBubble: display answer with inline citation markers
    - Implement useOptimistic for optimistic UI updates during submission
    - Implement error handling: dismiss loading on network error/timeout, re-enable input, show error message
    - _Requirements: 2.1, 2.2, 2.3, 2.8, 2.10, 2.11_

  - [x] 11.3 Implement source panel, confidence indicator, and citation navigation
    - Implement SourcePanel: list source chunks with section_heading, relevance score, retrieval_method
    - Implement ConfidenceIndicator: color-coded (green for score >= 0.7, amber for score >= 0.4, red for score < 0.4)
    - Implement citation click navigation: scroll source panel to referenced chunk, visually highlight
    - Implement fallback display: show found/not-found topics and suggested documents when is_fallback is true
    - _Requirements: 2.4, 2.5, 2.6, 2.7_

  - [x] 11.4 Implement document upload and list interface
    - Implement UploadArea: accept .txt, .md, .html, .pdf (max 50MB), drag-and-drop plus file picker
    - Implement client-side validation: reject disallowed extensions or oversized files with inline message before any network request
    - Implement upload flow: POST multipart to /v1/ingest via API Gateway, show loading (60s timeout), success notification with filename and chunk count
    - Implement retry on network error without re-selecting file
    - Implement DocumentList: fetch GET /v1/documents, display filename, format, ingestion_date sorted descending
    - Implement Layout with navigation between Chat and Documents views
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6_

  - [x] 11.5 Implement WCAG 2.0 AA accessibility compliance
    - Use semantic HTML elements (main, nav, article, section, aside) throughout
    - Add ARIA attributes where native semantics insufficient (aria-live for chat updates, aria-describedby for errors)
    - Implement keyboard navigation: all interactive elements focusable, visible focus indicators, no keyboard traps
    - Implement focus management: move focus to new messages, manage focus on view transitions
    - Ensure contrast ratio 4.5:1 for normal text, 3:1 for large text
    - Ensure touch targets minimum 44x44px
    - Respect prefers-reduced-motion media query
    - Associate error messages with controls via aria-describedby
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x]* 11.6 Write property tests for Frontend (Properties 6-9)
    - **Property 6: Confidence score color mapping** — Green when score >= 0.7, amber when >= 0.4 and < 0.7, red when < 0.4; ranges exhaustive and non-overlapping
    - **Validates: Requirements 2.4**
    - **Property 7: Whitespace-only input rejection** — Any whitespace-only string prevents submission, no API request sent
    - **Validates: Requirements 2.10**
    - **Property 8: File upload validation** — Accept iff extension in txt/md/html/pdf AND size <= 50MB; reject with inline message before network request
    - **Validates: Requirements 3.1**
    - **Property 9: Document list ordering** — Documents displayed in strictly descending ingestion_date order
    - **Validates: Requirements 3.5**

- [x] 12. Sprint 5 Checkpoint
  - Ensure Frontend renders correctly, chat submits queries and displays responses, document upload works, WCAG 2.0 AA accessibility passes automated checks, and property tests pass.
  - Ask the user if questions arise.

- [ ] 13. Sprint 6: Testing and Sample Data

  - [-] 13.1 Create sample legislative documents (data/sample_documents/)
    - Create 2 Acts in Markdown: Transport Infrastructure Act and Road Use Management Act, each with minimum 2 Parts, 2 Divisions, 5 Sections, 1500+ chars body text
    - Create 2 Regulations: Driver Licensing Regulation and Heavy Vehicle Access Regulation
    - Create 2 internal policies and 2 business rules documents
    - Include minimum 4 cross-references between documents, 2 definitions sections, 2 penalty provisions
    - Exercise all 7 legal entity types (Act, Section, Regulation, Definition, Obligation, Authority, Penalty) and all 8 relationship types
    - _Requirements: 8.1, 8.2, 8.5, 8.6_

  - [-] 13.2 Create golden QA dataset (data/golden_dataset.json)
    - Create 20 question-answer pairs: 5 licence queries, 5 permit/route queries, 5 legislative interpretation, 5 road design standards
    - Each entry includes: question (max 300 chars), expected_answer (max 2000 chars), source_document filename, section_references, minimum_confidence score
    - Ensure all answers are fully derivable from sample documents content
    - Validate no entry references a non-existent source document or section
    - _Requirements: 8.3, 8.4, 8.7_

  - [-] 13.3 Implement contract tests between services (tests/contract/)
    - Write test_query_graph_contract.py: Query Service client expectations match Graph Service response schemas
    - Write test_query_embedding_contract.py: Query Service client expectations match Embedding Service response schemas
    - Write test_ingestion_graph_contract.py: Ingestion Service client expectations match Graph Service request/response schemas
    - Write test_ingestion_embedding_contract.py: Ingestion Service client expectations match Embedding Service request/response schemas
    - Write test_gateway_routing_contract.py: API Gateway routing matches downstream service endpoint definitions
    - All contracts validate against shared domain-models Pydantic schemas
    - _Requirements: 19.4_

  - [~] 13.4 Implement E2E tests (tests/e2e/)
    - Write test_ingest_query_pipeline.py: ingest sample document through API Gateway to Ingestion Service, query through API Gateway to Query Service, verify response includes citation from ingested document with verification_status verified
    - Write test_graph_traversal_cross_service.py: verify Query Service calls Graph Service via HTTP and returns related entities for AMENDS/REFERENCES relationships
    - Write test_fallback_behavior.py: query with no relevant documents returns is_fallback true, composite below 0.4, non-empty suggested_documents
    - Write test_circuit_breaker_degradation.py: when Graph Service unavailable, Query Service returns degraded response using dense and sparse only within 30s
    - Include correlation_id from X-Correlation-ID response header in all test failure output
    - Set 60-second timeout per individual E2E test
    - _Requirements: 9.1, 9.2, 9.3, 9.5, 9.6, 9.7_

  - [~] 13.5 Implement Playwright frontend E2E tests (tests/e2e/playwright/)
    - Write test_frontend.py: submit question, verify non-empty answer within 30s, at least one citation marker rendered and clickable, source panel renders at least one source chunk with visible section heading
    - Test document upload flow end-to-end
    - Test accessibility basics: focus management, keyboard navigation
    - _Requirements: 9.4_

  - [-] 13.6 Create Postman collections and Newman automation
    - Create Postman collection for API Gateway endpoints (ask, ingest, documents, health)
    - Create Postman collection for each internal service (Graph, Embedding, Ingestion, Query)
    - Write Newman scripts for CI integration testing against Docker Compose environment
    - Include environment variables for base URLs, API keys, correlation IDs
    - _Requirements: 19.5_

  - [ ]* 13.7 Write property test for prompt validation (Property 10)
    - **Property 10: Agent prompt initialization validation** — For any agent, if system prompt is empty/None/fails to load, raise ConfigurationError and prevent accepting requests
    - **Validates: Requirements 4.8**

- [~] 14. Sprint 6 Checkpoint
  - Ensure sample data is valid, golden dataset references existing documents, contract tests pass, E2E tests pass against Docker Compose, and Postman collections execute successfully.
  - Ask the user if questions arise.

- [ ] 15. Sprint 7: Observability and Resilience

  - [~] 15.1 Implement OpenTelemetry distributed tracing across all services
    - Add opentelemetry-sdk and opentelemetry-exporter-otlp to each service
    - Instrument each FastAPI app with OpenTelemetry middleware
    - Configure spans with service_name, correlation_id, operation_name, duration_ms
    - Correlate spans using X-Correlation-ID as trace parent identifier
    - Configure OTLP exporter endpoint via environment variable
    - Implement PII log scrubbing across all services: truncate raw user query text to 100 characters in log entries, log only first 8 characters of API key values (never full key), ensure no personally identifiable information (email addresses, names from document content) appears in log entries or error responses returned to clients
    - _Requirements: 18.1, 18.6, 17.7_

  - [~] 15.2 Implement Prometheus metrics per service
    - Add /metrics endpoint to each service exposing: request_latency_seconds (histogram), request_total (counter by status_code), active_requests (gauge), error_total (counter by error_type)
    - Add token usage metrics per agent per request in Embedding Service
    - _Requirements: 18.2, 18.5_

  - [~] 15.3 Create Grafana dashboard configurations
    - Create system overview dashboard showing all services health, latency, error rates
    - Create per-service detail dashboard with request rates, latencies, error breakdowns
    - Create agent pipeline dashboard showing latency breakdown across Retrieval, Generation, Citation Verification, and Evaluation Agent stages
    - _Requirements: 18.3_

  - [~] 15.4 Define alerting rules
    - Configure alerts: P99 latency exceeds 30s for any service, error rate exceeds 5 percent over 5-minute window, health check fails for more than 60 consecutive seconds
    - _Requirements: 18.4_

  - [ ]* 15.5 Write property tests for resilience patterns (Properties 26-27)
    - **Property 26: Circuit breaker state transitions** — Transitions from CLOSED to OPEN after exactly 5 consecutive failures; rejects all calls for 30s; transitions to HALF_OPEN allowing 1 probe; success closes, failure reopens
    - **Validates: Requirements 13.3**
    - **Property 27: Retry with exponential backoff and jitter** — At most 3 attempts with delays of base_delay x multiplier^(attempt-1) plus jitter where base=1s, multiplier=2, jitter in 0 to 500ms
    - **Validates: Requirements 13.4**

  - [~] 15.6 Implement cost tracking for token usage
    - Aggregate Bedrock API token consumption through Embedding Service token tracking
    - Expose cost attribution metrics per agent per request
    - _Requirements: 18.5_

- [~] 16. Sprint 7 Checkpoint
  - Ensure distributed tracing shows end-to-end spans, Prometheus metrics are scraped, Grafana dashboards render data, circuit breaker and retry property tests pass.
  - Ask the user if questions arise.

- [ ] 17. Sprint 8: Terraform, CI/CD, and Production Readiness

  - [~] 17.1 Create Terraform modules (infrastructure/terraform/)
    - Implement VPC module: public/private subnets, NAT gateway, security groups
    - Implement ECS/Fargate module: task definitions and services for each microservice (Gateway, Query, Ingestion, Graph, Embedding)
    - Implement ALB module: Application Load Balancer with path-based routing to services
    - Implement Neo4j EC2 module: EC2 instance for Neo4j Community Edition
    - Implement ElastiCache module: Redis for embedding cache in prod
    - Implement S3 module: document storage bucket
    - Implement CloudWatch module: log groups per service
    - Implement IAM module: service-specific roles with least privilege
    - Tag all resources: project, environment, managed_by=terraform
    - Use variable validation blocks; state in S3 with DynamoDB lock; sensitive outputs marked
    - _Requirements: 17.4_

  - [~] 17.2 Implement GitLab CI/CD per-service pipelines
    - Create .gitlab-ci/ directory with shared pipeline templates (lint, test, security, build stages)
    - Create per-service .gitlab-ci.yml extending shared templates
    - Pipeline stages: lint (ruff/eslint) then typecheck (mypy/tsc) then unit tests then property tests then integration tests then security scan (bandit/pip-audit or eslint-plugin-security/npm audit) then Docker image build
    - Build and tag Docker images with git commit SHA; push only when all stages pass
    - Report failing stage, specific test, and correlation_id on failure
    - _Requirements: 19.1, 19.2, 19.6, 19.7_

  - [~] 17.3 Implement test gates and security scanning
    - Enforce minimum 80 percent code coverage (unit plus property tests combined)
    - Enforce all property-based tests passing
    - Enforce no critical/high vulnerabilities from SAST (bandit, eslint-plugin-security) or dependency scanning (pip-audit, npm audit)
    - Integrate Newman/Postman API test stage running against Docker Compose environment
    - _Requirements: 19.3, 19.5, 17.2, 17.3_

  - [~] 17.4 Create SSDLC artifacts and defense-in-depth validation
    - Create STRIDE threat model document covering RAG pipeline data flow from ingestion through retrieval to generation, identifying threats at each service boundary
    - Validate input at API Gateway boundary AND each individual service boundary (defense in depth)
    - Ensure secrets managed via environment variables (dev) and AWS Secrets Manager (prod); no secrets in VCS or logs
    - _Requirements: 17.1, 17.4, 17.5_

  - [~] 17.5 Create Kiro hooks for development workflow
    - Create lint-frontend hook: run eslint on frontend file changes
    - Create validate-prompts hook: validate agent prompt files are non-empty on edit
    - Create security-scan-gateway hook: preToolUse on write to services/gateway/, verify fastapi-guard middleware is configured and security headers are applied
    - _Requirements: 4.8, 12.9, 12.10_

- [~] 18. Sprint 8 Checkpoint - Final
  - Ensure Terraform plans successfully, CI pipeline stages execute in correct order, test gates block on failures, security scans produce no critical findings, and all property tests pass across all services.
  - Ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional property-based test tasks and can be skipped for faster MVP
- Each task references specific requirements for traceability (all 19 requirements covered)
- All 30 correctness properties are assigned to specific property test tasks
- Checkpoints ensure incremental validation at sprint boundaries
- Property tests use Hypothesis with minimum 100 examples per property
- Backend services use Python 3.11+ with FastAPI; Frontend uses React 19 + TypeScript + TailwindCSS
- Inter-service communication uses the shared libs/service-client with circuit breaker and retry
- All services share Pydantic models from libs/domain-models to prevent schema drift
- Docker Compose provides the local development environment; Terraform targets AWS ECS/Fargate for production
- Service dependency order: shared libs (Sprint 0) then Graph/Embedding (Sprint 1) then Ingestion (Sprint 2) then Query (Sprint 3) then Gateway (Sprint 4) then Frontend (Sprint 5)

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.3"] },
    { "id": 2, "tasks": ["1.4", "1.5", "1.6", "1.7", "1.8"] },
    { "id": 3, "tasks": ["3.1", "3.4"] },
    { "id": 4, "tasks": ["3.2", "3.3", "3.5"] },
    { "id": 5, "tasks": ["5.1", "5.2"] },
    { "id": 6, "tasks": ["5.3", "5.4"] },
    { "id": 7, "tasks": ["7.1", "7.2"] },
    { "id": 8, "tasks": ["7.3", "7.4"] },
    { "id": 9, "tasks": ["7.5"] },
    { "id": 10, "tasks": ["9.1"] },
    { "id": 11, "tasks": ["9.2", "9.3"] },
    { "id": 12, "tasks": ["11.1"] },
    { "id": 13, "tasks": ["11.2", "11.3", "11.4"] },
    { "id": 14, "tasks": ["11.5", "11.6"] },
    { "id": 15, "tasks": ["13.1", "13.2"] },
    { "id": 16, "tasks": ["13.3", "13.6", "13.7"] },
    { "id": 17, "tasks": ["13.4", "13.5"] },
    { "id": 18, "tasks": ["15.1", "15.2"] },
    { "id": 19, "tasks": ["15.3", "15.4", "15.5", "15.6"] },
    { "id": 20, "tasks": ["17.1", "17.2"] },
    { "id": 21, "tasks": ["17.3", "17.4", "17.5"] }
  ]
}
```
