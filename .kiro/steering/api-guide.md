---
inclusion: fileMatch
fileMatchPattern: "src/api/**"
---

# API Layer Guide

## Middleware Stack (order matters)

1. **Correlation ID** — generates UUID, attaches to request state, includes in response headers
2. **Request Validation** — validates against OpenAPI schema, returns 422 on failure
3. **Authentication** — validates JWT, extracts user identity and roles (skips /health, /ready)
4. **Rate Limiting** — per-user and per-role limits, returns 429 with Retry-After
5. **Global Error Handler** — catches all exceptions, maps to `ErrorResponse`

## Route Handler Pattern

```python
@router.post("/v1/<resource>", response_model=<ResponseModel>)
async def handler(
    request: <RequestModel>,
    user: AuthenticatedUser = Depends(get_current_user),
    service: <DomainService> = Depends(get_service),
    correlation_id: str = Depends(get_correlation_id),
) -> <ResponseModel>:
    # 1. Extract validated input from request model
    # 2. Call domain service with correlation_id
    # 3. Map domain result to response model
    # 4. Return response
    ...
```

## Error Response Contract

All errors (4xx and 5xx) MUST return:
```json
{
  "error_code": "VALIDATION_ERROR",
  "message": "Human-readable description",
  "correlation_id": "uuid-format-string",
  "details": {}
}
```

## Authentication

- OAuth2/OIDC JWT validation
- Three roles: `reader` (query), `editor` (ingest), `admin` (all)
- Role hierarchy: admin > editor > reader
- 403 Forbidden on unauthorized access (never 404 to hide resource existence)
- Exempt endpoints: `GET /health`, `GET /ready`

## Rate Limiting

- Per-user limits stored in Redis
- Return `429 Too Many Requests` with `Retry-After` header (seconds)
- Different limits per role (admin > editor > reader)

## Dependency Injection

Use FastAPI's `Depends()` for all service dependencies:
- Services created in lifespan event, stored in `app.state`
- Dependency functions in `src/api/dependencies/`
- Never instantiate services inside route handlers
