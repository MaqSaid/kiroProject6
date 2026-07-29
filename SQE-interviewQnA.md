# Senior Quality Engineer (SQE) — Technical Interview Questions & Answers
## Based on the Legislation RAG Platform

---

## Testing Strategy Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   LEGISLATION RAG PLATFORM                               │
│                   Testing Strategy Overview                              │
└─────────────────────────────────────────────────────────────────────────┘

                          ┌───────────────────┐
                          │   Developer Push  │
                          │  (Feature Branch) │
                          └────────┬──────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 1: LINT                                                           │
│  [Ruff] [mypy] ← Static analysis + type checking                        │
│  Gate: No critical lint errors                                           │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 2: TEST (Unit + Property-Based)                                   │
│  [pytest unit/]              [Hypothesis property/]                       │
│   • test_chunking             • test_prop_confidence (Prop 17-18)        │
│   • test_auth_middleware      • test_prop_retrieval  (Prop 10-12)        │
│   • test_normalizers          • test_prop_chunkers   (Prop 4-8)          │
│   • test_security             • test_prop_api        (Prop 19-20)        │
│                                                                          │
│  Gate: 100% pass, coverage >= 80%                                        │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 3: SECURITY SCAN                                                  │
│  [Bandit/SAST] [pip-audit/SCA] [Trivy/Container] [Checkov/IaC]          │
│  [Gitleaks/Secrets]                                                      │
│  Gate: 0 critical/high findings                                          │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 4: CONTRACT TEST                                                  │
│  [Schemathesis] OpenAPI schema fuzzing                                   │
│   • Validates shared domain-models (libs/domain-models/)                 │
│   • Stateful chains: ingest -> query -> verify citations                 │
│  Gate: 0 schema divergence                                               │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 5: INTEGRATION TEST (after deploy to dev)                         │
│  [pytest -m integration] Docker Compose                                  │
│   • Circuit breaker fallback (graph down -> dense+sparse)                │
│   • All methods fail -> graceful empty response                          │
│   • Reranker failure -> fused results without reranking                  │
│   • Embedding failure -> empty results (no crash)                        │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 6: E2E TESTS                                                      │
│                                                                          │
│  [Playwright - UI E2E]           [pytest E2E - API cross-service]        │
│   • Chat flow (30s timeout)       • Ingest -> Query -> Verify citations  │
│   • Citation click -> scroll      • Graph traversal across services      │
│   • Fallback display              • Fallback when no docs ingested       │
│   • Document upload + validation  • Circuit breaker E2E behavior         │
│   • Mobile viewport (44px)        • Correlation ID in failures           │
│   • WCAG 2.0 AA accessibility                                            │
│   • Keyboard navigation                                                  │
│                                                                          │
│  Timeout: 60s per test (Requirement 9.6)                                 │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 7: DAST + PERFORMANCE                                             │
│  [OWASP ZAP]                  [k6 Performance]                           │
│   • LLM output injection       • 20 golden queries as payload            │
│   • File upload bypass          • p50 < 500ms, p95 < 2s, p99 < 5s       │
│   • Rate limit bypass           • 99.9% availability SLO                 │
│   • Auth bypass                                                          │
│  Gate: p95 < 2s for /v1/agents/ask                                       │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 8: EVALUATION (Golden Dataset Regression)                         │
│  [tests/evaluation/] 20 Q&A pairs from data/golden_dataset.json          │
│   • Correctness, Faithfulness, Retrieval relevance, Citation accuracy    │
│  Gate: < 5% regression on any metric                                     │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  STAGE 9: ACCESSIBILITY                                                  │
│  [axe-core] Automated WCAG 2.0 AA checks                                │
│   • Contrast (4.5:1 normal, 3:1 large), ARIA, keyboard, touch targets   │
└─────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
                          ┌───────────────────┐
                          │   DEPLOY PROD     │
                          │ (Manual + 1 Appr) │
                          └───────────────────┘


