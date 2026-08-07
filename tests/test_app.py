import importlib.metadata
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import HELD_STUB, render_config
from zk_age_verifier.app import CONFIG_ENV_VAR, app_factory, create_app
from zk_age_verifier.config import load_config
from zk_age_verifier.service.sessions import SessionStore


async def test_health(config_file: Path) -> None:
    app = create_app(load_config(config_file))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["zk_age_verifier"] == importlib.metadata.version("zk-age-verifier")
    assert body["pylongfellow"] == importlib.metadata.version("pylongfellow")
    assert body["engine"] == "google-cpp"
    assert body["ref"] is None


async def test_health_reports_build_ref(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZK_AGE_VERIFIER_BUILD_REF", "abc1234")
    app = create_app(load_config(config_file))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
    assert response.json()["ref"] == "abc1234"


def test_lifespan_wires_store(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("zk_age_verifier.app.load_held_circuit", lambda backend: HELD_STUB)
    app = create_app(load_config(config_file))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert isinstance(app.state.store, SessionStore)
        assert app.state.held is HELD_STUB


def test_unknown_backend_fails_startup(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text(render_config(**{"pylongfellow.backend": "no-such-backend"}))
    app = create_app(load_config(path))
    with pytest.raises(ValueError, match="unknown backend"):
        with TestClient(app):
            pass


def test_app_factory_reads_config_from_env(
    config_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(CONFIG_ENV_VAR, str(config_file))
    assert isinstance(app_factory(), FastAPI)
