---
inclusion: fileMatch
fileMatchPattern: services/gateway/**
---

# Security Middleware Guide

## fastapi-guard Configuration

The API Gateway uses `fastapi-guard` for automated penetration detection. It inspects request paths, query parameters, and headers for known attack patterns.

### Installation

```toml
# services/gateway/pyproject.toml
[project]
dependencies = [
    "fastapi>=0.110.0",
    "fastapi-guard>=1.0.0",
    "secure>=0.3.0",
    "httpx>=0.27.0",
]
```

### Middleware Setup

```python
from guard.middleware import GuardMiddleware

app = FastAPI(lifespan=lifespan)

# Add guard middleware BEFORE other middlewares
# It detects: SQL injection, XSS, path traversal, command injection
app.add_middleware(
    GuardMiddleware,
    blocked_response_status=403,
    blocked_response_message="Forbidden: Potential attack detected",
    enable_ip_blocking=False,       # Not needed in dev (behind gateway)
    enable_penetration_detection=True,
    enable_rate_limiting=False,     # We handle rate limiting separately
)
```

Detected patterns (returns HTTP 403):
- SQL injection: `' OR 1=1`, `UNION SELECT`, `DROP TABLE`
- XSS payloads: `<script>`, `javascript:`, `onerror=`
- Path traversal: `../`, `..\`, `%2e%2e/`
- Command injection: `; rm`, `| cat`, `` `whoami` ``

## Secure Library Headers Configuration

The `secure` library provides security headers on every response:

```python
import secure

# Configure security headers
secure_headers = secure.Secure(
    hsts=secure.StrictTransportSecurity()
        .max_age(31536000)
        .include_subdomains(),
    xfo=secure.XFrameOptions().deny(),
    xcto=secure.XContentTypeOptions(),
    referrer=secure.ReferrerPolicy().no_referrer(),
    xxp=secure.XXSSProtection().set("1; mode=block"),
    csp=secure.ContentSecurityPolicy()
        .default_src("'self'")
        .script_src("'self'")
        .style_src("'self'", "'unsafe-inline'")
        .img_src("'self'", "data:")
        .connect_src("'self'"),
)

@app.middleware("http")
async def set_secure_headers(request: Request, call_next):
    response = await call_next(request)
    secure_headers.framework.fastapi(response)
    return response
```

Headers set on every response:
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- `X-XSS-Protection: 1; mode=block`
- `Content-Security-Policy: default-src 'self'; script-src 'self'; ...`

## HTTPBearer API Key Validation Pattern

```python
from fastapi import Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Validate X-API-Key header against configured key set."""

    def __init__(self, app, valid_keys: set[str]):
        super().__init__(app)
        self.valid_keys = valid_keys

    async def dispatch(self, request: Request, call_next):
        # Skip auth for health endpoints
        if request.url.path.startswith("/health"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key")
        if not api_key:
            raise HTTPException(
                status_code=401,
                detail="Missing X-API-Key header",
            )
        if api_key not in self.valid_keys:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key",
            )

        # Log key identifier (first 8 chars), never the full key
        logger.info("request_authenticated", key_prefix=api_key[:8])
        return await call_next(request)
```

Key rules:
- Validate against a configured set (env var or secrets manager)
- Never log the full API key value — only a prefix for identification
- Skip authentication on health check endpoints
- Return HTTP 401 for missing or invalid keys

## Rate Limiting Token Bucket Implementation

```python
import time
from collections import defaultdict

class TokenBucket:
    """In-memory token bucket rate limiter (dev environment)."""

    def __init__(self, rate: int = 60, period: float = 60.0):
        self.rate = rate          # tokens per period
        self.period = period      # period in seconds
        self.buckets: dict[str, dict] = defaultdict(
            lambda: {"tokens": rate, "last_refill": time.monotonic()}
        )

    def allow(self, key: str) -> bool:
        bucket = self.buckets[key]
        now = time.monotonic()
        elapsed = now - bucket["last_refill"]

        # Refill tokens based on elapsed time
        refill = int(elapsed * self.rate / self.period)
        if refill > 0:
            bucket["tokens"] = min(self.rate, bucket["tokens"] + refill)
            bucket["last_refill"] = now

        if bucket["tokens"] > 0:
            bucket["tokens"] -= 1
            return True
        return False


class RateLimitMiddleware(BaseHTTPMiddleware):
    """60 requests per minute per API key."""

    def __init__(self, app, limiter: TokenBucket):
        super().__init__(app)
        self.limiter = limiter

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health endpoints
        if request.url.path.startswith("/health"):
            return await call_next(request)

        api_key = request.headers.get("X-API-Key", "anonymous")
        if not self.limiter.allow(api_key):
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Try again later.",
            )
        return await call_next(request)
```

Configuration:
- 60 requests per minute per API key
- Token bucket refills continuously (not fixed window)
- In dev: in-memory storage (resets on service restart)
- In prod: AWS API Gateway handles rate limiting

## CORS Configuration (Dev Environment)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
    ],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type", "X-API-Key", "X-Correlation-ID"],
    expose_headers=["X-Correlation-ID"],
)
```

## CSP Header Configuration

Content Security Policy restricts what resources the browser can load:

```python
csp = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "connect-src 'self'; "
    "font-src 'self'; "
    "frame-ancestors 'none'"
)
```

Key directives:
- `script-src 'self'` — Only scripts from same origin (no CDN, no inline)
- `style-src 'self' 'unsafe-inline'` — Allows TailwindCSS inline styles
- `connect-src 'self'` — API calls only to same origin (frontend proxies to gateway)
- `frame-ancestors 'none'` — Prevents clickjacking (equivalent to X-Frame-Options: DENY)

## Middleware Stack Order

Middleware executes in reverse order of `add_middleware` calls. Register in this order:

```python
# 1. CORS (outermost — must handle preflight before other middleware)
app.add_middleware(CORSMiddleware, ...)

# 2. Security headers (set on every response)
# (applied via @app.middleware("http") decorator)

# 3. Guard (penetration detection — reject attacks early)
app.add_middleware(GuardMiddleware, ...)

# 4. Correlation ID (generate/propagate before auth logs need it)
app.add_middleware(CorrelationIDMiddleware)

# 5. API Key Auth (authenticate before rate limiting)
app.add_middleware(APIKeyAuthMiddleware, valid_keys=keys)

# 6. Rate Limiting (after auth so we rate-limit per authenticated key)
app.add_middleware(RateLimitMiddleware, limiter=bucket)

# 7. Request Logging (innermost — log after all enrichment)
app.add_middleware(RequestLoggingMiddleware)
```
