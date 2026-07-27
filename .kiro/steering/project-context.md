---
inclusion: auto
---

# Project Context — Legislation RAG Platform (Microservices Architecture)

## What This Project Is
A microservices-based Legislation RAG Platform enabling internal users to query legislation, policies, and business rules through a natural language chat interface. The platform uses hybrid retrieval (dense vector, sparse BM25, and knowledge graph traversal) combined with Reciprocal Rank Fusion, Strands Agents for orchestration, and a React 19 frontend. The architecture comprises **five FastAPI microservices** and a **React SPA frontend**, communicating via HTTP with resilience patterns.

## Architecture
Five independently deployable FastAPI services + shared libraries:
- **API Gateway** (`services/gateway/`): Auth, rate limiting, CORS, routing, correlation ID injection
- **Query Service** (`services/query-service/`): RAGOrchestrator, agent pipeline, hybrid search + RRF fusion
- **Ingestion Service** (`services/ingestion-service/`): Document upload, chunking, entity extraction, vector/graph storage
- **Graph Service** (`services/graph-service/`): Exclusive Neo4j owner — entity/relationship CRUD + traversal
- **Embedding Service** (`services/embedding-service/`): Exclusive Bedrock owner — embedding with SHA-256 cache

Each service owns its data store exclusively — no shared databases.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, async/await
- **Inter-Service Communication**: httpx + ResilientClient (circuit breaker + retry + correlation ID)
- **Vector Store**: ChromaDB (owned by Ingestion Service)
- **Graph Store**: Neo4j Community Edition (owned by Graph Service)
- **Sparse Index**: rank_bm25 (in-memory, within Query Service)
- **Embeddings**: AWS Bedrock (via Embedding Service)
- **Agents**: Strands Agents (Retrieval, Generation, Citation Verification, Ingestion, Evaluation)
- **Reranker**: cross-encoder/ms-marco-MiniLM-L-12-v2 (local, within Query Service)
- **Frontend**: React 19 + TypeScript + TailwindCSS + Vite
- **Observability**: OpenTelemetry + Prometheus + Grafana
- **IaC**: Terraform (AWS), Docker Compose (dev)
- **CI/CD**: GitLab CI/CD
- **Testing**: pytest + Hypothesis (PBT) + Playwright (E2E) + Contract tests

## Directory Structure
```
services/
├── gateway/               # FastAPI API Gateway service
├── query-service/         # FastAPI query orchestration
├── ingestion-service/     # FastAPI document processing
├── graph-service/         # FastAPI Neo4j wrapper
└── embedding-service/     # FastAPI Bedrock embedding wrapper
libs/
├── domain-models/         # Shared Pydantic models (pip install -e)
└── service-client/        # Shared httpx + circuit breaker + retry
frontend/                  # React 19 SPA (Vite + TypeScript + TailwindCSS)
infrastructure/
├── terraform/             # AWS IaC (VPC, ECS/Fargate, ALB, etc.)
└── docker/                # Dockerfiles and docker-compose.yml
data/
├── sample_documents/      # 8 synthetic legislative documents
└── golden_dataset.json    # 20 golden Q&A pairs
tests/
├── e2e/                   # Cross-service E2E tests
└── contract/              # API contract tests between services
```

## Key Patterns
- **Microservices**: Each service independently deployable with its own data store
- **Inter-service communication via ResilientClient with circuit breaker**: 5 consecutive failures open for 30s, then half-open probe. Retries: 3 attempts, exponential backoff (1s base), jitter up to 500ms.
- **Hexagonal Architecture**: Domain logic never imports infrastructure within each service
- **Port/Adapter**: All external I/O through Protocol interfaces
- **Strategy Pattern**: Chunkers selected via ChunkerRegistry with auto-selection
- **DDD Patterns**: Domain events, value objects (DocumentId, ChunkId, EntityId), aggregate roots
- **Shared Domain Models**: Single Pydantic model package prevents schema drift across services
- **RRF Fusion**: Weighted combination of 3 retrieval methods (dense=0.5, sparse=0.2, graph=0.3)
- **Graceful Degradation**: Renormalize RRF weights when methods unavailable
- **Correlation ID Propagation**: X-Correlation-ID header passed through all inter-service calls

## Spec Location
`.kiro/specs/legislation-rag-platform/`
