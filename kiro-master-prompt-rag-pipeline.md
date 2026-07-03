# Master Prompt for Kiro — Production RAG Pipeline with Hybrid Search

> **How to use:** Paste the entire prompt below into Kiro in **Spec mode**. Kiro will generate `requirements.md` first. Review and approve it before letting Kiro proceed to `design.md`, and approve that before `tasks.md`. Do not let it skip ahead.

---

## PROMPT STARTS HERE — COPY EVERYTHING BELOW THIS LINE

You are acting as a Principal Software Architect and AI Platform Engineer. I want to build a **production-grade Retrieval-Augmented Generation (RAG) system with hybrid search over internal documentation**, developed under a full Secure Software Development Life Cycle (SSDLC).

We will follow Kiro's spec-driven workflow strictly, in three gated stages:

1. **STAGE 1 — `requirements.md`:** Produce complete requirements using user stories with **EARS-format acceptance criteria** (WHEN / IF / WHILE / WHERE … THE SYSTEM SHALL …). Cover functional, non-functional, security, compliance, accessibility, and operational requirements. **Stop after this stage and wait for my explicit approval.**
2. **STAGE 2 — `design.md`:** Only after I approve requirements, produce the design: bounded contexts (DDD), architecture diagrams (Mermaid), API contracts (OpenAPI-first), data models, sequence diagrams, design patterns, error handling, and testing strategy. **Stop and wait for my approval.**
3. **STAGE 3 — `tasks.md`:** Only after I approve the design, produce an ordered, dependency-aware task list where every task is small, testable, references the requirement(s) it satisfies, and follows TDD (test written before implementation). Include CI/CD, IaC, security, and documentation tasks — not just application code.

Do not merge stages. Do not generate design or tasks until I approve the previous stage.

---

## 1. Product Scope (What the System Does)

Build a RAG platform that:

1. **Ingests** internal documentation in Markdown, plain text, HTML, and PDF; normalizes to clean plaintext with metadata (source file, section heading, page number); stores raw documents alongside processed versions so re-indexing never requires re-upload.
2. **Chunks** documents using three switchable, tracked strategies: (a) fixed-size with overlap (baseline), (b) recursive character splitting by section headers (structure-aware), (c) semantic chunking on topic boundaries via embedding similarity. Every chunk records which strategy produced it.
3. **Embeds and indexes**: dense embeddings via OpenAI `text-embedding-3-small` stored in ChromaDB (or Qdrant) with metadata (source document, chunk index, section heading, chunking strategy, character count), plus a parallel **BM25 sparse index** (`rank_bm25`) over the same chunks. Both indexes must remain in sync transactionally.
4. **Deduplicates** at ingestion: reject/flag chunks with cosine similarity > 0.95 against existing chunks.
5. **Retrieves with hybrid search**: dense top-k (start k=10) + sparse BM25 top-k, fused via **Reciprocal Rank Fusion (RRF)** with configurable weighting (default 0.7 dense / 0.3 sparse), followed by a **cross-encoder or LLM-as-judge reranker** over the top 20 candidates, keeping the top 5.
6. **Generates grounded answers** (GPT-4o or Claude Sonnet) that answer only from retrieved context, cite chunks with bracketed references ([1], [2]), and explicitly state when context is insufficient.
7. **Verifies citations post-generation**: parse each citation, send each citation–claim pair to an LLM-as-judge, and flag unsupported citations.
8. **Scores answer confidence** on three dimensions: retrieval confidence, citation coverage (% of claims with verified citations), and answer completeness; return a composite score with every answer.
9. **Handles "I don't know" gracefully**: below a retrieval-confidence threshold, return a structured response stating what was found, what wasn't, and which documents may be worth manual review. Never hallucinate.
10. **Evaluation framework**: a golden dataset of 50+ hand-written Q&A pairs (simple lookups, multi-hop across documents, no-answer cases, ambiguous questions); automated metrics for answer correctness (LLM-as-judge vs golden), faithfulness, retrieval relevance, and citation accuracy; run on every pipeline change (embedded in CI); a chunking-strategy comparison report showing which strategy wins per metric.
11. **API (API-first, contract-first)**: `POST /v1/ask` (answer + citations + confidence + source metadata), `GET /v1/documents`, `POST /v1/ingest`, plus health/readiness endpoints. Full OpenAPI 3.1 specification authored **before** implementation; implementation validated against the contract.
12. **Dashboard/UI**: a web frontend (React preferred; Streamlit acceptable for MVP) showing the generated answer with clickable citations, retrieved chunks ranked by relevance, confidence scores broken down by dimension, and a hybrid vs dense-only side-by-side comparison toggle.
13. **Containerized delivery**: Docker + docker-compose for API, vector store, and frontend, with a seed script that indexes a sample corpus so a reviewer can run it immediately.

## 2. Architecture and Engineering Standards (Non-Negotiable)

