# Legislation RAG Platform — Complete Project Documentation

## Executive Summary

The Legislation RAG Platform is a production-grade Retrieval-Augmented Generation (RAG) system designed for regulated industries (banking, financial services, compliance). It ingests internal policy documents (PDF, HTML, Markdown, plaintext), indexes them across three complementary retrieval methods (dense vectors, sparse keywords, knowledge graph), and answers natural-language compliance questions with grounded, cited responses and confidence scoring.

**Primary use case:** Know Your Customer (KYC) / Anti-Money Laundering (AML) compliance — analysts ask questions about internal policies and receive precise, auditable answers with verifiable citations linking every claim to its source paragraph.

**Key guarantees:**
- 100% citation traceability — every claim links to a specific source passage
- Composite confidence scoring with fallback when certainty is low
- Prompt injection detection at the API boundary
- Tiered model selection for cost optimization (~$0.001 per standard query)
- Hybrid search covering semantic, keyword, and entity-relationship queries

---

## Technology Stack

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| **AI/ML** | AWS Bedrock (Nova Lite, Nova Pro, Claude Sonnet), Strands Agents SDK, sentence-transformers (cross-encoder reranker) |
| **Vector Store** | ChromaDB (local/dev), OpenSearch/Qdrant (production) |
| **Keyword Search** | rank-bm25 (in-memory BM25 sparse retrieval) |
| **Knowledge Graph** | Neo4j 5 Community (local), AWS Neptune (production) |
| **Caching** | Redis 7 |
| **Frontend** | React 19, TypeScript 5.7, Vite 6, TailwindCSS 4, @tanstack/react-query 5 |
| **Infrastructure** | Terraform (AWS ECS/Fargate, VPC, ALB, IAM), Docker multi-stage |
| **CI/CD** | GitLab CI (lint → test → security → build → deploy) |
| **Observability** | structlog (JSON), OpenTelemetry, Prometheus, CloudWatch |
| **Testing** | pytest, Hypothesis (property-based), Schemathesis (API contract), Vitest + Testing Library (frontend) |
| **Security** | fastapi-guard (penetration detection), secure (security headers), python-jose (JWT) |

---

## Architecture

### Hexagonal (Ports & Adapters) Pattern

The core application uses strict domain isolation:

```
┌─────────────────────────────────────────────────────────────────┐
│                         API Layer                                 │
│    FastAPI routes → request validation → auth → rate limiting    │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                      Domain Services                             │
│  RetrievalService │ GenerationService │ IngestionService │ etc. │
│         (pure business logic — no infrastructure imports)        │
└────────────────────────────┬────────────────────────────────────┘
                             │ Ports (Protocol interfaces)
┌────────────────────────────▼────────────────────────────────────┐
│                   Infrastructure Adapters                         │
│  ChromaDB │ BM25 │ Neo4j │ Bedrock │ CrossEncoder │ Redis       │
└─────────────────────────────────────────────────────────────────┘
```

**Key rule:** Domain services only import from `src/ports/` and `src/domain/models/` — never from `src/infrastructure/`. This allows swapping storage backends (e.g., ChromaDB → OpenSearch) without touching business logic.

### Ports (Interfaces)

| Port | Methods | Purpose |
|------|---------|---------|
| `VectorStorePort` | `store`, `search`, `delete_by_document`, `find_similar` | Dense vector operations |
| `SparseIndexPort` | `index`, `search`, `delete_by_document` | BM25 keyword matching |
| `GraphStorePort` | `store_entities`, `store_relationships`, `traverse`, `delete_by_document` | Knowledge graph operations |
| `EmbeddingPort` | `embed`, `embed_single` | Text-to-vector embedding |
| `RerankerPort` | `rerank` | Cross-encoder reranking |
| `DocumentStorePort` | `store`, `retrieve`, `list_documents` | Raw document persistence |
| `LLMPort` | (generation interface) | Language model calls |
| `CachePort` | (caching interface) | Result caching |

### AI Agent Orchestration (Strands SDK)

Five specialized agents coordinated by a `RAGOrchestrator`:

| Agent | Model Tier | Purpose |
|-------|-----------|---------|
| **Retrieval Agent** | Nova Lite | Hybrid search across dense/sparse/graph, RRF fusion, reranking |
| **Generation Agent** | Nova Pro | Grounded answer generation with bracketed citations |
| **Citation Verification Agent** | Nova Lite | LLM-as-judge faithfulness validation of each claim |
| **Ingestion Agent** | Nova Lite | Document processing pipeline orchestration |
| **Evaluation Agent** | Nova Pro | Quality benchmarking and regression detection |

