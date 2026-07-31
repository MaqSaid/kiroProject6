# Production Architecture — GCP Layer-by-Layer Deep Dive

## Complete GCP Architecture

```
INTERNET
    |
LAYER 1: EDGE (Cloud CDN + Cloud Armor WAF)
    Static: Firebase Hosting (React SPA)
    API: Cloud Armor -> Cloud Run
    |
LAYER 2: AUTH (Google Identity Platform)
    JWT validation, SAML federation, MFA
    |
LAYER 3: COMPUTE (Cloud Run - Serverless Containers)
    Gateway(2-20) -> Query Service(2-15) -> Embedding(2-10) -> Vertex AI
                  -> Ingestion(1-10)     -> Graph(2-8)      -> Neo4j Aura
    |
LAYER 4: DATA (Managed Services - VPC Connected)
    Vertex AI Vector Search | Neo4j Aura | Cloud Memorystore (Redis)
    Cloud SQL (PostgreSQL)  | Cloud Storage | Secret Manager
    |
LAYER 5: ASYNC (Pub/Sub + Cloud Run Jobs)
    GCS Event -> Pub/Sub -> Cloud Run Job: Parse -> Chunk -> Embed -> Index
    |
LAYER 6: OBSERVABILITY (Cloud Operations)
    Cloud Logging | Cloud Trace | Cloud Monitoring -> Alerting -> PagerDuty
```

---

## LAYER 1: Cloud CDN + Cloud Armor

Cloud CDN serves the React SPA from Firebase Hosting with edge caching. Cloud Armor provides WAF with OWASP rules, DDoS protection, rate limiting, and geo-fencing.

**Frontend:** Firebase Hosting with automatic CDN. Deploy: `firebase deploy --only hosting`

**Cloud Armor policy:** Blocks SQL injection, XSS, rate limits to 60 req/min/IP, blocks prompt injection patterns at edge.

---

## LAYER 2: Google Identity Platform

Replaces static API keys with proper user identity. Supports SAML federation for government Active Directory, MFA, and JWT issuance. Every query is attributable to a specific analyst (AUSTRAC audit requirement).

---

## LAYER 3: Cloud Run (5 Services)

Each microservice runs as an independent Cloud Run service with concurrency-based auto-scaling, built-in TLS, and load balancing.

| Service | Min/Max | Concurrency | Timeout | CPU/Memory |
|---|---|---|---|---|
| Gateway | 2/20 | 80 | 60s | 1 CPU / 512Mi |
| Query Service | 2/15 | 10 | 60s | 2 CPU / 2Gi |
| Embedding Service | 0/10 | 50 | 30s | 1 CPU / 1Gi |
| Graph Service | 2/8 | 80 | 15s | 1 CPU / 1Gi |
| Ingestion Service | 0/10 | 5 | 300s | 2 CPU / 2Gi |

Service-to-service auth via IAM invoker roles (Workload Identity) — no static API keys.

---

## LAYER 4: Data Services

- **Vertex AI Vector Search:** Managed ANN (768-dim, cosine, streaming updates)
- **Neo4j Aura:** Managed graph DB via GCP Marketplace (openCypher compatible)
- **Cloud Memorystore:** Redis 7 for caching and rate limit state
- **Cloud SQL:** PostgreSQL 15 for audit logs, metadata, HITL queue
- **Cloud Storage:** Raw document persistence with lifecycle policies
- **Secret Manager:** Credentials with IAM access and version control

---

## LAYER 5: Async Processing

Document ingestion triggers: GCS upload event -> Pub/Sub -> Cloud Run Job (parse, chunk, embed, index). Fan-out for parallel processing of large batch uploads.

---

## LAYER 6: Observability

- **Cloud Logging:** Auto-collected JSON from Cloud Run stdout (structlog compatible)
- **Cloud Trace:** OpenTelemetry OTLP export, distributed trace across all services
- **Cloud Monitoring:** Custom metrics, SLO dashboards, error budget alerting

---

## Environment Strategy

| Environment | Scaling | Deploy Trigger | Cost Profile |
|---|---|---|---|
| dev | Scale-to-zero | Auto (push) | ~$50/month |
| prod | Min 2 instances | Manual + approval | ~$555/month |

Rollback: `gcloud run services update-traffic SERVICE --to-revisions=PREVIOUS=100`
