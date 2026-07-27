"""Proxy routing logic: path matching to service forwarding."""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from fastapi import Request
from fastapi.responses import JSONResponse, Response

logger = structlog.get_logger(__name__)

# Route configuration: prefix -> (service_url_attr, timeout)
ROUTE_TABLE: list[dict[str, Any]] = [
    {
        "prefixes": ["/v1/ask", "/v1/agents/ask"],
        "service": "query",
        "timeout_attr": "query_timeout",
    },
    {
        "prefixes": ["/v1/ingest", "/v1/documents"],
        "service": "ingestion",
        "timeout_attr": "ingestion_timeout",
    },
]


def match_route(path: str) -> dict[str, Any] | None:
    """Match a request path to its target service configuration."""
    for route in ROUTE_TABLE:
        for prefix in route["prefixes"]:
            if path == prefix or path.startswith(prefix + "/"):
                return route
    return None


async def proxy_request(
    request: Request,
    target_base_url: str,
    timeout: float,
    correlation_id: str,
) -> Response:
    """Forward a request to the target service and return its response.

    Returns HTTP 504 on timeout, HTTP 502 on connection error.
    """
    # Build the target URL preserving path and query string
    target_url = f"{target_base_url.rstrip('/')}{request.url.path}"
    if request.url.query:
        target_url += f"?{request.url.query}"

    # Build headers to forward (filter out hop-by-hop headers)
    headers = dict(request.headers)
    # Remove host header - let httpx set it correctly
    headers.pop("host", None)
    # Inject correlation ID
    headers["X-Correlation-ID"] = correlation_id

    # Read the request body
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                content=body,
            )

        # Return the downstream response to the client
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get("content-type"),
        )

    except httpx.TimeoutException:
        logger.error(
            "proxy_timeout",
            target_url=target_url,
            timeout=timeout,
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=504,
            content={
                "error_code": "GATEWAY_TIMEOUT",
                "message": f"Request to downstream service timed out after {int(timeout)} seconds",
                "correlation_id": correlation_id,
            },
        )
    except (httpx.ConnectError, httpx.RequestError) as exc:
        logger.error(
            "proxy_connection_error",
            target_url=target_url,
            error=str(exc),
            correlation_id=correlation_id,
        )
        return JSONResponse(
            status_code=502,
            content={
                "error_code": "BAD_GATEWAY",
                "message": "Downstream service is unreachable",
                "correlation_id": correlation_id,
            },
        )
