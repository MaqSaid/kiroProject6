---
inclusion: manual
---

# Skill: Microservice Scaffold

## Purpose
Create a new microservice following the project's multi-service architecture with Dockerfile, pyproject.toml, health endpoints, structured logging, and test setup.

## Process

1. **Create service directory** — `services/<service-name>/`
2. **Create pyproject.toml** — Dependencies, test config
3. **Create src/ structure** — app.py, routes, middleware, config
4. **Create Dockerfile** — Multi-stage, non-root, healthcheck
5. **Create tests/ structure** — conftest, unit, property dirs
6. **Wire into docker-compose** — Service definition, networking

## Directory Template

```
services/<service-name>/
├── src/
│   ├── __init__.py
│   ├── app.py
│   ├── config.py
│   ├── api/
│   │   ├── routes.py
│   │   └── health.py
│   ├── middleware/
│   │   ├── correlation_id.py
│   │   └── error_handler.py
│   └── services/
├── tests/
│   ├── conftest.py
│   ├── unit/
│   └── property/
├── Dockerfile
└── pyproject.toml
```

## Dockerfile Template

```dockerfile
FROM python:3.11-slim AS builder
WORKDIR /app
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[prod]"
COPY src/ src/

FROM python:3.11-slim AS runtime
WORKDIR /app
RUN adduser --disabled-password --no-create-home appuser
COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD python -c "import httpx; httpx.get('http://localhost:8000/health/live').raise_for_status()"
CMD ["uvicorn", "src.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

## Service Inventory

| Service | Port | Dependencies | Purpose |
|---------|------|-------------|---------|
| gateway | 8080 | All services | Auth, rate limiting, routing |
| embedding-service | 8001 | Bedrock API | Vector embedding generation |
| graph-service | 8002 | Neo4j | Entity/relationship CRUD + traversal |
| ingestion-service | 8003 | embedding, graph | Document processing pipeline |
| query-service | 8004 | embedding, graph, gateway | Hybrid search + generation |

## Checklist

- [ ] pyproject.toml with pinned dependencies
- [ ] Dockerfile with multi-stage build and non-root user
- [ ] Health endpoints (/health, /health/ready, /health/live)
- [ ] Structured logging with service_name binding
- [ ] Correlation ID middleware
- [ ] Error handler middleware returning structured JSON
- [ ] Config via environment variables (pydantic-settings)
- [ ] Added to docker-compose.yml with healthcheck
- [ ] Test directory with conftest.py
