"""Security headers middleware using the secure library."""

from __future__ import annotations

import secure
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


# Configure security headers per requirements:
# - Strict-Transport-Security: max-age=31536000; includeSubDomains
# - X-Frame-Options: DENY
# - X-Content-Type-Options: nosniff
# - Referrer-Policy: no-referrer
# - X-XSS-Protection: 1; mode=block
# - Content-Security-Policy: script-src 'self'
secure_headers = secure.Secure(
    hsts=secure.StrictTransportSecurity().max_age(31536000).include_subdomains(),
    xfo=secure.XFrameOptions().deny(),
    xcto=secure.XContentTypeOptions(),
    referrer=secure.ReferrerPolicy().no_referrer(),
    custom=[secure.CustomHeader("X-XSS-Protection", "1; mode=block")],
    csp=secure.ContentSecurityPolicy()
    .default_src("'self'")
    .script_src("'self'")
    .style_src("'self'", "'unsafe-inline'")
    .img_src("'self'", "data:")
    .connect_src("'self'")
    .font_src("'self'")
    .frame_ancestors("'none'"),
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Apply security headers to every response using the secure library."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        secure_headers.set_headers(response)
        return response