═══════════════════════════════════════════════════════════════════════════

                      TEST PYRAMID (This Project)

                               ╱╲
                              ╱  ╲        E2E / Playwright / Perf (slow)
                             ╱────╲
                            ╱      ╲      Integration (service boundaries)
                           ╱────────╲
                          ╱          ╲    Contract (Schemathesis)
                         ╱────────────╲
                        ╱              ╲  Property-Based (Hypothesis, 200 ex)
                       ╱────────────────╲
                      ╱                  ╲ Unit (pytest, fast, isolated)
                     ╱════════════════════╲

═══════════════════════════════════════════════════════════════════════════

                 MICROSERVICES TEST BOUNDARIES

  ┌──────────┐       ┌──────────────┐       ┌──────────────┐
  │ Frontend │─E2E──▶│  API Gateway │─E2E──▶│Query Service │
  │(Playwright)      │              │       │              │
  └──────────┘       └──────┬───────┘       └──────┬───────┘
                            │                      │
                     Contract Tests          ┌─────┴──────┐
                            │                │            │
                     ┌──────▼───────┐  ┌─────▼────┐ ┌────▼─────┐
                     │  Ingestion   │  │  Graph   │ │ Embedding│
                     │  Service     │  │  Service │ │  Service │
                     └──────┬───────┘  └────┬─────┘ └────┬─────┘
                            │               │            │
                     ┌──────▼───────┐ ┌─────▼────┐ ┌────▼─────┐
                     │   ChromaDB   │ │  Neo4j   │ │  Bedrock │
                     └──────────────┘ └──────────┘ └──────────┘

  Each service: Unit + Property tests (internal)
  Between services: Contract tests (Schemathesis)
  Across all: E2E tests (Playwright + pytest)
  Resilience: Integration tests (circuit breaker fakes)
```

---

## SECTION 1: Playwright E2E Testing (20 Questions)

---

### Q1: How would you structure Playwright E2E tests for the chat interface?

**A:** Tests target the core user flows using role-based locators that map to the actual components.

**Project example** (from `frontend-guide.md`):
```typescript
import { test, expect } from '@playwright/test';

