---
inclusion: fileMatch
fileMatchPattern: "infrastructure/**,Dockerfile*,docker-compose*,.gitlab-ci*"
---

# Deployment Guide

## Environment Tiers

| Environment | Agent Tier | Vector Store | Graph Store | Cache | Infra |
|-------------|-----------|--------------|-------------|-------|-------|
| local | lite | ChromaDB (container) | Neo4j (container) | Redis (container) | docker-compose |
| dev | lite | ChromaDB (ECS) | Neo4j (ECS) | ElastiCache | Terraform |
| staging | pro | Qdrant (managed) | Neptune | ElastiCache | Terraform |
| production | pro | Qdrant (managed) | Neptune | ElastiCache | Terraform |

## Environment Variables by Stage

### Local Development
```env
RAG_AGENT_REGION=us-east-1
RAG_AGENT_TIER=lite
RAG_AGENT_TEMPERATURE=0.1
RAG_AGENT_MAX_TOKENS=2048
CHROMADB_HOST=localhost
CHROMADB_PORT=8000
NEO4J_URI=bolt://localhost:7687
REDIS_URL=redis://localhost:6379
```

### Production
```env
RAG_AGENT_REGION=us-east-1
RAG_AGENT_TIER=pro
RAG_GENERATION_TIER=pro
RAG_AGENT_MAX_TOKENS=4096
CHROMADB_HOST=qdrant.internal.example.com
NEO4J_URI=bolt://neptune-endpoint:8182
REDIS_URL=redis://elasticache-endpoint:6379
```

## Docker Build

Multi-stage build, non-root user, health check endpoint.

## CI/CD Pipeline Stages

```
lint -> unit-test -> property-test -> build -> security-scan -> integration-test -> deploy-dev -> eval-suite -> deploy-staging -> deploy-prod
```

## Terraform Module Structure

```
infrastructure/
  modules/
    networking/    - VPC, subnets, security groups
    compute/       - ECS Fargate, ALB, autoscaling
    data-stores/   - Qdrant, Neptune, ElastiCache, S3
    secrets/       - Secrets Manager, IAM policies
    observability/ - OpenTelemetry Collector, CloudWatch, Grafana
    security/      - WAF, rate limiting
  environments/
    dev/
    staging/
    prod/
  backend.tf       - S3 state + DynamoDB lock
```

## Rollback Strategy

1. ECS: Blue/green deployment, rollback = point ALB back to previous task def
2. Database migrations: Always backward-compatible, no destructive changes
3. Terraform: terraform plan as merge gate, manual approval for prod
4. Feature flags: Use environment variables to toggle new features
