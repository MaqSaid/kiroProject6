# Legislation RAG Platform — Complete Project Documentation (GCP Edition)

## Executive Summary

The Legislation RAG Platform is a production-grade Retrieval-Augmented Generation (RAG) system deployed on **Google Cloud Platform**, designed for regulated industries (banking, financial services, compliance). It ingests internal policy documents (PDF, HTML, Markdown, plaintext), indexes them across three complementary retrieval methods (dense vectors, sparse keywords, knowledge graph), and answers natural-language compliance questions with grounded, cited responses and confidence scoring.

**Primary use case:** Know Your Customer (KYC) / Anti-Money Laundering (AML) compliance — analysts ask questions about internal policies and receive precise, auditable answers with verifiable citations linking every claim to its source paragraph.

**Key guarantees:**
- 100% citation traceability — every claim links to a specific source passage
- Composite confidence scoring with fallback when certainty is low
- Prompt injection detection at the API boundary + Vertex AI Safety Settings
- Tiered model selection for cost optimization (~$0.0003 per standard query with Gemini Flash)
- Hybrid search covering semantic, keyword, and entity-relationship queries

---

## Technology Stack (GCP Native)

| Layer | Technologies |
|-------|-------------|
| **Backend** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 |
| **AI/ML** | Vertex AI (Gemini 2.0 Flash, Gemini 1.5 Pro), Google ADK, sentence-transformers (cross-encoder) |
| **Vector Store** | Vertex AI Vector Search (managed ANN) |
| **Keyword Search** | rank-bm25 (in-memory BM25 sparse retrieval) |
| **Knowledge Graph** | Neo4j Aura (GCP Marketplace) |
| **Caching** | Cloud Memorystore for Redis 7 |
| **Persistent State** | Cloud SQL (PostgreSQL 15) |
| **Frontend** | React 19, TypeScript 5.7, Vite 6, TailwindCSS 4, @tanstack/react-query 5 |
| **Infrastructure** | Terraform (Google provider), Cloud Run, VPC, IAM, Workload Identity |
| **CI/CD** | GitLab CI (lint, test, security, build, deploy) |
| **Observability** | structlog (JSON), OpenTelemetry, Cloud Trace, Cloud Monitoring |
| **Security** | Cloud Armor, Google Identity Platform, Secret Manager, Workload Identity |

---

## Architecture

### Hexagonal (Ports and Adapters) Pattern

```
+---------------------------------------------------------------------+
|                         API Layer (Cloud Run)                         |
|    FastAPI routes -> validation -> auth -> rate limiting              |
+--------------------------------+------------------------------------+
                                 |
+--------------------------------v------------------------------------+
|                      Domain Services                                 |
|  RetrievalService | GenerationService | IngestionService             |
|         (pure business logic - no infrastructure imports)            |
+--------------------------------+------------------------------------+
                                 | Ports (Protocol interfaces)
+--------------------------------v------------------------------------+
|                   GCP Infrastructure Adapters                        |
|  Vertex AI Vector Search | BM25 | Neo4j Aura | Vertex Embeddings   |
|  CrossEncoder | Cloud Storage | Memorystore | Cloud SQL             |
+---------------------------------------------------------------------+
```

### AI Agent Orchestration (Google ADK)

Five specialized agents coordinated by a `SequentialAgent`:

| Agent | Model | Purpose |
|-------|-------|---------|
| **Retrieval Agent** | Gemini 2.0 Flash | Hybrid search, RRF fusion, reranking |
| **Generation Agent** | Gemini 1.5 Pro | Grounded answer generation with citations |
| **Citation Verification Agent** | Gemini 2.0 Flash | LLM-as-judge faithfulness validation |
| **Ingestion Agent** | Gemini 2.0 Flash | Document processing orchestration |
| **Evaluation Agent** | Gemini 1.5 Pro | Quality benchmarking |

### Service Architecture (Cloud Run)

| Service | Purpose | Scaling |
|---------|---------|---------|
| **gateway** | Auth, rate limiting, routing | 2-20 |
| **query-service** | Agent pipeline orchestration | 2-15 |
| **ingestion-service** | Document processing | 1-10 |
| **embedding-service** | Vertex AI embedding calls | 2-10 |
| **graph-service** | Neo4j Aura CRUD + traversal | 2-8 |

---

## Data Flow

### Query: POST /v1/agents/ask

User Query -> Cloud Armor -> Gateway (JWT + rate limit) -> Query Service -> Retrieval Agent (parallel: Vertex AI Vector Search + BM25 + Neo4j Aura) -> RRF Fusion -> Cross-Encoder Rerank -> Generation Agent (Gemini 1.5 Pro) -> Citation Verification (Gemini Flash) -> Confidence Scoring -> Response

### Ingestion: POST /v1/ingest

Upload -> Validate -> Store (Cloud Storage) -> Normalize -> Chunk -> Deduplicate -> Embed (Vertex AI) -> Index (Vector Search + BM25 + Neo4j) -> Store metadata (Cloud SQL) -> Publish event (Pub/Sub)

---

## Security and Compliance

- **Edge:** Cloud Armor WAF (OWASP, geo-fencing to Australia)
- **Auth:** Google Identity Platform (SAML for government SSO)
- **Service Identity:** Workload Identity (zero static credentials)
- **Secrets:** GCP Secret Manager (versioned, IAM-gated)
- **Data Sovereignty:** All data in `australia-southeast1` (APRA/AUSTRAC compliant)
- **Prompt Safety:** Vertex AI Safety Settings + regex detection at API boundary

---

## Observability

- **Logs:** structlog JSON -> Cloud Logging (auto-parsed, queryable by correlation_id)
- **Traces:** OpenTelemetry -> Cloud Trace (OTLP endpoint)
- **Metrics:** Prometheus client -> Cloud Monitoring (custom dashboards, SLO alerting)
- **Alerts:** Cloud Monitoring alerting policies -> PagerDuty / Slack

---

## Local Development

```bash
pip install -e ".[dev,test]"
gcloud auth application-default login
docker compose up -d
uvicorn src.api.app:create_app --factory --host 0.0.0.0 --port 8080 --reload
cd frontend && npm install && npm run dev
pytest tests/unit tests/property -v
```