test('submitting a question shows an answer', async ({ page }) => {
  await page.goto('/');
  const input = page.getByRole('textbox', { name: /ask a question/i });
  await input.fill('What are the speed limits under Section 45?');
  await page.getByRole('button', { name: /send/i }).click();
  const answer = page.getByRole('article').first();
  await expect(answer).toBeVisible({ timeout: 30_000 });
  await expect(answer).not.toBeEmpty();
});
```

The `QueryInput.tsx` renders `aria-label="Ask a question"` and the `SourcePanel.tsx`
uses `data-testid="source-chunk-${citationIndex}"` — designed for Playwright selectors.

---

### Q2: How do you handle the 30-second API timeout in Playwright tests?

**A:** The project's `api-client.ts` already enforces 30s:

```typescript
ask(query: string): Promise<AgentAskResponse> {
  return request<AgentAskResponse>('/v1/agents/ask', {
    method: 'POST',
    body: JSON.stringify({ query }),
    timeoutMs: 30_000,
  });
}
```

In Playwright, use targeted timeouts on specific assertions only:
```typescript
await expect(answer).toBeVisible({ timeout: 30_000 });
```

Per requirement 9.6, each test has a 60s max. Use `page.route()` to mock responses for
fast deterministic tests, keeping only 1-2 full integration tests with live services.

---

### Q3: How would you test citation marker click navigation?

**A:** The `AnswerText.tsx` renders citations as buttons with testids. `ChatPage.tsx` handles scrolling via `scrollIntoView`. The `SourcePanel.tsx` highlights the target chunk with `aria-current="true"`.

**Playwright test:**
```typescript
test('clicking citation scrolls source panel to chunk', async ({ page }) => {
  const citation = page.getByTestId('citation-marker-1');
  await citation.click();
  const sourceChunk = page.getByTestId('source-chunk-1');
  await expect(sourceChunk).toBeInViewport();
  await expect(sourceChunk).toHaveAttribute('aria-current', 'true');
});
```

---

### Q4: How do you test confidence score color-coding?

**A:** `ConfidenceIndicator.tsx` maps scores to colors (green >= 0.7, amber >= 0.4, red < 0.4). The component renders `aria-label` with the label and percentage.

**Playwright test:**
```typescript
test('high confidence shows green indicator', async ({ page }) => {
  // Mock API response with composite: 0.85
  const indicator = page.getByTestId('confidence-indicator');
  await expect(indicator).toHaveAttribute('aria-label', /High confidence: 85%/);
});
```

---

### Q5: How do you test the fallback display when confidence is low?

**A:** `FallbackDisplay.tsx` renders when `is_fallback: true` with `data-testid="fallback-display"` and `role="status"`. It shows found topics, not-found topics, and suggested documents.

**Playwright test:**
```typescript
test('fallback response shows topics and suggestions', async ({ page }) => {
  await page.route('**/v1/agents/ask', route => route.fulfill({
    body: JSON.stringify({
      is_fallback: true,
      fallback_info: { found_topics: ['speed limits'], not_found_topics: ['parking'], suggested_documents: ['Transport Act 2023.md'] },
      confidence_scores: { composite: 0.2 }, answer: '', citations: [], source_chunks: []
    })
  }));
  // Submit query...
  await expect(page.getByTestId('fallback-display')).toBeVisible();
  await expect(page.getByTestId('fallback-display')).toContainText('Unable to provide a confident answer');
  await expect(page.getByTestId('fallback-found-topics')).toContainText('speed limits');
  await expect(page.getByTestId('fallback-not-found-topics')).toContainText('parking');
});
```

---

### Q6: How do you test whitespace-only input rejection?

**A:** `QueryInput.tsx` rejects whitespace-only input without sending a request:
```tsx
if (!query.trim()) {
  return { error: null, submitted: false };
}
```

**Playwright test:**
```typescript
test('whitespace-only input does not send request', async ({ page }) => {
  let requestMade = false;
  await page.route('**/v1/agents/ask', route => { requestMade = true; route.abort(); });
  await page.goto('/');
  const input = page.getByRole('textbox', { name: /ask a question/i });
  await input.fill('   \t  ');
  await page.getByRole('button', { name: /send/i }).click();
  // Wait a moment to confirm no request was fired
  await page.waitForTimeout(500);
  expect(requestMade).toBe(false);
});
```

---

### Q7: How do you test the document upload file validation?

**A:** `DocumentUpload.tsx` validates client-side before any network request:
```typescript
const ALLOWED_EXTENSIONS = ['.txt', '.md', '.html', '.pdf'];
const MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024; // 50 MB
```

**Playwright test:**
```typescript
test('rejects file with invalid extension', async ({ page }) => {
  await page.goto('/documents');
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles({
    name: 'script.exe', mimeType: 'application/octet-stream', buffer: Buffer.from('x')
  });
  const error = page.locator('#upload-validation-error');
  await expect(error).toContainText('Invalid file type ".exe"');
});
```

---

### Q8: How do you test the document list sorting by date?

**A:** `DocumentList.tsx` sorts by `ingestion_date` descending:
```tsx
const sortedDocuments = useMemo(() => {
  return [...documents].sort(
    (a, b) => new Date(b.ingestion_date).getTime() - new Date(a.ingestion_date).getTime()
  );
}, [data?.documents]);
```

**Playwright test:**
```typescript
test('documents are sorted by date descending', async ({ page }) => {
  await page.route('**/v1/documents', route => route.fulfill({
    body: JSON.stringify({ documents: [
      { document_id: '1', filename: 'old.md', format: 'md', ingestion_date: '2024-01-01T00:00:00Z', chunks_produced: 5 },
      { document_id: '2', filename: 'new.md', format: 'md', ingestion_date: '2024-06-01T00:00:00Z', chunks_produced: 8 },
    ]})
  }));
  await page.goto('/documents');
  const items = page.getByRole('listitem');
  await expect(items.first()).toContainText('new.md');
  await expect(items.last()).toContainText('old.md');
});
```

---

### Q9: How do you test the skip-to-content accessibility link?

**A:** `Layout.tsx` has a skip link:
```tsx
<a href="#main-content"
   className="sr-only focus:not-sr-only focus:absolute ...">
  Skip to main content
