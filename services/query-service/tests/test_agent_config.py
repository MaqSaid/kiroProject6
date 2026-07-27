"""Unit tests for Strands Agent configuration and prompt loading.

Tests verify:
- All five agent prompts load successfully via load_all_agent_prompts
- ConfigurationError raised when any prompt is missing or empty
- AgentPromptConfig validates non-empty system_prompt
- get_strands_agent_kwargs returns correct dict structure
- Each agent class loads its prompt at initialization
- Each agent class raises ConfigurationError for missing prompt
"""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.agent_config import (
    AGENT_NAMES,
    AgentPromptConfig,
    PlatformAgentPrompts,
    get_strands_agent_kwargs,
    load_all_agent_prompts,
)
from src.agents.exceptions import ConfigurationError


class TestLoadAllAgentPrompts:
    """Tests that load_all_agent_prompts loads all five agents successfully."""

    def test_loads_all_five_prompts(self):
        """All five agent prompts load without error."""
        prompts = load_all_agent_prompts()
        assert isinstance(prompts, PlatformAgentPrompts)

    def test_retrieval_prompt_is_non_empty(self):
        """Retrieval agent prompt is non-empty string."""
        prompts = load_all_agent_prompts()
        assert len(prompts.retrieval.system_prompt) > 0

    def test_generation_prompt_is_non_empty(self):
        """Generation agent prompt is non-empty string."""
        prompts = load_all_agent_prompts()
        assert len(prompts.generation.system_prompt) > 0

    def test_citation_verification_prompt_is_non_empty(self):
        """Citation verification agent prompt is non-empty string."""
        prompts = load_all_agent_prompts()
        assert len(prompts.citation_verification.system_prompt) > 0

    def test_ingestion_prompt_is_non_empty(self):
        """Ingestion agent prompt is non-empty string."""
        prompts = load_all_agent_prompts()
        assert len(prompts.ingestion.system_prompt) > 0

    def test_evaluation_prompt_is_non_empty(self):
        """Evaluation agent prompt is non-empty string."""
        prompts = load_all_agent_prompts()
        assert len(prompts.evaluation.system_prompt) > 0

    def test_agent_names_tuple_has_five_entries(self):
        """AGENT_NAMES contains exactly five agent identifiers."""
        assert len(AGENT_NAMES) == 5

    def test_raises_configuration_error_for_missing_prompt(self, tmp_path):
        """ConfigurationError raised if a prompt file is missing."""
        # Create all prompts except one
        for name in AGENT_NAMES:
            if name != "retrieval_agent":
                (tmp_path / f"{name}.txt").write_text("Some content", encoding="utf-8")

        with patch("src.agents.prompt_loader.PROMPTS_DIR", tmp_path):
            with pytest.raises(ConfigurationError, match="Prompt file not found"):
                load_all_agent_prompts()


class TestAgentPromptConfig:
    """Tests for AgentPromptConfig validation."""

    def test_valid_config_creation(self):
        """AgentPromptConfig creates successfully with non-empty prompt."""
        config = AgentPromptConfig(
            agent_name="test_agent",
            system_prompt="You are a test agent.",
        )
        assert config.agent_name == "test_agent"
        assert config.system_prompt == "You are a test agent."

    def test_raises_for_empty_prompt(self):
        """AgentPromptConfig raises ConfigurationError for empty prompt."""
        with pytest.raises(ConfigurationError, match="empty or None"):
            AgentPromptConfig(agent_name="test_agent", system_prompt="")

    def test_raises_for_whitespace_only_prompt(self):
        """AgentPromptConfig raises ConfigurationError for whitespace-only prompt."""
        with pytest.raises(ConfigurationError, match="empty or None"):
            AgentPromptConfig(agent_name="test_agent", system_prompt="   \n\t  ")


