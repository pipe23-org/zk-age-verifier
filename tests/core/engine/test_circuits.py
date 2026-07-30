import hashlib
import json
from pathlib import Path

import pytest

from zk_age_verifier.core.engine import circuits
from zk_age_verifier.core.engine.circuits import (
    CIRCUIT_VERSION,
    NUM_ATTRIBUTES,
    SYSTEM,
    HeldCircuit,
    load_held_circuit,
    zk_system_id,
)

HELD_ZK_SYSTEM_ID = (
    "longfellow-libzk-v1_7_1_4151_4096_"
    "8d079211715200ff06c5109639245502bfe94aa869908d31176aae4016182121"
)

ANNEX_EXAMPLE_ZK_SYSTEM_ID = (
    "longfellow-libzk-v1_6_1_4096_2945_"
    "137e5a75ce72735a37c8a72da1a8a0a5df8d13365c2ae3d2c2bd6a0e7197c7c6"
)


def _sidecar(blob: bytes, **overrides: object) -> dict[str, object]:
    sidecar: dict[str, object] = {
        "system": SYSTEM,
        "circuit_id": "abc123",
        "byte_sha256": hashlib.sha256(blob).hexdigest(),
        "version": CIRCUIT_VERSION,
        "num_attributes": NUM_ATTRIBUTES,
        "block_enc_hash": 4151,
        "block_enc_sig": 4096,
    }
    sidecar.update(overrides)
    return sidecar


def _stage(tmp_path: Path, blob: bytes, sidecar: dict[str, object]) -> None:
    circuits_dir = tmp_path / "circuits"
    circuits_dir.mkdir()
    (circuits_dir / "v7-1attr.circuit").write_bytes(blob)
    (circuits_dir / "v7-1attr.json").write_text(json.dumps(sidecar))


def test_load_held_circuit_reads_vendored_artifact() -> None:
    held = load_held_circuit(backend="google-cpp")
    assert isinstance(held, HeldCircuit)
    assert held.spec.system == SYSTEM
    assert held.spec.version == CIRCUIT_VERSION
    assert held.spec.num_attributes == NUM_ATTRIBUTES
    assert held.zk_system_id == HELD_ZK_SYSTEM_ID
    assert held.handle.backend.name == "google-cpp"
    assert held.handle.spec == held.spec


def test_load_held_circuit_integrity_failure_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob = b"CIRCUIT-BYTES"
    sidecar = _sidecar(blob, byte_sha256="0" * 64)
    _stage(tmp_path, blob, sidecar)
    monkeypatch.setattr(circuits, "files", lambda package: tmp_path)
    with pytest.raises(RuntimeError, match="circuit blob hashes to"):
        load_held_circuit(backend="google-cpp")


def test_load_held_circuit_pin_mismatch_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    blob = b"CIRCUIT-BYTES"
    sidecar = _sidecar(blob, version=6)
    _stage(tmp_path, blob, sidecar)
    monkeypatch.setattr(circuits, "files", lambda package: tmp_path)
    with pytest.raises(RuntimeError, match="pinned to longfellow-libzk-v1 v7"):
        load_held_circuit(backend="google-cpp")


def test_annex_example_is_a_skew_tripwire() -> None:
    """Guard the AV profile's documented example so annex or pin drift is detected.

    This is not a compatibility claim: the profile's example is at circuit v6 and
    would fail this verifier with unsupported-circuit. On failure, either the annex
    revved (re-capture; if it now matches our held identity, promote to exact-string
    agreement) or our pinned version moved (re-check both pins).
    """
    # av-doc-technical-specification docs/annexes/annex-A/annex-A-av-profile.md:668,
    # HEAD 3a213e8, 2026-05-04.
    system, version, num_attributes, block_enc_hash, block_enc_sig, circuit_hash = (
        ANNEX_EXAMPLE_ZK_SYSTEM_ID.split("_")
    )
    assert system == "longfellow-libzk-v1"
    assert version == "6"
    assert num_attributes == "1"
    assert block_enc_hash == "4096"
    assert block_enc_sig == "2945"
    assert circuit_hash == "137e5a75ce72735a37c8a72da1a8a0a5df8d13365c2ae3d2c2bd6a0e7197c7c6"
    assert ANNEX_EXAMPLE_ZK_SYSTEM_ID != HELD_ZK_SYSTEM_ID


def test_zk_system_id_from_spec() -> None:
    held = load_held_circuit(backend="google-cpp")
    assert zk_system_id(held.spec) == HELD_ZK_SYSTEM_ID