</a>
```

**Playwright test:**
```typescript
test('skip link becomes visible on focus and navigates to main', async ({ page }) => {
  await page.goto('/');
  await page.keyboard.press('Tab');
  const skipLink = page.getByRole('link', { name: 'Skip to main content' });
  await expect(skipLink).toBeVisible();
  await skipLink.click();
  await expect(page.locator('#main-content')).toBeFocused();
});
```

---

### Q10: How do you test keyboard navigation through the chat interface?

**A:** The project enforces keyboard accessibility: Tab through elements, Enter to submit, visible focus rings (`focus-visible:ring-2`).

**Playwright test:**
```typescript
test('full keyboard flow: tab to input, type, enter to submit', async ({ page }) => {
  await page.goto('/');
  // Tab to the input field
  await page.keyboard.press('Tab'); // Skip link
  await page.keyboard.press('Tab'); // Nav: Chat
  await page.keyboard.press('Tab'); // Nav: Documents
  await page.keyboard.press('Tab'); // Query input
  const input = page.getByRole('textbox', { name: /ask a question/i });
  await expect(input).toBeFocused();
  await page.keyboard.type('What is Section 12?');
  await page.keyboard.press('Enter');
  // Verify submission happened (loading state appears)
  await expect(page.getByRole('status')).toContainText('Thinking');
});
```

---

### Q11: How do you test the error state with retry functionality?

**A:** `ErrorState.tsx` renders with `role="alert"` and a retry button with `aria-label="Retry the failed request"`.

**Playwright test:**
```typescript
test('network error shows error alert with retry button', async ({ page }) => {
  await page.route('**/v1/agents/ask', route => route.abort());
  await page.goto('/');
  const input = page.getByRole('textbox', { name: /ask a question/i });
  await input.fill('What is Section 12?');
  await page.getByRole('button', { name: /send/i }).click();
  const errorAlert = page.getByRole('alert');
  await expect(errorAlert).toBeVisible({ timeout: 35_000 });
  await expect(errorAlert).toContainText('Something went wrong');
  const retryBtn = page.getByRole('button', { name: /retry/i });
  await expect(retryBtn).toBeVisible();
});
```

---

### Q12: How do you test the source panel renders section headings?

**A:** `SourcePanel.tsx` renders each chunk with `data-testid="source-heading-N"`:
```tsx
<span data-testid={`source-heading-${citationIndex}`}>
  {chunk.section_heading || 'Untitled Section'}
</span>
```

**Playwright test (requirement 9.4):**
```typescript
test('source panel shows at least one chunk with visible section heading', async ({ page }) => {
  // Submit query, wait for answer...
  const sourcePanel = page.getByTestId('source-panel');
  await expect(sourcePanel).toBeVisible();
  const heading = page.getByTestId('source-heading-1');
  await expect(heading).toBeVisible();
  await expect(heading).not.toBeEmpty();
});
```

---

### Q13: How do you test the retrieval method badges in the source panel?

**A:** `SourcePanel.tsx` shows method badges (dense/sparse/graph) with testids:
```tsx
<span data-testid={`source-method-${citationIndex}`}
      aria-label={`Retrieval method: ${chunk.retrieval_method}`}>
  {chunk.retrieval_method}
</span>
```

**Playwright test:**
```typescript
test('source chunks display retrieval method badges', async ({ page }) => {
  await page.route('**/v1/agents/ask', route => route.fulfill({
    body: JSON.stringify({
      source_chunks: [
        { chunk_id: '1', text: 'content', section_heading: 'S45', score: 0.9, retrieval_method: 'dense' },
        { chunk_id: '2', text: 'content', section_heading: 'S12', score: 0.7, retrieval_method: 'graph' },
      ],
      answer: 'Answer [1]', citations: [], confidence_scores: { composite: 0.8 }, is_fallback: false
    })
  }));
  // Submit query...
  await expect(page.getByTestId('source-method-1')).toHaveText('dense');
  await expect(page.getByTestId('source-method-2')).toHaveText('graph');
});
```

---

### Q14: How do you test the conversation history ARIA live region?

**A:** `ConversationHistory.tsx` is an ARIA log:
```tsx
<div role="log" aria-live="polite" aria-atomic="false"
     aria-relevant="additions" aria-label="Conversation history">
