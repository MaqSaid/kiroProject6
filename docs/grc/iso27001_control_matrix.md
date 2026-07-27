# ISO 27001:2022 Control Matrix — Legislation RAG Platform

## Purpose

Maps ISO 27001:2022 Annex A controls to their implementation in the Legislation RAG Platform. This matrix serves as evidence for internal and external ISMS audits, demonstrating how each applicable control is addressed through technical measures, policies, and operational procedures.

## Scope

- All microservices (ingestion, embedding, query, graph, generation)
- AWS infrastructure (ECS, Neptune, OpenSearch, S3, Bedrock)
- CI/CD pipeline (GitLab CI with security scanning)
- Infrastructure as Code (Terraform)
- Development and operational processes

## Control Matrix

### A.5 — Organizational Controls

| Control ID | Control Title | Applicability | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| A.5.1 | Policies for information security | Applicable | Information security policy suite documented covering data classification, access control, acceptable use, and incident response | docs/security/policy.md | Implemented |
| A.5.2 | Information security roles and responsibilities | Applicable | Security Lead, AI/ML Lead, Platform Lead, and Compliance Officer roles defined with explicit responsibilities for ISMS and AIMS | docs/grc/README.md (Responsible Parties) | Implemented |
| A.5.3 | Segregation of duties | Applicable | Separate roles for development, deployment (CI/CD pipeline), and production access. Terraform apply requires approval; prod deploy requires manual gate with reviewer approval | .gitlab-ci.yml (deploy-prod stage), infrastructure/terraform/ | Implemented |
| A.5.4 | Management responsibilities | Applicable | Quarterly GRC review cadence established. Management sign-off required for risk acceptance decisions and control exceptions | docs/grc/README.md (Review Cadence) | Implemented |
| A.5.5 | Contact with authorities | Applicable | Documented contacts for OAIC (Office of the Australian Information Commissioner), ACSC (Australian Cyber Security Centre), and relevant state regulators | docs/security/incident-response.md | Implemented |
| A.5.6 | Contact with special interest groups | Applicable | Participation in ACSC partnership program, AustCyber community, and OWASP local chapter for threat intelligence sharing | docs/security/policy.md | Implemented |
| A.5.7 | Threat intelligence | Applicable | Trivy vulnerability database updates daily. Semgrep rules updated from registry. ACSC advisory feeds monitored. Dependabot/Renovate for dependency advisories | .gitlab-ci.yml (scan-security stage) | Implemented |
| A.5.8 | Information security in project management | Applicable | Security requirements included in feature specs. Threat modelling conducted for architectural changes. Security review gate in CI/CD pipeline blocks deployment on critical findings | .kiro/specs/, .gitlab-ci.yml | Implemented |
| A.5.9 | Inventory of information and other associated assets | Applicable | Infrastructure assets tracked via Terraform state. Data assets catalogued (legislation corpus in S3, embeddings in OpenSearch, graph data in Neptune). Service inventory in docker-compose.yml | infrastructure/terraform/, docker-compose.yml | Implemented |
| A.5.10 | Acceptable use of information and other associated assets | Applicable | Acceptable use policy defines permitted use of legislation data, LLM services, and platform resources. API rate limiting enforces usage boundaries | docs/security/policy.md, services/gateway/ | Implemented |
| A.5.14 | Information transfer | Applicable | All inter-service communication over internal Docker network. External API traffic encrypted via TLS 1.2+. S3 transfers use HTTPS endpoints only. No data transfer to third parties except Bedrock API calls | infrastructure/terraform/modules/networking/, services/gateway/ | Implemented |
| A.5.23 | Information security for use of cloud services | Applicable | AWS shared responsibility model documented. Cloud security controls implemented: VPC isolation, security groups, IAM least-privilege, encryption at rest/transit, CloudTrail logging | infrastructure/terraform/, docs/security/ | Implemented |
| A.5.24 | Information security incident management planning and preparation | Applicable | Incident response plan with defined severity levels, escalation paths, and communication templates. Runbooks for common security scenarios (credential leak, data breach, service compromise) | docs/security/incident-response.md | Implemented |
| A.5.25 | Assessment and decision on information security events | Applicable | CloudWatch alarms and Grafana alerts for anomaly detection. Structured logging enables correlation of security events. Alert rules define thresholds for investigation triggers | infrastructure/terraform/modules/observability/, alerting rules | Implemented |
| A.5.26 | Response to information security incidents | Applicable | Incident response procedures define containment (revoke credentials, isolate services), eradication (patch, redeploy), and recovery steps. Post-incident review required within 5 business days | docs/security/incident-response.md | Implemented |
| A.5.29 | Information security during disruption | Applicable | Multi-AZ ECS deployment for service continuity. Neptune and OpenSearch cluster replication. S3 cross-region replication for legislation corpus. Terraform enables rapid infrastructure rebuild | infrastructure/terraform/, AWS service configurations | Implemented |
| A.5.30 | ICT readiness for business continuity | Applicable | RTO < 4 hours, RPO < 1 hour defined. Automated infrastructure provisioning via Terraform. Container images stored in ECR with multi-region replication. Backup and restore procedures tested quarterly | infrastructure/terraform/, docs/security/ | Implemented |

