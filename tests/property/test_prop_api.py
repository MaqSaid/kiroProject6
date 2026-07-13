"""Property tests for API validation and error responses.

# Feature: production-rag-pipeline-hybrid-search, Properties 19-20
"""

from __future__ import annotations

import re
import uuid

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from src.api.models import AskRequest, ErrorResponse

UUID_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


@pytest.mark.property
@settings(max_examples=100)
@given(query=st.text(min_size=0, max_size=0))
def test_empty_query_rejected(query: str) -> None:
    """Property 19a: Empty query violates min_length=1."""
    with pytest.raises(Exception):
        AskRequest(query=query)


@pytest.mark.property
@settings(max_examples=50)
@given(query=st.text(min_size=2001, max_size=3000))
def test_oversized_query_rejected(query: str) -> None:
    """Property 19b: Query > 2000 chars rejected."""
    with pytest.raises(Exception):
        AskRequest(query=query)


@pytest.mark.property
@settings(max_examples=100)
@given(top_k=st.integers(min_value=-100, max_value=0))
def test_invalid_top_k_rejected(top_k: int) -> None:
    """Property 19c: top_k <= 0 rejected."""
    with pytest.raises(Exception):
        AskRequest(query="valid query", top_k=top_k)


@pytest.mark.property
@settings(max_examples=100)
@given(top_k=st.integers(min_value=51, max_value=200))
def test_excessive_top_k_rejected(top_k: int) -> None:
    """Property 19d: top_k > 50 rejected."""
    with pytest.raises(Exception):
        AskRequest(query="valid query", top_k=top_k)


@pytest.mark.property
@settings(max_examples=100)
@given(
    query=st.text(min_size=1, max_size=100, alphabet=st.characters(whitelist_categories=("L", "N", "Z"))),
    top_k=st.integers(min_value=1, max_value=50),
)
def test_valid_requests_accepted(query: str, top_k: int) -> None:
    """Property 19e: Valid requests pass."""
    req = AskRequest(query=query, top_k=top_k)
    assert req.query == query
    assert req.top_k == top_k


@pytest.mark.property
@settings(max_examples=100)
@given(
    error_code=st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=("L", "N"))),
    message=st.text(min_size=1, max_size=200),
)
def test_error_response_has_required_fields(error_code: str, message: str) -> None:
    """Property 20a: Error response has error_code, message, correlation_id (UUID)."""
    correlation_id = str(uuid.uuid4())
    error = ErrorResponse(error_code=error_code, message=message, correlation_id=correlation_id)
    assert len(error.error_code) > 0
    assert len(error.message) > 0
    assert UUID_PATTERN.match(error.correlation_id)


@pytest.mark.property
@settings(max_examples=50)
@given(details=st.dictionaries(
    keys=st.text(min_size=1, max_size=20, alphabet=st.characters(whitelist_categories=("L",))),
    values=st.text(min_size=0, max_size=50),
    max_size=5,
))
def test_error_response_accepts_details(details: dict) -> None:
    """Property 20b: Error response accepts arbitrary details dict."""
    error = ErrorResponse(
        error_code="TEST", message="msg", correlation_id=str(uuid.uuid4()), details=details
    )
    assert error.details == details