```

**Playwright test:**
```typescript
test('conversation history is announced to screen readers', async ({ page }) => {
  await page.goto('/');
  const log = page.getByRole('log', { name: 'Conversation history' });
  await expect(log).toBeVisible();
  await expect(log).toHaveAttribute('aria-live', 'polite');
  await expect(log).toHaveAttribute('aria-relevant', 'additions');
});
```

---

### Q15: How do you test focus management after answer arrives?

**A:** `MessageBubble.tsx` moves focus to assistant responses:
```tsx
useEffect(() => {
  if (message.role === 'assistant' && !message.pending && articleRef.current) {
    articleRef.current.focus();
  }
}, [message.role, message.pending]);
```

**Playwright test:**
```typescript
test('focus moves to answer article after response arrives', async ({ page }) => {
  await page.goto('/');
  const input = page.getByRole('textbox', { name: /ask a question/i });
  await input.fill('What is Section 45?');
  await page.getByRole('button', { name: /send/i }).click();
  const answer = page.getByRole('article', { name: /assistant response/i }).first();
  await expect(answer).toBeVisible({ timeout: 30_000 });
  await expect(answer).toBeFocused();
});
```

---

### Q16: How do you test the loading state (pending message)?

**A:** `MessageBubble.tsx` renders a spinner with `aria-busy="true"` and `role="status"`:
```tsx
{message.pending && (
  <div aria-busy="true" role="status">
    <span>Thinking...</span>
  </div>
)}
```

**Playwright test:**
```typescript
test('shows thinking indicator while waiting for response', async ({ page }) => {
  // Delay the API response
  await page.route('**/v1/agents/ask', async route => {
    await new Promise(r => setTimeout(r, 3000));
    route.fulfill({ body: JSON.stringify({ answer: 'test', ... }) });
  });
  await page.goto('/');
  const input = page.getByRole('textbox', { name: /ask a question/i });
  await input.fill('test');
  await page.getByRole('button', { name: /send/i }).click();
  await expect(page.getByRole('status')).toContainText('Thinking');
});
```

---

### Q17: How do you test the navigation between Chat and Documents views?

**A:** `Layout.tsx` has NavLinks with active states:
```tsx
<NavLink to="/" ...>Chat</NavLink>
<NavLink to="/documents" ...>Documents</NavLink>
```

**Playwright test:**
```typescript
test('navigate between chat and documents', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('region', { name: 'Chat' })).toBeVisible();
  await page.getByRole('link', { name: 'Documents' }).click();
  await expect(page.getByRole('region', { name: 'Document management' })).toBeVisible();
  await page.getByRole('link', { name: 'Chat' }).click();
  await expect(page.getByRole('region', { name: 'Chat' })).toBeVisible();
});
```

---

### Q18: How do you test mobile viewport responsive behavior?

**A:** Project uses TailwindCSS responsive breakpoints (`sm:`, `md:`, `lg:`) and 44px touch targets.

**Playwright test:**
```typescript
test('mobile viewport maintains touch targets', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 }); // iPhone SE
  await page.goto('/');
  const sendButton = page.getByRole('button', { name: /send/i });
  const box = await sendButton.boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(44);
  expect(box!.height).toBeGreaterThanOrEqual(44);
});
```

---

### Q19: How do you test the confidence score progress bars?

**A:** `ConfidenceScore.tsx` renders progress bars with ARIA:
```tsx
<div role="progressbar" aria-valuenow={percentage}
     aria-valuemin={0} aria-valuemax={100}
     aria-label={`${label}: ${percentage}%`}>