class TestGetStrandsAgentKwargs:
    """Tests for get_strands_agent_kwargs helper."""

    def test_returns_dict_with_system_prompt(self):
        """Returns dict containing the system_prompt key."""
        config = AgentPromptConfig(
            agent_name="test_agent",
            system_prompt="You are a test agent.",
        )
        kwargs = get_strands_agent_kwargs(config)
        assert kwargs == {"system_prompt": "You are a test agent."}

    def test_system_prompt_value_matches(self):
        """system_prompt value matches the config."""
        prompt_text = "You are an evaluation agent for legal documents."
        config = AgentPromptConfig(agent_name="evaluation_agent", system_prompt=prompt_text)
        kwargs = get_strands_agent_kwargs(config)
        assert kwargs["system_prompt"] == prompt_text


class TestAgentInitializationWithPrompts:
    """Tests that each agent class loads its prompt at initialization."""

    def test_retrieval_agent_loads_prompt(self):
        """RetrievalAgent loads retrieval_agent prompt at init."""
        from src.agents.retrieval_agent import RetrievalAgent

        agent = RetrievalAgent(system_prompt="Test retrieval prompt")
        assert agent.system_prompt == "Test retrieval prompt"

    def test_generation_agent_loads_prompt(self):
        """GenerationAgent loads generation_agent prompt at init."""
        from src.agents.generation_agent import GenerationAgent

        agent = GenerationAgent(system_prompt="Test generation prompt")
        assert agent.system_prompt == "Test generation prompt"

    def test_citation_agent_loads_prompt(self):
        """CitationVerificationAgent loads citation_verification_agent prompt."""
        from src.agents.citation_agent import CitationVerificationAgent

        agent = CitationVerificationAgent(system_prompt="Test citation prompt")
        assert agent.system_prompt == "Test citation prompt"

    def test_evaluation_agent_loads_prompt(self):
        """EvaluationAgent loads evaluation_agent prompt at init."""
        from src.agents.evaluation_agent import EvaluationAgent

        agent = EvaluationAgent(system_prompt="Test evaluation prompt")
        assert agent.system_prompt == "Test evaluation prompt"

    def test_retrieval_agent_loads_from_file_by_default(self):
        """RetrievalAgent loads from file when no system_prompt arg given."""
        from src.agents.retrieval_agent import RetrievalAgent

        agent = RetrievalAgent()
        assert "Retrieval Agent" in agent.system_prompt
        assert "AMENDS" in agent.system_prompt

    def test_generation_agent_loads_from_file_by_default(self):
        """GenerationAgent loads from file when no system_prompt arg given."""
        from src.agents.generation_agent import GenerationAgent

        agent = GenerationAgent()
        assert "Generation Agent" in agent.system_prompt
        assert "Section [number]" in agent.system_prompt

    def test_citation_agent_loads_from_file_by_default(self):
        """CitationVerificationAgent loads from file when no arg given."""
        from src.agents.citation_agent import CitationVerificationAgent

        agent = CitationVerificationAgent()
        assert "Citation Verification Agent" in agent.system_prompt

    def test_evaluation_agent_loads_from_file_by_default(self):
        """EvaluationAgent loads from file when no system_prompt arg given."""
        from src.agents.evaluation_agent import EvaluationAgent

        agent = EvaluationAgent()
        assert "Evaluation Agent" in agent.system_prompt

    def test_retrieval_agent_raises_for_missing_prompt(self, tmp_path):
        """RetrievalAgent raises ConfigurationError for missing prompt file."""
        from src.agents.retrieval_agent import RetrievalAgent

        with patch("src.agents.prompt_loader.PROMPTS_DIR", tmp_path):
            with pytest.raises(ConfigurationError):
                RetrievalAgent()

    def test_generation_agent_raises_for_missing_prompt(self, tmp_path):
        """GenerationAgent raises ConfigurationError for missing prompt file."""
        from src.agents.generation_agent import GenerationAgent

        with patch("src.agents.prompt_loader.PROMPTS_DIR", tmp_path):
            with pytest.raises(ConfigurationError):
                GenerationAgent()
