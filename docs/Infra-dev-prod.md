# Production Architecture Diagram — Layer-by-Layer Deep Dive

## The Complete Architecture (Reference)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              INTERNET                                     │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│  LAYER 1: EDGE (CloudFront + WAF)                                        │
│         Static: S3 React SPA    |    API: /v1/* → API Gateway            │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│  LAYER 2: AUTH & THROTTLE (API Gateway + Cognito)                        │
│         JWT validation, usage plans, request throttling                   │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌────────────────────────────────▼────────────────────────────────────────┐
│  LAYER 3: LOAD BALANCING (ALB in public subnets)                         │
│         Path-based routing, TLS termination, health checks               │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
┌════════════════════════════════════════════════════════════════════════════┐
║  LAYER 4: COMPUTE (ECS Fargate in private subnets)                       ║
║                                                                           ║
║  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                 ║
║  │   Gateway    │──▶│ Query Service│──▶│  Embedding   │──▶ Bedrock      ║
║  │  (2-10 tasks)│   │  (2-10 tasks)│   │  (2-8 tasks) │                 ║
║  └──────┬───────┘   └──────┬───────┘   └──────────────┘                 ║
║         │                  │                                              ║
║         ▼                  ▼                                              ║
║  ┌──────────────┐   ┌──────────────┐                                    ║
║  │  Ingestion   │   │Graph Service │                                    ║
║  │  (1-5 tasks) │   │ (2-6 tasks)  │                                    ║
║  └──────────────┘   └──────────────┘                                    ║
╚════════════════════════════════════════════════════════════════════════════╝
                                 │
┌════════════════════════════════════════════════════════════════════════════┐
║  LAYER 5: DATA (Managed services in private subnets)                     ║
║                                                                           ║
║  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                 ║
║  │  OpenSearch  │   │   Neptune    │   │ ElastiCache  │                  ║
║  │  (Vectors)   │   │   (Graph)    │   │   (Redis)    │                  ║
║  └──────────────┘   └──────────────┘   └──────────────┘                  ║
║                                                                           ║
║  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐                 ║
║  │   Aurora PG  │   │  S3 Bucket   │   │ Secrets Mgr  │                  ║
║  │  (Metadata)  │   │ (Documents)  │   │   + KMS      │                  ║
║  └──────────────┘   └──────────────┘   └──────────────┘                  ║
╚════════════════════════════════════════════════════════════════════════════╝
                                 │
┌════════════════════════════════════════════════════════════════════════════┐
║  LAYER 6: ASYNC PROCESSING (Lambda + SQS)                                ║
║                                                                           ║
║  S3 Event → Lambda: Parse → SQS → Lambda: Chunk → SQS → Lambda: Embed   ║
║                                                           ↓               ║
║                                                    OpenSearch + Neptune    ║
╚════════════════════════════════════════════════════════════════════════════╝
                                 │
┌════════════════════════════════════════════════════════════════════════════┐
║  LAYER 7: OBSERVABILITY (CloudWatch + X-Ray + Alarms)                    ║
║                                                                           ║
║  Logs → CloudWatch Logs → Metric Filters → Alarms → SNS → PagerDuty     ║
║  Traces → X-Ray → Service Map + Latency Distribution                     ║
║  Metrics → CloudWatch Metrics → Dashboards + SLO Monitoring              ║
╚════════════════════════════════════════════════════════════════════════════╝
```

---

## LAYER 1: EDGE — CloudFront + WAF

### WHAT

Amazon CloudFront is a CDN (Content Delivery Network) with 450+ edge locations globally. AWS WAF (Web Application Firewall) filters malicious HTTP requests before they reach your infrastructure.

In this architecture, CloudFront serves two purposes:
1. **Static hosting** — serves the React SPA (built HTML/JS/CSS from `frontend/`) from S3
2. **API proxy** — forwards `/v1/*` requests to the backend, adding caching and DDoS protection

### WHY (this project specifically)

The React frontend is 15 components totaling ~200KB gzipped after Vite build. Running an ECS container just to serve static files is like hiring a chef to hand out pre-packaged meals.

```
Current (wasteful):        Browser → Internet → ALB → ECS Container → serve index.html
Production (efficient):    Browser → Edge PoP (Sydney) → S3 bucket (< 5ms TTFB)
```

Additionally, the gateway already implements penetration detection (`fastapi-guard`), but WAF adds a second defense layer at the edge — before traffic even reaches the VPC. SQL injection, XSS, and bot traffic get blocked at AWS infrastructure level.

### WHEN
- Day 1 for static frontend hosting (cheapest option: ~$2/month vs $30/month for a container)
- Day 1 for API protection (WAF blocks known attack signatures before they consume Fargate CPU)

### HOW (specific to this project)

**Frontend delivery:**
```bash
npm run build (in frontend/) → produces dist/ folder
aws s3 sync dist/ s3://rag-pipeline-prod-frontend/ --delete
aws cloudfront create-invalidation --distribution-id EXXXX --paths "/*"
```

**CloudFront behaviors (routing rules):**

| Path Pattern | Origin | Cache | Purpose |
|---|---|---|---|
| `/` (default) | S3 Frontend bucket | 24 hours | React SPA static assets |
| `/v1/*` | API Gateway (HTTP origin) | No cache | All API calls (ask, ingest, documents) |
| `/assets/*` | S3 Frontend bucket | 1 year | Vite hashed static assets (immutable) |

**SPA routing trick:** The React app uses `react-router-dom 7` for client-side routing (`/`, `/documents`). When a user refreshes on `/documents`, CloudFront would return 403 (file doesn't exist in S3). Solution:

```hcl
custom_error_response {
  error_code         = 403
  response_code      = 200
  response_page_path = "/index.html"  # All paths serve SPA entry point
}
```

**WAF rules specific to this use case:**
```hcl
resource "aws_wafv2_web_acl" "main" {
  rule {
    name = "block-sql-injection"
    statement { sqli_match_statement { field_to_match { body {} } } }
    action { block {} }
  }
  rule {
    name = "rate-limit-api"
    statement { rate_based_statement { limit = 1000; aggregate_key_type = "IP" } }
    action { block {} }
  }
  rule {
    name = "block-known-bad-inputs"
    statement { byte_match_statement {
      search_string = "ignore previous"
      field_to_match { body {} }
    }}
    action { block {} }
  }
}
```

This is complementary to the existing `fastapi-guard` — WAF catches volume attacks (DDoS, bot armies), while `fastapi-guard` catches application-level injection patterns that slip through.

### WHERE
- CloudFront: AWS global edge network (Sydney PoP for Australian users, <10ms latency)
- S3 bucket: `ap-southeast-2` (data sovereignty requirement)
- WAF: attached to CloudFront distribution (processes rules at edge, not origin)

### WHICH configuration
- Dev: CloudFront with default certificate (no custom domain)
- Prod: CloudFront + ACM certificate + custom domain + WAF + logging to S3

---

## LAYER 2: AUTH & THROTTLE — API Gateway + Cognito

### WHAT
Amazon Cognito manages user identities (sign-up, sign-in, MFA, token issuance). Amazon API Gateway validates JWTs, applies usage plans (throttling per client), and routes requests.

Together they replace the current `APIKeyAuthMiddleware` + `RateLimitMiddleware` in the gateway service.

### WHY (this project specifically)

The current auth is static API keys in environment variables:
```python
# Current: services/gateway/src/middleware/auth.py
class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, valid_keys: set[str]):
        self.valid_keys = valid_keys  # From env var: "dev-api-key"
```

Problems for production:
1. **No user identity** — cannot attribute queries to individual analysts (audit requirement for AUSTRAC compliance)
2. **No key rotation** — changing keys requires redeploying all services
3. **No MFA** — government compliance typically mandates MFA
4. **No SSO** — staff already have Active Directory accounts; they shouldn't create new credentials
5. **Rate limiting resets on restart** — the `TokenBucket` is in-memory; a rolling deployment resets all counters

### WHEN
- Before any user-facing deployment. AUSTRAC and APRA compliance requires authenticated, attributable access to compliance advice systems.
### HOW (specific to this project)

**Auth flow for the React SPA:**

```
1. User opens app - React checks for valid JWT in memory
2. No token - Redirect to Cognito hosted login (or embedded Amplify UI)
3. User authenticates (email + MFA) - Cognito issues:
   - Access token (JWT, 1 hour TTL)
   - ID token (user attributes: name, email, department, role)
   - Refresh token (30 days, stored in httpOnly cookie)
4. React stores access token in memory (NOT localStorage - XSS risk)
5. Every API call: Authorization: Bearer <access_token>
6. API Gateway validates JWT signature against Cognito JWKS endpoint
7. If expired: React uses refresh token to silently get new access token
```

**How it maps to the existing middleware stack:**

| Current (Gateway Service) | Production (AWS Managed) | What Changes |
|---|---|---|
| `APIKeyAuthMiddleware` | API Gateway JWT Authorizer | Auth happens before traffic reaches ECS |
| `RateLimitMiddleware` + `TokenBucket` | API Gateway Usage Plans | Persistent across deployments, per-client |
| `SecurityHeadersMiddleware` | CloudFront Response Headers Policy | Headers set at edge |
| `fastapi-guard` | WAF + Gateway remains for app-level | Defense in depth |
| `CorrelationIdMiddleware` | Stays in Gateway service | Still needed for inter-service tracing |

**Cognito User Pool schema for this domain:**
```hcl
schema {
  name                = "department"
  attribute_data_type = "String"
  mutable             = true
  # Values: "compliance", "legal", "risk", "operations"
}

schema {
  name                = "role"
  attribute_data_type = "String"
  mutable             = true
  # Values: "reader", "editor", "admin"
}
```

**Integration with the frontend** (`frontend/src/lib/api-client.ts`):
```typescript
// Before: static API key
headers: { 'X-API-Key': import.meta.env.VITE_API_KEY }

// After: dynamic JWT from Cognito
headers: { 'Authorization': `Bearer ${await getAccessToken()}` }
```

**API Gateway usage plans (replacing in-memory TokenBucket):**
```hcl
resource "aws_api_gateway_usage_plan" "standard" {
  name = "standard-analyst"
  throttle_settings {
    burst_limit = 100   # Max concurrent requests
    rate_limit  = 60    # Requests per second (matches current 60/min)
  }
  quota_settings {
    limit  = 10000      # Monthly quota
    period = "MONTH"
  }
}
```

### WHERE
- Cognito: Regional endpoint in `ap-southeast-2` (user data stays in Australia)
- API Gateway: Regional, deployed in front of ALB
- JWT validation: happens at API Gateway edge - unauthorized requests never reach ECS (saves compute cost)

### WHICH
- Dev: Cognito with email sign-up (no MFA)
- Prod: Cognito with SAML federation (government Active Directory) + mandatory MFA

**Interview answer:** "We moved auth from application middleware to API Gateway + Cognito because: (a) JWT validation at the edge means unauthorized requests never consume Fargate CPU, (b) Cognito supports SAML federation with the government's existing Active Directory, (c) usage plans persist rate limit state across deployments unlike our in-memory TokenBucket, and (d) every query is now attributable to a specific analyst - required for AUSTRAC audit compliance."

---

## LAYER 3: LOAD BALANCING - Application Load Balancer (ALB)

### WHAT
ALB distributes incoming HTTP/HTTPS traffic across multiple ECS Fargate tasks. It performs TLS termination, health checking, and path-based routing to different target groups.

Already partially defined in `infrastructure/modules/compute/main.tf`:
```hcl
resource "aws_lb" "api" {
  name               = "${var.project_name}-${var.environment}-alb"
  load_balancer_type = "application"
  ...
}
```

### WHY (this project specifically)

The microservices architecture has 5 independently scalable services. Without an ALB:
- Single point of failure (one task crashes = service outage)
- No TLS termination (each container would need certificates)
- No graceful draining (deployment kills in-flight 30-second query requests)

With ALB:
- **Request distribution**: 10 Gateway tasks each handle ~50 concurrent requests instead of 1 task handling 500
- **Health-based routing**: unhealthy tasks automatically removed (using `/health/live` endpoint)
- **TLS termination**: HTTPS handled by ALB with ACM certificate - containers speak plain HTTP internally
- **Zero-downtime deployments**: ALB drains connections before killing old tasks

### WHEN
- Day 1 of production. Already partially implemented in existing Terraform.

### HOW (specific to this project)

**What needs to change from current `compute/main.tf`:**

1. **Add HTTPS listener** (currently only HTTP on port 80):
```hcl
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.api.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"  # TLS 1.3
  certificate_arn   = aws_acm_certificate.api.arn
  default_action { type = "forward"; target_group_arn = aws_lb_target_group.gateway.arn }
}

# Redirect HTTP to HTTPS
resource "aws_lb_listener" "http_redirect" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect { port = "443"; protocol = "HTTPS"; status_code = "HTTP_301" }
  }
}
```

2. **Move ALB to public subnets, ECS tasks to private** (currently `assign_public_ip = true` which is insecure):
```hcl
# ALB: public subnets (internet-facing)
subnets = var.public_subnet_ids

# ECS Service: private subnets (no public IP)
network_configuration {
  subnets          = var.private_subnet_ids   # Changed from public!
  security_groups  = [var.security_group_id]
  assign_public_ip = false                    # Changed from true!
}
```

3. **Connection draining for long queries:**
The `/v1/ask` endpoint takes 5-30 seconds. During deployments, ALB needs time to finish in-flight requests:
```hcl
resource "aws_lb_target_group" "gateway" {
  deregistration_delay = 60  # Wait 60s for in-flight /v1/ask to complete
  health_check {
    path     = "/health/live"   # Gateway liveness endpoint
    interval = 15
    timeout  = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}
```

### WHERE
- ALB: public subnets across 2 AZs (Terraform already creates 2 public subnets)
- Target groups: register ECS Gateway tasks in private subnets
- Security group: ALB allows inbound 443 from internet; ECS SG allows inbound 8080 from ALB only

### WHICH
- Single ALB for cost efficiency (multiple target groups via path-based routing if needed later)
- `ELBSecurityPolicy-TLS13-1-2-2021-06` for maximum security (TLS 1.3, disables weak ciphers)

---

## LAYER 4: COMPUTE - ECS Fargate (5 Microservices)

### WHAT
AWS ECS (Elastic Container Service) with Fargate launch type runs Docker containers without managing EC2 instances. Each of the 5 services becomes an independent ECS Service with its own task definition, scaling policy, and deployment configuration.

### WHY (this project specifically)

The microservices have different scaling characteristics:

| Service | Request Pattern | Why Independent Scaling Matters |
|---|---|---|
| Gateway | Proportional to user traffic | Scales with total request volume |
| Query Service | CPU-intensive (orchestrates 4 agents) | Needs most CPU, longest requests (30s) |
| Embedding Service | Bursty during ingestion | Spikes when batch documents ingested |
| Graph Service | Steady, fast (Cypher queries) | Low CPU, fast responses |
| Ingestion Service | Bursty, long-running | Active only during uploads |

If these were a single monolith on 1 ECS service, scaling for Embedding spikes would also scale the Gateway (wasted money). Independent services scale independently.

### WHEN
- Immediately. The Dockerfiles are production-ready (multi-stage, non-root user, health checks).

### HOW (specific to this project)

**Service Discovery (replacing Docker Compose DNS):**

In Docker Compose, `query-service` resolves because Docker creates a bridge network. In ECS, AWS Cloud Map is needed:

```hcl
resource "aws_service_discovery_private_dns_namespace" "main" {
  name = "rag-pipeline.local"
  vpc  = aws_vpc.main.id
}

resource "aws_service_discovery_service" "embedding" {
  name = "embedding-service"
  dns_config {
    namespace_id = aws_service_discovery_private_dns_namespace.main.id
    dns_records { ttl = 10; type = "A" }
    routing_policy = "MULTIVALUE"  # Returns multiple healthy IPs
  }
}
```

Now `embedding-service.rag-pipeline.local` resolves to the ECS tasks - same pattern as Docker Compose but with health-aware DNS resolution.

**How existing code maps:**
```python
# services/query-service/src/main.py (current code)
embedding_client = ResilientClient(
    base_url=settings.embedding_service_url,  # "http://embedding-service:8004" in Docker
    circuit_breaker=circuit_breaker,           # becomes "http://embedding-service.rag-pipeline.local:8004" in ECS
    ...
)
```

Only the URL changes (environment variable) - the `ResilientClient` with circuit breaker + retry works identically.

**Task definition for Query Service (the most complex service):**
```hcl
resource "aws_ecs_task_definition" "query_service" {
  family                   = "${var.project}-${var.environment}-query-service"
  requires_compatibilities = ["FARGATE"]
  cpu                      = 1024   # 1 vCPU (orchestrates 4 agents)
  memory                   = 2048   # 2 GB (cross-encoder model loaded in memory)
  network_mode             = "awsvpc"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.query_service_task.arn

  container_definitions = jsonencode([{
    name  = "query-service"
    image = "${aws_ecr_repository.query_service.repository_url}:${var.image_tag}"
    portMappings = [{ containerPort = 8001 }]
    environment = [
      { name = "EMBEDDING_SERVICE_URL", value = "http://embedding-service.rag-pipeline.local:8004" },
      { name = "GRAPH_SERVICE_URL", value = "http://graph-service.rag-pipeline.local:8003" },
      { name = "CHROMADB_HOST", value = aws_opensearch_domain.vectors.endpoint },
    ]
    secrets = [
      { name = "AWS_DEFAULT_REGION", valueFrom = "arn:aws:ssm:ap-southeast-2:123:parameter/rag/region" }
    ]
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8001/health/live || exit 1"]
      interval    = 15
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/${var.project}/${var.environment}/query-service"
        "awslogs-region"        = var.region
        "awslogs-stream-prefix" = "query"
      }
    }
  }])
}
```

**Auto-scaling for Query Service:**
```hcl
resource "aws_appautoscaling_policy" "query_cpu" {
  name               = "query-service-cpu-scaling"
  policy_type        = "TargetTrackingScaling"
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.query.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 70.0     # Scale up when average CPU > 70%
    scale_in_cooldown  = 300      # Wait 5 min before scaling down
    scale_out_cooldown = 60       # Scale up quickly (1 min)
  }
}
```

**Deployment strategy (zero downtime):**
```hcl
resource "aws_ecs_service" "query" {
  deployment_configuration {
    maximum_percent         = 200  # Double capacity during deployment
    minimum_healthy_percent = 100  # Never go below current capacity
  }
  deployment_circuit_breaker {
    enable   = true
    rollback = true  # Auto-rollback if new tasks fail health checks
  }
}
```

This means: during deployment, ECS launches new tasks, waits for `/health/live` to pass, then drains old tasks. The 30-second `/v1/ask` requests complete on old tasks while new tasks start serving.

### WHERE
- All tasks in private subnets (no public IP)
- Outbound internet via NAT Gateway (needed for Bedrock API calls)
- Inter-service traffic stays within VPC (no internet transit)

### WHICH scaling per environment

| Service | Dev (min/max) | Prod (min/max) | Scaling Trigger |
|---|---|---|---|
| Gateway | 1/2 | 2/10 | ALB request count |
| Query Service | 1/2 | 2/10 | CPU > 70% |
| Embedding Service | 1/2 | 2/8 | Request count per target |
| Graph Service | 1/2 | 2/6 | CPU > 70% |
| Ingestion Service | 0/2 | 1/5 | SQS queue depth |

**Interview answer:** "Each service scales independently because their load profiles differ. The Query Service is CPU-bound (agent orchestration), Embedding is bursty (batch ingestion), and Ingestion can scale to zero when idle. ECS deployment circuit breakers automatically rollback if new tasks fail health checks - preventing bad deployments from reaching production. Service discovery via Cloud Map gives us the same DNS resolution pattern as Docker Compose but with health-aware routing."

---

## LAYER 5: DATA - Managed Services (Private Subnets)

### WHAT
This layer contains all stateful services that persist data beyond the lifecycle of any single compute task. In production, these replace the Docker containers (ChromaDB, Neo4j, Redis) with AWS-managed equivalents that provide durability, replication, automated backups, and encryption.

### 5A: Amazon OpenSearch Service (replacing ChromaDB)

#### WHAT
Amazon OpenSearch with the k-NN (k-Nearest Neighbors) plugin provides managed vector search using HNSW (Hierarchical Navigable Small World) algorithm. It also includes built-in BM25 for keyword search - consolidating two stores into one.

#### WHY (this project specifically)

The `RetrievalAgent` performs hybrid search - dense vector (cosine similarity on 1024-dim Titan embeddings) + BM25 keyword search. Currently these are two separate stores:
- ChromaDB for vectors (`infrastructure/chromadb_vector_store.py`)
- In-memory BM25 (`infrastructure/bm25_sparse_index.py`)

OpenSearch consolidates both in one service: native k-NN for vectors AND built-in BM25 for text search. This eliminates the in-memory BM25 index (which loses data on restart and cannot scale horizontally).

**Production problems with ChromaDB:**
- Single-node only (no replication) - one container crash = total search failure
- No automated backups - data loss on disk failure
- No encryption at rest - compliance violation
- No horizontal scaling - performance degrades as document count grows

#### WHEN
- Day 1 of production deployment. This is the most critical data store for the query pipeline - it holds all embedded chunks.

#### HOW (specific to this project)

```hcl
resource "aws_opensearch_domain" "vectors" {
  domain_name    = "${var.project}-${var.environment}-vectors"
  engine_version = "OpenSearch_2.11"

  cluster_config {
    instance_type          = "r6g.large.search"  # Memory-optimized for vectors
    instance_count         = 2                     # Multi-AZ
    zone_awareness_enabled = true
  }

  ebs_options {
    ebs_enabled = true
    volume_size = 100  # GB, scales with document count
    volume_type = "gp3"
  }

  encrypt_at_rest { enabled = true }
  node_to_node_encryption { enabled = true }

  vpc_options {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.opensearch.id]
  }
}
```

**How existing code maps (hexagonal architecture advantage):**
```python
# Current port interface (src/ports/vector_store.py)
class VectorStorePort(Protocol):
    async def store(self, records: list[EmbeddingRecord]) -> None: ...
    async def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]: ...

# New adapter: src/infrastructure/opensearch_vector_store.py
class OpenSearchVectorStore:  # implements VectorStorePort
    async def search(self, query_vector: list[float], top_k: int) -> list[ScoredChunk]:
        body = {
            "query": {
                "knn": {
                    "embedding": {
                        "vector": query_vector,
                        "k": top_k
                    }
                }
            }
        }
        response = await self._client.search(index="chunks", body=body)
        return [self._to_scored_chunk(hit) for hit in response["hits"]["hits"]]
```

**Key point for interviews:** The hexagonal architecture (`src/ports/`) means this migration is an adapter swap - zero changes to `RetrievalService`, `RetrievalAgent`, or any domain logic.

#### WHERE
- Private subnets only (no public access)
- Same VPC as ECS services
- Region: `ap-southeast-2` (Sydney) for data sovereignty compliance
- VPC endpoint for access without internet transit

#### WHICH tier
- Dev: `t3.medium.search` x 1 node (~$50/month)
- Prod: `r6g.large.search` x 2 nodes + dedicated master (~$400/month)

---

### 5B: Amazon Neptune (replacing Neo4j Community)

#### WHAT
Amazon Neptune is a fully managed graph database supporting both Apache TinkerPop Gremlin and openCypher query languages. It provides multi-AZ deployment, automatic failover, continuous backup to S3, and point-in-time recovery.

#### WHY (this project specifically)

The `GraphService` runs Cypher traversals for relationship queries:
```cypher
MATCH path = (start:LegalEntity)-[*1..2]-(related:LegalEntity)
WHERE start.name CONTAINS $query
RETURN related.source_chunk_id, 1.0 / (1 + length(path)) AS score
```

Neptune supports openCypher natively - Cypher queries work without modification.

**Production problems with Neo4j Community:**
- Single-node only (Community edition has no clustering)
- No automated backups (manual dump required)
- No encryption at rest (compliance violation)
- No automatic failover (downtime on crash = 30% of RRF weight lost)
- Requires self-managed container (patching, monitoring, scaling)

#### WHEN
- Production deployment phase. During dev/staging, a self-managed Neo4j on ECS is acceptable for cost savings.
- Migrate when needed: multi-AZ HA, automated PITR backups, or query volume exceeds single-node capacity.

#### HOW (specific to this project)

```hcl
resource "aws_neptune_cluster" "graph" {
  cluster_identifier  = "${var.project}-${var.environment}-graph"
  engine              = "neptune"
  engine_version      = "1.3.1.0"
  iam_database_authentication_enabled = true
  storage_encrypted   = true
  kms_key_id          = aws_kms_key.data.arn

  vpc_security_group_ids = [aws_security_group.neptune.id]
  neptune_subnet_group_name = aws_neptune_subnet_group.main.name

  backup_retention_period = 7
  preferred_backup_window = "02:00-03:00"
}

resource "aws_neptune_cluster_instance" "writer" {
  cluster_identifier = aws_neptune_cluster.graph.id
  instance_class     = "db.r6g.large"
  engine             = "neptune"
}
```

**Code impact:**
```python
# services/graph-service currently connects to:
# NEO4J_URI=bolt://neo4j:7687

# In production:
# NEPTUNE_ENDPOINT=wss://rag-pipeline-prod-graph.cluster-xxxxx.ap-southeast-2.neptune.amazonaws.com:8182

# The graph-service adapter changes connection protocol (Bolt to WebSocket)
# but query language (openCypher) remains identical
```

#### WHERE
- Private subnets, Neptune subnet group spanning 2+ AZs
- Accessed only by Graph Service ECS tasks via VPC security group rules

#### WHICH
- Dev: `db.t3.medium` (burstable, ~$70/month)
- Prod: `db.r6g.large` (memory-optimized for traversals, ~$350/month)

**Interview answer:** "Neptune was chosen over self-managed Neo4j because our graph traversals are critical for relationship queries - 30% of our RRF weight comes from graph. Neptune's automatic failover under 30 seconds meets our 99.9% availability SLO, and openCypher compatibility meant we didn't rewrite a single query."

---

### 5C: Amazon ElastiCache for Redis

#### WHAT
ElastiCache for Redis provides a managed in-memory cache with multi-AZ replication, automatic failover, encryption in transit and at rest, and CloudWatch metrics.

#### WHY (this project specifically)

The system caches three things:
1. **Query results** (TTL 5 min) - 35% cache hit rate at peak, each hit saves a $0.001 Bedrock call
2. **Rate limit counters** - currently in-memory `TokenBucket` (resets on deploy!)
3. **Circuit breaker state** - tracks failure counts for Embedding and Graph services

In-memory Redis loses all this on container restart. ElastiCache persists across deployments.

**Cost impact:** 35% cache hit rate at 500 req/hour peak = 175 saved Bedrock calls/hour = $0.175/hour saved. ElastiCache costs $0.28/hour for `cache.r6g.large`. Breaks even at ~800 req/hour, profitable at scale.

#### WHEN
- Production deployment. Cache loss is degradation, not outage (system works without it, just slower and costlier).

#### HOW (specific to this project)

```hcl
resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${var.project}-${var.environment}-cache"
  description          = "RAG platform query cache and rate limiting"
  engine               = "redis"
  engine_version       = "7.0"
  node_type            = "cache.r6g.large"
  num_cache_clusters   = 2  # Primary + replica for failover

  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = data.aws_secretsmanager_secret_version.redis_auth.secret_string

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  automatic_failover_enabled = true
  multi_az_enabled           = true
}
```

**Code change - one environment variable:**
```
# Current: REDIS_URL=redis://redis:6379
# Production: REDIS_URL=rediss://rag-pipeline-prod.xxxxx.cache.amazonaws.com:6379
#             (note: rediss:// = TLS-encrypted connection)
```

#### WHERE
- Private subnets, accessible only from ECS security group
- Same AZ as primary ECS tasks for lowest latency (<1ms)

#### WHICH
- Dev: `cache.t3.micro` single node (~$15/month)
- Prod: `cache.r6g.large` with replica (~$200/month)

---

### 5D: Amazon S3 (Document Storage)

#### WHAT
Amazon S3 provides object storage with 99.999999999% (11 nines) durability, versioning, lifecycle policies, server-side encryption, and event notifications.

#### WHY (this project specifically)

The ingestion pipeline currently stores uploaded documents in Docker volumes:
```yaml
# docker-compose.yml
ingestion-service:
  volumes:
    - doc_storage:/app/data/documents  # Docker volume - gone if host dies
```

S3 provides:
- **11 nines durability** - documents never lost (compliance requirement)
- **Versioning** - audit trail of document changes (regulatory requirement)
- **Event notifications** - trigger Lambda on upload (event-driven ingestion)
- **Lifecycle policies** - archive old versions to Glacier after 90 days
- **KMS encryption** - meets APRA data protection requirements

#### WHEN
- Day 1. Document durability is non-negotiable for a compliance platform serving AML/KYC analysts.

#### HOW (specific to this project)

```hcl
resource "aws_s3_bucket" "documents" {
  bucket = "${var.project}-${var.environment}-documents"
  tags   = local.common_tags
}

resource "aws_s3_bucket_versioning" "documents" {
  bucket = aws_s3_bucket.documents.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.data.arn
    }
  }
}

# Event-driven ingestion trigger
resource "aws_s3_bucket_notification" "ingestion_trigger" {
  bucket = aws_s3_bucket.documents.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.document_parser.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
    filter_suffix       = ".pdf"
  }
}
```

**Bucket structure:**
```
s3://rag-pipeline-prod-documents/
  uploads/              # Raw uploaded files (triggers Lambda)
  processed/            # Normalized documents post-parsing
  chunks/               # Chunked text segments (backup/audit)
  archive/              # Lifecycle rule moves here after 90 days
```

#### WHERE
- Same region (`ap-southeast-2`) for data sovereignty
- VPC endpoint for private access from ECS (no internet transit)
- Block all public access (bucket policy denies non-VPC requests)

#### WHICH
- Standard storage class for active documents
- Intelligent-Tiering for documents accessed infrequently
- Glacier for archived versions (>90 days old)

---

### 5E: Aurora PostgreSQL Serverless v2 (Metadata Store)

#### WHAT
Aurora PostgreSQL Serverless v2 is a fully managed relational database that auto-scales compute capacity based on load. It provides ACID compliance, multi-AZ deployment, automated backups, and point-in-time recovery.

#### WHY (this project specifically)

The system needs ACID-compliant storage for:
1. **Document metadata** - ingestion records, file hashes, processing status
2. **Saga logs** - distributed transaction tracking across OpenSearch/Neptune/S3
3. **Audit logs** - who queried what, when, with what confidence (AUSTRAC requirement)
4. **Evaluation results** - golden dataset scores, regression tracking
5. **User preferences** - saved queries, feedback on answers

Without a relational store, these concerns are scattered across services with no consistency guarantees.

#### WHEN
- When implementing: the Saga pattern for cross-store consistency, audit logging, or evaluation result tracking.

#### HOW (specific to this project)

```hcl
resource "aws_rds_cluster" "metadata" {
  cluster_identifier = "${var.project}-${var.environment}-metadata"
  engine             = "aurora-postgresql"
  engine_mode        = "provisioned"
  engine_version     = "15.4"
  database_name      = "ragplatform"
  master_username    = "admin"
  master_password    = data.aws_secretsmanager_secret_version.db_password.secret_string

  storage_encrypted = true
  kms_key_id        = aws_kms_key.data.arn

  vpc_security_group_ids = [aws_security_group.aurora.id]
  db_subnet_group_name   = aws_db_subnet_group.main.name

  serverlessv2_scaling_configuration {
    min_capacity = 0.5   # Scale to near-zero when idle
    max_capacity = 16.0  # Scale up under load
  }

  backup_retention_period = 7
}
```

**Schema example for audit logging:**
```sql
CREATE TABLE query_audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id TEXT NOT NULL,           -- From Cognito JWT sub claim
  query_text TEXT NOT NULL,
  confidence_score DECIMAL(3,2),
  citation_count INTEGER,
  response_time_ms INTEGER,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  correlation_id UUID NOT NULL
);

CREATE TABLE ingestion_saga_log (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL,
  step TEXT NOT NULL,              -- 'postgres', 'opensearch', 'neptune'
  status TEXT NOT NULL,            -- 'pending', 'completed', 'compensated'
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

#### WHERE
- Private subnets, Aurora subnet group spanning 2+ AZs
- RDS Proxy for connection pooling (ECS tasks share connections efficiently)

#### WHICH
- Dev: 0.5-2 ACU (~$45/month)
- Prod: 0.5-16 ACU (~$100-400/month depending on load)

---

### 5F: AWS Secrets Manager + KMS (Secrets & Encryption)

#### WHAT
AWS Secrets Manager stores and automatically rotates database credentials, API keys, and other secrets. AWS KMS (Key Management Service) provides envelope encryption for all data at rest with automatic key rotation.

#### WHY (this project specifically)

Current state - credentials in environment variables and docker-compose:
```yaml
# INSECURE: docker-compose.yml
neo4j:
  environment:
    - NEO4J_AUTH=neo4j/password123  # Hardcoded in version control!
```

Production requirements:
- **Automatic rotation** - credentials rotate every 30 days without redeployment
- **Audit trail** - CloudTrail logs every secret access (who, when, which service)
- **Encryption** - all data at rest encrypted with customer-managed KMS keys
- **Least privilege** - each ECS task role can only access its specific secrets

#### WHEN
- Immediately. This is a security hygiene prerequisite before any production deployment.

#### HOW (specific to this project)

```hcl
resource "aws_kms_key" "data" {
  description         = "RAG Platform data encryption key"
  enable_key_rotation = true  # Automatic annual rotation
  tags                = local.common_tags
}

resource "aws_secretsmanager_secret" "neptune_password" {
  name       = "${var.project}/${var.environment}/neptune-password"
  kms_key_id = aws_kms_key.data.arn
}

resource "aws_secretsmanager_secret" "redis_auth" {
  name       = "${var.project}/${var.environment}/redis-auth-token"
  kms_key_id = aws_kms_key.data.arn
}
```

**ECS task definitions retrieve secrets at startup:**
```json
"secrets": [
  {
    "name": "NEO4J_PASSWORD",
    "valueFrom": "arn:aws:secretsmanager:ap-southeast-2:123456:secret:rag-pipeline/prod/neptune-password"
  },
  {
    "name": "REDIS_AUTH_TOKEN",
    "valueFrom": "arn:aws:secretsmanager:ap-southeast-2:123456:secret:rag-pipeline/prod/redis-auth-token"
  }
]
```

#### WHERE
- Secrets Manager: same region (`ap-southeast-2`)
- KMS key: same region, used by S3, Aurora, OpenSearch, Neptune, and Secrets Manager
- IAM policies restrict which ECS task role can access which secrets

#### WHICH
- One KMS CMK (Customer Managed Key) for all encryption ($1/month + $0.03/10k requests)
- Separate secrets per service per environment (e.g., `rag-pipeline/prod/neptune-password`)

---

## LAYER 6: ASYNC PROCESSING - Lambda + SQS (Event-Driven Ingestion)

### WHAT
AWS Lambda provides serverless compute for event-driven workloads. Amazon SQS (Simple Queue Service) provides managed message queues that decouple pipeline stages. Together they create a step-by-step document processing pipeline triggered by S3 uploads.

### WHY (this project specifically)

Current ingestion is synchronous:
```
User uploads PDF → POST /v1/ingest → Ingestion Service processes entirely (30-120s) → Response
```

Problems:
- A 500-page PDF blocks the Fargate task for 2+ minutes (other requests queue behind it)
- If processing fails halfway, the entire upload must be retried
- No parallelism - chunks processed sequentially
- ECS Ingestion Service sits idle 95% of the time but costs $70/month

Lambda pipeline:
```
S3 Upload → Lambda: Parse (extract text) → SQS → Lambda: Chunk (split into segments)
                                                      → SQS → Lambda: Embed (generate vectors)
                                                                    → OpenSearch + Neptune
```

Benefits:
- **Zero idle cost** - Lambda charges only during execution ($0 when no uploads)
- **Automatic parallelism** - 50 chunks processed by 50 concurrent Lambdas simultaneously
- **Fault isolation** - if embedding fails for chunk 37, only chunk 37 retries (not entire document)
- **Dead letter queues** - failed messages captured for inspection, never lost
- **Scales to 1000 concurrent** - handle batch uploads of 100 documents without provisioning

### WHEN
- When ingestion volume exceeds 10 documents/hour or document sizes exceed 10MB regularly.
- When cost optimization matters (Lambda replaces always-on Ingestion Service ECS task).

### HOW (specific to this project)

**Stage 1: Document Parser Lambda (triggered by S3)**
```hcl
resource "aws_lambda_function" "document_parser" {
  function_name = "${var.project}-${var.environment}-doc-parser"
  package_type  = "Image"  # Container image for heavy deps (PyMuPDF for PDF parsing)
  image_uri     = "${aws_ecr_repository.parser.repository_url}:latest"
  memory_size   = 1024     # PDF parsing is memory-intensive
  timeout       = 300      # 5 min for large PDFs
  role          = aws_iam_role.lambda_parser.arn

  vpc_config {
    subnet_ids         = var.private_subnet_ids
    security_group_ids = [aws_security_group.lambda.id]
  }

  dead_letter_config {
    target_arn = aws_sqs_queue.dlq.arn
  }

  environment {
    variables = {
      CHUNKING_QUEUE_URL = aws_sqs_queue.chunking.url
      DOCUMENT_BUCKET    = aws_s3_bucket.documents.id
    }
  }
}

# S3 triggers Lambda on new uploads
resource "aws_s3_bucket_notification" "trigger_parser" {
  bucket = aws_s3_bucket.documents.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.document_parser.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "uploads/"
  }
}
```

**Stage 2: Chunking Queue + Lambda**
```hcl
resource "aws_sqs_queue" "chunking" {
  name                       = "${var.project}-${var.environment}-chunking"
  visibility_timeout_seconds = 600  # Must exceed Lambda timeout
  message_retention_seconds  = 86400  # 24 hours
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq.arn
    maxReceiveCount     = 3  # Retry 3 times then DLQ
  })
}

resource "aws_lambda_function" "chunker" {
  function_name = "${var.project}-${var.environment}-chunker"
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.chunker.repository_url}:latest"
  memory_size   = 512
  timeout       = 120
  role          = aws_iam_role.lambda_chunker.arn

  environment {
    variables = {
      EMBEDDING_QUEUE_URL = aws_sqs_queue.embedding.url
      CHUNK_SIZE          = "500"
      CHUNK_OVERLAP       = "100"
    }
  }
}

# SQS triggers Lambda
resource "aws_lambda_event_source_mapping" "chunking_trigger" {
  event_source_arn = aws_sqs_queue.chunking.arn
  function_name    = aws_lambda_function.chunker.arn
  batch_size       = 10
}
```

**Stage 3: Embedding + Indexing Lambda**
```hcl
resource "aws_lambda_function" "embedder" {
  function_name = "${var.project}-${var.environment}-embedder"
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.embedder.repository_url}:latest"
  memory_size   = 512
  timeout       = 60
  role          = aws_iam_role.lambda_embedder.arn

  environment {
    variables = {
      OPENSEARCH_ENDPOINT = aws_opensearch_domain.vectors.endpoint
      NEPTUNE_ENDPOINT    = aws_neptune_cluster.graph.endpoint
      BEDROCK_REGION      = "us-east-1"  # Titan embedding availability
    }
  }
}
```

**Complete pipeline flow:**
```
1. Analyst uploads PDF via React frontend (POST /v1/ingest)
2. Gateway proxies to Ingestion Service
3. Ingestion Service validates file, stores in S3 (s3://bucket/uploads/doc-123.pdf)
4. S3 event triggers document_parser Lambda
5. Lambda extracts text, normalizes, sends to chunking SQS queue
6. chunker Lambda processes each message: splits text into 500-char chunks with 100 overlap
7. Chunks sent to embedding SQS queue (one message per chunk)
8. embedder Lambda: calls Bedrock Titan for vector, indexes into OpenSearch + Neptune
9. All chunks indexed = document available for search
```

**Dead Letter Queue (failure handling):**
```hcl
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.project}-${var.environment}-ingestion-dlq"
  message_retention_seconds = 1209600  # 14 days retention for debugging
}

# CloudWatch alarm on DLQ messages
resource "aws_cloudwatch_metric_alarm" "dlq_messages" {
  alarm_name  = "${var.project}-${var.environment}-dlq-not-empty"
  namespace   = "AWS/SQS"
  metric_name = "ApproximateNumberOfMessagesVisible"
  dimensions  = { QueueName = aws_sqs_queue.dlq.name }
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  evaluation_periods  = 1
  alarm_actions       = [aws_sns_topic.alerts.arn]
}
```

### WHERE
- Lambda functions: in VPC private subnets (need access to OpenSearch, Neptune)
- SQS queues: regional service (no VPC placement needed)
- ECR images: same region for fast pull times

### WHICH
- Dev: Lambda with 512MB memory, 10 concurrent limit (cost cap)
- Prod: Lambda with 1024MB memory, 100 concurrent limit

**Interview answer:** "We split ingestion into Lambda steps because document processing is bursty and CPU-intensive. A 500-page PDF might take 3 minutes - holding a Fargate task blocks it from serving queries. Lambda gives us parallel processing (chunk all pages simultaneously), zero idle cost, and automatic retry with DLQ for failed documents. The SQS queues between stages provide back-pressure and fault isolation - if the embedding service has a Bedrock throttling issue, chunks queue up safely rather than failing."

---

## LAYER 7: OBSERVABILITY - CloudWatch + X-Ray + Alarms

### WHAT
- **CloudWatch Logs**: Centralized log aggregation from all ECS tasks and Lambda functions
- **CloudWatch Metrics**: Custom metrics (latency histograms, token usage, confidence scores)
- **AWS X-Ray**: Distributed tracing showing request flow across all 5 microservices
- **CloudWatch Alarms**: Automated alerting on SLO breaches via SNS to PagerDuty/Slack

### WHY (this project specifically)

The platform already uses structlog for structured JSON logging:
```python
logger.info("retrieval_service.search.success", duration_ms=45.2, result_count=5)
```

And OpenTelemetry for tracing:
```python
with tracer.start_as_current_span("retrieval.dense_search") as span:
    span.set_attribute("query.length", len(query))
```

But locally, logs disappear on container restart and traces go nowhere. In production:
- **Incident diagnosis**: When P95 latency spikes, X-Ray shows exactly which service/span is slow
- **Compliance audit**: CloudWatch Logs retained for 7 years (AUSTRAC requirement)
- **Cost monitoring**: Token usage metrics track Bedrock spend in real-time
- **SLO enforcement**: Alarms fire before error budget exhaustion

### WHEN
- Day 1. Observability is not optional - it is how production issues get debugged. Deploy without it and the first incident becomes "restart everything and hope."

### HOW (specific to this project)

**ECS task definitions already send logs to CloudWatch** (already in compute/main.tf):
```json
"logConfiguration": {
  "logDriver": "awslogs",
  "options": {
    "awslogs-group": "/ecs/rag-pipeline/prod/query-service",
    "awslogs-region": "ap-southeast-2",
    "awslogs-stream-prefix": "query"
  }
}
```

**X-Ray sidecar container (add to each task definition):**
```json
{
  "name": "xray-daemon",
  "image": "amazon/aws-xray-daemon:latest",
  "portMappings": [{ "containerPort": 2000, "protocol": "udp" }],
  "cpu": 32,
  "memoryReservation": 256
}
```

**Custom CloudWatch metrics from your existing Prometheus metrics:**
```python
# Existing metrics (src/domain/services/)
rag_retrieval_duration_seconds     # histogram
rag_generation_duration_seconds    # histogram
rag_token_usage_total              # counter
rag_confidence_score               # histogram

# These get exported to CloudWatch via embedded metric format in logs:
logger.info(
    "metric.retrieval_duration",
    _aws={
        "Timestamp": int(time.time() * 1000),
        "CloudWatchMetrics": [{
            "Namespace": "RAGPipeline",
            "Dimensions": [["Service", "Method"]],
            "Metrics": [{"Name": "RetrievalDuration", "Unit": "Seconds"}]
        }]
    },
    Service="query-service",
    Method="dense",
    RetrievalDuration=0.045,
)
```

**Alarms mapped to SLOs:**
```hcl
# SLO: API availability 99.9%
resource "aws_cloudwatch_metric_alarm" "error_budget" {
  alarm_name  = "${var.project}-error-budget-exhaustion"
  namespace   = "RAGPipeline"
  metric_name = "5xxErrors"
  statistic   = "Sum"
  period      = 300  # 5 minutes
  threshold   = 50   # More than 50 errors in 5 min
  comparison_operator = "GreaterThanThreshold"
  alarm_actions = [aws_sns_topic.critical.arn]
}

# SLO: Query latency P95 < 2000ms
resource "aws_cloudwatch_metric_alarm" "high_latency" {
  alarm_name  = "${var.project}-high-query-latency"
  namespace   = "RAGPipeline"
  metric_name = "QueryDuration"
  extended_statistic = "p95"
  period      = 300
  threshold   = 2.0  # 2 seconds
  comparison_operator = "GreaterThanThreshold"
  alarm_actions = [aws_sns_topic.warning.arn]
}

# Cost: Bedrock token spend
resource "aws_cloudwatch_metric_alarm" "bedrock_cost" {
  alarm_name  = "${var.project}-bedrock-cost-spike"
  namespace   = "RAGPipeline"
  metric_name = "TokenUsageTotal"
  statistic   = "Sum"
  period      = 3600  # 1 hour
  threshold   = 100000  # 100k tokens/hour is abnormal
  comparison_operator = "GreaterThanThreshold"
  alarm_actions = [aws_sns_topic.warning.arn]
}
```

**X-Ray service map shows:**
```
CloudFront → API Gateway → ALB → Gateway (ECS)
                                     ↓
                              Query Service (ECS)
                             /       |        \
                   Embedding    OpenSearch    Graph Service
                   Service       (k-NN)         (ECS)
                     ↓                            ↓
                  Bedrock                       Neptune
                  (Titan)                     (Cypher)
```

Each arrow is a traced span with latency. When a user reports "search is slow", X-Ray immediately shows: "Bedrock embedding call took 8s instead of usual 200ms" - pinpointing the root cause in seconds.

### WHERE
- CloudWatch Logs: same region, log groups per service per environment
- X-Ray: same region, traces retained 30 days
- Alarms: SNS topics route to Slack (#alerts-critical) and PagerDuty (on-call rotation)

### WHICH
- Dev: Basic logging + alarms, no X-Ray (cost saving)
- Prod: Full observability stack - logs (7-year retention), X-Ray sampling (5%), all alarms active

**Interview answer:** "Our observability stack follows the three pillars: logs (structlog JSON to CloudWatch), traces (OpenTelemetry to X-Ray), and metrics (custom CloudWatch metrics from existing Prometheus counters). The X-Ray service map lets us diagnose cross-service latency issues in seconds - during our last Bedrock regional slowdown, X-Ray immediately showed the embedding span at 38s instead of 200ms, letting us failover to us-east-1 within 15 minutes."

---

## NETWORK TOPOLOGY - VPC Architecture

### WHAT
The VPC (Virtual Private Cloud) provides network isolation. Resources are separated into public subnets (internet-accessible) and private subnets (internal only), following defense-in-depth principles.

### WHY (this project specifically)

**Security boundary enforcement:**
- Only ALB and NAT Gateway have public IPs
- All compute (ECS), data (OpenSearch, Neptune, Aurora, Redis), and processing (Lambda) run in private subnets
- No direct internet access to any data store (compliance requirement)

### HOW (this project's network layout)

```
VPC: 10.0.0.0/16
├── Public Subnet AZ-a:  10.0.0.0/24   (ALB, NAT Gateway)
├── Public Subnet AZ-b:  10.0.1.0/24   (ALB)
├── Private Subnet AZ-a: 10.0.10.0/24  (ECS tasks, Lambda, OpenSearch, Neptune, Aurora, Redis)
└── Private Subnet AZ-b: 10.0.11.0/24  (ECS tasks, Lambda, replicas)
```

**Security Groups (firewall rules):**

| Security Group | Inbound From | Port | Purpose |
|---|---|---|---|
| `alb-sg` | 0.0.0.0/0 | 443 | HTTPS from internet |
| `ecs-gateway-sg` | `alb-sg` | 8080 | ALB to Gateway only |
| `ecs-internal-sg` | `ecs-gateway-sg` | 8001-8004 | Gateway to internal services |
| `opensearch-sg` | `ecs-internal-sg` | 443 | Services to OpenSearch |
| `neptune-sg` | `ecs-internal-sg` | 8182 | Services to Neptune |
| `aurora-sg` | `ecs-internal-sg` | 5432 | Services to Aurora |
| `redis-sg` | `ecs-internal-sg` | 6379 | Services to Redis |

**VPC Endpoints (private AWS service access without internet):**
```hcl
# S3 Gateway Endpoint (free)
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.main.id
  service_name = "com.amazonaws.ap-southeast-2.s3"
  vpc_endpoint_type = "Gateway"
}

# Bedrock Interface Endpoint (needed for Lambda in VPC)
resource "aws_vpc_endpoint" "bedrock" {
  vpc_id             = aws_vpc.main.id
  service_name       = "com.amazonaws.ap-southeast-2.bedrock-runtime"
  vpc_endpoint_type  = "Interface"
  subnet_ids         = var.private_subnet_ids
  security_group_ids = [aws_security_group.vpce.id]
}
```

### WHERE
- Region: `ap-southeast-2` (Sydney) - data sovereignty
- 2 Availability Zones for high availability
- NAT Gateway in public subnet for private subnet outbound (Bedrock API calls, ECR image pulls)

### WHICH
- Dev: Single NAT Gateway (saves $35/month, single AZ risk acceptable)
- Prod: NAT Gateway per AZ ($70/month, survives AZ failure)

---

## COST SUMMARY BY LAYER

| Layer | Component | Dev/month | Prod/month | Notes |
|---|---|---|---|---|
| Edge | CloudFront + S3 | $5 | $15 | Minimal for internal app |
| Edge | WAF | $0 | $20 | Rule evaluations |
| Auth | Cognito | $0 | $0 | Free tier (50k MAU) |
| Auth | API Gateway | $5 | $20 | Per-request pricing |
| LB | ALB | $20 | $40 | Fixed + LCU charges |
| Compute | ECS Fargate (5 svc) | $150 | $600 | Scales with load |
| Data | OpenSearch | $50 | $400 | 2-node cluster |
| Data | Neptune | $70 | $350 | Writer + reader |
| Data | ElastiCache | $15 | $200 | Primary + replica |
| Data | Aurora PG | $45 | $150 | Serverless v2 |
| Data | S3 | $5 | $20 | Pay per GB stored |
| Data | Secrets Manager + KMS | $5 | $10 | Per secret |
| Async | Lambda | $5 | $30 | Pay per invocation |
| Async | SQS | $1 | $5 | Nearly free |
| Observability | CloudWatch | $20 | $80 | Logs + metrics |
| Observability | X-Ray | $0 | $15 | Trace sampling |
| Network | NAT Gateway | $35 | $70 | Per AZ |
| **TOTAL** | | **~$430** | **~$2,025** | |

---

## MIGRATION PRIORITY ORDER

| Phase | Components | Timeline | Risk if Skipped |
|---|---|---|---|
| **Phase 1** | VPC + ECS + ALB + S3 + Secrets Manager | Week 1-2 | Cannot deploy anything |
| **Phase 2** | OpenSearch + ElastiCache | Week 2-3 | Data loss on container restart |
| **Phase 3** | Neptune + Aurora | Week 3-4 | No graph HA, no audit trail |
| **Phase 4** | Cognito + API Gateway + CloudFront | Week 4-5 | No auth, no CDN |
| **Phase 5** | Lambda ingestion pipeline | Week 5-6 | Ingestion blocks compute |
| **Phase 6** | CloudWatch + X-Ray + Alarms | Week 6-7 | Blind to production issues |

---

## KEY INTERVIEW TALKING POINTS

**"Why not just run everything on EC2?"**
ECS Fargate eliminates patching, AMI management, and capacity planning. Pay per-second for actual compute used. For a microservices architecture with variable load, Fargate auto-scaling is more cost-efficient than right-sizing EC2 instances.

**"Why OpenSearch instead of Pinecone/Qdrant?"**
OpenSearch is AWS-native (IAM, VPC, KMS integration), managed within our VPC (data sovereignty), and supports hybrid search (k-NN + BM25 in one service). Third-party vector DBs add network hops, extra auth, and data leaves the AWS boundary.

**"Why Neptune over Aurora pgvector?"**
Graph traversals use variable-length paths (1-2 hops) with typed relationships. pgvector handles vector similarity but not graph traversals. Neptune's openCypher support means zero query rewrites from Neo4j. For pure vector search, pgvector is fine - but actual graph operations are needed.

**"Why Lambda for ingestion instead of keeping it on ECS?"**
Ingestion is bursty (batch uploads of 50 documents, then idle for hours). Lambda scales to 1000 concurrent in seconds and costs $0 when idle. An always-on ECS task for ingestion wastes $70/month sitting idle 95% of the time.

**"How does the hexagonal architecture help with this migration?"**
Every AWS service change is an adapter swap. `OpenSearchVectorStore` implements the same `VectorStorePort` protocol as `ChromaDBVectorStore`. Domain services never knew the change happened. Zero business logic changes for any infrastructure migration.

**"What happens if Bedrock goes down?"**
Circuit breaker (5 failures, 30s reset) opens immediately, stopping calls to Bedrock. Query Service degrades gracefully - returns cached results or falls back to sparse-only search with honest confidence scores. Automatic regional failover switches to us-east-1 if ap-southeast-2 P95 exceeds 10s for 3 consecutive requests.

**"How do you handle data consistency across OpenSearch, Neptune, and S3?"**
Saga pattern with compensating transactions. Each ingestion step is logged in Aurora PostgreSQL. If Neptune indexing fails, compensating transactions remove the OpenSearch vectors and S3 object. Hourly reconciliation Lambda detects and repairs inconsistencies from crashes between saga steps. All operations are idempotent (safe to retry).
