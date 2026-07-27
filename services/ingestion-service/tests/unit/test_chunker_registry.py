"""Unit tests for ChunkerRegistry auto-selection, explicit selection, and fallback.

Tests cover:
- Auto-select returns legal_hierarchical for "Transport_Act_2024.md"
- Auto-select returns legal_hierarchical for "Road_Regulation.pdf"
- Auto-select returns recursive for "notes.md" (no keyword)
- Auto-select returns recursive for "page.html"
- Auto-select returns fixed_size for "data.txt"
- Auto-select returns fixed_size for "file.xyz" (unknown extension)
- Explicit selection works for registered names
- Explicit selection raises ValueError for unregistered names
- Fallback to fixed_size when legal_hierarchical is unavailable
- registered_strategies returns correct list
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domain.processing.chunker_registry import ChunkerRegistry


class FakeChunker:
    """Fake chunker for testing purposes."""

    def __init__(self, name: str) -> None:
        self.name = name

    def chunk(self, document: Any) -> list[Any]:
        return []


@pytest.fixture
def registry() -> ChunkerRegistry:
    """Create a registry with all four strategies registered and available."""
    reg = ChunkerRegistry()
    reg.register("fixed_size", FakeChunker("fixed_size"), available=True)
    reg.register("recursive", FakeChunker("recursive"), available=True)
    reg.register("semantic", FakeChunker("semantic"), available=True)
    reg.register("legal_hierarchical", FakeChunker("legal_hierarchical"), available=True)
    return reg


class TestAutoSelect:
    """Tests for auto-selection based on file extension and keywords."""

    def test_legal_hierarchical_for_act_md(self, registry: ChunkerRegistry) -> None:
        """Auto-select returns legal_hierarchical for 'Transport_Act_2024.md'."""
        chunker = registry.auto_select("Transport_Act_2024.md")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_legal_hierarchical_for_regulation_pdf(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select returns legal_hierarchical for 'Road_Regulation.pdf'."""
        chunker = registry.auto_select("Road_Regulation.pdf")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_legal_hierarchical_for_rule_md(self, registry: ChunkerRegistry) -> None:
        """Auto-select returns legal_hierarchical for filename with 'Rule'."""
        chunker = registry.auto_select("Business_Rule_2024.md")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_legal_hierarchical_for_policy_pdf(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select returns legal_hierarchical for filename with 'Policy'."""
        chunker = registry.auto_select("Transport_Policy.pdf")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_legal_hierarchical_from_metadata_keyword(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select returns legal_hierarchical when metadata contains keyword."""
        chunker = registry.auto_select(
            "document.md", metadata={"title": "Heavy Vehicle Act 2024"}
        )
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_legal_hierarchical_from_content_preview(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select returns legal_hierarchical when content_preview contains keyword."""
        chunker = registry.auto_select(
            "document.pdf",
            content_preview="This is the Transport Act 2024, Part 3, Division 2.",
        )
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_recursive_for_pdf_without_keywords_in_content(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select returns recursive for .pdf when content has no legislative keywords."""
        chunker = registry.auto_select(
            "report.pdf",
            content_preview="This is a general report about quarterly results.",
        )
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "recursive"

    def test_legal_hierarchical_for_section_keyword(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select detects 'Section' as legislative keyword."""
        chunker = registry.auto_select(
            "document.md",
            content_preview="Section 45 prescribes the penalties.",
        )
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_legal_hierarchical_for_schedule_keyword(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select detects 'Schedule' as legislative keyword."""
        chunker = registry.auto_select(
            "document.pdf",
            content_preview="See Schedule 1 for fee details.",
        )
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_recursive_for_md_without_keyword(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select returns recursive for 'notes.md' (no keyword)."""
        chunker = registry.auto_select("notes.md")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "recursive"

    def test_recursive_for_html(self, registry: ChunkerRegistry) -> None:
        """Auto-select returns recursive for 'page.html'."""
        chunker = registry.auto_select("page.html")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "recursive"

    def test_fixed_size_for_txt(self, registry: ChunkerRegistry) -> None:
        """Auto-select returns fixed_size for 'data.txt'."""
        chunker = registry.auto_select("data.txt")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "fixed_size"

    def test_fixed_size_for_unknown_extension(
        self, registry: ChunkerRegistry
    ) -> None:
        """Auto-select returns fixed_size for 'file.xyz' (unknown extension)."""
        chunker = registry.auto_select("file.xyz")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "fixed_size"

    def test_fixed_size_for_no_extension(self, registry: ChunkerRegistry) -> None:
        """Auto-select returns fixed_size for files without extension."""
        chunker = registry.auto_select("README")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "fixed_size"

    def test_case_insensitive_keyword_detection(
        self, registry: ChunkerRegistry
    ) -> None:
        """Keywords are detected case-insensitively."""
        chunker = registry.auto_select("transport_ACT_2024.pdf")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "legal_hierarchical"

    def test_case_insensitive_extension(self, registry: ChunkerRegistry) -> None:
        """Extension detection is case-insensitive."""
        chunker = registry.auto_select("page.HTML")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "recursive"


class TestExplicitSelection:
    """Tests for explicit strategy selection by name."""

    def test_get_by_name_registered(self, registry: ChunkerRegistry) -> None:
        """Explicit selection works for registered names."""
        chunker = registry.get_by_name("recursive")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "recursive"

    def test_get_by_name_all_strategies(self, registry: ChunkerRegistry) -> None:
        """All registered strategies can be selected by name."""
        for name in ("fixed_size", "recursive", "semantic", "legal_hierarchical"):
            chunker = registry.get_by_name(name)
            assert isinstance(chunker, FakeChunker)
            assert chunker.name == name

    def test_get_by_name_unregistered_raises(
        self, registry: ChunkerRegistry
    ) -> None:
        """Explicit selection raises ValueError for unregistered names."""
        with pytest.raises(ValueError, match="not recognized"):
            registry.get_by_name("nonexistent_strategy")

    def test_get_by_name_error_includes_registered_list(
        self, registry: ChunkerRegistry
    ) -> None:
        """Error message includes the list of registered strategies."""
        with pytest.raises(ValueError, match="Registered strategies"):
            registry.get_by_name("unknown")


class TestFallback:
    """Tests for fallback behavior when strategies are unavailable."""

    def test_fallback_to_fixed_size_when_legal_hierarchical_unavailable(
        self,
    ) -> None:
        """Falls back to fixed_size when legal_hierarchical is unavailable."""
        reg = ChunkerRegistry()
        reg.register("fixed_size", FakeChunker("fixed_size"), available=True)
        reg.register("recursive", FakeChunker("recursive"), available=True)
        reg.register(
            "legal_hierarchical",
            FakeChunker("legal_hierarchical"),
            available=False,
        )

        chunker = reg.auto_select("Transport_Act_2024.md")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "fixed_size"

    def test_fallback_when_recursive_unavailable(self) -> None:
        """Falls back to fixed_size when recursive is unavailable."""
        reg = ChunkerRegistry()
        reg.register("fixed_size", FakeChunker("fixed_size"), available=True)
        reg.register("recursive", FakeChunker("recursive"), available=False)

        chunker = reg.auto_select("page.html")
        assert isinstance(chunker, FakeChunker)
        assert chunker.name == "fixed_size"

    def test_fallback_raises_when_fixed_size_not_registered(self) -> None:
        """Raises ValueError when fixed_size is not registered for fallback."""
        reg = ChunkerRegistry()
        reg.register(
            "legal_hierarchical",
            FakeChunker("legal_hierarchical"),
            available=False,
        )

        with pytest.raises(ValueError, match="Cannot fall back to fixed_size"):
            reg.auto_select("Transport_Act_2024.md")


class TestRegisteredStrategies:
    """Tests for the registered_strategies property."""

    def test_returns_all_registered(self, registry: ChunkerRegistry) -> None:
        """registered_strategies returns correct list with name and availability."""
        strategies = registry.registered_strategies
        assert len(strategies) == 4

        names = [s["name"] for s in strategies]
        assert "fixed_size" in names
        assert "recursive" in names
        assert "semantic" in names
        assert "legal_hierarchical" in names

        for s in strategies:
            assert "name" in s
            assert "available" in s
            assert s["available"] is True

    def test_reflects_availability_status(self) -> None:
        """registered_strategies correctly reflects mixed availability."""
        reg = ChunkerRegistry()
        reg.register("fixed_size", FakeChunker("fixed_size"), available=True)
        reg.register("semantic", FakeChunker("semantic"), available=False)

        strategies = reg.registered_strategies
        assert len(strategies) == 2

        fixed = next(s for s in strategies if s["name"] == "fixed_size")
        semantic = next(s for s in strategies if s["name"] == "semantic")

        assert fixed["available"] is True
        assert semantic["available"] is False

    def test_empty_registry(self) -> None:
        """registered_strategies returns empty list for empty registry."""
        reg = ChunkerRegistry()
        assert reg.registered_strategies == []