Model tier configuration:
- **Lite** (`apac.amazon.nova-lite-v1:0`): Simple tool-calling and orchestration
- **Pro** (`apac.amazon.nova-pro-v1:0`): Reasoning and generation tasks
- **Premium** (`apac.anthropic.claude-sonnet-4-20250514-v1:0`): Complex evaluation (fallback)

---

## Directory Structure

```
legislation-rag-platform/
├── src/                           # Core monolith (hexagonal architecture)
│   ├── agents/                    # 5 AI agents + orchestrator
│   │   ├── base.py               # Shared config, model factory, tier selection
│   │   ├── orchestrator.py        # Coordinates all agents end-to-end
│   │   ├── retrieval_agent.py     # Hybrid search agent
│   │   ├── generation_agent.py    # Answer generation agent
│   │   ├── citation_verification_agent.py  # Faithfulness checking
│   │   ├── ingestion_agent.py     # Document processing agent
│   │   └── evaluation_agent.py    # Quality benchmarking agent
│   ├── api/                       # FastAPI application layer
│   │   ├── app.py                 # Application factory + lifespan DI
│   │   ├── models.py             # Request/response Pydantic models
│   │   ├── routes/               # Route handlers (pipeline.py, agents.py)
│   │   ├── middleware/           # Auth, rate limit, correlation ID
│   │   └── dependencies/        # FastAPI Depends() functions
│   ├── domain/                    # Pure business logic
│   │   ├── models/               # Pydantic entities + enums
│   │   ├── services/            # RetrievalService, GenerationService, etc.
│   │   ├── processing/          # Normalizers, chunkers, entity extraction
│   │   └── events/              # Domain events + event bus
│   ├── infrastructure/           # Port implementations (adapters)
│   │   ├── bedrock_embedding.py
│   │   ├── chromadb_vector_store.py
│   │   ├── bm25_sparse_index.py
│   │   ├── cross_encoder_reranker.py
│   │   ├── in_memory_graph_store.py
│   │   ├── local_document_store.py
│   │   ├── in_memory_cache.py
│   │   └── resilience/          # Circuit breaker, retry logic
│   └── ports/                    # Protocol interfaces (8 ports)
├── services/                      # Microservices (independently deployable)
│   ├── gateway/                   # API gateway (auth, rate limit, routing)
│   ├── query-service/            # Query orchestration + agent pipeline
│   ├── ingestion-service/        # Document processing service
│   ├── embedding-service/        # Bedrock embedding generation
│   └── graph-service/            # Neo4j entity/relationship CRUD
├── libs/                          # Shared libraries (monorepo packages)
│   ├── domain-models/            # Shared Pydantic domain models
│   └── service-client/           # Resilient httpx client (circuit breaker)
├── frontend/                      # React 19 SPA
│   └── src/
│       ├── components/           # 15 UI components
│       ├── hooks/                # useAsk, useDocuments, useIngest
│       ├── pages/                # ChatPage, DocumentsPage
│       ├── lib/                  # API client
│       └── types/                # TypeScript interfaces
├── infrastructure/                # IaC
│   ├── environments/             # dev/ and prod/ Terraform configs
│   ├── modules/                  # networking, compute, data-stores, secrets
│   ├── docker/                   # Docker Compose (full microservices stack)
│   └── terraform/                # (placeholder)
├── tests/                         # Comprehensive test suite
│   ├── unit/                     # Unit tests (mirrors src/ structure)
│   ├── property/                 # 20 Hypothesis property-based tests
│   ├── integration/              # External service tests
│   ├── contract/                 # API contract tests
│   ├── e2e/                      # End-to-end tests
│   └── evaluation/               # Golden dataset benchmarking harness
├── docs/                          # Documentation
│   ├── openapi/                  # OpenAPI 3.1 specs (per service)
│   └── grc/                      # ISO 27001 + ISO 42001 control matrices
├── data/                          # Sample documents + golden dataset
├── scripts/                       # Utility scripts
├── pyproject.toml                 # Root package config (monorepo)
├── Dockerfile                     # Multi-stage Docker build
├── docker-compose.yml             # Simplified local dev stack
├── .gitlab-ci.yml                 # CI/CD pipeline
└── .kiro/steering/               # AI coding assistant guidelines
```