### A.6 — People Controls

| Control ID | Control Title | Applicability | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| A.6.1 | Screening | Applicable | Background checks required for team members with access to production systems and legislation data. Verification of qualifications for security-sensitive roles | HR processes (external to repo) | Implemented |
| A.6.2 | Terms and conditions of employment | Applicable | Employment contracts include confidentiality clauses, acceptable use obligations, and post-employment restrictions on data access | HR processes (external to repo) | Implemented |
| A.6.3 | Information security awareness, education and training | Applicable | Annual security awareness training. Secure coding training for developers (OWASP Top 10, AI-specific risks). Phishing simulation exercises conducted quarterly | Training records (external to repo) | Implemented |
| A.6.4 | Disciplinary process | Applicable | Defined process for security policy violations including verbal warning, written warning, access revocation, and termination depending on severity | HR processes (external to repo) | Implemented |
| A.6.5 | Responsibilities after termination or change of employment | Applicable | Offboarding checklist includes: revoke GitLab access, rotate shared secrets, remove AWS IAM user, revoke VPN certificates, return equipment | Offboarding checklist (external to repo) | Implemented |
| A.6.6 | Confidentiality or non-disclosure agreements | Applicable | NDA required for all team members and contractors with access to the platform. Covers legislation data processing, AI model configurations, and infrastructure details | Legal agreements (external to repo) | Implemented |
| A.6.7 | Remote working | Applicable | VPN required for access to management plane. MFA enforced on all remote access. Endpoint security requirements (disk encryption, OS patching, screen lock) defined | docs/security/policy.md | Implemented |

### A.7 — Physical Controls

| Control ID | Control Title | Applicability | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| A.7.1 | Physical security perimeters | Limited Applicability | Platform hosted entirely on AWS. AWS SOC 2 Type II reports provide assurance for physical data centre security. Development occurs on secured corporate endpoints | AWS compliance reports | Accepted (Cloud Provider) |
| A.7.4 | Physical security monitoring | Limited Applicability | Delegated to AWS for data centre facilities. Corporate office monitoring covers development workstations | AWS SOC 2 reports | Accepted (Cloud Provider) |
| A.7.9 | Security of assets off-premises | Applicable | Developer laptops require full-disk encryption (BitLocker/FileVault), screen lock after 5 minutes, and endpoint protection. No production data stored locally | docs/security/policy.md | Implemented |
| A.7.10 | Storage media | Applicable | S3 bucket lifecycle policies enforce retention and deletion. EBS volumes encrypted with AWS KMS. No removable media used for data transfer | infrastructure/terraform/modules/data-stores/ | Implemented |

### A.8 — Technological Controls

