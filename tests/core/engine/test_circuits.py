from pathlib import Path

import pytest
from pylongfellow import mdoc
from pylongfellow.mdoc import ZkSpec

from zk_age_verifier.core.engine.circuits import (
    SYSTEM,
    HeldCircuit,
    ensure_circuit,
    load_held_circuit,
    zk_system_id,
)


def _spec(
    circuit_hash: str = "abc123",
    *,
    version: int = 7,
    num_attributes: int = 1,
    block_enc_hash: int = 4151,
    block_enc_sig: int = 4096,
) -> ZkSpec:
    return ZkSpec(
        system=SYSTEM,
        circuit_hash=circuit_hash,
        num_attributes=num_attributes,
        version=version,
        block_enc_hash=block_enc_hash,
        block_enc_sig=block_enc_sig,
    )


def test_load_held_circuit_unpinned_table_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        mdoc,
        "zk_specs",
        lambda: (_spec(version=6), _spec(version=5, num_attributes=2)),
    )
    with pytest.raises(RuntimeError, match=r"found 0.*\(5, 2\), \(6, 1\)"):
        load_held_circuit(tmp_path / "circuits")


def test_ensure_circuit_cache_miss_generates_and_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mdoc, "generate_circuit", lambda s: b"STUB")
    monkeypatch.setattr(mdoc, "circuit_id", lambda c: "abc123")
    cache_dir = tmp_path / "circuits"
    assert ensure_circuit(_spec(), cache_dir) == b"STUB"
    assert (cache_dir / "abc123").read_bytes() == b"STUB"
    assert not (cache_dir / "abc123.tmp").exists()


def test_ensure_circuit_cache_hit_skips_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "circuits"
    cache_dir.mkdir(parents=True)
    (cache_dir / "abc123").write_bytes(b"CACHED")

    def _no_generate(spec: ZkSpec) -> bytes:
        raise AssertionError("generate_circuit called on a cache hit")

    monkeypatch.setattr(mdoc, "generate_circuit", _no_generate)
    monkeypatch.setattr(mdoc, "circuit_id", lambda c: "abc123")
    assert ensure_circuit(_spec(), cache_dir) == b"CACHED"


def test_ensure_circuit_corrupted_cache_regenerates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache_dir = tmp_path / "circuits"
    cache_dir.mkdir(parents=True)
    (cache_dir / "abc123").write_bytes(b"CORRUPT")
    monkeypatch.setattr(mdoc, "generate_circuit", lambda s: b"FRESH")
    monkeypatch.setattr(
        mdoc,
        "circuit_id",
        lambda c: "abc123" if c == b"FRESH" else "wronghash",
    )
    assert ensure_circuit(_spec(), cache_dir) == b"FRESH"
    assert (cache_dir / "abc123").read_bytes() == b"FRESH"


def test_ensure_circuit_post_generation_mismatch_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mdoc, "generate_circuit", lambda s: b"FRESH")
    monkeypatch.setattr(mdoc, "circuit_id", lambda c: "wronghash")
    with pytest.raises(RuntimeError, match="generated circuit hashes"):
        ensure_circuit(_spec(), tmp_path / "circuits")


def test_load_held_circuit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pinned = _spec()
    monkeypatch.setattr(mdoc, "zk_specs", lambda: (pinned,))
    monkeypatch.setattr(mdoc, "generate_circuit", lambda s: b"STUB")
    monkeypatch.setattr(mdoc, "circuit_id", lambda c: "abc123")
    held = load_held_circuit(tmp_path / "circuits")
    assert isinstance(held, HeldCircuit)
    assert held.spec is pinned
    assert held.circuit == b"STUB"
    assert held.zk_system_id == zk_system_id(pinned)


HELD_ZK_SYSTEM_ID = (
    "longfellow-libzk-v1_7_1_4151_4096_"
    "8d079211715200ff06c5109639245502bfe94aa869908d31176aae4016182121"
)

ANNEX_EXAMPLE_ZK_SYSTEM_ID = (
    "longfellow-libzk-v1_6_1_4096_2945_"
    "137e5a75ce72735a37c8a72da1a8a0a5df8d13365c2ae3d2c2bd6a0e7197c7c6"
)


def test_held_identity_pinned_to_spec_table(spec: ZkSpec) -> None:
    # Pins the circuit identity against pylongfellow's compiled-in spec table
    # (upstream zk_spec.cc, transitive through the pylongfellow pin): a dependency
    # bump that moves the identity must fail here, not at the phone.
    assert zk_system_id(spec) == HELD_ZK_SYSTEM_ID


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
