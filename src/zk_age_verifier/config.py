"""Configuration loading: a TOML file with environment-variable overrides.

The verifier reads a TOML file with two tables, ``[service]`` and ``[trust]``.
Structure — lists and nested tables — comes from the TOML file. Environment
variables named ``ZK_AGE_VERIFIER_SECTION__KEY`` override scalar values within a
section; ``ZK_AGE_VERIFIER_`` is the prefix and ``__`` separates nesting levels.
Unprefixed environment variables are ignored. Unknown keys in the TOML file are
rejected, as is an unknown key nested under a known section in a prefixed
environment variable (``ZK_AGE_VERIFIER_SERVICE__BOGUS``). An unknown top-level
prefixed environment variable (``ZK_AGE_VERIFIER_BOGUS``) is silently ignored
by pydantic-settings.

Source priority, highest first: constructor arguments, environment variables,
the TOML file, then model defaults.
"""

import os
import tomllib
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class ConfigError(Exception):
    """Raised when a configuration file is missing, unparseable, or invalid."""


def validate_origin(value: str) -> str:
    """Require a bare ``scheme://host[:port]`` origin with no path.

    The origin is hashed into the presentation transcript, so it must be
    exactly what the consumer page's browser will assert.

    Args:
        value: The candidate origin.

    Returns:
        The value unchanged.

    Raises:
        ValueError: The scheme is not http(s), the host is missing, or a path,
            query, or fragment is present.
    """
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https"):
        raise ValueError("expected_origin must use http or https")
    if not parts.hostname:
        raise ValueError("expected_origin must include a host")
    if parts.path or parts.query or parts.fragment:
        raise ValueError("expected_origin must be a bare origin with no path, query, or fragment")
    return value


def _default_circuit_cache_dir() -> Path:
    """Return the default circuit cache directory, honouring ``XDG_CACHE_HOME``.

    The container image and compose files spell this path literally (Dockerfile,
    compose.test.yaml, the site-dc-mdoc compose); a change here must move them too.
    """
    cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(cache_home) if cache_home else Path.home() / ".cache"
    return base / "zk-age-verifier" / "circuits"


class ServiceConfig(BaseModel):
    """The ``[service]`` table: origin binding, session hygiene, circuit cache."""

    model_config = ConfigDict(extra="forbid")

    expected_origin: str
    session_ttl_seconds: int = 300
    session_cap: int = 1000
    timestamp_skew_seconds: int = 300
    cors_allowed_origins: list[str] = Field(default_factory=list)
    circuit_cache_dir: Path = Field(default_factory=_default_circuit_cache_dir)

    @field_validator("expected_origin")
    @classmethod
    def _validate_origin(cls, value: str) -> str:
        """Validate the configured origin against the shared rules."""
        return validate_origin(value)


class TrustSource(BaseModel):
    """One ``[trust]`` source: exactly one of ``pem``, ``etsi_xml``."""

    model_config = ConfigDict(extra="forbid")

    pem: str | None = None
    etsi_xml: str | None = None

    @model_validator(mode="after")
    def _validate_single_source(self) -> "TrustSource":
        """Reject entries that set zero or several source keys."""
        set_keys = [
            key
            for key, value in (("pem", self.pem), ("etsi_xml", self.etsi_xml))
            if value is not None
        ]
        if len(set_keys) != 1:
            raise ValueError("each trust source must set exactly one of pem, etsi_xml")
        return self


class TrustConfig(BaseModel):
    """The ``[trust]`` table: a non-empty list of anchor sources."""

    model_config = ConfigDict(extra="forbid")

    sources: list[TrustSource] = Field(min_length=1)


class Config(BaseSettings):
    """The whole configuration file."""

    model_config = SettingsConfigDict(
        env_prefix="ZK_AGE_VERIFIER_",
        env_nested_delimiter="__",
        extra="forbid",
    )

    service: ServiceConfig
    trust: TrustConfig


def load_config(path: str | Path) -> Config:
    """Load and validate a configuration file.

    Args:
        path: Path to the TOML file.

    Returns:
        The validated configuration.

    Raises:
        ConfigError: The file is missing, not valid TOML, or fails validation.
    """
    file = Path(path)
    if not file.is_file():
        raise ConfigError(f"config file not found: {path}")

    class _Config(Config):
        """Binds the TOML source to this call's path without shared class state."""

        @classmethod
        def settings_customise_sources(
            cls,
            settings_cls: type[BaseSettings],
            init_settings: PydanticBaseSettingsSource,
            env_settings: PydanticBaseSettingsSource,
            dotenv_settings: PydanticBaseSettingsSource,
            file_secret_settings: PydanticBaseSettingsSource,
        ) -> tuple[PydanticBaseSettingsSource, ...]:
            """Order the sources: init, env, then this call's TOML file."""
            return (
                init_settings,
                env_settings,
                TomlConfigSettingsSource(settings_cls, toml_file=file),
            )

    try:
        return _Config()
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"invalid TOML in {path}: {exc}") from exc
    except ValidationError as exc:
        raise ConfigError(f"invalid configuration in {path}: {exc}") from exc
