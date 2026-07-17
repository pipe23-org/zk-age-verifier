"""Vendored bytes prove and verify against their captured transcript.

The ``eu-av-vendored`` entry is google/longfellow-zk ``mdoc_tests[15]`` byte-exact.
Upstream ships no device key for it, so it cannot drive a live presentation; its
device signature is bound to the transcript captured in ``transcript.bin``. The
check: foreign bytes prove over that captured transcript through the same circuit
the presenter holds, and the proof verifies.
"""

from datetime import UTC, datetime

import pytest
from pylongfellow import mdoc

from tests.integration.presenter import CREDENTIALS_DIR, load_credential
from zk_age_verifier.config import _default_circuit_cache_dir
from zk_age_verifier.core.engine.circuits import load_held_circuit

# Proves and verifies bytes directly, never the socket: skipped under --transport=live.
pytestmark = pytest.mark.inprocess_only

NAMESPACE = "eu.europa.ec.av.1"


def test_vendored_bytes_prove_and_verify() -> None:
    cred = load_credential("eu-av-vendored")
    transcript = (CREDENTIALS_DIR / cred.name / "transcript.bin").read_bytes()
    held = load_held_circuit(_default_circuit_cache_dir())
    attrs = [
        mdoc.RequestedAttribute(NAMESPACE, "age_over_18", cred.claims[NAMESPACE]["age_over_18"])
    ]
    timestamp = datetime.now(UTC).replace(microsecond=0)

    proof = mdoc.prove(
        held.circuit, cred.mdoc_bytes, cred.issuer_pk, transcript, attrs, timestamp, held.spec
    )

    mdoc.verify(
        held.circuit, cred.issuer_pk, transcript, attrs, timestamp, proof, cred.doc_type, held.spec
    )
