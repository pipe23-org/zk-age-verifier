"""Honest path: real prove, real HPKE both directions, real verify."""

from typing import Any

import httpx

from tests.integration.presenter import present
from zk_age_verifier.core.transport.dc import build_session_transcript


def test_honest_presentation_verifies(
    client: httpx.Client, created_session: dict[str, Any], origin: str
) -> None:
    data = present(created_session["transports"]["dc"], origin)

    verdict = client.post(f"/sessions/{created_session['public_id']}/presentation", json=data)
    assert verdict.status_code == 200
    body = verdict.json()
    assert body["state"] == "verified"
    assert body["result"] == {"age_over_18": True}

    debug = client.get(f"/debug/transcript/{created_session['public_id']}")
    assert debug.status_code == 200
    encryption_info_b64 = created_session["transports"]["dc"]["digital"]["requests"][0]["data"][
        "encryptionInfo"
    ]
    expected = build_session_transcript(encryption_info_b64, origin)
    assert debug.json()["transcript_hex"] == expected.hex()