| Control ID | Control Title | Applicability | Implementation | Evidence | Status |
|---|---|---|---|---|---|
| A.8.1 | User endpoint devices | Applicable | Developer workstations require: OS auto-updates enabled, full-disk encryption, endpoint detection and response (EDR) agent, screen lock ≤5 min. Docker Desktop for local development in isolated containers | docs/security/policy.md, docker-compose.yml | Implemented |
| A.8.2 | Privileged access rights | Applicable | AWS IAM roles follow least-privilege principle. Production console access restricted to Security Lead and Platform Lead. Terraform state management requires specific IAM role assumption. ECS task roles scoped per service | infrastructure/terraform/modules/security/, IAM policies | Implemented |
| A.8.3 | Information access restriction | Applicable | API authentication required for all endpoints. Role-based access control in gateway service. Neptune and OpenSearch accessible only within VPC. S3 buckets have explicit deny policies for public access | services/gateway/, infrastructure/terraform/modules/networking/ | Implemented |
| A.8.4 | Access to source code | Applicable | GitLab repository with branch protection on main. Merge requests require 1+ approval. Force push disabled. CI pipeline must pass before merge. Repository access audited quarterly | GitLab project settings, .gitlab-ci.yml | Implemented |
| A.8.5 | Secure authentication | Applicable | API key authentication for service consumers. JWT tokens with short expiry (15 min access, 7 day refresh). MFA enforced for GitLab, AWS Console, and infrastructure access. Service-to-service authentication via IAM roles | services/gateway/, infrastructure/terraform/modules/security/ | Implemented |
| A.8.6 | Capacity management | Applicable | ECS auto-scaling policies based on CPU/memory thresholds. OpenSearch domain sizing reviewed quarterly. CloudWatch alarms on resource utilisation >80%. Cost alerting via AWS Budgets | infrastructure/terraform/modules/compute/, monitoring dashboards | Implemented |
| A.8.7 | Protection against malware | Applicable | Container images scanned with Trivy (CRITICAL/HIGH blocks deployment). No persistent storage mounts from untrusted sources. GuardDuty enabled for runtime threat detection. Input validation on all API endpoints | .gitlab-ci.yml (scan-security), infrastructure/terraform/ | Implemented |
| A.8.8 | Management of technical vulnerabilities | Applicable | Trivy scans container images in CI. Semgrep and Bandit perform SAST on Python code. Checkov scans Terraform for misconfigurations. Gitleaks detects leaked secrets. Dependabot monitors dependency CVEs. Critical findings block merge | .gitlab-ci.yml (scan-security stage) | Implemented |
| A.8.9 | Configuration management | Applicable | All infrastructure defined as code (Terraform). Application configuration via environment variables and AWS Secrets Manager. Docker images built from version-controlled Dockerfiles. No manual configuration drift permitted | infrastructure/terraform/, Dockerfiles, docker-compose.yml | Implemented |
| A.8.10 | Information deletion | Applicable | S3 lifecycle policies enforce data retention periods. OpenSearch index lifecycle management (ILM) policies auto-delete indices past retention. Neptune graph data deletion procedures documented. Privacy Act deletion requests handled within 30 days | infrastructure/terraform/modules/data-stores/ | Implemented |
| A.8.11 | Data masking | Applicable | PII detection and redaction in ingestion pipeline before embedding. Structured logging excludes sensitive fields (API keys, tokens). Query logs redact user-identifiable information. Bedrock API calls exclude PII from prompts | services/ingestion/, logging configuration | Implemented |
| A.8.12 | Data leakage prevention | Applicable | VPC endpoints prevent data egress to internet for Neptune, OpenSearch, and S3. Outbound security groups restrict traffic to known destinations. S3 bucket policies block cross-account access. No public endpoints for data stores | infrastructure/terraform/modules/networking/ | Implemented |
| A.8.13 | Information backup | Applicable | Neptune automated snapshots daily (35-day retention). OpenSearch automated snapshots to S3. S3 versioning enabled on legislation corpus bucket. Terraform state backed up with S3 versioning and DynamoDB locking | infrastructure/terraform/modules/data-stores/ | Implemented |
| A.8.14 | Redundancy of information processing facilities | Applicable | ECS services deployed across multiple AZs. Neptune cluster with read replicas in separate AZs. OpenSearch multi-AZ deployment. Application Load Balancer distributes traffic across healthy targets | infrastructure/terraform/modules/compute/, modules/data-stores/ | Implemented |
| A.8.15 | Logging | Applicable | Structured JSON logging via structlog with correlation IDs. CloudWatch Logs for all ECS services. CloudTrail for AWS API activity. VPC Flow Logs for network monitoring. OpenTelemetry traces for request lifecycle. Log retention: 90 days hot, 1 year archive | services/ (structlog config), infrastructure/terraform/modules/observability/ | Implemented |
| A.8.16 | Monitoring activities | Applicable | Prometheus metrics collection. Grafana dashboards for SLO monitoring. CloudWatch alarms for infrastructure health. Error budget tracking with automated alerts. Circuit breaker state monitoring. Anomaly detection on API traffic patterns | infrastructure/terraform/modules/observability/, alerting rules | Implemented |
| A.8.20 | Networks security | Applicable | VPC with public/private subnet separation. Private subnets for all data services (Neptune, OpenSearch). NAT Gateway for controlled outbound access. Security groups enforce least-privilege port access. Network ACLs as secondary defence layer | infrastructure/terraform/modules/networking/ | Implemented |
| A.8.21 | Security of network services | Applicable | Application Load Balancer with TLS 1.2+ termination. AWS Certificate Manager for certificate provisioning and rotation. WAF rules on ALB for OWASP Top 10 protection. VPC endpoints for AWS service access without internet traversal | infrastructure/terraform/modules/networking/, modules/security/ | Implemented |
| A.8.22 | Segregation of networks | Applicable | Separate VPC subnets for: public (ALB), application (ECS tasks), data (Neptune, OpenSearch). Security groups isolate service communication. Dev/stage/prod environments in separate AWS accounts or VPCs | infrastructure/terraform/modules/networking/ | Implemented |
| A.8.23 | Web filtering | Applicable | AWS WAF attached to ALB with rule groups for: SQL injection, XSS, known bad inputs, rate limiting, geo-restriction (AU-only if required). Bot control rules for automated access | infrastructure/terraform/modules/security/ | Implemented |
| A.8.24 | Use of cryptography | Applicable | TLS 1.2+ for all data in transit. AES-256 (SSE-S3/SSE-KMS) for S3 data at rest. Neptune storage encryption with KMS. OpenSearch encryption at rest with KMS. EBS encryption for all volumes. KMS key rotation enabled annually | infrastructure/terraform/modules/data-stores/, modules/secrets/ | Implemented |
| A.8.25 | Secure development life cycle | Applicable | GitLab CI enforces: linting (ruff), type checking (mypy), unit tests, SAST (Semgrep/Bandit), SCA (Trivy), secret scanning (Gitleaks), IaC scanning (Checkov). Branch protection requires passing pipeline. Code review required for all changes | .gitlab-ci.yml, GitLab project settings | Implemented |
| A.8.26 | Application security requirements | Applicable | Input validation on all API endpoints (Pydantic models). Output encoding for responses. Rate limiting per API key. Request size limits. SQL/NoSQL injection prevention via parameterised queries. CORS policy restricts origins | services/gateway/, FastAPI middleware | Implemented |
| A.8.27 | Secure system architecture and engineering principles | Applicable | Microservices architecture with single-responsibility services. Defence in depth (WAF → ALB → Security Groups → Application validation). Least privilege IAM. Immutable infrastructure via containers. Secrets never in code | Architecture documentation, infrastructure/terraform/ | Implemented |
| A.8.28 | Secure coding | Applicable | Bandit for Python security anti-patterns. Semgrep rules for injection, deserialization, and SSRF. Type hints enforced (mypy strict mode). Dependency pinning with hashes. No eval/exec usage. Input sanitisation in all services | .gitlab-ci.yml, pyproject.toml, services/ | Implemented |
| A.8.31 | Separation of development, test and production environments | Applicable | Three environments (dev/stage/prod) with separate Terraform state, separate AWS resources, and separate CI/CD deployment stages. Environment-specific terraform.tfvars. No production data in dev/stage | infrastructure/terraform/environments/, .gitlab-ci.yml | Implemented |
| A.8.32 | Change management | Applicable | All changes via merge requests with required reviews. CI pipeline validates changes before merge. Terraform plan reviewed before apply. Deployment to prod requires manual approval. Rollback strategy defined for failed deployments | .gitlab-ci.yml, GitLab MR workflow | Implemented |
| A.8.33 | Test information | Applicable | Synthetic test data used in dev/stage environments. No production legislation data in non-prod. Test fixtures generated from anonymised samples. Property-based testing with Hypothesis for edge cases | tests/, .hypothesis/ | Implemented |
| A.8.34 | Protection of information systems during audit testing | Applicable | Audit testing conducted in isolated environments. DAST (OWASP ZAP) runs against stage environment only. Penetration testing scoped and scheduled to avoid production impact. Audit logs preserved separately | .gitlab-ci.yml (scan-dast stage) | Implemented |

## Summary Statistics

| Category | Total Controls | Applicable | Implemented | Accepted | Not Applicable |
|---|---|---|---|---|---|
| A.5 Organizational | 17 | 17 | 17 | 0 | 0 |
| A.6 People | 7 | 7 | 7 | 0 | 0 |
| A.7 Physical | 4 | 4 | 2 | 2 | 0 |
| A.8 Technological | 22 | 22 | 22 | 0 | 0 |
| **Total** | **50** | **50** | **48** | **2** | **0** |

## Review and Approval

| Role | Name | Date | Signature |
|---|---|---|---|
| Security Lead | | | |
| Compliance Officer | | | |
| Platform Lead | | | |

## Version History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-01-01 | GRC Team | Initial control matrix creation |