---

## Core Data Flow

### Query Pipeline (POST /v1/ask)

```
User Query
    │
    ▼
Security Scan (prompt injection detection)
    │
    ▼
Embed Query (Bedrock Titan → 1024-dim vector)
    │
    ▼
Parallel Search ─┬─ Dense (ChromaDB cosine similarity)
                 ├─ Sparse (BM25 keyword matching)
                 └─ Graph (Neo4j entity traversal, max 2 hops)
    │
    ▼
Reciprocal Rank Fusion (RRF)
    score(d) = Σ (weight_i / (k + rank_i(d)))
    k=60, weights: dense=0.5, sparse=0.2, graph=0.3
    │
    ▼
Cross-Encoder Reranking (top-20 → top-5)
    model: ms-marco-MiniLM-L-12-v2
    │
    ▼
Answer Generation (Bedrock Nova Pro)
    Grounded in retrieved chunks only
    Bracketed citations [1], [2], [3]
    │
    ▼
Citation Verification (LLM-as-judge)
    Each claim validated against source chunk
    │
    ▼
Confidence Scoring
    composite = 0.35*retrieval + 0.40*citation + 0.25*completeness
    │
    ▼
Response (answer + citations + confidence + sources)
    If composite < 0.4 → fallback response
```

### Ingestion Pipeline (POST /v1/ingest)

```
Document Upload (PDF/HTML/MD/TXT)
    │
    ▼
Validate (format, size ≤ 50MB, filename safety)
    │
    ▼
Store Raw Document
    │
    ▼
Normalize (format-specific → plaintext + sections)
    │
    ▼
Chunk (fixed_size=500 chars, overlap=100 | recursive | semantic)
    │
    ▼
Deduplicate (cosine similarity > 0.95 → skip)
    │
    ▼
Index (embed → ChromaDB + BM25 + Neo4j entities)
    │
    ▼
Emit DocumentIngestedEvent
```

---

## API Endpoints

### Core Monolith API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness probe |
| `GET` | `/ready` | Readiness probe (checks vector store + sparse index) |
| `POST` | `/v1/ask` | Hybrid search + generation (main query endpoint) |
| `POST` | `/v1/ingest` | Document upload and processing |
| `GET` | `/v1/documents` | List ingested documents |

### Gateway API (Microservices)

| Method | Path | Description | Timeout |
|--------|------|-------------|---------|
| `POST` | `/v1/agents/ask` | Full agent pipeline (5 agents) | 30s |
| `POST` | `/v1/ask` | Direct retrieval (no agent orchestration) | 30s |
| `POST` | `/v1/ingest` | Document upload (multipart) | 60s |
| `GET` | `/v1/documents` | Document listing | 5s |
| `GET` | `/health` | Aggregated health (all downstream) | - |
| `GET` | `/health/ready` | Gateway readiness | - |
| `GET` | `/health/live` | Gateway liveness | - |

### Security

- API key authentication via `X-API-Key` header (health endpoints exempt)
- Rate limiting: 60 requests/minute/key (token bucket)
- Prompt injection detection on all query inputs
- Security headers: HSTS, X-Frame-Options DENY, CSP, X-Content-Type-Options

---

## Domain Models

### Core Entities (Pydantic v2)

```
RawDocument          → Uploaded file (id, filename, format, content, metadata)
NormalizedDocument   → Parsed plaintext with sections
Chunk                → Text segment (id, document_id, index, text, section, strategy)
ScoredChunk          → Chunk + relevance score + retrieval method
EmbeddingRecord      → Chunk vector + metadata
ExtractedEntity      → Named entity from document
ExtractedRelationship→ Entity-to-entity relationship
Query                → User query with parameters
Citation             → Claim-to-source mapping (index, claim, source_text, verified)
ConfidenceScore      → 3-dimension confidence (retrieval, citation, completeness, composite)
GenerationResult     → Complete answer with citations + confidence
```

### Enums

- `DocumentFormat`: markdown, plaintext, html, pdf
- `ChunkingStrategy`: fixed_size, recursive, semantic
- `UserRole`: reader, editor, admin
- `RRFWeights`: dense=0.5, sparse=0.2, graph=0.3 (must sum to 1.0)

---

## Microservices Architecture

### Service Dependency Layers

