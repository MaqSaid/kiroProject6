"""Security service for prompt injection detection, document scanning, and input validation.

Implements a pure domain service with no external dependencies — only regex pattern matching
and structured result models.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SecurityScanResult:
    """Result of a security scan operation.

    Attributes:
        passed: True if the scan detected no threats.
        reason: Human-readable explanation (empty string if passed).
        detected_patterns: List of pattern category names that matched.
    """

    passed: bool
    reason: str = ""
    detected_patterns: list[str] = field(default_factory=list)


# --- Pattern Definitions ---

# Direct injection: attempts to override system prompt or inject new instructions
_DIRECT_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "system_prompt_override",
        re.compile(
            r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules|context)",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_override",
        re.compile(
            r"forget\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules|context)",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_override",
        re.compile(
            r"disregard\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules|context)",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_override",
        re.compile(
            r"you\s+are\s+now\s+(?:a|an|the)?\s*\w+",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_override",
        re.compile(
            r"new\s+instructions?\s*[:.]",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_override",
        re.compile(
            r"your\s+new\s+(role|instructions?|task|purpose)",
            re.IGNORECASE,
        ),
    ),
]

# Instruction injection: attempts to override or manipulate assistant behavior
_INSTRUCTION_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "instruction_injection",
        re.compile(
            r"(?:^|\s)override\s+(the\s+)?(system|safety|content)\s*(prompt|filter|policy|rules?)",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction_injection",
        re.compile(
            r"disregard\s+(your|the|all)\s+(guidelines|rules|safeguards|safety|restrictions)",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction_injection",
        re.compile(
            r"(?:do\s+not|don'?t)\s+follow\s+(your|the|any)\s+(rules|guidelines|instructions)",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction_injection",
        re.compile(
            r"bypass\s+(the\s+)?(safety|content|security)\s*(filter|check|restriction|policy)",
            re.IGNORECASE,
        ),
    ),
    (
        "instruction_injection",
        re.compile(
            r"ignore\s+(your|the|all)\s+(rules|guidelines|safeguards|safety|restrictions)",
            re.IGNORECASE,
        ),
    ),
]

# Role-play attacks: attempts to make the model assume a new persona
_ROLEPLAY_ATTACK_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "roleplay_attack",
        re.compile(
            r"pretend\s+(you\s+are|to\s+be|you'?re)\s+",
            re.IGNORECASE,
        ),
    ),
    (
        "roleplay_attack",
        re.compile(
            r"act\s+as\s+(if\s+you\s+are\s+|a\s+|an\s+|the\s+)?",
            re.IGNORECASE,
        ),
    ),
    (
        "roleplay_attack",
        re.compile(
            r"roleplay\s+as\s+",
            re.IGNORECASE,
        ),
    ),
    (
        "roleplay_attack",
        re.compile(
            r"you\s+must\s+(now\s+)?act\s+(like|as)\s+",
            re.IGNORECASE,
        ),
    ),
    (
        "roleplay_attack",
        re.compile(
            r"from\s+now\s+on\s+(you\s+are|act\s+as|behave\s+as)",
            re.IGNORECASE,
        ),
    ),
    (
        "roleplay_attack",
        re.compile(
            r"imagine\s+you\s+are\s+",
            re.IGNORECASE,
        ),
    ),
]

# System prompt extraction: attempts to reveal the system prompt
_EXTRACTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "prompt_extraction",
        re.compile(
            r"(reveal|show|print|display|output|repeat)\s+(your|the)\s+(system\s+)?(prompt|instructions|rules)",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_extraction",
        re.compile(
            r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions|rules|guidelines)",
            re.IGNORECASE,
        ),
    ),
    (
        "prompt_extraction",
        re.compile(
            r"(tell|give)\s+me\s+your\s+(system\s+)?(prompt|instructions|rules)",
            re.IGNORECASE,
        ),
    ),
]

# All patterns combined for scanning
_ALL_QUERY_PATTERNS: list[tuple[str, re.Pattern[str]]] = (
    _DIRECT_INJECTION_PATTERNS
    + _INSTRUCTION_INJECTION_PATTERNS
    + _ROLEPLAY_ATTACK_PATTERNS
    + _EXTRACTION_PATTERNS
)


class SecurityService:
    """Domain service for security scanning and input validation.

    Detects prompt injection attempts, scans documents for indirect injection,
    and validates filenames against path traversal attacks.

    This is a pure domain service with no external dependencies.
    """

    def __init__(self) -> None:
        self._query_patterns = _ALL_QUERY_PATTERNS

    def scan_query(self, query: str) -> SecurityScanResult:
        """Scan a user query for prompt injection patterns.

        Checks for direct injection (system prompt override, instruction injection),
        role-play attacks, and system prompt extraction attempts.

        Args:
            query: The raw user query string.

        Returns:
            SecurityScanResult with passed=True if safe, or passed=False
            with reason and detected patterns if injection detected.
        """
        detected: list[str] = []

        for category, pattern in self._query_patterns:
            if pattern.search(query):
                if category not in detected:
                    detected.append(category)

        if detected:
            reason = f"Prompt injection detected: {', '.join(detected)}"
            logger.warning(
                "prompt_injection_detected",
                query_length=len(query),
                detected_patterns=detected,
            )
            return SecurityScanResult(
                passed=False,
                reason=reason,
                detected_patterns=detected,
            )

        logger.debug("query_scan_passed", query_length=len(query))
        return SecurityScanResult(passed=True)

    def scan_document(self, content: str) -> SecurityScanResult:
        """Scan document content for indirect prompt injection payloads.

        Checks for injection patterns embedded within document text that could
        manipulate the LLM during retrieval-augmented generation.

        Args:
            content: The document text content to scan.

        Returns:
            SecurityScanResult indicating pass/reject with detected patterns.
        """
        # Skeleton — full implementation in task 14.2
        raise NotImplementedError("scan_document will be implemented in task 14.2")

    def validate_filename(self, filename: str) -> bool:
        """Validate a filename against path traversal and unsafe characters.

        Args:
            filename: The filename to validate.

        Returns:
            True if the filename is safe, False otherwise.
        """
        # Skeleton — full implementation in task 14.3
        raise NotImplementedError("validate_filename will be implemented in task 14.3")
