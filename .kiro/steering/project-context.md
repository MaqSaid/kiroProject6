---
inclusion: auto
---

# Project Context — Production RAG Pipeline with Hybrid Search

## What This Project Is
A production-grade Retrieval-Augmented Generation system with three-way hybrid search (dense vectors + BM25 sparse + knowledge graph). It ingests documents, chunks them, indexes across three stores, retrieves via RRF fusion with reranking, generates cited answers, and provides confidence scoring.

## Tech Stack
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, async/await
- **Vector Store**: ChromaDB (dev) / Qdrant (prod)
- **Graph Store**: Neo4j (dev) / Amazon Neptune (prod)
- **Sparse Index**: rank_bm25 (in-memory)
- **Embeddings**: OpenAI text-embedding-3-small (1536 dims)
- **Generation**: GPT-4o primary, Claude Sonnet fallback
- **Entity Extraction**: Instructor + Pydantic structured output
- **Reranker**: cross-encoder/ms-marco-MiniLM-L-12-v2 (local)
- **Frontend**: React 18 + TypeScript + Tailwind CSS + Vite
- **Observability**: OpenTelemetry + Prometheus + Grafana
- **IaC**: Terraform (AWS)
- **CI/CD**: GitLab CI/CD
- **Testing**: pytest + Hypothesis (PBT) + Playwright (E2E)

## Directory Structure
```
src/
├── domain/
│   ├── models/          # Pydantic domain entities
│   ├── services/        # Domain services (ingestion, retrieval, generation, confidence)
│   ├── processing/      # Normalizers, chunkers, entity extractor
│   └── events/          # Domain events
├── ports/               # Protocol interfaces (driven ports)
├── infrastructure/      # Adapters (ChromaDB, Neo4j, OpenAI, BM25, Redis)
│   └── resilience/      # Circuit breaker, retry logic
├── api/
│   ├── routes/          # FastAPI route handlers
│   ├── middleware/      # Auth, error handler, correlation ID, rate limiter
│   └── dependencies/    # DI container
└── config/              # Settings, environment config
tests/
├── unit/
├── property/            # Hypothesis property-based tests
└── integration/
frontend/                # React + TypeScript dashboard
infrastructure/          # Terraform modules
```

## Key Patterns
- **Hexagonal Architecture**: Domain never imports infrastructure
- **Port/Adapter**: All external I/O through Protocol interfaces
- **Strategy Pattern**: Chunkers selected via ChunkerFactory
- **Circuit Breaker**: On all external provider calls
- **Event-Driven**: Domain events emitted on ingestion
- **RRF Fusion**: Weighted combination of 3 retrieval methods

## Spec Location
`.kiro/specs/production-rag-pipeline-hybrid-search/`
