import httpx
from fastapi.testclient import TestClient

from tests.conftest import VERIFIER_URL, Verifier

PROBLEM_JSON = "application/problem+json"


def test_session_forwards_body_to_verifier_sessions(client: TestClient, verifier: Verifier) -> None:
    verifier.response = httpx.Response(
        201,
        json={
            "session_id": "abc",
            "transports": {"dc": {}},
            "expires_at": "2026-07-14T00:00:00Z",
        },
    )
    reply = client.post("/av/session", json={"checks": ["age_over_18"]})

    assert reply.status_code == 201
    assert reply.json()["session_id"] == "abc"
    (forwarded,) = verifier.requests
    assert forwarded.method == "POST"
    assert str(forwarded.url) == f"{VERIFIER_URL}/sessions"
    assert forwarded.content == b'{"checks":["age_over_18"]}'


def test_session_passes_problem_json_through(client: TestClient, verifier: Verifier) -> None:
    verifier.response = httpx.Response(
        400,
        json={"title": "Bad Request", "detail": "unsupported vocabulary"},
        headers={"content-type": PROBLEM_JSON},
    )
    reply = client.post("/av/session", json={"checks": ["age_over_21"]})

    assert reply.status_code == 400
    assert reply.headers["content-type"] == PROBLEM_JSON
    assert reply.json()["detail"] == "unsupported vocabulary"


def test_response_forwards_to_presentation_route(client: TestClient, verifier: Verifier) -> None:
    verifier.response = httpx.Response(
        200, json={"state": "verified", "result": {"age_over_18": True}}
    )
    reply = client.post("/av/response?session=xyz", json={"response": "b64url"})

    assert reply.status_code == 200
    assert reply.json()["state"] == "verified"
    (forwarded,) = verifier.requests
    assert str(forwarded.url) == f"{VERIFIER_URL}/sessions/xyz/presentation"
    assert forwarded.content == b'{"response":"b64url"}'


def test_response_passes_failed_verdict_through(client: TestClient, verifier: Verifier) -> None:
    verifier.response = httpx.Response(200, json={"state": "failed", "reason": "decrypt-failed"})
    reply = client.post("/av/response?session=xyz", json={"response": "b64url"})

    assert reply.status_code == 200
    assert reply.json() == {"state": "failed", "reason": "decrypt-failed"}


def test_response_passes_session_errors_through(client: TestClient, verifier: Verifier) -> None:
    verifier.response = httpx.Response(
        409,
        json={"title": "Conflict", "detail": "session already attempted"},
        headers={"content-type": PROBLEM_JSON},
    )
    reply = client.post("/av/response?session=xyz", json={"response": "b64url"})

    assert reply.status_code == 409
    assert reply.headers["content-type"] == PROBLEM_JSON


def test_response_requires_session_query_param(client: TestClient, verifier: Verifier) -> None:
    reply = client.post("/av/response", json={"response": "b64url"})

    assert reply.status_code == 422
    assert verifier.requests == []


def test_index_serves_gate_page(client: TestClient) -> None:
    reply = client.get("/")

    assert reply.status_code == 200
    assert "text/html" in reply.headers["content-type"]
    assert "/static/dc.js" in reply.text


def test_static_module_is_served(client: TestClient) -> None:
    reply = client.get("/static/dc.js")

    assert reply.status_code == 200
    assert "navigator.credentials.get" in reply.text