```
Layer 1: Infrastructure    → Neo4j, ChromaDB
Layer 2: Leaf Services     → Graph Service (8003), Embedding Service (8004)
Layer 3: Mid Services      → Query Service (8001), Ingestion Service (8002)
Layer 4: Entry Point       → API Gateway (8080)
Layer 5: Client            → Frontend (5173)
```

### Inter-Service Communication

- All calls use `ResilientClient` (from `libs/service-client/`)
- Circuit breaker: opens after 5 failures, resets after 30s
- Retry: 3 attempts with exponential backoff (1s, 2s, 4s) + jitter
- Correlation ID (`X-Correlation-ID`) propagated through all calls
- Graceful degradation: if graph service is down, renormalize RRF weights and proceed

### Service Details

| Service | Port | Dependencies | Purpose |
|---------|------|-------------|---------|
| **gateway** | 8080 | query-service, ingestion-service | Auth, rate limiting, CORS, routing |
| **query-service** | 8001 | graph-service, embedding-service, ChromaDB | Full query pipeline with agents |
| **ingestion-service** | 8002 | graph-service, embedding-service, ChromaDB | Document processing |
| **embedding-service** | 8004 | AWS Bedrock | Vector embedding (Titan v2, 1024-dim) |
| **graph-service** | 8003 | Neo4j | Entity CRUD + relationship traversal |

---

## Frontend

### Tech Stack
- React 19 (with useOptimistic, useActionState, Suspense)
- TypeScript 5.7 (strict mode)
- Vite 6 (build tool, HMR)
- TailwindCSS 4 (utility-first CSS)
- @tanstack/react-query 5 (server state management)
- react-router-dom 7 (client-side routing)
- eslint-plugin-jsx-a11y (accessibility linting)

### Pages
- **ChatPage** (`/`) — Conversational Q&A interface with optimistic updates
- **DocumentsPage** (`/documents`) — Document upload and listing

### Components (15)
`QueryInput` · `AnswerDisplay` · `AnswerText` · `CitationList` · `ConfidenceIndicator` · `ConfidenceScore` · `ConversationHistory` · `DocumentList` · `DocumentUpload` · `ErrorState` · `FallbackDisplay` · `Layout` · `MessageBubble` · `SearchResults` · `SourcePanel`

### Accessibility (WCAG 2.0 AA)
- Semantic HTML throughout (`<main>`, `<nav>`, `<article>`, `<button>`)
- `aria-live="polite"` on conversation area
- `aria-busy="true"` during loading states
- `role="alert"` on error notifications
- `role="log"` on conversation history
- Visible focus indicators (`ring-2 ring-offset-2`)
- Minimum 44x44px touch targets
- `prefers-reduced-motion` respected

### API Client
- Timeout: 30s for queries, 60s for ingestion
- API key injected via `X-API-Key` header
- AbortController for request cancellation
- Typed error handling with `ApiClientError`

---

## Infrastructure (Terraform)

### AWS Resources

| Resource | Module | Purpose |
|----------|--------|---------|
| VPC | `networking` | Isolated network (10.0.0.0/16) with public + private subnets |
| Subnets | `networking` | 2 public + 2 private across 2 AZs |
| Internet Gateway | `networking` | Public internet access |
| NAT Gateway | `networking` | Private subnet outbound |
| Security Group | `networking` | Ingress on 8080 only |
| ECS Cluster | `compute` | Fargate container cluster |
| ECS Task Definition | `compute` | API container (Fargate, configurable CPU/memory) |
| ECS Service | `compute` | Desired count with ALB integration |
| ALB | `compute` | Application Load Balancer |
| Auto Scaling | `compute` | CPU-based (target 70%, min 1-10 instances) |
| IAM Roles | `compute` | Task execution + Bedrock InvokeModel access |

### Environments

| Environment | CPU | Memory | Desired Count | Deploy Trigger |
|-------------|-----|--------|---------------|----------------|
| **dev** | 512 | 1024 | 1 | Auto (merge to main) |
| **prod** | 1024 | 2048 | 2 | Manual gate + approval |

### Backend State
- S3 bucket: `rag-pipeline-terraform-state`
- DynamoDB lock table: `rag-pipeline-terraform-locks`
- Encrypted at rest

---

## Testing Strategy

### Test Pyramid

