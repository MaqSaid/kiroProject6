# ISO 42001:2023 AI Control Matrix — Legislation RAG Platform

## Purpose

Maps ISO 42001:2023 controls to AI-specific governance practices for the Legislation RAG Platform. This matrix demonstrates compliance with the AI Management System (AIMS) standard, covering the full AI system lifecycle from data governance through deployment, monitoring, and responsible AI practices.

## Scope

- Retrieval-Augmented Generation (RAG) pipeline
- Bedrock Nova Pro LLM integration (third-party AI service)
- Embedding models for vector search
- Knowledge graph reasoning (Neptune/Neo4j)
- AI output quality evaluation and monitoring
- Data governance for legislation corpus

## AI System Description

| Attribute | Description |
|---|---|
| AI System Type | Retrieval-Augmented Generation (RAG) |
| AI Functionality | Legal information retrieval, synthesis, and citation |
| AI Risk Level | Medium (informational, not decision-making) |
| Autonomy Level | Human-in-the-loop (outputs require user interpretation) |
| Third-party AI | AWS Bedrock Nova Pro (generation), embedding models |
| Training Data | Australian legislation corpus (publicly available) |
| Stakeholders | Legal professionals, researchers, government, public |

## Control Matrix

### AI System Lifecycle

| Control ID | Control Title | Category | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| AI.4.1 | AI system inventory and registration | AI Governance | All AI components registered: Bedrock Nova Pro (generation), embedding model (vectorisation), cross-encoder (reranking), knowledge graph reasoning (Neptune). Component versions tracked in requirements files and Terraform | docs/architecture/, requirements.txt, infrastructure/terraform/ | Implemented |
| AI.4.2 | AI system lifecycle management | AI Governance | Defined lifecycle stages: design → development → testing → deployment → monitoring → retirement. Each stage has defined gates, approvals, and documentation requirements. CI/CD pipeline enforces stage transitions | .gitlab-ci.yml, docs/architecture/ | Implemented |
| AI.4.3 | AI system design documentation | AI Governance | Architecture decision records (ADRs) document design choices for: retrieval strategy, chunking approach, embedding model selection, reranking methodology, generation prompting, and citation assembly | docs/architecture/ | Implemented |
| AI.4.4 | AI system requirements specification | AI Governance | Functional requirements (retrieval accuracy, citation fidelity, latency targets) and non-functional requirements (availability, scalability, security) documented. Acceptance criteria defined for each RAG component | .kiro/specs/, docs/evaluation/ | Implemented |
| AI.4.5 | AI system verification and validation | AI Governance | Evaluation suite measures: MRR (Mean Reciprocal Rank), citation accuracy, answer relevance, faithfulness, and hallucination rate. Regression testing blocks deployment on >5% metric degradation | tests/evaluation/, .gitlab-ci.yml (evaluate stage) | Implemented |

### Data Governance

| Control ID | Control Title | Category | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| AI.5.1 | Data quality management | Data Governance | Legislation corpus validated for: completeness (all current acts included), currency (update pipeline monitors gazette publications), integrity (checksums on ingested documents), and format consistency (HTML/XML parsing validation) | services/ingestion/, data quality checks | Implemented |
| AI.5.2 | Data provenance and lineage | Data Governance | Full traceability from source legislation → parsed document → chunks → embeddings → graph nodes. Each chunk retains metadata: source act, section, version date, jurisdiction, and ingestion timestamp | services/ingestion/ (metadata schema) | Implemented |
| AI.5.3 | Data bias assessment | Data Governance | Legislation corpus assessed for jurisdictional coverage bias (federal vs state representation). Embedding model evaluated for semantic bias in legal terminology. Retrieval fairness tested across legal domains | docs/evaluation/bias-assessment.md | Implemented |
| AI.5.4 | Training and evaluation data management | Data Governance | Evaluation dataset curated with diverse legal queries across jurisdictions and topics. Golden answers maintained by legal domain experts. Dataset versioned and stored separately from training pipeline | tests/evaluation/golden_dataset/ | Implemented |
| AI.5.5 | Data protection and privacy | Data Governance | Legislation data is publicly available (no PII concerns in source). User queries may contain PII — redacted before logging and excluded from Bedrock API calls. Data retention policies applied to query logs (90-day default) | services/gateway/ (PII redaction), data retention policies | Implemented |

### Model Management

