"""Black-box rows: one knob per presentation-shaped reason, library material, problem+json.

Every row uses only HTTP on the two session routes plus the presenter, so the
same suite runs unchanged against a live socket.
"""

from datetime import timedelta
from typing import Any

import httpx

from tests.integration.presenter import Knobs, present


def _failed_reason(client: httpx.Client, session_id: str, data: dict[str, str]) -> str:
    verdict = client.post(f"/sessions/{session_id}/presentation", json=data)
    assert verdict.status_code == 200
    body = verdict.json()
    assert body["state"] == "failed"
    return str(body["reason"])


def test_wrong_origin_fails_decrypt(client: httpx.Client, created_session: dict[str, Any]) -> None:
    data = present(created_session["transports"]["dc"], "https://attacker.example.org")
    assert _failed_reason(client, created_session["session_id"], data) == "decrypt-failed"


def test_malformed_envelope(
    client: httpx.Client, created_session: dict[str, Any], origin: str
) -> None:
    data = present(created_session["transports"]["dc"], origin, knobs=Knobs(malform_envelope=True))
    assert _failed_reason(client, created_session["session_id"], data) == "invalid-envelope"


def test_standard_mdoc_rejected(
    client: httpx.Client, created_session: dict[str, Any], origin: str
) -> None:
    data = present(created_session["transports"]["dc"], origin, knobs=Knobs(standard_mdoc=True))
    reason = _failed_reason(client, created_session["session_id"], data)
    assert reason == "standard-mdoc-not-accepted"


def test_foreign_circuit(
    client: httpx.Client, created_session: dict[str, Any], origin: str
) -> None:
    foreign = "longfellow-libzk-v1_9_1_0000_0000_0000"
    data = present(created_session["transports"]["dc"], origin, knobs=Knobs(zk_system_id=foreign))
    assert _failed_reason(client, created_session["session_id"], data) == "unsupported-circuit"


def test_stale_proof(client: httpx.Client, created_session: dict[str, Any], origin: str) -> None:
    data = present(
        created_session["transports"]["dc"],
        origin,
        knobs=Knobs(timestamp_offset=timedelta(hours=1)),
    )
    assert _failed_reason(client, created_session["session_id"], data) == "stale-proof"


def test_corrupted_proof(
    client: httpx.Client, created_session: dict[str, Any], origin: str
) -> None:
    data = present(created_session["transports"]["dc"], origin, knobs=Knobs(corrupt_proof=True))
    assert _failed_reason(client, created_session["session_id"], data) == "proof-invalid"


def test_mdl_claim_mismatch(
    client: httpx.Client, created_session: dict[str, Any], origin: str
) -> None:
    data = present(created_session["transports"]["dc"], origin, credential="mdl")
    assert _failed_reason(client, created_session["session_id"], data) == "claim-mismatch"


def test_untrusted_issuer(
    client: httpx.Client, created_session: dict[str, Any], origin: str
) -> None:
    data = present(created_session["transports"]["dc"], origin, credential="eu-av-untrusted")
    assert _failed_reason(client, created_session["session_id"], data) == "untrusted-issuer"


def test_unknown_session_is_problem_json(client: httpx.Client) -> None:
    response = client.post("/sessions/nonexistent/presentation", json={"response": "x"})
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
