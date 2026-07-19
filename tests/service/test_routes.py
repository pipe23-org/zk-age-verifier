from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import HELD_STUB, render_config
from zk_age_verifier.app import create_app
from zk_age_verifier.config import load_config
from zk_age_verifier.core.transport.dc import build_handover_hash, build_session_transcript
from zk_age_verifier.service import routes

MakeApp = Callable[..., FastAPI]


def _config_text(*, cap: int = 1000, cors: list[str] | None = None) -> str:
    if cors is None:
        return render_config(session_cap=cap)
    return render_config(session_cap=cap, cors_allowed_origins=cors)


@pytest.fixture
def make_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MakeApp:
    monkeypatch.setattr("zk_age_verifier.app.load_held_circuit", lambda cache_dir: HELD_STUB)

    def _make(*, cap: int = 1000, cors: list[str] | None = None) -> FastAPI:
        path = tmp_path / "config.toml"
        path.write_text(_config_text(cap=cap, cors=cors))
        return create_app(load_config(path))

    return _make


def _open_session(client: TestClient) -> str:
    response = client.post("/sessions", json={"checks": ["age_over_18"]})
    assert response.status_code == 201
    session_id: str = response.json()["session_id"]
    return session_id


def test_create_session_returns_pinned_request(make_app: MakeApp) -> None:
    with TestClient(make_app()) as client:
        response = client.post("/sessions", json={"checks": ["age_over_18"]})
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"session_id", "transports", "expires_at"}
    assert body["transports"]["dc"]["mediation"] == "required"
    assert body["transports"]["dc"]["digital"]["requests"][0]["protocol"] == "org-iso-mdoc"
    assert body["expires_at"].endswith("Z")


def test_create_session_origin_override(make_app: MakeApp) -> None:
    app = make_app()
    with TestClient(app) as client:
        response = client.post(
            "/sessions",
            json={"checks": ["age_over_18"], "expected_origin": "https://other.example"},
        )
        assert response.status_code == 201
        session = app.state.store.get(response.json()["session_id"])
    assert session.expected_origin == "https://other.example"


def test_create_session_bad_origin_override_is_422(make_app: MakeApp) -> None:
    with TestClient(make_app()) as client:
        response = client.post(
            "/sessions", json={"checks": ["age_over_18"], "expected_origin": "not-an-origin"}
        )
    assert response.status_code == 422


def test_unknown_vocabulary_is_400(make_app: MakeApp) -> None:
    with TestClient(make_app()) as client:
        response = client.post("/sessions", json={"checks": ["age_over_16"]})
    assert response.status_code == 400
    assert response.headers["content-type"] == "application/problem+json"
    assert "age_over_18" in response.json()["detail"]


@pytest.mark.parametrize(
    "payload",
    [
        {"checks": "age_over_18"},
        {"checks": [1]},
        {"checks": ["age_over_18"], "bogus": 1},
        {},
    ],
)
def test_structural_violation_is_422(make_app: MakeApp, payload: dict[str, object]) -> None:
    with TestClient(make_app()) as client:
        response = client.post("/sessions", json=payload)
    assert response.status_code == 422


def test_cap_returns_503(make_app: MakeApp) -> None:
    with TestClient(make_app(cap=1)) as client:
        assert client.post("/sessions", json={"checks": ["age_over_18"]}).status_code == 201
        response = client.post("/sessions", json={"checks": ["age_over_18"]})
    assert response.status_code == 503


