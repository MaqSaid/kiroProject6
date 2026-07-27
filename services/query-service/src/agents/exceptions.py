"""Custom exceptions for agent configuration and initialization."""


class ConfigurationError(Exception):
    """Raised when an agent's system prompt fails to load or is empty.

    This error prevents the agent from accepting requests until a valid
    prompt is provided, as required by Requirement 4.8.
    """

    pass
