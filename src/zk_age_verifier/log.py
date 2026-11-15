"""structlog configuration — call configure_logging() once at startup."""

import logging
import os

import structlog

from zk_age_verifier.config import ConfigError

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}


def _configured_level() -> int:
    """Return the threshold named by LOG_LEVEL, info when it is unset."""
    name = os.environ.get("LOG_LEVEL", "info")
    try:
        return _LEVELS[name.lower()]
    except KeyError as exc:
        accepted = ", ".join(_LEVELS)
        raise ConfigError(f"LOG_LEVEL is {name!r}; accepted values are {accepted}") from exc


def configure_logging() -> None:
    """Configure structlog: JSON lines by default, pretty console when LOG_FORMAT=console.

    Stdlib logging is routed through the same renderer, so server and library
    logs come out in the one stream. ``LOG_LEVEL`` names the threshold.

    Raises:
        ConfigError: ``LOG_LEVEL`` names no accepted level.
    """
    level = _configured_level()
    processors: list[structlog.typing.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
    ]
    renderer: structlog.typing.Processor
    if os.environ.get("LOG_FORMAT") == "console":
        renderer = structlog.dev.ConsoleRenderer()
    else:
        processors.append(structlog.processors.format_exc_info)
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
    logging.basicConfig(handlers=[handler], level=level, force=True)
