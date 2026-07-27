---
inclusion: fileMatch
fileMatchPattern: infrastructure/docker/**
---

# Docker Compose Guide

## Service Startup Dependency Order

Services must start in dependency order to ensure downstream services are ready before callers attempt connections.

```
Layer 1 (Infrastructure):  Neo4j, ChromaDB
Layer 2 (Leaf Services):   Graph Service, Embedding Service
Layer 3 (Mid Services):    Ingestion Service, Query Service
Layer 4 (Entry Point):     API Gateway
Layer 5 (Client):          Frontend (Vite dev server)
```

In `docker-compose.yml`, use `depends_on` with health check conditions:

```yaml
services:
  neo4j:
    image: neo4j:5-community
    healthcheck:
      test: ["CMD", "neo4j", "status"]
      interval: 10s
      timeout: 5s
      retries: 5

  graph-service:
    build: ../../services/graph-service
    depends_on:
      neo4j:
        condition: service_healthy

  embedding-service:
    build: ../../services/embedding-service
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
      interval: 10s
      timeout: 5s
      retries: 3

  ingestion-service:
    build: ../../services/ingestion-service
    depends_on:
      graph-service:
        condition: service_healthy
      embedding-service:
        condition: service_healthy

  query-service:
    build: ../../services/query-service
    depends_on:
      graph-service:
        condition: service_healthy
      embedding-service:
        condition: service_healthy

  gateway:
    build: ../../services/gateway
    depends_on:
      query-service:
        condition: service_healthy
      ingestion-service:
        condition: service_healthy
    ports:
      - "8080:8000"

  frontend:
    build: ../../frontend
    depends_on:
      gateway:
        condition: service_healthy
    ports:
      - "5173:5173"
```

## Health Check Configuration Patterns

### FastAPI Services

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 15s
```

- Use `/health/live` for Docker health checks (always 200 if process is running)
- Use `/health/ready` for load balancer readiness (confirms dependencies connected)
- `start_period` gives the service time to initialize before health checks begin

### Neo4j

```yaml
healthcheck:
  test: ["CMD", "neo4j", "status"]
  interval: 10s
  timeout: 5s
  retries: 5
  start_period: 30s
```

Neo4j takes longer to start — give it 30s before checking.

### ChromaDB

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]
  interval: 10s
  timeout: 5s
  retries: 3
  start_period: 10s
```

## Environment Variable Conventions

### Naming Pattern
```
<SERVICE>_<SETTING> for inter-service URLs
<DEPENDENCY>_<SETTING> for infrastructure connections
```

### Standard Variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `GRAPH_SERVICE_URL` | Query, Ingestion | `http://graph-service:8000` | Graph Service base URL |
| `EMBEDDING_SERVICE_URL` | Query, Ingestion | `http://embedding-service:8000` | Embedding Service base URL |
| `QUERY_SERVICE_URL` | Gateway | `http://query-service:8000` | Query Service base URL |
| `INGESTION_SERVICE_URL` | Gateway | `http://ingestion-service:8000` | Ingestion Service base URL |
| `NEO4J_URI` | Graph Service | `bolt://neo4j:7687` | Neo4j Bolt connection URI |
| `NEO4J_USER` | Graph Service | `neo4j` | Neo4j username |
| `NEO4J_PASSWORD` | Graph Service | `password` | Neo4j password (dev only) |
| `CHROMADB_HOST` | Ingestion | `chromadb` | ChromaDB hostname |
| `CHROMADB_PORT` | Ingestion | `8000` | ChromaDB port |
| `AWS_REGION` | Embedding | `us-east-1` | AWS Bedrock region |
| `API_KEYS` | Gateway | `dev-key-001` | Comma-separated valid API keys |
| `LOG_LEVEL` | All | `INFO` | Structlog log level |
| `VITE_API_BASE_URL` | Frontend | `http://localhost:8080` | API Gateway URL for frontend |
| `VITE_API_KEY` | Frontend | `dev-key-001` | API key for frontend requests |

### Environment File Pattern

```yaml
services:
  graph-service:
    env_file:
      - .env.common
      - .env.graph-service
    environment:
      - SERVICE_NAME=graph-service
```

Use `.env.common` for shared variables (LOG_LEVEL, etc.) and per-service `.env.<service>` for service-specific config.

## Volume Mount Patterns

### Development Volumes (hot reload)

```yaml
services:
  graph-service:
    volumes:
      - ../../services/graph-service/src:/app/src:ro
      - ../../libs/domain-models/src:/libs/domain-models/src:ro
      - ../../libs/service-client/src:/libs/service-client/src:ro
```

Mount source code as read-only for hot reload with `uvicorn --reload`.

### Data Persistence Volumes

```yaml
volumes:
  neo4j-data:
  chromadb-data:

services:
  neo4j:
    volumes:
      - neo4j-data:/data
      - neo4j-data:/logs
  chromadb:
    volumes:
      - chromadb-data:/chroma/chroma
```

Named volumes persist between `docker compose down` and `docker compose up`.

### Sample Data Volume

```yaml
services:
  ingestion-service:
    volumes:
      - ../../data/sample_documents:/data/sample_documents:ro
```

## DNS-Based Service Discovery

Docker Compose creates a default network where services resolve by container name:

```yaml
networks:
  default:
    name: legislation-rag-network
```

Service hostnames equal service names in `docker-compose.yml`:
- `graph-service` resolves to Graph Service container
- `embedding-service` resolves to Embedding Service container
- `neo4j` resolves to Neo4j container
- `chromadb` resolves to ChromaDB container

All services bind to port 8000 internally. Only the gateway and frontend expose external ports.

## Debugging Across Containers

### View logs for a specific service
```bash
docker compose logs -f graph-service
```

### Filter by correlation ID across all services
```bash
docker compose logs | grep "correlation_id.*<uuid>"
```

### Execute commands inside a running container
```bash
docker compose exec graph-service python -c "import httpx; print('ok')"
```

### Restart a single service (preserves others)
```bash
docker compose restart embedding-service
```

### Rebuild and restart after code changes
```bash
docker compose up --build graph-service -d
```

### Check service health status
```bash
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
```
