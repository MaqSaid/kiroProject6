"""Structlog JSON logging configuration for the Ingestion Service.

Configures structlog with consistent fields: timestamp, level, service_name,
correlation_id, and message across all log entries.
"""

import logging
import os
from contextvars import ContextVar

import structlog

# Context variable for correlation ID propagation
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="")

SERVICE_NAME = os.getenv("SERVICE_NAME", "ingestion-service")


def add_service_context(
    logger: structlog.types.WrappedLogger,
    method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    """Add service_name and correlation_id to every log entry."""
    event_dict["service_name"] = SERVICE_NAME
    cid = correlation_id_ctx.get("")
    if cid:
        event_dict["correlation_id"] = cid
    return event_dict


def configure_logging() -> None:
    """Configure structlog for JSON output with consistent fields."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_service_context,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Get a configured structlog logger instance."""
    return structlog.get_logger(name)