```

**Playwright test:**
```typescript
test('confidence breakdown shows all four dimensions', async ({ page }) => {
  // Mock response with known scores...
  const scores = page.getByTestId('confidence-scores');
  await expect(scores).toBeVisible();
  await expect(page.getByRole('progressbar', { name: /Retrieval: 80%/ })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: /Citation Coverage: 60%/ })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: /Completeness: 70%/ })).toBeVisible();
  await expect(page.getByRole('progressbar', { name: /Composite: 72%/ })).toBeVisible();
});
```

---

### Q20: How do you test the document upload retry without re-selecting the file?

**A:** `DocumentUpload.tsx` keeps `selectedFile` in state and re-uses it on retry:
```tsx
const handleRetry = useCallback(() => {
  if (selectedFile) {
    reset();
    mutate(selectedFile);  // Re-uses the stored file
  }
}, [selectedFile, mutate, reset]);
```

**Playwright test (requirement 3.6):**
```typescript
test('retry upload reuses previously selected file', async ({ page }) => {
  let attempts = 0;
  await page.route('**/v1/ingest', route => {
    attempts++;
    if (attempts === 1) route.abort(); // First attempt fails
    else route.fulfill({ body: JSON.stringify({ document_id: '123', chunks_produced: 10 }) });
  });
  await page.goto('/documents');
  const fileInput = page.locator('input[type="file"]');
  await fileInput.setInputFiles('data/sample_documents/transport_act.md');
  // First attempt fails
  await expect(page.getByRole('alert')).toContainText('Upload failed');
  // Click retry — no file picker needed
  await page.getByRole('button', { name: /retry upload/i }).click();
  // Second attempt succeeds
  await expect(page.getByRole('status')).toContainText('uploaded successfully');
  expect(attempts).toBe(2);
});
```

---

## SECTION 2: Other SQE Tools (15 Questions)

---

### Q21: How would you use Schemathesis for contract testing?

**A:** The project has shared Pydantic models in `libs/domain-models/` and TypeScript types in `frontend/src/types/api.ts`:

```typescript
export interface AgentAskResponse {
  answer: string;
  citations: Citation[];
  confidence_scores: ConfidenceScores;
  source_chunks: SourceChunk[];
  is_fallback: boolean;
  fallback_info: FallbackInfo | null;
}
```

Run: `schemathesis run http://localhost:8080/openapi.json --stateful=links --checks all`

Stateful mode chains: `POST /v1/ingest` then `POST /v1/agents/ask` to verify citations reference the ingested document.

---

### Q22: How would you test circuit breaker degraded behavior?

**A:** From `tests/integration/test_degraded_mode.py`:

```python
@pytest.mark.integration
def test_graph_unavailable_returns_dense_plus_sparse():
    service = RetrievalService(
        vector_store=WorkingVectorStore(),
        sparse_index=WorkingSparseIndex(),
        graph_store=FailingGraphStore(),
        reranker=FakeReranker(), ...
    )
    results = asyncio.run(service.retrieve("test query", top_k=5))
    assert len(results) >= 1

@pytest.mark.integration
def test_all_search_methods_fail_returns_empty():
    service = RetrievalService(
        vector_store=FailingVectorStore(),
        sparse_index=FailingSparseIndex(),
        graph_store=FailingGraphStore(), ...
    )
    results = asyncio.run(service.retrieve("test query", top_k=5))
    assert results == []
```

Uses fakes (not mocks) per testing guide convention.

---

### Q23: How do you use Hypothesis for confidence scoring?

**A:** From `tests/property/test_prop_confidence.py`:

```python
@pytest.mark.property
@settings(max_examples=200)
@given(retrieval=confidence_float, citation=confidence_float, completeness=confidence_float)
def test_confidence_composite_is_weighted_sum(retrieval, citation, completeness):
    expected = min(1.0, 0.35 * retrieval + 0.40 * citation + 0.25 * completeness)
    score = ConfidenceScore(retrieval_confidence=retrieval, citation_coverage=citation,
                            answer_completeness=completeness, composite=expected)
    actual = 0.35 * score.retrieval_confidence + 0.40 * score.citation_coverage + 0.25 * score.answer_completeness
    assert abs(score.composite - min(1.0, actual)) < 1e-6
```

---

### Q24: How do you test the RRF fusion algorithm?

**A:** From `tests/property/test_prop_retrieval.py`:

