"""Base configuration and utilities shared across all RAG pipeline agents.

Provides model factory, common configuration, and shared tool utilities
that all agents use. Supports tiered model selection for cost optimization.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog
from strands import Agent
from strands.models import BedrockModel

logger = structlog.get_logger(__name__)


class ModelTier(str, Enum):
    """Model tiers for cost-optimized agent configuration.

    LITE: Cheapest, for simple orchestration and tool-calling tasks.
    PRO: Mid-tier, for tasks requiring reasoning and judgment.
    PREMIUM: High-quality, for complex generation and evaluation.
    """

    LITE = "lite"
    PRO = "pro"
    PREMIUM = "premium"


# Model ID mappings per tier (Bedrock inference profile format)
# Agents use ap-southeast-4 (Melbourne) for lower latency
BEDROCK_MODEL_TIERS: dict[ModelTier, str] = {
    ModelTier.LITE: "apac.amazon.nova-lite-v1:0",
    ModelTier.PRO: "apac.amazon.nova-pro-v1:0",
    ModelTier.PREMIUM: "apac.anthropic.claude-sonnet-4-20250514-v1:0",
}

# Recommended tier per agent role
AGENT_TIER_DEFAULTS: dict[str, ModelTier] = {
    "retrieval": ModelTier.LITE,
    "generation": ModelTier.PRO,
    "citation_verification": ModelTier.LITE,
    "ingestion": ModelTier.LITE,
    "evaluation": ModelTier.PRO,
}


@dataclass
class AgentConfig:
    """Configuration for RAG pipeline agents.

    Attributes:
        model_id: The Bedrock model identifier (inference profile format).
        region_name: AWS region for Bedrock API calls.
        temperature: Sampling temperature (lower = more deterministic).
        max_tokens: Maximum tokens in model response.
        tier: Which model tier to use (lite, pro, premium).
    """

    model_id: str = ""
    region_name: str = "us-east-1"
    temperature: float = 0.1
    max_tokens: int = 4096
    tier: ModelTier = ModelTier.LITE
    extra_params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Resolve model_id from tier if not explicitly set."""
        if not self.model_id:
            self.model_id = BEDROCK_MODEL_TIERS[self.tier]


def get_default_config() -> AgentConfig:
    """Build agent configuration from environment variables.

    Environment Variables:
        RAG_AGENT_MODEL_ID: Override model ID directly (takes precedence over tier).
        RAG_AGENT_REGION: AWS region (default: ap-southeast-4 for agents).
        RAG_AGENT_TEMPERATURE: Sampling temperature (default: 0.1).
        RAG_AGENT_MAX_TOKENS: Max tokens (default: 4096).
        RAG_AGENT_TIER: Model tier - lite, pro, or premium (default: lite).
    """
    tier_str = os.environ.get("RAG_AGENT_TIER", "lite")
    try:
        tier = ModelTier(tier_str)
    except ValueError:
        tier = ModelTier.LITE

    return AgentConfig(
        model_id=os.environ.get("RAG_AGENT_MODEL_ID", ""),
        region_name=os.environ.get("RAG_AGENT_REGION", "ap-southeast-4"),
        temperature=float(os.environ.get("RAG_AGENT_TEMPERATURE", "0.1")),
        max_tokens=int(os.environ.get("RAG_AGENT_MAX_TOKENS", "4096")),
        tier=tier,
    )


def get_config_for_agent(agent_role: str) -> AgentConfig:
    """Get the recommended configuration for a specific agent role.

    Uses the AGENT_TIER_DEFAULTS mapping to select the right model tier
    per agent role, balancing cost vs capability.

    Args:
        agent_role: One of 'retrieval', 'generation', 'citation_verification',
                    'ingestion', 'evaluation'.

    Returns:
        AgentConfig with the appropriate tier and model for the role.
    """
    # Check for global override first
    override_model = os.environ.get("RAG_AGENT_MODEL_ID", "")
    if override_model:
        # If user explicitly set a model, use it for all agents
        return get_default_config()

    tier = AGENT_TIER_DEFAULTS.get(agent_role, ModelTier.LITE)

    # Allow per-agent tier override via env var
    # e.g., RAG_GENERATION_TIER=premium
    env_key = f"RAG_{agent_role.upper()}_TIER"
    tier_override = os.environ.get(env_key, "")
    if tier_override:
        try:
            tier = ModelTier(tier_override)
        except ValueError:
            pass

    return AgentConfig(
        region_name=os.environ.get("RAG_AGENT_REGION", "us-east-1"),
        temperature=float(os.environ.get("RAG_AGENT_TEMPERATURE", "0.1")),
        max_tokens=int(os.environ.get("RAG_AGENT_MAX_TOKENS", "4096")),
        tier=tier,
    )


def create_model(config: AgentConfig | None = None) -> BedrockModel:
    """Create a Strands BedrockModel instance from configuration.

    Args:
        config: Agent configuration. Uses defaults if None.

    Returns:
        A configured BedrockModel instance.
    """
    if config is None:
        config = get_default_config()

    model = BedrockModel(
        model_id=config.model_id,
        region_name=config.region_name,
        temperature=config.temperature,
        max_tokens=config.max_tokens,
    )

    logger.info(
        "model.created",
        model_id=config.model_id,
        region=config.region_name,
        tier=config.tier.value,
    )

    return model


def create_agent(
    tools: list[Any],
    system_prompt: str,
    config: AgentConfig | None = None,
) -> Agent:
    """Create a Strands Agent with the given tools and system prompt.

    Args:
        tools: List of @tool-decorated functions for the agent.
        system_prompt: System instructions for the agent.
        config: Optional agent configuration.

    Returns:
        A configured Strands Agent ready for invocation.
    """
    model = create_model(config)

    agent = Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
    )

    logger.info(
        "agent.created",
        model_id=config.model_id if config else "default",
        tool_count=len(tools),
    )

    return agent
