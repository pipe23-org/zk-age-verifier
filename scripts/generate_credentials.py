"""Generate the constructed test credentials and their certificate family.

Rebuilds the vendored EU AV credential's claims under locally held keys through
``pylongfellow.mdoc.create_credential``, constructing three entries: ``eu-av``
(the honest default), ``mdl`` (a mobile driving licence with the same claims
under doctype ``org.iso.18013.5.1.mDL``, used to drive ``claim-mismatch``), and
``eu-av-untrusted`` (``eu-av``'s claims with its leaf signed by a second CA
discarded in the same run and committed nowhere, used to drive
``untrusted-issuer``). Each entry gets a fresh issuer keypair signing its MSO,
a leaf certificate binding that key, and a device keypair whose private half is
written into the entry so the presenter can sign each session's fresh
transcript. The trusted leaves chain to a test CA (key generated in-memory and
discarded).

Before building anything, the script checks pylongfellow's
``DeviceAuthentication`` encoding against the vendored credential's device
signature, and it runs a pylongfellow prove/verify round-trip over each
constructed credential as the acceptance check.

Outputs are written only to ``tests/integration/credentials/``: the CA PEM as
``test-anchor.pem`` (what test configs name as their ``pem`` trust source), the
vendored entry's ``leaf.pem``, and each constructed entry's ``credential.cbor``,
``leaf.pem``, ``device-key.pem``, and ``manifest.toml``. Rerunning regenerates
the whole family; recommit the outputs.
"""

import hashlib
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import cbor2
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pylongfellow import mdoc

from zk_age_verifier.config import _default_circuit_cache_dir
from zk_age_verifier.core.engine.circuits import load_held_circuit

CREDENTIALS_DIR = Path(__file__).resolve().parents[1] / "tests/integration/credentials"
TEMPLATE_ENTRY = "eu-av-vendored"

MDL_DOC_TYPE = "org.iso.18013.5.1.mDL"
MDL_NAMESPACE = "org.iso.18013.5.1"

# Certificate and MSO validity, one window for the whole family. Fixed rather
# than derived from the run date so a regeneration changes only what the fresh
# keys force to change.
VALID_FROM = datetime(2026, 7, 1, tzinfo=UTC)
VALID_UNTIL = datetime(2036, 7, 1, tzinfo=UTC)