```python
@pytest.mark.property
@given(n=st.integers(min_value=2, max_value=15))
def test_rrf_output_sorted_descending(n):
    dense = make_ranked_list(n, "dense")
    sparse = make_ranked_list(n, "sparse")
    weights = RRFWeights(dense=0.5, sparse=0.2, graph=0.3)
    service = RetrievalService.__new__(RetrievalService)
    fused = service._reciprocal_rank_fusion(dense, sparse, [], weights)
    scores = [sc.score for sc in fused]
    for i in range(len(scores) - 1):
        assert scores[i] >= scores[i + 1]
```

---

### Q25: What performance test scenarios would you write?

**A:** Based on SLO definitions (p50 < 500ms, p95 < 2s, 99.9% availability). Use the 20 golden Q&A pairs from `data/golden_dataset.json` as payloads:

```javascript
export const options = {
  thresholds: {
    'http_req_duration': ['p(50)<500', 'p(95)<2000', 'p(99)<5000'],
    'http_req_failed': ['rate<0.001'],
  },
};
```

---

### Q26: How do you handle test data in microservices?

**A:** Seed through API Gateway `/v1/ingest` (never directly into databases). Project has 8 sample documents and 20 golden Q&A pairs. Clean up via `DELETE /documents/{id}`.

---

### Q27: How would you integrate OWASP ZAP?

**A:** Focus areas: LLM output injection (Req 7.7 mandates sanitization), file upload bypass, rate limiting (60 req/min), auth bypass (X-API-Key required). CI stage: `scan-dast`.

---

### Q28: How do you test correlation ID propagation?

**A:** `conftest.py` provides: `correlation_id = "test-correlation-id-00000000"`. Verify it appears in error responses per requirement 9.5.

---

### Q29: How is the test pyramid structured?

**A:** `tests/property/` (Hypothesis PBT), `tests/unit/` (pytest), `tests/integration/` (Docker Compose), `tests/contract/` (Schemathesis), `tests/e2e/` (Playwright + API), `tests/evaluation/` (golden dataset regression).

---

### Q30: How do you test the reranker selection?

**A:** From `tests/property/test_prop_retrieval.py`:

```python
@given(n=st.integers(5, 20), top_n=st.integers(3, 5))
def test_reranker_selects_top_n_highest_scored(n, top_n):
    candidates = [make_scored_chunk(0.1 + i * 0.04, "fused") for i in range(n)]
    reranked = asyncio.run(fake_rerank("test", candidates, top_n))
    assert len(reranked) == top_n
    for i in range(len(reranked) - 1):
        assert reranked[i].score >= reranked[i + 1].score
```

---

### Q31: How do you test embedding service failure?

**A:** From `tests/integration/test_degraded_mode.py`:

```python
def test_embedding_failure_returns_empty():
    class FailingEmbedding:
        async def embed_single(self, text): raise ConnectionError("down")
    service = RetrievalService(embedding_port=FailingEmbedding(), ...)
    results = asyncio.run(service.retrieve("test", top_k=5))
    assert results == []
```

---

### Q32: How are Hypothesis profiles configured?

**A:** From `tests/conftest.py`:

```python
settings.register_profile("ci", max_examples=200, deadline=None)
settings.register_profile("dev", max_examples=50, deadline=None)
settings.register_profile("debug", max_examples=10, deadline=None)
```

Run with: `pytest --hypothesis-profile=ci tests/property/`

---

### Q33: What is the CI pipeline gate strategy?

**A:** From `.gitlab-ci.yml`: lint -> test -> security-scan -> build -> deploy-dev -> integration-test -> deploy-prod (manual gate). Gates: 100% unit pass, 80% coverage, 0 critical SAST, 0 critical CVEs.

---

### Q34: How do you test citation verification status?

**A:** `CitationList.tsx` color-codes: verified=green, partial=amber, unsupported=red. Test by mocking response with different statuses and verifying badge text.

---

### Q35: How do you test the optimistic UI pattern?

**A:** `ChatPage.tsx` uses `useOptimistic`. Test: submit query, verify user message appears immediately (before server response), then verify "Thinking..." indicator while waiting.

---

*End of Interview Q&A*