- **Domain-Driven Design**: identify bounded contexts explicitly (e.g., Ingestion, Indexing, Retrieval, Generation, Evaluation, Identity/Access). Define ubiquitous language, aggregates, entities, value objects, domain events, and anti-corruption layers between contexts. In STAGE 1, capture domain vocabulary; in STAGE 2, produce a context map.
- **Microservices where justified**: default to a modular monolith with clean context boundaries; split into microservices only where the design shows independent scaling/deployment needs (e.g., ingestion workers vs query API). Justify every service boundary in `design.md`.
- **Clean Architecture + SOLID**: dependency rule enforced (domain has no framework dependencies), ports/adapters (hexagonal) for LLM providers, embedding providers, and vector stores so ChromaDB↔Qdrant and OpenAI↔Anthropic are swappable behind interfaces. Document and enforce reusable design patterns (Repository, Strategy for chunkers, Adapter for providers, Factory, Circuit Breaker, Retry with backoff).
- **API-first**: OpenAPI contract is the source of truth; generate server stubs/clients from it; contract tests in CI.
- **TDD**: every task in `tasks.md` starts with writing a failing test. No implementation task without a preceding test task.
- **Tech stack**: Python 3.11+, FastAPI (async), LangChain text splitters for chunking, ChromaDB or Qdrant, rank_bm25, Docker, Terraform, GitLab CI/CD.

## 3. Testing Strategy (Embedded in CI/CD — Define in Requirements and Design)

Define a full test pyramid and embed **all** of it in the pipeline:

- **Unit tests** (pytest, ≥85% coverage gate on domain and application layers).
- **Integration tests**: vector store, BM25 index sync, LLM adapters (with recorded/mocked responses), database, message queues if used.
- **Contract tests**: implementation vs OpenAPI spec (e.g., Schemathesis).
- **End-to-end tests**: full ask→retrieve→generate→cite flow against a seeded corpus; UI E2E via Playwright including mobile viewports.
- **Regression tests**: golden Q&A eval suite (correctness, faithfulness, retrieval relevance, citation accuracy) runs on every merge; fail the pipeline on metric regression beyond a defined tolerance.
- **Application security testing**:
  - SAST (Semgrep/Bandit), SCA/dependency scanning with SBOM generation (Syft/Grype or GitLab Dependency Scanning), secret detection (Gitleaks/GitLab Secret Detection), container image scanning (Trivy), IaC scanning (Checkov/tfsec).
  - DAST (OWASP ZAP) against the running API and UI in a pipeline stage.
  - API security tests against **OWASP API Security Top 10** and web/UI tests against **OWASP Top 10**: injection, broken auth, broken object-level authorization, SSRF, mass assignment, XSS, CSRF, insecure deserialization, security misconfiguration, rate-limit abuse.
  - **LLM-specific security**: test against OWASP Top 10 for LLM Applications — prompt injection (direct and indirect via ingested documents), insecure output handling, training/context data poisoning via the ingest endpoint, sensitive information disclosure, and denial-of-wallet (token abuse) protections.
  - Input validation and fuzzing on `POST /v1/ingest` (malicious PDFs/HTML, oversized payloads, path traversal in filenames) and `POST /v1/ask`.
  - **Penetration testing**: define scope, rules of engagement, and cadence (pre-release pen test + after major changes); include remediation workflow and re-test requirements.
- **Performance/load tests** (k6 or Locust): latency SLOs for /v1/ask (e.g., p95 targets), throughput, and cost-per-query tracking.
- **Accessibility tests**: automated axe-core/Pa11y + Lighthouse accessibility budget in CI, plus a manual audit checklist (keyboard navigation, screen reader, contrast).

## 4. SSDLC, Security by Design, and GRC

- Follow a complete **SSDLC**: threat modeling (STRIDE) during design for every bounded context and every external interface; security requirements captured in STAGE 1; abuse cases alongside user stories; security gates at every pipeline stage; signed artifacts and provenance (SLSA-aligned).
- **Security by design**: authN/authZ on all endpoints (OAuth2/OIDC, RBAC), TLS everywhere, encryption at rest (documents, embeddings, indexes), secrets in a vault (never in code or CI variables in plaintext), least-privilege IAM, audit logging of ingestion/query/admin actions, PII handling policy for ingested documents, data retention and deletion capability.
- **GRC implementation**: define a control matrix mapping system controls to:
  - **ISO/IEC 27001** (ISMS): Annex A controls relevant to access control, cryptography, operations security, supplier (LLM provider) management, logging and monitoring, incident management, business continuity.
  - **ISO/IEC 42001** (AI Management System): AI policy, AI risk assessment and impact assessment for the RAG system, human oversight, transparency (citations and confidence scores are transparency controls — map them), model/provider lifecycle management, data governance for the corpus, and continuous monitoring of AI performance (the eval suite is the control — map it).
  - Produce as artifacts: risk register, statement of applicability (relevant controls only), AI impact assessment, incident response runbook, and audit-evidence checklist. These must appear as explicit tasks in `tasks.md`.