| Control ID | Control Title | Category | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| AI.6.1 | Model selection and evaluation | Model Management | Bedrock Nova Pro selected based on: Australian legal domain performance benchmarking, latency requirements (<2s generation), cost efficiency, and data residency (ap-southeast-2 availability). Evaluation results documented | docs/architecture/adr-model-selection.md | Implemented |
| AI.6.2 | Model versioning and configuration | Model Management | Model versions pinned in configuration (Bedrock model ID). Embedding model version tracked in requirements. Prompt templates versioned in source control. Configuration changes require review and evaluation gate pass | services/generation/ (model config), infrastructure/terraform/ | Implemented |
| AI.6.3 | Model performance monitoring | Model Management | Continuous monitoring of: response latency, token usage, generation quality scores, citation accuracy rate, and hallucination detection rate. Grafana dashboards track trends. Alerts on degradation beyond threshold | infrastructure/terraform/modules/observability/, monitoring dashboards | Implemented |
| AI.6.4 | Model update and retirement procedures | Model Management | Defined process for model updates: evaluation on golden dataset → shadow deployment in stage → A/B comparison → production rollout. Retirement criteria: deprecated by provider, performance degradation, or superior alternative validated | docs/architecture/model-lifecycle.md | Implemented |

### Responsible AI

| Control ID | Control Title | Category | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| AI.7.1 | Fairness and non-discrimination | Responsible AI | RAG system tested for equitable retrieval across: federal/state/territory legislation, different legal domains (criminal, civil, administrative), and plain language vs technical queries. No demographic profiling of users | docs/evaluation/fairness-assessment.md | Implemented |
| AI.7.2 | Transparency and explainability | Responsible AI | All generated responses include: source citations with section references, confidence scores (retrieval, citation, completeness dimensions), and retrieval methodology indicator (dense/sparse/graph/fused). Users can inspect source documents | services/generation/ (citation assembly), API response schema | Implemented |
| AI.7.3 | Human oversight and control | Responsible AI | System designed as informational tool — outputs clearly labelled as AI-generated and not legal advice. Users retain full decision-making authority. No automated legal decisions made. Kill switch available for generation service | services/gateway/ (disclaimer), operational runbooks | Implemented |
| AI.7.4 | Accountability framework | Responsible AI | AI/ML Lead accountable for model performance and responsible AI practices. Platform Lead accountable for system reliability. Clear escalation path for AI-related incidents. Post-incident reviews include AI-specific analysis | docs/grc/README.md (Responsible Parties) | Implemented |
| AI.7.5 | Safety and harm prevention | Responsible AI | Output guardrails prevent: generation of legal advice, fabrication of non-existent legislation, and hallucinated section references. Confidence thresholds gate response delivery — low-confidence responses include explicit uncertainty warnings | services/generation/ (guardrails), confidence scoring | Implemented |

### AI Risk Management

| Control ID | Control Title | Category | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| AI.8.1 | AI-specific risk assessment | AI Risk Management | AI risks identified and scored in risk register: hallucination, citation inaccuracy, model bias, prompt injection, data poisoning, model degradation, vendor lock-in. Risk appetite defined per category | docs/grc/risk_register.md (AI/ML category) | Implemented |
| AI.8.2 | AI impact assessment | AI Risk Management | Impact assessment conducted for: potential harm from incorrect legal information, user over-reliance on AI outputs, accessibility of AI features, and environmental impact of compute resources | docs/architecture/ai-impact-assessment.md | Implemented |
| AI.8.3 | Residual AI risk acceptance | AI Risk Management | Residual risks (e.g., irreducible hallucination rate) formally documented with acceptance criteria, compensating controls (confidence scoring, citations, disclaimers), and monitoring thresholds for re-evaluation | docs/grc/risk_register.md | Implemented |

### Third-Party AI Services

| Control ID | Control Title | Category | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| AI.9.1 | Third-party AI service assessment | Third-Party AI | AWS Bedrock assessed for: data processing location (ap-southeast-2 confirmed), data retention policy (no training on customer data), security certifications (SOC 2, ISO 27001), SLA guarantees, and model provenance documentation | docs/architecture/vendor-assessment-bedrock.md | Implemented |
| AI.9.2 | Third-party AI service agreements | Third-Party AI | AWS service terms reviewed for: intellectual property rights, data usage restrictions, liability allocation, service continuity commitments, and model deprecation notification periods. Legal review completed | Legal agreements (external to repo) | Implemented |
| AI.9.3 | Third-party AI service monitoring | Third-Party AI | Bedrock API monitored for: availability (circuit breaker pattern), latency degradation, response quality drift, cost tracking per request, and service health dashboard integration. Fallback strategy documented for outages | services/generation/ (circuit breaker), monitoring dashboards | Implemented |

