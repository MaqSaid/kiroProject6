# Multi-stage build for Query Service
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir hatchling

# Copy shared libraries first for caching
COPY libs/domain-models/ /build/libs/domain-models/
COPY libs/service-client/ /build/libs/service-client/

# Install shared libraries
RUN pip install --no-cache-dir /build/libs/domain-models/ \
    && pip install --no-cache-dir /build/libs/service-client/

# Copy service source and install
COPY services/query-service/pyproject.toml /build/service/pyproject.toml
COPY services/query-service/src/ /build/service/src/

RUN pip install --no-cache-dir /build/service/

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy service source
COPY services/query-service/src/ /app/src/

RUN chown -R appuser:appuser /app

USER appuser

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    SERVICE_NAME=query-service

EXPOSE 8001

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; r = urllib.request.urlopen('http://localhost:8001/health'); assert r.status == 200"

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8001"]