| Level | Framework | Location | Marker | Count |
|-------|-----------|----------|--------|-------|
| **Property-based** | Hypothesis | `tests/property/` | `@pytest.mark.property` | 20 properties |
| **Unit** | pytest | `tests/unit/` | `@pytest.mark.unit` | mirrors src/ |
| **Integration** | pytest | `tests/integration/` | `@pytest.mark.integration` | requires Docker |
| **Contract** | Schemathesis | `tests/contract/` | `@pytest.mark.contract` | OpenAPI fuzzing |
| **E2E** | pytest | `tests/e2e/` | `@pytest.mark.e2e` | full stack |
| **Evaluation** | custom | `tests/evaluation/` | CLI harness | golden dataset |

### Property-Based Tests (20 Formal Properties)

| File | Properties Tested |
|------|------------------|
| `test_prop_normalizers.py` | P1: Normalizer preserves content |
| `test_prop_document_store.py` | P2: Store/retrieve round-trip |
| `test_prop_ingestion.py` | P3: Ingestion pipeline invariants |
| `test_prop_chunkers.py` | P4-P8: Chunk size, overlap, coverage, ordering, text preservation |
| `test_prop_deduplication.py` | P9: Duplicate detection threshold |
| `test_prop_retrieval.py` | P10-P12: Retrieval scoring, RRF monotonicity, reranking |
| `test_prop_generation.py` | P13-P15: Citation validity, grounding, fallback |
| `test_prop_security.py` | P16: Injection pattern detection |
| `test_prop_confidence.py` | P17-P18: Score bounds, composite formula |
| `test_prop_api.py` | P19-P20: API contract invariants |

### Evaluation Harness

Metrics computed against a golden dataset:
- **ROUGE-L F1** — Answer quality vs reference
- **Entity Recall** — Key entities present in answer
- **MRR** — Mean Reciprocal Rank of first relevant citation
- **Recall@K / Precision@K** — Retrieval quality at top-K
- **Confidence Calibration** — ECE and overconfidence rate

### Hypothesis Profiles

| Profile | Max Examples | Use Case |
|---------|-------------|----------|
| `ci` | 200 | CI pipeline (thorough) |
| `dev` | 50 | Local development (fast feedback) |
| `debug` | 10 | Debugging failures |

### Coverage Target
- Minimum: 70% line coverage (enforced in CI)
- Source: `src/`, `services/`, `libs/`

---

## CI/CD Pipeline (GitLab CI)

```
lint → test:unit → sast → dependency-scan → build:docker → deploy:dev → test:integration → deploy:prod
```

| Stage | Tool | Gate |
|-------|------|------|
| **lint** | ruff + mypy | MR only |
| **test:unit** | pytest (unit + property) | MR + main |
| **sast** | Bandit | Always |
| **dependency-scan** | pip-audit | Always |
| **build:docker** | Docker build + push | main only |
| **deploy:dev** | Terraform apply | main (auto) |
| **test:integration** | pytest (integration) | main |
| **deploy:prod** | Terraform apply | main (manual) |

---

## Security

### Application Security

| Layer | Control |
|-------|---------|
| **Input** | Prompt injection detection (regex patterns for 4 attack categories) |
| **Transport** | HTTPS (HSTS enforced), TLS 1.2+ minimum |
| **Authentication** | API key validation (X-API-Key header) |
| **Authorization** | Role-based (reader, editor, admin) |
| **Rate Limiting** | Token bucket (60 req/min/key) |
| **Headers** | HSTS, X-Frame-Options DENY, CSP, X-Content-Type-Options, Referrer-Policy |
| **Penetration Detection** | fastapi-guard (SQL injection, XSS, path traversal, command injection) |
| **Secrets** | Never logged, AWS Secrets Manager in production |

### Prompt Injection Detection Categories
1. **Direct injection** — "ignore previous instructions", "you are now a..."
2. **Instruction injection** — "override the system prompt", "bypass safety filter"
3. **Role-play attacks** — "pretend you are", "act as if", "from now on"
4. **Extraction attacks** — "reveal your system prompt", "what are your instructions"

### Infrastructure Security
- All data stores in private subnets (no public access)
- IAM roles with least-privilege (only `bedrock:InvokeModel`)
- Encrypted state file (S3 with AES-256)
- Container scanning (Trivy) blocks CRITICAL findings
- Non-root container user

---

## Observability

### Structured Logging (structlog)
- JSON output format
- Consistent fields: `correlation_id`, `service_name`, `duration_ms`
- Naming convention: `<component>.<operation>.<outcome>`
- Example: `retrieval_service.search.success`, `generation_service.llm_call.failed`

