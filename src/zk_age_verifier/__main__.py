"""Command-line entry point for zk-age-verifier."""

import argparse
import os
import sys
from pathlib import Path

from granian import Granian
from granian.constants import Interfaces

from zk_age_verifier.app import CONFIG_ENV_VAR
from zk_age_verifier.config import ConfigError, load_config

APP_TARGET = "zk_age_verifier.app:app_factory"


def _serve(host: str, port: int) -> None:
    """Boot the ASGI app under granian in factory mode.

    Kept as a seam so tests can drive ``main`` without starting a server.
    """
    Granian(APP_TARGET, address=host, port=port, interface=Interfaces.ASGI, factory=True).serve()


def main(argv: list[str] | None = None) -> None:
    """Validate the configuration, then serve the verifier.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv`` when ``None``.
    """
    parser = argparse.ArgumentParser(
        description="Verifier service for EU age-verification proofs "
        "(Longfellow ZK over mdoc, W3C Digital Credentials API)",
    )
    parser.add_argument("--config", required=True, help="Path to the TOML configuration file.")
    parser.add_argument("--host", default="127.0.0.1", help="Address to bind (default: 127.0.0.1).")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind (default: 8000).")
    args = parser.parse_args(argv)

    try:
        load_config(args.config)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    os.environ[CONFIG_ENV_VAR] = str(Path(args.config).resolve())
    _serve(args.host, args.port)


if __name__ == "__main__":
    main()
