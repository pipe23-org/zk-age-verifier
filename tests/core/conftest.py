import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from pylongfellow import mdoc
from pylongfellow.mdoc import ZkSpec

from zk_age_verifier.core.engine.circuits import CIRCUIT_VERSION, NUM_ATTRIBUTES, SYSTEM

SECRET = int.from_bytes(bytes(range(1, 33)), "big")


@pytest.fixture
def spec() -> ZkSpec:
    (match,) = (
        s
        for s in mdoc.zk_specs()
        if s.system == SYSTEM
        and s.version == CIRCUIT_VERSION
        and s.num_attributes == NUM_ATTRIBUTES
    )
    return match


@pytest.fixture
def recipient_key() -> ec.EllipticCurvePublicKey:
    return ec.derive_private_key(SECRET, ec.SECP256R1()).public_key()
