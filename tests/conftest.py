"""Root conftest.py — shared pytest fixtures and Hypothesis configuration."""

import pytest
from hypothesis import HealthCheck, settings

# Register Hypothesis profiles
settings.register_profile(
    "ci",
    max_examples=200,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
settings.register_profile(
    "dev",
    max_examples=50,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)
settings.register_profile(
    "debug",
    max_examples=10,
    suppress_health_check=[HealthCheck.too_slow],
    deadline=None,
)


@pytest.fixture
def correlation_id() -> str:
    """Provide a test correlation ID."""
    return "test-correlation-id-00000000"
