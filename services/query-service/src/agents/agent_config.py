"""Strands Agent configuration for the Legislation RAG Platform.

Configures all five domain agents with their legal-specific system prompts.
Each agent is configured as a Strands Agent with its system prompt loaded
from configurable text files at initialization time.

If any prompt is missing or empty, a ConfigurationError is raised,
preventing the platform from accepting requests (Requirement 4.6, 4.8).

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from src.agents.exceptions import ConfigurationError
from src.agents.prompt_loader import load_prompt

logger = structlog.get_logger(__name__)

# Agent identifiers matching prompt filenames
AGENT_NAMES = (
    "retrieval_agent",
    "generation_agent",
    "citation_verification_agent",
    "ingestion_agent",
    "evaluation_agent",
)


@dataclass(frozen=True)
class AgentPromptConfig:
    """Configuration for a single Strands Agent system prompt.

    Attributes:
        agent_name: Identifier for the agent (matches prompt filename).
        system_prompt: The loaded system prompt text.
    """

    agent_name: str
    system_prompt: str

    def __post_init__(self) -> None:
        """Validate that the system prompt is non-empty after load."""
        if not self.system_prompt or not self.system_prompt.strip():
            raise ConfigurationError(
                f"System prompt for '{self.agent_name}' is empty or None. "
                "Cannot initialize agent without a valid system prompt."
            )


@dataclass(frozen=True)
class PlatformAgentPrompts:
    """All agent prompts for the Legislation RAG Platform.

    Contains the loaded system prompts for all five agents.
    Raises ConfigurationError if any prompt is missing or empty.
    """

    retrieval: AgentPromptConfig
    generation: AgentPromptConfig
    citation_verification: AgentPromptConfig
    ingestion: AgentPromptConfig
    evaluation: AgentPromptConfig


def load_all_agent_prompts() -> PlatformAgentPrompts:
    """Load and validate all agent system prompts at initialization.

    Loads each agent's system prompt from the prompts directory and
    validates that none are empty. This function should be called during
    the application lifespan startup event.

    Returns:
        PlatformAgentPrompts with all five agent configurations.

    Raises:
        ConfigurationError: If any prompt file is missing or empty.
    """
    logger.info("agent_config.loading_prompts")

    prompts: dict[str, AgentPromptConfig] = {}
    for agent_name in AGENT_NAMES:
        prompt_text = load_prompt(agent_name)
        config = AgentPromptConfig(agent_name=agent_name, system_prompt=prompt_text)
        prompts[agent_name] = config
        logger.info(
            "agent_config.prompt_loaded",
            agent=agent_name,
            prompt_length=len(prompt_text),
        )

    platform_prompts = PlatformAgentPrompts(
        retrieval=prompts["retrieval_agent"],
        generation=prompts["generation_agent"],
        citation_verification=prompts["citation_verification_agent"],
        ingestion=prompts["ingestion_agent"],
        evaluation=prompts["evaluation_agent"],
    )

    logger.info("agent_config.all_prompts_loaded", agent_count=len(AGENT_NAMES))
    return platform_prompts


def get_strands_agent_kwargs(prompt_config: AgentPromptConfig) -> dict[str, Any]:
    """Build keyword arguments for Strands Agent initialization.

    Returns the configuration dict suitable for passing to the Strands
    Agent constructor, including the system_prompt parameter.

    Args:
        prompt_config: The agent's prompt configuration.

    Returns:
        Dict with 'system_prompt' key and the loaded prompt text.
    """
    return {
        "system_prompt": prompt_config.system_prompt,
    }
