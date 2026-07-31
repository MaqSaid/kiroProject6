# Senior Quality Engineer (SQE) — Technical Interview Q&A (GCP Edition)
## Based on the Legislation RAG Platform — Google Cloud Platform Stack

---

## Testing Strategy Flow (GCP CI/CD)

```
Developer Push (Feature Branch)
    |
STAGE 1: LINT [Ruff + mypy strict]
    |
STAGE 2: TEST (Unit + Property-Based) [pytest + Hypothesis 200 examples]
    |
STAGE 3: SECURITY SCAN [Bandit, pip-audit, Trivy, Checkov, Gitleaks]
    |
STAGE 4: CONTRACT TEST [Schemathesis OpenAPI fuzzing]
    |
STAGE 5: BUILD + PUSH [Docker -> Artifact Registry]
    |
STAGE 6: DEPLOY DEV [Terraform -> Cloud Run revision]
    |
STAGE 7: INTEGRATION TEST [pytest against Cloud Run dev]
    |
STAGE 8: E2E [Playwright UI + pytest API]
    |
STAGE 9: EVALUATION [Vertex AI Evaluation + custom golden dataset]
    |
STAGE 10: PERFORMANCE [k6 load test, p95 < 5s gate]
    |
DEPLOY PROD (Manual + 1 Approval, Cloud Run traffic split)
```

---

## SECTION 1: Playwright E2E Testing

### Q1: How do you structure E2E tests against Cloud Run?

**A:** Tests target the Cloud Run dev environment. Gateway service handles auth and routing identically to production.

```typescript
import { test, expect } from '@playwright/test';

test('submitting a question shows a cited answer', async ({ page }) => {
  await page.goto(process.env.FRONTEND_URL || 'http://localhost:5173');
  const input = page.getByRole('textbox', { name: /ask a question/i });
  await input.fill('What are the KYC requirements for high-risk customers?');
  await page.getByRole('button', { name: /send/i }).click();
  const answer = page.getByRole('article').first();
  await expect(answer).toBeVisible({ timeout: 30_000 });
  await expect(answer).toContainText('[1]');
});
```

### Q2: How do you handle Cloud Run cold starts in E2E?

**A:** Pre-warm in CI before Playwright runs:
```typescript
test.beforeAll(async ({ request }) => {
  await request.get(`${process.env.API_URL}/health/ready`);
});
```
First test uses 45s timeout (cold start buffer), subsequent use 30s.

### Q3: How do you test accessibility for streaming chat?

**A:** Cloud-agnostic WCAG 2.0 AA validation:
- `aria-live="polite"` on conversation area
- `aria-busy="true"` during streaming
- `role="log"` on history, `role="doc-noteref"` on citations
- axe-core scan: zero violations
- 44x44px touch targets, 4.5:1 contrast ratio

---

## SECTION 2: Property-Based Testing

### Q4: How do property tests validate RRF fusion?

**A:** Pure Python logic — fully cloud-agnostic:

```python
from hypothesis import given, strategies as st

@given(scores=st.lists(st.floats(0.0, 1.0), min_size=1, max_size=20))
def test_rrf_output_monotonically_decreasing(scores):
    fused = rrf_fusion(scores)
    result_scores = [c.score for c in fused]
    assert result_scores == sorted(result_scores, reverse=True)

@given(composite=st.floats(0.0, 1.0))
def test_confidence_bounds(composite):
    assert 0.0 <= composite <= 1.0
```

### Q5: How do you test the Vertex AI embedding adapter?

**A:** Via port interface with in-memory fake (no Vertex AI calls in unit tests):

```python
@given(texts=st.lists(st.text(min_size=1, max_size=500), min_size=1, max_size=10))
def test_embedding_preserves_count(texts):
    fake = FakeVertexEmbeddingAdapter(dimensions=768)
    vectors = asyncio.run(fake.embed(texts))
    assert len(vectors) == len(texts)
    assert all(len(v) == 768 for v in vectors)
```

---

## SECTION 3: Contract Testing

### Q6: How do you run Schemathesis against Cloud Run?

**A:**
```bash
schemathesis run \
  --url https://query-service-dev-xxxx.a.run.app/openapi.json \
  --header "Authorization: Bearer $TOKEN" \
  --hypothesis-max-examples=200 \
  --stateful=links
```
Validates: no 500s, response matches Pydantic schema, stateful chains work (ingest -> query -> verify).

### Q7: How do you test A2A agent contracts?