### Monitoring and Evaluation

| Control ID | Control Title | Category | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| AI.10.1 | Continuous AI performance evaluation | Monitoring | Automated evaluation pipeline runs on schedule: retrieval accuracy (MRR >0.8), generation faithfulness (RAGAS score >0.85), citation accuracy (>95% valid references), and hallucination rate (<5%). Results tracked over time | tests/evaluation/, .gitlab-ci.yml (evaluate stage) | Implemented |
| AI.10.2 | AI system drift detection | Monitoring | Monitoring for: embedding distribution drift (cosine similarity baseline comparison), query pattern changes, retrieval score degradation, and generation quality decline. Alerts trigger investigation when drift exceeds thresholds | services/evaluation/ (drift monitoring) | Implemented |
| AI.10.3 | AI output quality assurance | Monitoring | Multi-dimensional confidence scoring: retrieval confidence, citation confidence, completeness confidence, and composite score. Low-confidence outputs flagged with warnings. Quality sampling for human review on periodic basis | services/generation/ (confidence scoring) | Implemented |
| AI.10.4 | User feedback integration | Monitoring | Feedback mechanism for users to report: incorrect citations, outdated information, irrelevant retrieval, or harmful outputs. Feedback routed to evaluation pipeline for model assessment and retrieval tuning | services/gateway/ (feedback endpoint) | Planned |

### AI Incident Management

| Control ID | Control Title | Category | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| AI.11.1 | AI incident classification | Incident Management | AI-specific incident taxonomy: hallucination event (fabricated content served), citation failure (invalid references), bias manifestation (unfair retrieval patterns), prompt injection (adversarial input exploitation), model degradation (quality below threshold) | docs/security/ai-incident-taxonomy.md | Implemented |
| AI.11.2 | AI incident response procedures | Incident Management | Response procedures per incident type: immediate (disable generation, serve cached responses), investigation (root cause analysis with evaluation pipeline), remediation (prompt update, retrieval tuning, model rollback), and communication (stakeholder notification) | docs/security/ai-incident-response.md | Implemented |
| AI.11.3 | AI incident learning and improvement | Incident Management | Post-incident reviews include: root cause analysis specific to AI components, evaluation dataset augmentation with failure cases, retrieval/generation pipeline improvements, and updated monitoring thresholds | Post-incident review templates | Implemented |

## Summary Statistics

| Category | Total Controls | Implemented | Planned | Not Applicable |
|---|---|---|---|---|
| AI System Lifecycle | 5 | 5 | 0 | 0 |
| Data Governance | 5 | 5 | 0 | 0 |
| Model Management | 4 | 4 | 0 | 0 |
| Responsible AI | 5 | 5 | 0 | 0 |
| AI Risk Management | 3 | 3 | 0 | 0 |
| Third-Party AI Services | 3 | 3 | 0 | 0 |
| Monitoring and Evaluation | 4 | 3 | 1 | 0 |
| AI Incident Management | 3 | 3 | 0 | 0 |
| **Total** | **32** | **31** | **1** | **0** |

## Relationship to ISO 27001

This AI control matrix complements the ISO 27001:2022 control matrix. Key intersections:

| ISO 42001 Control | Related ISO 27001 Control | Integration Point |
|---|---|---|
| AI.5.5 Data protection | A.8.11 Data masking | PII handling in AI pipeline |
| AI.9.1 Third-party AI assessment | A.5.23 Cloud services | Bedrock vendor assessment |
| AI.10.1 Performance evaluation | A.8.16 Monitoring | AI-specific monitoring metrics |
| AI.11.2 AI incident response | A.5.26 Incident response | AI incident taxonomy integration |
| AI.6.2 Model versioning | A.8.9 Configuration management | Model configuration as code |
| AI.8.1 AI risk assessment | A.5.30 Business continuity | AI failure impact on service availability |

## Review and Approval

| Role | Name | Date | Signature |
|---|---|---|---|
| AI/ML Lead | | | |
| Security Lead | | | |
| Compliance Officer | | | |

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-01 | GRC Team | Initial AI control matrix creation |
