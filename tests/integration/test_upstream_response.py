"""Our envelope parser against upstream verifier-service bytes we did not produce.

The bytes are the ``ZKDeviceResponseCBOR`` field of google/longfellow-zk's
reference verifier-service example request (``tests/data/``; see its README for
provenance). They diverge from the multipaz shape our parser reads in two ways:
the ``zkSystemId`` is a bare circuit hash rather than the six-token identity
string, and ``documentData`` carries no ``deviceSigned`` key. The strict parser
requires ``deviceSigned`` present, so it rejects these bytes; the bare-hash
identity is not itself a rejection cause. This verifier does not accept a real
wallet response with these shapes today.
"""

import base64
import json
from pathlib import Path

import cbor2
import pytest

from zk_age_verifier.core.engine.mdoc_zk import MalformedPresentation, parse_device_response

# Calls the parser directly, never the socket: skipped under --transport=live.
pytestmark = pytest.mark.inprocess_only

EXAMPLE = Path(__file__).parent.parent / "data" / "upstream-verifier-service-request.json"


def _response_bytes() -> bytes:
    request = json.loads(EXAMPLE.read_text())
    return base64.b64decode(request["ZKDeviceResponseCBOR"])


def test_upstream_response_rejected_for_absent_device_signed() -> None:
    with pytest.raises(MalformedPresentation, match="missing or malformed"):
        parse_device_response(_response_bytes())


def test_absent_device_signed_is_the_only_blocker() -> None:
    response = cbor2.loads(_response_bytes())
    document_data = cbor2.loads(response["zkDocuments"][0]["documentData"].value)
    document_data["deviceSigned"] = {}
    response["zkDocuments"][0]["documentData"] = cbor2.CBORTag(24, cbor2.dumps(document_data))

    parsed = parse_device_response(cbor2.dumps(response))

    assert parsed.zk_system_id == "137e5a75ce72735a37c8a72da1a8a0a5df8d13365c2ae3d2c2bd6a0e7197c7c6"
    assert "_" not in parsed.zk_system_id
    assert parsed.doc_type == "org.iso.18013.5.1.mDL"
