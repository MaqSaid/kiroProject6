"""Unit tests for legal domain agent prompt loader.

Tests verify:
- ConfigurationError raised for missing prompt files
- ConfigurationError raised for empty prompt files
- Each prompt file loads successfully and contains key domain terms
- Retrieval prompt contains cross-reference and graph traversal terms
- Generation prompt contains citation format and speculative language prohibition
- Citation prompt contains section_heading metadata verification
- Ingestion prompt contains all 7 entity types and all 8 relationship types
- Evaluation prompt contains legislative accuracy and citation precision terms
"""

from unittest.mock import patch

import pytest

from src.agents.exceptions import ConfigurationError
from src.agents.prompt_loader import load_prompt, PROMPTS_DIR


class TestLoadPromptMissingFile:
    """Tests that ConfigurationError is raised for missing prompt files."""

    def test_raises_configuration_error_for_nonexistent_file(self):
        """load_prompt raises ConfigurationError when the prompt file doesn't exist."""
        with pytest.raises(ConfigurationError, match="Prompt file not found"):
            load_prompt("nonexistent_agent")

    def test_error_message_contains_file_path(self):
        """The error message includes the expected file path."""
        with pytest.raises(ConfigurationError) as exc_info:
            load_prompt("fake_agent_name")
        assert "fake_agent_name.txt" in str(exc_info.value)


class TestLoadPromptEmptyFile:
    """Tests that ConfigurationError is raised for empty prompt files."""

    def test_raises_configuration_error_for_empty_file(self, tmp_path):
        """load_prompt raises ConfigurationError when the prompt file is empty."""
        empty_file = tmp_path / "empty_agent.txt"
        empty_file.write_text("", encoding="utf-8")

        with patch("src.agents.prompt_loader.PROMPTS_DIR", tmp_path):
            with pytest.raises(ConfigurationError, match="Prompt file is empty"):
                load_prompt("empty_agent")

    def test_raises_configuration_error_for_whitespace_only_file(self, tmp_path):
        """load_prompt raises ConfigurationError when file contains only whitespace."""
        ws_file = tmp_path / "whitespace_agent.txt"
        ws_file.write_text("   \n\t\n  ", encoding="utf-8")

        with patch("src.agents.prompt_loader.PROMPTS_DIR", tmp_path):
            with pytest.raises(ConfigurationError, match="Prompt file is empty"):
                load_prompt("whitespace_agent")


class TestLoadPromptSuccess:
    """Tests that each prompt file loads successfully."""

    def test_retrieval_agent_loads(self):
        """Retrieval agent prompt loads without error."""
        prompt = load_prompt("retrieval_agent")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_generation_agent_loads(self):
        """Generation agent prompt loads without error."""
        prompt = load_prompt("generation_agent")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_citation_verification_agent_loads(self):
        """Citation verification agent prompt loads without error."""
        prompt = load_prompt("citation_verification_agent")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_ingestion_agent_loads(self):
        """Ingestion agent prompt loads without error."""
        prompt = load_prompt("ingestion_agent")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_evaluation_agent_loads(self):
        """Evaluation agent prompt loads without error."""
        prompt = load_prompt("evaluation_agent")
        assert isinstance(prompt, str)
        assert len(prompt) > 0


class TestRetrievalAgentPromptContent:
    """Tests that the retrieval agent prompt contains required domain terms."""

    @pytest.fixture
    def prompt(self):
        return load_prompt("retrieval_agent")

    def test_contains_amends_keyword(self, prompt):
        """Retrieval prompt contains AMENDS cross-reference keyword."""
        assert "AMENDS" in prompt

    def test_contains_references_keyword(self, prompt):
        """Retrieval prompt contains REFERENCES cross-reference keyword."""
        assert "REFERENCES" in prompt

    def test_contains_implements_keyword(self, prompt):
        """Retrieval prompt contains IMPLEMENTS cross-reference keyword."""
        assert "IMPLEMENTS" in prompt

    def test_contains_graph_traversal(self, prompt):
        """Retrieval prompt contains graph traversal instruction."""
        assert "graph traversal" in prompt.lower()

    def test_contains_legal_entity_types(self, prompt):
        """Retrieval prompt mentions all 7 legal entity types."""
        entity_types = ["Act", "Section", "Regulation", "Definition",
                        "Obligation", "Authority", "Penalty"]
        for entity_type in entity_types:
            assert entity_type in prompt, f"Missing entity type: {entity_type}"


