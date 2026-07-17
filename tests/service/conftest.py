from collections.abc import Callable
from pathlib import Path

import pytest
from pylongfellow import mdoc

from tests.conftest import render_config
from zk_age_verifier.config import Config, load_config
from zk_age_verifier.core.engine.circuits import (
    CIRCUIT_VERSION,
    NUM_ATTRIBUTES,
    SYSTEM,
    HeldCircuit,
    zk_system_id,
)
from zk_age_verifier.core.transport.dc import DcTransport
from zk_age_verifier.service.sessions import SessionStore


def _config(path: Path, *, ttl: int, cap: int) -> Config:
    path.write_text(render_config(session_ttl_seconds=ttl, session_cap=cap))
    return load_config(path)


@pytest.fixture
def held() -> HeldCircuit:
    (spec,) = (
        s
        for s in mdoc.zk_specs()
        if s.system == SYSTEM
        and s.version == CIRCUIT_VERSION
        and s.num_attributes == NUM_ATTRIBUTES
    )
    return HeldCircuit(spec=spec, circuit=b"", zk_system_id=zk_system_id(spec))


@pytest.fixture
def make_store(tmp_path: Path, held: HeldCircuit) -> Callable[..., SessionStore]:
    def _make(*, ttl: int = 300, cap: int = 1000) -> SessionStore:
        return SessionStore(_config(tmp_path / "config.toml", ttl=ttl, cap=cap), DcTransport(held))

    return _make


@pytest.fixture
def store(make_store: Callable[..., SessionStore]) -> SessionStore:
    return make_store()