### Distributed Tracing (OpenTelemetry)
- Span naming: `<service>.<operation>`
- Standard attributes: `correlation_id`, `query.length`, `result.count`, `duration_ms`
- Trace context propagated via HTTP headers

### Metrics (Prometheus)
- `rag_retrieval_duration_seconds` (histogram, by method)
- `rag_generation_duration_seconds` (histogram, by model)
- `rag_token_usage_total` (counter, by model + operation)
- `rag_confidence_score` (histogram, by dimension)
- `rag_circuit_breaker_state` (gauge, by target + state)

---

## Compliance & Governance

### Standards Covered
- **ISO 27001:2022** — Information Security Management System
- **ISO 42001:2023** — AI Management System

### GRC Artifacts (in `docs/grc/`)
- `iso27001_control_matrix.md` — Annex A controls mapped to platform implementation
- `iso42001_ai_control_matrix.md` — AI-specific governance controls
- `risk_register.md` — Risk identification, scoring, mitigation

### Data Sovereignty
- All LLM inference: `ap-southeast-4` (Melbourne, Australia)
- Embedding model: `us-east-1` (Titan availability requirement)
- All persistent data: Australian AWS region
- Satisfies APRA and AUSTRAC data residency requirements

---

## Local Development

### Prerequisites
- Python 3.11+
- Node.js 18+ (frontend)
- Docker + Docker Compose
- AWS CLI configured (for Bedrock access)

### Quick Start

```bash
# 1. Install Python dependencies
pip install -e ".[dev,test]"

# 2. Start infrastructure services
docker compose -f infrastructure/docker/docker-compose.yml up -d

# 3. Run the API server
uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8080 --reload

# 4. Run frontend (separate terminal)
cd frontend && npm install && npm run dev

# 5. Run tests
pytest tests/unit tests/property -v
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RAG_AGENT_REGION` | `us-east-1` | AWS region for Bedrock |
| `RAG_AGENT_TIER` | `lite` | Model tier (lite/pro/premium) |
| `RAG_AGENT_TEMPERATURE` | `0.1` | LLM sampling temperature |
| `RAG_AGENT_MAX_TOKENS` | `4096` | Max response tokens |
| `CHROMADB_HOST` | `chromadb` | ChromaDB hostname |
| `NEO4J_URI` | `bolt://neo4j:7687` | Neo4j connection URI |
| `API_KEYS` | `dev-api-key` | Valid API keys (comma-separated) |
| `VITE_API_BASE_URL` | `http://localhost:8080` | Frontend API target |

---

## Key Design Decisions

1. **Hexagonal architecture** — Domain logic is infrastructure-agnostic; swap ChromaDB for OpenSearch by implementing a new adapter without touching services.

2. **Tiered model selection** — Nova Lite for cheap tool-calling, Nova Pro for generation, Claude Sonnet as premium fallback. Reduces per-query cost by ~70%.

3. **Hybrid search with RRF** — Three retrieval methods cover different query types. RRF fusion is parameter-free (no learned weights), robust to missing methods.

4. **LLM-as-judge citation verification** — Every claim is validated against its source chunk to prevent hallucination before presenting to users.

5. **Confidence scoring with fallback** — System never presents a low-confidence answer as authoritative. Below threshold (0.4), it explains what it found and what's missing.

6. **Property-based testing** — 20 formal properties tested with thousands of generated inputs (Hypothesis) validate correctness invariants across edge cases.

7. **Event-driven ingestion** — `DocumentIngestedEvent` allows decoupled downstream processing (e.g., re-indexing, notifications).

8. **Monolith + Microservices** — The `src/` monolith serves as the reference implementation and local dev mode. The `services/` directory provides independently deployable microservices for production.

---

## Monorepo Package Structure

| Package | Location | Description |
|---------|----------|-------------|
| `legislation-rag-platform` | root `pyproject.toml` | Core application |
| `legislation-rag-domain-models` | `libs/domain-models/` | Shared Pydantic models |
| `legislation-rag-service-client` | `libs/service-client/` | Resilient HTTP client |
| `legislation-rag-gateway` | `services/gateway/` | API gateway service |
| `legislation-rag-query-service` | `services/query-service/` | Query orchestration |
| `legislation-rag-ingestion-service` | `services/ingestion-service/` | Document processing |
| `legislation-rag-embedding-service` | `services/embedding-service/` | Vector embeddings |
| `legislation-rag-graph-service` | `services/graph-service/` | Neo4j operations |

All services reference shared libraries via path-based dependencies and are installed in editable mode during development.