**A:** Contract tests verify inter-agent HTTP schemas match shared domain-models:
```python
@pytest.mark.contract
async def test_embedding_service_returns_768_dims():
    response = await client.post("/embed", json={"text": "test"})
    assert response.status_code == 200
    assert len(response.json()["vector"]) == 768
```

---

## SECTION 4: LLM Evaluation (Vertex AI)

### Q8: How do you evaluate RAG quality?

**A:** Dual approach:

**Vertex AI Evaluation API:**
```python
from vertexai.evaluation import EvalTask
eval_task = EvalTask(
    dataset=golden_dataset,
    metrics=["groundedness", "relevance", "coherence", "safety"],
)
results = eval_task.evaluate()
```

**Custom harness:** ROUGE-L, Entity Recall, MRR, Confidence Calibration (ECE).

### Q9: How does LLM-as-Judge work for citation verification?

**A:** Gemini Flash reviews each claim-source pair:
```python
@tool
def verify_claim_pair(claim: str, source_text: str) -> str:
    """Returns: verified, unsupported, or partial"""
    # Gemini Flash classifies faithfulness
```
If >20% unsupported -> fallback. Citation coverage = 40% of composite score.

### Q10: How do Pydantic guardrails enforce quality?

**A:** Every boundary is schema-enforced:
```python
class ConfidenceScore(BaseModel):
    retrieval_confidence: float = Field(ge=0.0, le=1.0)
    citation_coverage: float = Field(ge=0.0, le=1.0)
    answer_completeness: float = Field(ge=0.0, le=1.0)
    composite: float = Field(ge=0.0, le=1.0)
```
Malformed LLM output is rejected before reaching the user.

---

## SECTION 5: Observability (Cloud Operations)

### Q11: How do you trace requests across Cloud Run services?

**A:** OpenTelemetry propagates trace context:
```python
with tracer.start_as_current_span("retrieval.dense_search") as span:
    span.set_attribute("query.length", len(query))
    results = await vector_search.search(vector, top_k)
    span.set_attribute("result.count", len(results))
```
Cloud Trace shows full waterfall: gateway -> query-service -> embedding/graph/vector search -> generation -> verification.

### Q12: How do you monitor per-agent token cost?

**A:** Prometheus counters exported to Cloud Monitoring:
```python
token_counter = Counter('rag_token_usage_total', 'Tokens', ['model', 'operation'])
token_counter.labels(model="gemini-flash", operation="verify").inc(usage.total_tokens)
```

### Q13: How do you set SLOs?

**A:** Cloud Monitoring SLO: 99.9% of requests complete within 5s (P95). Multi-burn-rate alerting on error budget consumption.

---

## SECTION 6: Integration Testing

### Q14: Circuit breaker testing?

**A:**
```python
@pytest.mark.integration
async def test_graph_down_graceful_degradation():
    with mock_graph_unavailable():
        response = await client.post("/v1/agents/ask", json={"query": "test"})
    assert response.status_code == 200  # Still answers with dense + sparse
```

### Q15: Vector Search integration?

**A:** Ingest -> wait for indexing (eventual consistency) -> query -> verify retrieved chunks reference ingested document.

---

## SECTION 7: Security Testing

### Q16: Prompt injection testing?

**A:** Parametrized payloads (4 categories) verify either 403 (blocked by Cloud Armor/SecurityService) or safe grounded output with citations.

### Q17: IAM validation?

**A:** Infrastructure tests verify least-privilege: query-service SA has only `aiplatform.user`, not `admin`. No `secretmanager.secretAccessor` on compute SAs.

---

## SECTION 8: Performance Testing

### Q18: How do you load test Cloud Run?

**A:** k6 with golden dataset queries. Thresholds: p95 < 5s, error rate < 1%. CI gate blocks deployment on breach.

### Q19: Auto-scaling verification?

**A:** Monitor `run.googleapis.com/container/instance_count` during load ramp. Verify scaling decisions match configured concurrency limits.

---

## SECTION 9: Continuous Evaluation

### Q20: How do you prevent quality regression?

**A:** CI Stage 9 runs Vertex AI Evaluation against golden dataset. Any metric dropping >5% from baseline blocks deployment:
```python
@pytest.mark.evaluation
def test_no_regression():
    results = eval_task.evaluate()
    for metric, baseline in BASELINES.items():
        assert results[metric] >= baseline - 0.05
```

---

*SQE interview preparation for GCP-native quality engineering: Playwright E2E, Hypothesis properties, Schemathesis contracts, Vertex AI Evaluation, Cloud Trace observability, Cloud Run performance testing.*
