"""Top-level package for zk-age-verifier."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("zk-age-verifier")
except PackageNotFoundError:  # pragma: no cover - not installed (editable source tree)
    __version__ = "0.0.0"