class TestGenerationAgentPromptContent:
    """Tests that the generation agent prompt contains required domain terms."""

    @pytest.fixture
    def prompt(self):
        return load_prompt("generation_agent")

    def test_contains_citation_format(self, prompt):
        """Generation prompt contains the required citation format pattern."""
        assert "Section [number]([subsection])" in prompt or \
               "Section [number]" in prompt

    def test_contains_speculative_language_prohibition(self, prompt):
        """Generation prompt prohibits speculative language."""
        assert "shall not use speculative language" in prompt.lower()

    def test_contains_legislative_phrasing(self, prompt):
        """Generation prompt instructs passive legislative phrasing."""
        assert "passive" in prompt.lower() or "legislative phrasing" in prompt.lower()

    def test_contains_source_chunk_grounding(self, prompt):
        """Generation prompt requires claims supported by source chunks."""
        assert "source chunk" in prompt.lower()


class TestCitationVerificationPromptContent:
    """Tests that the citation verification prompt contains required terms."""

    @pytest.fixture
    def prompt(self):
        return load_prompt("citation_verification_agent")

    def test_contains_section_heading_metadata(self, prompt):
        """Citation prompt contains section_heading metadata verification."""
        assert "section_heading metadata" in prompt.lower() or \
               "section_heading" in prompt

    def test_contains_verbatim_match(self, prompt):
        """Citation prompt contains verbatim match instruction."""
        assert "verbatim" in prompt.lower()

    def test_contains_paraphrase_match(self, prompt):
        """Citation prompt contains paraphrase match instruction."""
        assert "paraphrase" in prompt.lower()

    def test_contains_unsupported_flagging(self, prompt):
        """Citation prompt contains instruction to flag unsupported claims."""
        assert "unsupported" in prompt.lower()


class TestIngestionAgentPromptContent:
    """Tests that the ingestion agent prompt contains all entity and relationship types."""

    @pytest.fixture
    def prompt(self):
        return load_prompt("ingestion_agent")

    def test_contains_all_entity_types(self, prompt):
        """Ingestion prompt contains all 7 legal entity types."""
        entity_types = ["Act", "Section", "Regulation", "Definition",
                        "Obligation", "Authority", "Penalty"]
        for entity_type in entity_types:
            assert entity_type in prompt, f"Missing entity type: {entity_type}"

    def test_contains_all_relationship_types(self, prompt):
        """Ingestion prompt contains all 8 relationship types."""
        relationship_types = [
            "CONTAINS", "DEFINES", "AMENDS", "REFERENCES",
            "IMPLEMENTS", "IMPOSES", "GRANTS_POWER", "PRESCRIBES_PENALTY",
        ]
        for rel_type in relationship_types:
            assert rel_type in prompt, f"Missing relationship type: {rel_type}"

    def test_contains_minimum_entity_per_section(self, prompt):
        """Ingestion prompt requires minimum one entity per legislative section."""
        assert "minimum" in prompt.lower() and "entity" in prompt.lower()


class TestEvaluationAgentPromptContent:
    """Tests that the evaluation agent prompt contains required scoring terms."""

    @pytest.fixture
    def prompt(self):
        return load_prompt("evaluation_agent")

    def test_contains_legislative_accuracy(self, prompt):
        """Evaluation prompt contains legislative accuracy scoring."""
        assert "legislative accuracy" in prompt.lower() or \
               "legislative_accuracy" in prompt.lower()

    def test_contains_citation_precision(self, prompt):
        """Evaluation prompt contains citation precision scoring."""
        assert "citation precision" in prompt.lower() or \
               "citation_precision" in prompt.lower()

    def test_contains_obligation_authority_completeness(self, prompt):
        """Evaluation prompt contains obligation/authority completeness scoring."""
        assert "obligation" in prompt.lower()
        assert "authority" in prompt.lower()
        assert "completeness" in prompt.lower()
