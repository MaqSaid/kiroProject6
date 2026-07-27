"""Health check models for service status reporting."""

from pydantic import BaseModel, Field


class ServiceHealthStatus(BaseModel):
    """Health status of a single service."""

    service: str = Field(..., min_length=1, description="Name of the service")
    status: str = Field(..., min_length=1, description="Health status (e.g., 'healthy', 'unhealthy')")
    latency_ms: float | None = Field(
        default=None, ge=0.0, description="Response latency in milliseconds"
    )


class AggregatedHealthResponse(BaseModel):
    """Aggregated health status across all services."""

    status: str = Field(
        ..., min_length=1, description="Overall system status (e.g., 'healthy', 'degraded')"
    )
    services: list[ServiceHealthStatus] = Field(
        default_factory=list, description="Individual service health statuses"
    )
