# Multi-stage build for RAG Pipeline API
# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir hatchling

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY src/ /app/src/
COPY run_agents.py /app/

RUN mkdir -p /app/data/documents /app/data/chroma && chown -R appuser:appuser /app

USER appuser

ENV RAG_AGENT_REGION=us-east-1 \
    RAG_AGENT_TIER=lite \
    RAG_AGENT_TEMPERATURE=0.1 \
    RAG_AGENT_MAX_TOKENS=4096 \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8080/health', timeout=5); assert r.status_code == 200"

CMD ["uvicorn", "src.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