def test_response_verified_passes_state_through(
    make_app: MakeApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    async def stub(
        session: object,
        held: object,
        anchors: object,
        body: dict[str, object],
        config: object,
    ) -> dict[str, object]:
        captured.update(held=held, body=body)
        return {"state": "verified", "result": {"age_over_18": True}, "verified_at": "t"}

    monkeypatch.setattr(routes, "verify_response", stub)
    with TestClient(make_app()) as client:
        session_id = _open_session(client)
        response = client.post(f"/sessions/{session_id}/presentation", json={"response": "abc"})
    assert response.status_code == 200
    assert response.json()["state"] == "verified"
    assert captured["held"] is HELD_STUB
    assert captured["body"] == {"response": "abc"}


def test_response_failed_reason_passthrough(
    make_app: MakeApp, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def stub(*_a: object, **_k: object) -> dict[str, object]:
        return {"state": "failed", "reason": "proof-invalid"}

    monkeypatch.setattr(routes, "verify_response", stub)
    with TestClient(make_app()) as client:
        session_id = _open_session(client)
        response = client.post(f"/sessions/{session_id}/presentation", json={"response": "abc"})
    assert response.status_code == 200
    assert response.json() == {"state": "failed", "reason": "proof-invalid"}


def test_response_unknown_is_404(make_app: MakeApp) -> None:
    with TestClient(make_app()) as client:
        response = client.post("/sessions/nope/presentation", json={"response": "abc"})
    assert response.status_code == 404


def test_response_expired_is_404(make_app: MakeApp) -> None:
    app = make_app()
    with TestClient(app) as client:
        session_id = _open_session(client)
        app.state.store._sessions[session_id].expires_at = datetime.now(UTC) - timedelta(seconds=1)
        response = client.post(f"/sessions/{session_id}/presentation", json={"response": "abc"})
    assert response.status_code == 404


def test_response_second_attempt_is_409(make_app: MakeApp, monkeypatch: pytest.MonkeyPatch) -> None:
    async def stub(*_a: object, **_k: object) -> dict[str, object]:
        return {"state": "failed", "reason": "invalid-envelope"}

    monkeypatch.setattr(routes, "verify_response", stub)
    with TestClient(make_app()) as client:
        session_id = _open_session(client)
        url = f"/sessions/{session_id}/presentation"
        assert client.post(url, json={"response": "abc"}).status_code == 200
        response = client.post(url, json={"response": "abc"})
    assert response.status_code == 409


def test_response_shape_violation_is_422(make_app: MakeApp) -> None:
    with TestClient(make_app()) as client:
        session_id = _open_session(client)
        url = f"/sessions/{session_id}/presentation"
        response = client.post(url, json={"response": "abc", "extra": 1})
    assert response.status_code == 422


def test_debug_transcript_happy(make_app: MakeApp) -> None:
    app = make_app()
    with TestClient(app) as client:
        session_id = _open_session(client)
        session = app.state.store.get(session_id)
        expected_hash = build_handover_hash(
            session.dc.encryption_info_b64, session.expected_origin
        ).hex()
        expected_transcript = build_session_transcript(
            session.dc.encryption_info_b64, session.expected_origin
        ).hex()
        response = client.get(f"/debug/transcript/{session_id}")
    assert response.status_code == 200
    assert response.json() == {
        "origin": session.expected_origin,
        "encryption_info_b64": session.dc.encryption_info_b64,
        "handover_hash_hex": expected_hash,
        "transcript_hex": expected_transcript,
    }


def test_debug_transcript_unknown_is_404(make_app: MakeApp) -> None:
    with TestClient(make_app()) as client:
        response = client.get("/debug/transcript/nope")
    assert response.status_code == 404


def test_cors_installed_when_configured(make_app: MakeApp) -> None:
    with TestClient(make_app(cors=["https://a.example"])) as client:
        response = client.options(
            "/sessions/x/presentation",
            headers={
                "Origin": "https://a.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert response.headers.get("access-control-allow-origin") == "https://a.example"


def test_cors_absent_by_default(make_app: MakeApp) -> None:
    with TestClient(make_app()) as client:
        response = client.options(
            "/sessions/x/presentation",
            headers={
                "Origin": "https://a.example",
                "Access-Control-Request-Method": "POST",
            },
        )
    assert "access-control-allow-origin" not in response.headers


def test_openapi_pins_dc_request(make_app: MakeApp) -> None:
    schema = make_app().openapi()
    schemas = schema["components"]["schemas"]
    for name in ("DcRequest", "DcRequestDigital", "DcRequestEntry", "DcRequestData"):
        assert schemas[name]["additionalProperties"] is False
    assert schemas["DcRequestEntry"]["properties"]["protocol"]["const"] == "org-iso-mdoc"
    assert schemas["DcRequest"]["properties"]["mediation"]["const"] == "required"
    requests_schema = schemas["DcRequestDigital"]["properties"]["requests"]
    assert requests_schema["minItems"] == 1
    assert requests_schema["maxItems"] == 1
    assert schemas["DcRequestData"]["properties"]["deviceRequest"]["pattern"] == r"^[A-Za-z0-9_-]+$"
    responses = schema["paths"]["/sessions"]["post"]["responses"]
    assert responses["422"]["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/ValidationProblem"
    }
