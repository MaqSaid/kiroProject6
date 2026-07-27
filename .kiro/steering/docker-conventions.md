# Docker & Container Conventions

## Dockerfile Requirements

Every Dockerfile MUST:

1. **Multi-stage build** — Separate builder and runtime stages
2. **Non-root user** — `RUN adduser --disabled-password appuser` + `USER appuser`
3. **Pinned base images** — `python:3.11-slim` not `python:latest`
4. **HEALTHCHECK instruction** — With interval, timeout, start-period
5. **Minimal COPY** — Only required files, use `.dockerignore`
6. **No secrets in layers** — Use build args or runtime env vars

## .dockerignore Template

```
.git
.venv
__pycache__
*.pyc
.pytest_cache
.hypothesis
.mypy_cache
.ruff_cache
node_modules
.env
*.egg-info
dist
build
reports
htmlcov
```

## Docker Compose Conventions

- Service names: kebab-case matching directory names
- Internal ports: 8000 for all Python services
- External port mapping: unique per service (8080, 8001, 8002, etc.)
- Health checks: always use `condition: service_healthy` for depends_on
- Networks: single `rag-network` bridge for inter-service communication
- Volumes: named volumes for persistent data (not bind mounts in prod)

## Image Naming

```
${REGISTRY}/${PROJECT}/${SERVICE}:${TAG}
```

Tags:
- `latest` — never use in production
- `v<semver>` — release versions
- `sha-<commit>` — CI builds for traceability

## Security Scanning

All container images scanned with Trivy before push:
```bash
trivy image --severity CRITICAL,HIGH --exit-code 1 ${IMAGE}
```

Block deployment on CRITICAL findings. Track HIGH findings in backlog.
