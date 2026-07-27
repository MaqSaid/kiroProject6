---
inclusion: auto
---

# Coding Standards — Production RAG Pipeline

## Python Backend

### Style
- Python 3.11+ with type hints on all function signatures (no `Any` unless unavoidable)
- Use `ruff` for linting and formatting (line length 100)
- Use `mypy` in strict mode for type checking
- Follow PEP 8 naming: `snake_case` for functions/variables, `PascalCase` for classes
- Docstrings on all public classes and functions (Google style)
- Imports sorted: stdlib → third-party → local (enforced by ruff isort)

### Architecture
- Hexagonal architecture: domain logic MUST NOT import from infrastructure
- All external dependencies accessed through Port interfaces (Protocol classes in `src/ports/`)
- Adapters in `src/infrastructure/` implement Port protocols
- Domain services in `src/domain/services/`
- Processing logic in `src/domain/processing/`
- API routes in `src/api/routes/`
- Application orchestration in `src/application/`
- Import rule: `src/domain/` → `src/ports/` is allowed; `src/domain/` → `src/infrastructure/` is FORBIDDEN
- Each adapter module should have a single responsibility (one port per adapter file)

### Dependencies
- Use Pydantic v2 for all data models (BaseModel, not dataclass)
- Use `async/await` for all I/O operations
- Use `uuid.uuid4()` for all entity IDs
- Use `structlog` for structured JSON logging (bind correlation_id early in request lifecycle)
- Use `hypothesis` for property-based tests
- Use `tenacity` for retry decorators (never hand-roll retry loops)
- Use `httpx` over `requests` for async HTTP calls

### Error Handling
- All errors return structured `ErrorResponse` with correlation_id
- Use custom exception hierarchy inheriting from a base `DomainError`
- Never expose stack traces in API responses
- Always log with correlation_id context
- Catch specific exceptions, never bare `except:`
- External call failures → wrap in domain-specific exceptions before propagating

### Security Patterns
- Validate all filenames: reject path traversal (`../`, `..\`), null bytes, control chars
- Sanitize all outputs: strip HTML/JS from generated content before returning
- Parameterize all queries (Cypher, BM25) — no string interpolation
- Token budgets enforced before every LLM/embedding call
- Prompt injection patterns checked on all user inputs before processing

### Testing
- Property tests in `tests/property/` with filename pattern `test_prop_<module>.py`
- Tag property tests: `# Feature: production-rag-pipeline-hybrid-search, Property N: <title>`
- Unit tests in `tests/unit/` mirroring `src/` structure
- Integration tests in `tests/integration/`
- Use `pytest-asyncio` for async test functions
- Minimum 100 examples per property test via `@settings(max_examples=100)`
- Mock external services (LLM, embedding, vector store) in unit tests — never make real API calls
- Use `respx` to mock httpx calls, custom fakes for port implementations
- Every adapter gets an in-memory fake for testing (e.g., `InMemoryVectorStore`)

### Resilience
- All external calls wrapped with circuit breaker (`src/infrastructure/resilience/`)
- Retry with exponential backoff + jitter for transient failures
- Timeouts on all async operations (default 5s for retrieval, 30s for generation)
- Graceful degradation: if one retrieval path fails, proceed with remaining paths

## React Frontend

### Style
- React 19 + TypeScript strict mode (no `any`)
- TailwindCSS for styling (no inline styles, no CSS modules)
- ESLint with `eslint-plugin-jsx-a11y` for accessibility
- Functional components only, no class components
- Custom hooks for shared logic (prefix with `use`)
- React Query (`@tanstack/react-query`) for server state management

### React 19 Patterns
- Use `use()` hook for data fetching with Suspense (replaces useEffect + useState loading patterns)
- Use `useActionState` for form submissions and mutations (replaces manual state management)
- Use `useOptimistic` for instant UI feedback before server confirmation
- Use `useFormStatus` for loading/pending states in submit buttons
- Use `ref` as a regular prop (no `forwardRef` needed)
- Wrap async components in `<Suspense fallback={...}>` boundaries
- Prefer server-compatible patterns: actions over event handlers for mutations

### Accessibility (WCAG 2.0 AA)
- Semantic HTML elements with ARIA where native semantics insufficient
- All interactive elements keyboard-accessible with visible focus indicators
- Contrast ratio: 4.5:1 normal text, 3:1 large text
- Touch targets: 44x44px minimum
- Respect `prefers-reduced-motion`
- Error messages programmatically associated with controls via `aria-describedby`
- No keyboard traps — all focus management uses `inert` or focus trap libraries

### Component Patterns
- Props interfaces defined separately from component (exported for testing)
- Loading/error/empty states handled in every data-fetching component
- Use Suspense boundaries for async component loading
- Prefer `useActionState` over `useState` + `useEffect` for form handling
- Components receive `ref` as a regular prop — do not use `forwardRef`

## Infrastructure (Terraform)

- One module per concern: networking, compute, data-stores, secrets, observability, security
- All resources tagged: `project`, `environment`, `managed_by=terraform`
- Use variable validation blocks for inputs
- State stored in S3 with DynamoDB lock table
- Sensitive outputs marked `sensitive = true`

## CI/CD (GitLab)

- Pipeline stages: lint → test → security-scan → build → deploy
- All stages use reusable `.gitlab-ci/` templates
- Security scans block merge on critical/high findings
- Contract tests validate API against OpenAPI spec

## Git
- Conventional commits: `feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `ci:`
- One logical change per commit
- All code must pass linting and type checking before commit
- Branch naming: `feature/<task-id>-short-desc`, `fix/<task-id>-short-desc`
