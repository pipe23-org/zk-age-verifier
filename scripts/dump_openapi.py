"""MkDocs hook: dump the app's OpenAPI schema for the API docs page."""

import json
from pathlib import Path

from fastapi import FastAPI
from mkdocs.config.defaults import MkDocsConfig

from zk_age_verifier.app import create_app
from zk_age_verifier.config import Config, ServiceConfig, TrustConfig, TrustSource

SPEC = Path(__file__).resolve().parent.parent / "docs" / "openapi.json"


def _schema_app() -> FastAPI:
    """Build the app on placeholder config; only the route schema is read."""
    config = Config(
        service=ServiceConfig(expected_origin="https://docs.invalid"),
        trust=TrustConfig(sources=[TrustSource(pem="/etc/zk-age-verifier/anchors")]),
    )
    return create_app(config)


def on_config(config: MkDocsConfig) -> MkDocsConfig:
    """Write docs/openapi.json before mkdocs collects the docs tree."""
    spec = json.dumps(_schema_app().openapi(), indent=2) + "\n"
    # Unchanged rewrites would retrigger `mkdocs serve`'s watcher in a loop.
    if not SPEC.exists() or SPEC.read_text() != spec:
        SPEC.write_text(spec)
    return config