def _template_claims(template: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    """Read the template's doctype and issuer-signed claims, one map per namespace."""
    document = template["documents"][0]
    claims: dict[str, dict[str, Any]] = {}
    for space, wrapped_items in document["issuerSigned"]["nameSpaces"].items():
        for wrapped in wrapped_items:
            item = cbor2.loads(wrapped.value)
            claims.setdefault(space, {})[item["elementIdentifier"]] = item["elementValue"]
    return document["docType"], claims


def _age_namespace(document: dict[str, Any]) -> str:
    """Return the namespace of the document's ``age_over_18`` element."""
    for space, wrapped_items in document["issuerSigned"]["nameSpaces"].items():
        for wrapped in wrapped_items:
            if cbor2.loads(wrapped.value)["elementIdentifier"] == "age_over_18":
                return space
    raise KeyError("credential holds no age_over_18 element")


def _write_manifest(
    entry: Path,
    doc_type: str,
    claims: dict[str, dict[str, Any]],
    issuer_key: ec.EllipticCurvePrivateKey,
    *,
    trusted: bool,
) -> None:
    """Write a constructed entry's ontology instance."""
    numbers = issuer_key.public_key().public_numbers()
    claims_lines = []
    for space, elements in claims.items():
        claims_lines.append(f'[claims."{space}"]')
        for identifier, value in elements.items():
            claims_lines.append(f'{identifier} = "{cbor2.dumps(value).hex()}"')
    claims_text = "\n".join(claims_lines)
    status = "trusted" if trusted else "untrusted"
    (entry / "manifest.toml").write_text(
        f"""[credential]
doctype = "{doc_type}"
source = "constructed"

[provenance]
generator = "scripts/generate_credentials.py"
template = "{TEMPLATE_ENTRY}"
generated = {date.today().isoformat()}

[issuer]
pk_x = "{numbers.x:064x}"
pk_y = "{numbers.y:064x}"

[device]
key = "device-key.pem"

[trust]
status = "{status}"
certificate = "leaf.pem"

{claims_text}
"""
    )


def _accept(credential: bytes, issuer_key: ec.EllipticCurvePrivateKey, transcript: bytes) -> None:
    """Prove and verify over the constructed credential, the acceptance check."""
    held = load_held_circuit(_default_circuit_cache_dir())
    numbers = issuer_key.public_key().public_numbers()
    document = cbor2.loads(credential)["documents"][0]
    doc_type = document["docType"]
    namespace = _age_namespace(document)
    attrs = [mdoc.RequestedAttribute(namespace, "age_over_18", b"\xf5")]
    timestamp = datetime.now(UTC).replace(microsecond=0)
    proof = mdoc.prove(
        held.circuit, credential, (numbers.x, numbers.y), transcript, attrs, timestamp, held.spec
    )
    mdoc.verify(
        held.circuit,
        (numbers.x, numbers.y),
        transcript,
        attrs,
        timestamp,
        proof,
        doc_type,
        held.spec,
    )


def _build_entry(
    name: str,
    doc_type: str,
    claims: dict[str, dict[str, Any]],
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cn: str,
    acceptance_transcript: bytes,
    *,
    trusted: bool,
) -> None:
    """Construct one credential entry: fresh keys, a leaf under ``ca_key``, and its files."""
    issuer_key = ec.generate_private_key(ec.SECP256R1())
    leaf = mdoc.create_certificate(
        f"zk-age-verifier {name} issuer",
        issuer_key.public_key(),
        ca_cn,
        ca_key,
        VALID_FROM,
        VALID_UNTIL,
    )
    created = mdoc.create_credential(
        doc_type,
        claims,
        acceptance_transcript,
        VALID_FROM,
        VALID_UNTIL,
        issuer_key=issuer_key,
        issuer_certificate=leaf,
    )
    _accept(created.mdoc, issuer_key, acceptance_transcript)
    print(f"acceptance: prove/verify round-trip over {name} succeeded")

    entry = CREDENTIALS_DIR / name
    entry.mkdir(exist_ok=True)
    (entry / "credential.cbor").write_bytes(created.mdoc)
    (entry / "leaf.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    (entry / "device-key.pem").write_bytes(
        created.device_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    _write_manifest(entry, doc_type, claims, issuer_key, trusted=trusted)
    print(f"wrote {entry}")


def main() -> None:
    """Regenerate the certificate family and the constructed credentials."""
    template_dir = CREDENTIALS_DIR / TEMPLATE_ENTRY
    template_bytes = (template_dir / "credential.cbor").read_bytes()
    template = cbor2.loads(template_bytes)
    template_manifest = tomllib.loads((template_dir / "manifest.toml").read_text())
    captured_transcript = (template_dir / template_manifest["device"]["transcript"]).read_bytes()
    mdoc.verify_device_authentication(template_bytes, captured_transcript)
    print("DeviceAuthentication encoding validated against the template's device signature")

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cn = "zk-age-verifier test CA"
    ca_cert = mdoc.create_certificate(
        ca_cn, ca_key.public_key(), ca_cn, ca_key, VALID_FROM, VALID_UNTIL, ca=True
    )

    # The second CA is discarded with the run: no PEM of it is written, so a leaf
    # it signs chains to no configured anchor.
    untrusted_ca_key = ec.generate_private_key(ec.SECP256R1())
    untrusted_ca_cn = "zk-age-verifier untrusted CA"

    handover = hashlib.sha256(b"zk-age-verifier constructed-credential generation").digest()
    acceptance_transcript = cbor2.dumps([None, None, ["dcapi", handover]])

    doc_type, claims = _template_claims(template)
    mdl_claims: dict[str, dict[str, Any]] = {MDL_NAMESPACE: {"age_over_18": True}}
    _build_entry("eu-av", doc_type, claims, ca_key, ca_cn, acceptance_transcript, trusted=True)
    _build_entry(
        "mdl", MDL_DOC_TYPE, mdl_claims, ca_key, ca_cn, acceptance_transcript, trusted=True
    )
    _build_entry(
        "eu-av-untrusted",
        doc_type,
        claims,
        untrusted_ca_key,
        untrusted_ca_cn,
        acceptance_transcript,
        trusted=False,
    )

    vendored_issuer_pub = ec.EllipticCurvePublicNumbers(
        int(template_manifest["issuer"]["pk_x"], 16),
        int(template_manifest["issuer"]["pk_y"], 16),
        ec.SECP256R1(),
    ).public_key()
    vendored_leaf = mdoc.create_certificate(
        "zk-age-verifier vendored issuer",
        vendored_issuer_pub,
        ca_cn,
        ca_key,
        VALID_FROM,
        VALID_UNTIL,
    )
    (CREDENTIALS_DIR / "test-anchor.pem").write_bytes(
        ca_cert.public_bytes(serialization.Encoding.PEM)
    )
    (template_dir / "leaf.pem").write_bytes(vendored_leaf.public_bytes(serialization.Encoding.PEM))
    print(f"wrote {CREDENTIALS_DIR / 'test-anchor.pem'}")
    print(f"wrote {template_dir / 'leaf.pem'}")


if __name__ == "__main__":
    main()
