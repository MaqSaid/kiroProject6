# Governance, Risk & Compliance (GRC) Artifacts

## Purpose

This directory contains GRC artifacts for the Legislation RAG Platform. These documents support compliance with:

- **ISO 27001:2022** — Information Security Management System (ISMS)
- **ISO 42001:2023** — Artificial Intelligence Management System (AIMS)

The artifacts provide evidence of security controls, AI governance, and risk management practices applied to the platform's design, development, deployment, and operation.

## Document Inventory

| Document | Standard | Description |
|----------|----------|-------------|
| [iso27001_control_matrix.md](./iso27001_control_matrix.md) | ISO 27001:2022 | Maps Annex A controls to RAG platform implementation |
| [iso42001_ai_control_matrix.md](./iso42001_ai_control_matrix.md) | ISO 42001:2023 | AI-specific controls for model management, data governance, responsible AI |
| [risk_register.md](./risk_register.md) | Both | Risk identification, scoring, and mitigation for platform risks |

## Platform Mapping

The RAG platform components covered by these artifacts:

- **Ingestion Service** — Document parsing, chunking, embedding generation
- **Retrieval Service** — Dense/sparse/graph search, reranking, fusion
- **Generation Service** — LLM orchestration (Bedrock Nova Pro), citation assembly
- **Graph Store** — Neptune knowledge graph for legislation relationships
- **Vector Store** — OpenSearch for embedding similarity search
- **API Gateway** — FastAPI endpoints, authentication, rate limiting
- **Infrastructure** — Terraform-managed AWS resources (ECS, RDS, Neptune, S3)
- **Observability** — Structlog, OpenTelemetry, Prometheus, Grafana
- **CI/CD** — GitLab CI pipeline with security scanning gates

## Review Cadence

| Artifact | Review Frequency | Next Review | Trigger for Ad-Hoc Review |
|----------|-----------------|-------------|---------------------------|
| Risk Register | Quarterly | Next quarter | New threat, incident, architecture change |
| ISO 27001 Control Matrix | Annually | Next annual cycle | Control failure, audit finding, major release |
| ISO 42001 AI Control Matrix | Annually | Next annual cycle | Model change, AI incident, regulatory update |

## Responsible Parties

| Role | Responsibility |
|------|---------------|
| Security Lead | ISO 27001 control matrix ownership, security risk items |
| AI/ML Lead | ISO 42001 control matrix ownership, AI-specific risks |
| Platform Lead | Risk register coordination, operational risk items |
| Compliance Officer | Review sign-off, audit liaison, regulatory change tracking |
| Engineering Team | Control implementation, evidence collection |

## Related Documents

- `docs/architecture/` — Architecture decision records and system design
- `docs/security/` — Security policies, threat models, incident response
- `docs/evaluation/` — RAG evaluation methodology and metrics
- `infrastructure/terraform/` — Infrastructure as Code (evidence for A.8.9)
- `.gitlab-ci.yml` — CI/CD pipeline configuration (evidence for A.8.25)
- `docker-compose.yml` — Container orchestration (evidence for A.8.1)

## How to Use These Artifacts

1. **Internal Audits** — Use control matrices as checklists during internal ISMS/AIMS audits
2. **External Audits** — Provide as evidence packages to certification bodies
3. **Risk Reviews** — Update risk register during quarterly risk review meetings
4. **Change Management** — Consult before architectural changes to assess control impact
5. **Incident Response** — Reference control ownership for escalation during security events

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-01 | GRC Team | Initial creation of all artifacts |
