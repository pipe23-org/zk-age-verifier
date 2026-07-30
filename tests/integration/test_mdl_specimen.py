"""The vendored upstream example proof verified by each backend.

The example request carries a complete proof but a wire shape the service's
parser rejects (``test_upstream_response.py``), so these tests call the
pylongfellow client directly. The isrg-rust case supplies the assumed empty
device-namespace map (https://github.com/pipe23-org/pylongfellow/issues/29).
"""

import base64
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import cbor2
import pytest
from pylongfellow import Pylongfellow, mdoc
from pylongfellow.mdoc import CircuitSpec

# Calls the client directly, never the socket: skipped under --transport=live.
pytestmark = pytest.mark.inprocess_only

DATA = Path(__file__).parent.parent / "data"

DOC_TYPE = "org.iso.18013.5.1.mDL"


@dataclass(frozen=True)
class Specimen:
    """The specimen's full verify input set, assembled from ``tests/data/``."""

    spec: CircuitSpec
    circuit: bytes
    proof: bytes
    transcript: bytes
    issuer_pk: tuple[int, int]
    timestamp: datetime
    attrs: list[mdoc.RequestedAttribute]


@pytest.fixture(scope="module")
def specimen() -> Specimen:
    """Assemble the verify inputs; proof and transcript come from the wire capture."""
    sidecar = json.loads((DATA / "v6-1attr.json").read_text())
    spec = CircuitSpec(
        system=sidecar["system"],
        circuit_hash=sidecar["circuit_id"],
        num_attributes=sidecar["num_attributes"],
        version=sidecar["version"],
        block_enc_hash=sidecar["block_enc_hash"],
        block_enc_sig=sidecar["block_enc_sig"],
    )

    request = json.loads((DATA / "upstream-verifier-service-request.json").read_text())
    response = cbor2.loads(base64.b64decode(request["ZKDeviceResponseCBOR"]))
    proof: bytes = response["zkDocuments"][0]["proof"]
    transcript = base64.b64decode(request["Transcript"])

    record = json.loads((DATA / "mdl-age-over-18-presentation.json").read_text())
    assert record["doctype"] == DOC_TYPE
    assert transcript == bytes.fromhex(record["transcript_hex"])

    return Specimen(
        spec=spec,
        circuit=(DATA / "v6-1attr.circuit").read_bytes(),
        proof=proof,
        transcript=transcript,
        issuer_pk=(int(record["issuer_pk_x"], 16), int(record["issuer_pk_y"], 16)),
        timestamp=datetime.fromisoformat(record["timestamp"]),
        attrs=[
            mdoc.RequestedAttribute(a["namespace"], a["id"], bytes.fromhex(a["cbor_value_hex"]))
            for a in record["attrs"]
        ],
    )


def test_google_cpp_verifies_its_own_proof(specimen: Specimen) -> None:
    client = Pylongfellow(backend="google-cpp")
    handle = client.load_circuit(specimen.spec, specimen.circuit)
    client.verify(
        handle,
        specimen.issuer_pk,
        specimen.transcript,
        specimen.attrs,
        specimen.timestamp,
        specimen.proof,
        DOC_TYPE,
    )


def test_isrg_rust_verifies_under_assumed_device_namespaces(specimen: Specimen) -> None:
    client = Pylongfellow(backend="isrg-rust")
    handle = client.load_circuit(specimen.spec, specimen.circuit)
    client.verify(
        handle,
        specimen.issuer_pk,
        specimen.transcript,
        specimen.attrs,
        specimen.timestamp,
        specimen.proof,
        DOC_TYPE,
        device_namespaces=b"\xa0",
    )
