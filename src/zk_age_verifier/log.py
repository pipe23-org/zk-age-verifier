"""structlog configuration — call configure_logging() once at startup."""

import logging
import os

import structlog


def configure_logging() -> None:
    """Configure structlog: JSON lines by default, pretty console when LOG_FORMAT=console.

    Stdlib logging is routed through the same renderer, so server and library
    logs come out in the one stream.
    """
    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    renderer: structlog.typing.Processor
    if os.environ.get("LOG_FORMAT") == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        renderer = structlog.processors.JSONRenderer()
    structlog.configure(
        processors=[*processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    handler = logging.StreamHandler()
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=processors,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        )
    )
    # force=True evicts handlers a server may already have installed on the root logger.
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)
