---
inclusion: manual
---

# Task Execution Plan — Prioritized Implementation Order

## Execution Strategy

Tasks are organized into 4 sprints. Each sprint has prerequisites, deliverables,
and a definition of done. Tasks within a sprint can be parallelized.

## Sprint 1: Working Pipeline (Infrastructure Adapters)

**Goal:** Get a working end-to-end pipeline locally with real storage backends.

### Tasks (in order):

1. **5.6 Bedrock Embeddings Adapter** (replaces OpenAI — stays in AWS)
   - Implement `EmbeddingPort` using Bedrock Titan Embeddings
   - Model: `amazon.titan-embed-text-v2:0` (1024 dims, $0.02/1M tokens)
   - Batch support with rate limiting

2. **5.3 ChromaDB Vector Store Adapter**
   - Implement `VectorStorePort` with real ChromaDB client
   - Collection: cosine similarity, 1024 dimensions (Titan)
   - store(), search(), delete_by_document(), find_similar()

3. **5.4 BM25 Sparse Index Adapter**
   - Implement `SparseIndexPort` with rank_bm25
   - In-memory index with document-level deletion
   - Tokenization using simple whitespace + lowercase

4. **5.8 Cross-Encoder Reranker Adapter**
   - Implement `RerankerPort` with sentence-transformers
   - Model: cross-encoder/ms-marco-MiniLM-L-12-v2
   - Local inference, no API calls

5. **5.5 Neo4j Graph Store Adapter** (can use in-memory stub initially)
   - Implement `GraphStorePort`
   - Start with in-memory fake, add Neo4j later with docker-compose

6. **5.9 Redis Cache Adapter** (can use in-memory stub initially)
   - Implement `CachePort`
   - Start with in-memory dict, add Redis later

7. **Wire docker-compose** for ChromaDB + Neo4j + Redis

### Definition of Done:
- `python run_agents.py ask` works with real ChromaDB + BM25
- Can ingest a document and query it end-to-end

---

## Sprint 2: Domain Services & API (Wire Everything Together)

**Goal:** Complete the API layer so the system is accessible via HTTP.

### Tasks:

8. **6.1-6.3 Indexing Service** (real implementation)
   - Wire vector store + sparse index + graph store
   - Deduplication with 0.95 threshold
   - Re-indexing support

9. **7.1 Entity Extractor** (use Strands agent for extraction)
   - Replace Instructor with a Strands tool that extracts entities
   - Simpler, stays on Bedrock, no OpenAI dependency

10. **8.1 Ingestion Service** (delegates to Ingestion Agent)
    - Wire: validate → normalize → chunk → extract → dedup → index → emit

11. **10.1-10.3 Retrieval Service** (delegates to Retrieval Agent)
    - Parallel search, RRF fusion, reranking

12. **11.1-11.2 Generation + Citation Service** (delegates to Generation + Verification Agents)

13. **12.1-12.2 Confidence Service**

14. **14.1-14.6 Security Service** (complete stubs)

15. **15.2-15.10 FastAPI routes and middleware**
    - Wire orchestrator into DI container
    - All endpoints functional

### Definition of Done:
- `POST /v1/ingest` ingests a real document
- `POST /v1/ask` returns a cited answer with confidence
- `GET /v1/documents` lists ingested docs
- `GET /health` returns 200

---

## Sprint 3: Testing & Quality (Property Tests + Evaluation)

**Goal:** All 20 correctness properties tested, evaluation framework running.

### Tasks:

16. **2.6-2.7** Unit + property tests for normalizers
17. **3.5-3.8** Property tests for chunkers
18. **5.2** Property test for document store round-trip
19. **6.4-6.5** Property tests for deduplication + re-chunking
20. **10.4-10.6** Property tests for RRF, reranker, metadata
21. **11.3-11.5** Property tests for citations + token budget
22. **12.3-12.4** Property tests for confidence + fallback
23. **14.7** Property test for prompt injection
24. **15.11-15.12** Property tests for API validation + error structure
25. **21.1-21.4** Evaluation framework + golden dataset

### Definition of Done:
- `pytest tests/property/ -v` — all 20 properties pass
- `pytest tests/unit/ --cov` — ≥85% coverage on domain layer
- `python run_agents.py evaluate` — produces metrics report

---

## Sprint 4: Production Readiness (Infra, CI/CD, Frontend)

**Goal:** Deployable to AWS with full CI/CD, monitoring, and UI.

### Tasks:

26. **17.1-17.5** Auth + RBAC
27. **18.1-18.4** Circuit breakers, retries, degradation tests
28. **19.1-19.7** Observability (logging, tracing, metrics, dashboards)
29. **22.1-22.7** React frontend
30. **24.1-24.7** Terraform modules
31. **25.1-25.3** Docker + docker-compose + seed script
32. **26.1-26.8** CI/CD pipeline
33. **27.1-27.4** GRC artifacts

### Definition of Done:
- `terraform apply` deploys to AWS
- CI pipeline passes all stages
- UI accessible and functional
- GRC artifacts complete
