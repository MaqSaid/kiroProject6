"""Prompt loader for legal domain agent system prompts.

Loads agent prompts from configurable text files at initialization time.
Raises ConfigurationError if any prompt file is missing or empty,
preventing the agent from accepting requests (Requirement 4.8).
"""

from pathlib import Path

from src.agents.exceptions import ConfigurationError

PROMPTS_DIR = Path(__file__).parent / "prompts"


def load_prompt(agent_name: str) -> str:
    """Load a system prompt for the specified agent.

    Args:
        agent_name: The agent identifier matching the prompt filename
                    (without .txt extension). One of:
                    - retrieval_agent
                    - generation_agent
                    - citation_verification_agent
                    - ingestion_agent
                    - evaluation_agent

    Returns:
        The prompt text content as a string.

    Raises:
        ConfigurationError: If the prompt file does not exist or is empty.
    """
    path = PROMPTS_DIR / f"{agent_name}.txt"
    if not path.exists():
        raise ConfigurationError(f"Prompt file not found: {path}")
    content = path.read_text(encoding="utf-8").strip()
    if not content:
        raise ConfigurationError(f"Prompt file is empty: {path}")
    return content
