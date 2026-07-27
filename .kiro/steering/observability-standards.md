# Observability Standards

## Structured Logging

All logs use structlog with JSON output and consistent fields:

```python
import structlog
logger = structlog.get_logger(__name__)

# Required fields on every log entry (via contextvars):
# - correlation_id: UUID from request
# - service_name: e.g., "ingestion-service"

# Log format: <component>.<operation>.<outcome>
logger.info("retrieval_service.search.success", duration_ms=45.2, result_count=5)
logger.warning("circuit_breaker.opened", target="embedding-service", failures=5)
logger.error("generation_service.llm_call.failed", error="timeout", model="nova-pro")
```

## Metric Naming

Prometheus metrics follow `<namespace>_<subsystem>_<name>_<unit>` pattern:

| Metric | Type | Labels |
|--------|------|--------|
| `rag_retrieval_duration_seconds` | histogram | method={dense,sparse,graph,fused} |
| `rag_rerank_duration_seconds` | histogram | model={cross-encoder} |
| `rag_generation_duration_seconds` | histogram | model={nova-pro,claude} |
| `rag_token_usage_total` | counter | model, operation={embed,generate} |
| `rag_cost_dollars_total` | counter | model, operation |
| `rag_confidence_score` | histogram | dimension={retrieval,citation,completeness,composite} |
| `rag_citation_failure_rate` | gauge | — |
| `rag_ingestion_chunks_total` | counter | strategy={fixed,recursive,semantic} |
| `rag_circuit_breaker_state` | gauge | target, state={closed,open,half_open} |

## Trace Span Conventions

OpenTelemetry spans use `<service>.<operation>` naming:

```python
with tracer.start_as_current_span("retrieval.dense_search") as span:
    span.set_attribute("query.length", len(query))
    span.set_attribute("top_k", top_k)
    results = await vector_store.search(query_vector, top_k)
    span.set_attribute("result.count", len(results))
```

Standard span attributes:
- `correlation_id`: request correlation UUID
- `user.id`: authenticated user identifier
- `query.length`: input query character count
- `result.count`: number of results returned
- `duration_ms`: operation duration

## SLO Definitions

| SLI | Target | Measurement |
|-----|--------|-------------|
| API availability | 99.9% | successful responses / total requests |
| Query latency p50 | < 500ms | histogram percentile |
| Query latency p95 | < 2000ms | histogram percentile |
| Query latency p99 | < 5000ms | histogram percentile |
| Ingestion throughput | > 10 docs/min | counter rate |
| Retrieval accuracy | > 0.8 MRR | evaluation suite |

## Alert Rules

```yaml
# Critical: Error budget exhaustion
- alert: ErrorBudgetExhausted
  expr: 1 - (sum(rate(http_requests_total{code=~"2.."}[30d])) / sum(rate(http_requests_total[30d]))) > 0.001
  for: 5m

# Warning: High latency
- alert: HighQueryLatency
  expr: histogram_quantile(0.95, rate(rag_retrieval_duration_seconds_bucket[5m])) > 2.0
  for: 10m

# Critical: Circuit breaker open
- alert: CircuitBreakerOpen
  expr: rag_circuit_breaker_state{state="open"} == 1
  for: 1m
```