## 5. UX/UI and Accessibility

- The UI must conform to **WCAG 2.0 Level AA as a floor** (target WCAG 2.1 AA where feasible): semantic HTML, ARIA where needed, full keyboard operability, visible focus states, ≥4.5:1 contrast, text resize to 200%, no keyboard traps, accessible error messaging.
- **Mobile-first responsive design**: fully functional on mobile devices (≥360px width), touch targets ≥44px, tested via responsive E2E tests across defined breakpoints.
- Accessibility acceptance criteria must appear in EARS format in STAGE 1 for every UI story.

## 6. Infrastructure, CI/CD, and Operations

- **Terraform for all infrastructure** (cloud-agnostic modules preferred; assume AWS unless I say otherwise): remote state with locking, module structure, per-environment workspaces (dev/stage/prod), `terraform plan` as a merge-request gate, policy-as-code checks (OPA/Sentinel or Checkov) in the pipeline, and documented IaC standards suitable for mentoring a team.
- **GitLab CI/CD**: define governed, **reusable pipeline templates** (build → unit → SAST/SCA/secrets → contract → integration → DAST → E2E → eval-suite regression → performance smoke → accessibility → package/sign → terraform plan/apply → deploy → post-deploy verification). Branch protection, mandatory code review, semantic versioning, environment promotion with manual gates to prod, and automated rollback.
- **Observability framework**: structured JSON logging with correlation IDs across services, metrics (Prometheus/OpenTelemetry) including RAG-specific metrics (retrieval latency, rerank latency, token usage, cost per query, confidence score distribution, citation-verification failure rate), distributed tracing (OpenTelemetry) across ingest and query paths, dashboards (Grafana), and alerting with defined SLOs/SLIs and error budgets.
- **HA/DR, scalability, resilience**: stateless API services behind a load balancer with horizontal autoscaling, vector store backup and restore procedures with tested RPO/RTO targets, circuit breakers and timeouts on all LLM/embedding provider calls, retry with exponential backoff and jitter, graceful degradation (fall back to dense-only if BM25 unavailable; return retrieval-only results if generation provider is down), rate limiting and quota management.
- **Cost optimization and capacity**: embedding/query caching, batch embedding, token budgets per request, provider cost dashboards, capacity monitoring with forecast alerts, and documented performance-tuning levers (k values, rerank depth, chunk sizes).

## 7. Deliverables Kiro Must Account For

- `requirements.md`, `design.md`, `tasks.md` (the spec trio).
- OpenAPI 3.1 spec, threat model, control matrix (ISO 27001 + ISO 42001), risk register, AI impact assessment.
- Terraform modules + environment configs, GitLab CI templates, Dockerfiles + compose, seed corpus + seed script.
- Golden eval dataset (50+ Q&A) and eval harness wired into CI.
- Chunking-strategy comparison report generator.
- README with quickstart, architecture overview, and a demo script outline (<4 min) plus a case-study template that leads with faithfulness % and citation-accuracy % numbers.

## 8. Rules for STAGE 1 (Do This Now)

Generate `requirements.md` now, and only `requirements.md`:

- Organize by capability area: Ingestion & Chunking, Indexing & Dedup, Hybrid Retrieval, Generation & Citation, Confidence & Fallback, Evaluation, API, UI/Accessibility, Security & AppSec, GRC/Compliance, Observability, HA/DR & Performance, CI/CD & IaC.
- Each area: user stories ("As a … I want … so that …") with numbered **EARS acceptance criteria**, including negative/abuse cases and measurable thresholds (coverage %, latency targets, similarity thresholds, WCAG criteria, RPO/RTO).
- Include explicit **out-of-scope** and **assumptions** sections, and a glossary of the DDD ubiquitous language.
- End with open questions you need me to answer before design.

Stop after `requirements.md` and wait for my approval.

## PROMPT ENDS HERE

---

## Suggested follow-up prompts (use after each approval)

**After approving requirements:**
> Requirements approved. Proceed to STAGE 2: generate `design.md` per the master prompt — bounded-context map, service decomposition decision (monolith-first vs microservices, with justification), Mermaid architecture and sequence diagrams, OpenAPI 3.1 contract, data models, design patterns catalog, threat model (STRIDE per context), observability design, HA/DR design with RPO/RTO, and the full test strategy mapped to pipeline stages. Stop and wait for approval.

**After approving design:**
> Design approved. Proceed to STAGE 3: generate `tasks.md` as an ordered, dependency-aware checklist. Every task must (a) reference the requirement IDs it satisfies, (b) begin with a failing test (TDD), (c) be completable in under a day, and (d) include the CI/CD, Terraform, security-scanning, GRC-artifact, eval-suite, and accessibility tasks — not just feature code. Group tasks by the six build phases (Ingestion → Retrieval → Generation/Citation → Evaluation → API/Dashboard → Polish) while keeping infra/security tasks interleaved from day one, not bolted on at the end.
