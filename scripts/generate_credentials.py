"""Generate the constructed test credentials and their certificate family.

Rebuilds the vendored EU AV credential's exact CBOR shapes under locally held
keys, then constructs three entries from those shapes: ``eu-av`` (the honest
default), ``mdl`` (a mobile driving licence with the same shapes under doctype
``org.iso.18013.5.1.mDL``, used to drive ``claim-mismatch``), and
``eu-av-untrusted`` (``eu-av``'s shapes and claims with its leaf signed by a
second CA discarded in the same run and committed nowhere, used to drive
``untrusted-issuer``). Each entry gets a fresh issuer keypair signing its MSO,
a leaf certificate binding that key, and a device keypair whose private half is
written into the entry so the presenter can sign each session's fresh
transcript. The trusted leaves chain to a test CA (key generated in-memory and
discarded).

Before signing anything, the script validates its own ``DeviceAuthentication``
encoding against the vendored credential's device signature, and it runs a
pylongfellow prove/verify round-trip over each constructed credential as the
acceptance check; that is pylongfellow's only role in this script.

Outputs are written only to ``tests/integration/credentials/``: the CA PEM as
``test-anchor.pem`` (what test configs name as their ``pem`` trust source), the
vendored entry's ``leaf.pem``, and each constructed entry's ``credential.cbor``,
``leaf.pem``, ``device-key.pem``, and ``manifest.toml``. Rerunning regenerates
the whole family; recommit the outputs.
"""

import hashlib
import os
import tomllib
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import cbor2
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)
from cryptography.x509.oid import NameOID

from zk_age_verifier.config import _default_circuit_cache_dir
from zk_age_verifier.core.engine.circuits import load_held_circuit

CREDENTIALS_DIR = Path(__file__).resolve().parents[1] / "tests/integration/credentials"
TEMPLATE_ENTRY = "eu-av-vendored"

MDL_DOC_TYPE = "org.iso.18013.5.1.mDL"
MDL_NAMESPACE = "org.iso.18013.5.1"

# COSE protected header {1: -7}: ES256, the only algorithm on this path.
COSE_ES256_PROTECTED = b"\xa1\x01\x26"

# Certificate and MSO validity, one window for the whole family. Fixed rather
# than derived from the run date so a regeneration changes only what the fresh
# keys force to change.
VALID_FROM = datetime(2026, 7, 1, tzinfo=UTC)
VALID_UNTIL = datetime(2036, 7, 1, tzinfo=UTC)


def _tdate(value: datetime) -> cbor2.CBORTag:
    """Encode a datetime the way the vendored MSO does: tag 0, whole seconds, Zulu."""
    return cbor2.CBORTag(0, value.strftime("%Y-%m-%dT%H:%M:%SZ"))


def _device_authentication_bytes(transcript: bytes, doc_type: str, namespaces: object) -> bytes:
    """Build ``DeviceAuthenticationBytes``, the device signature's detached payload."""
    authentication = ["DeviceAuthentication", cbor2.loads(transcript), doc_type, namespaces]
    return cbor2.dumps(cbor2.CBORTag(24, cbor2.dumps(authentication)))


def _cose_sign(key: ec.EllipticCurvePrivateKey, payload: bytes) -> bytes:
    """Sign a COSE ``Signature1`` structure over the payload, returning raw ``r||s``."""
    structure = cbor2.dumps(["Signature1", COSE_ES256_PROTECTED, b"", payload])
    r, s = decode_dss_signature(key.sign(structure, ec.ECDSA(hashes.SHA256())))
    return r.to_bytes(32, "big") + s.to_bytes(32, "big")


def _cose_verify(key: ec.EllipticCurvePublicKey, payload: bytes, signature: bytes) -> None:
    """Check a COSE ``Signature1`` signature; raises ``InvalidSignature`` on mismatch."""
    structure = cbor2.dumps(["Signature1", COSE_ES256_PROTECTED, b"", payload])
    der = encode_dss_signature(
        int.from_bytes(signature[:32], "big"), int.from_bytes(signature[32:], "big")
    )
    key.verify(der, structure, ec.ECDSA(hashes.SHA256()))


def _check_encoding_against_template(document: dict[str, Any], transcript: bytes) -> None:
    """Verify the template's device signature with our own encoder before we sign with it."""
    mso = cbor2.loads(cbor2.loads(document["issuerSigned"]["issuerAuth"][2]).value)
    cose_key = mso["deviceKeyInfo"]["deviceKey"]
    device_pub = ec.EllipticCurvePublicNumbers(
        int.from_bytes(cose_key[-2], "big"), int.from_bytes(cose_key[-3], "big"), ec.SECP256R1()
    ).public_key()
    payload = _device_authentication_bytes(
        transcript, document["docType"], document["deviceSigned"]["nameSpaces"]
    )
    signature = document["deviceSigned"]["deviceAuth"]["deviceSignature"][3]
    _cose_verify(device_pub, payload, signature)


def _make_certificate(
    subject_cn: str,
    public_key: ec.EllipticCurvePublicKey,
    issuer_cn: str,
    signing_key: ec.EllipticCurvePrivateKey,
    *,
    ca: bool,
) -> x509.Certificate:
    """Build one certificate of the family; the CA is the only self-signed one."""

    def _name(cn: str) -> x509.Name:
        """Build the two-attribute name every family certificate uses."""
        return x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, cn),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "pipe23"),
            ]
        )

    builder = (
        x509.CertificateBuilder()
        .subject_name(_name(subject_cn))
        .issuer_name(_name(issuer_cn))
        .public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(VALID_FROM)
        .not_valid_after(VALID_UNTIL)
    )
    if ca:
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None), critical=True
        )
    return builder.sign(signing_key, hashes.SHA256())


def _template_items(template: dict[str, Any]) -> tuple[str, dict[str, list[dict[str, Any]]]]:
    """Read the template's doctype and issuer-signed items, one list per namespace."""
    document = template["documents"][0]
    items: dict[str, list[dict[str, Any]]] = {}
    for space, wrapped_items in document["issuerSigned"]["nameSpaces"].items():
        items[space] = [cbor2.loads(wrapped.value) for wrapped in wrapped_items]
    return document["docType"], items


def _age_namespace(document: dict[str, Any]) -> str:
    """Return the namespace of the document's ``age_over_18`` element."""
    for space, wrapped_items in document["issuerSigned"]["nameSpaces"].items():
        for wrapped in wrapped_items:
            if cbor2.loads(wrapped.value)["elementIdentifier"] == "age_over_18":
                return space
    raise KeyError("credential holds no age_over_18 element")


def _rebuild_credential(
    doc_type: str,
    items: dict[str, list[dict[str, Any]]],
    issuer_key: ec.EllipticCurvePrivateKey,
    device_key: ec.EllipticCurvePrivateKey,
    leaf_der: bytes,
    acceptance_transcript: bytes,
) -> bytes:
    """Issue the given content under our keys, mirroring the template's CBOR shapes.

    Every map is built in the template's insertion order. The committed device
    signature is over ``acceptance_transcript`` so the committed bytes are
    self-consistent; the presenter replaces it with one over each session's
    transcript.
    """
    namespaces: dict[str, list[cbor2.CBORTag]] = {}
    digests: dict[str, dict[int, bytes]] = {}
    for space, space_items in items.items():
        for item in space_items:
            rebuilt = cbor2.CBORTag(
                24,
                cbor2.dumps(
                    {
                        "random": os.urandom(16),
                        "digestID": item["digestID"],
                        "elementIdentifier": item["elementIdentifier"],
                        "elementValue": item["elementValue"],
                    }
                ),
            )
            namespaces.setdefault(space, []).append(rebuilt)
            digests.setdefault(space, {})[item["digestID"]] = hashlib.sha256(
                cbor2.dumps(rebuilt)
            ).digest()

    device_numbers = device_key.public_key().public_numbers()
    mso = {
        "docType": doc_type,
        "version": "1.0",
        "digestAlgorithm": "SHA-256",
        "valueDigests": digests,
        "deviceKeyInfo": {
            "deviceKey": {
                1: 2,
                -1: 1,
                -2: device_numbers.x.to_bytes(32, "big"),
                -3: device_numbers.y.to_bytes(32, "big"),
            }
        },
        "validityInfo": {
            "signed": _tdate(VALID_FROM),
            "validFrom": _tdate(VALID_FROM),
            "validUntil": _tdate(VALID_UNTIL),
        },
    }
    mso_payload = cbor2.dumps(cbor2.CBORTag(24, cbor2.dumps(mso)))

    device_namespaces = cbor2.CBORTag(24, cbor2.dumps({}))
    device_payload = _device_authentication_bytes(
        acceptance_transcript, doc_type, device_namespaces
    )

    return cbor2.dumps(
        {
            "version": "1.0",
            "documents": [
                {
                    "docType": doc_type,
                    "issuerSigned": {
                        "nameSpaces": namespaces,
                        "issuerAuth": [
                            COSE_ES256_PROTECTED,
                            {33: leaf_der},
                            mso_payload,
                            _cose_sign(issuer_key, mso_payload),
                        ],
                    },
                    "deviceSigned": {
                        "nameSpaces": device_namespaces,
                        "deviceAuth": {
                            "deviceSignature": [
                                COSE_ES256_PROTECTED,
                                {},
                                None,
                                _cose_sign(device_key, device_payload),
                            ]
                        },
                    },
                }
            ],
            "status": 0,
        }
    )


def _write_manifest(
    entry: Path,
    doc_type: str,
    items: dict[str, list[dict[str, Any]]],
    issuer_key: ec.EllipticCurvePrivateKey,
    *,
    trusted: bool,
) -> None:
    """Write a constructed entry's ontology instance."""
    numbers = issuer_key.public_key().public_numbers()
    claims_lines = []
    for space, space_items in items.items():
        claims_lines.append(f'[claims."{space}"]')
        for item in space_items:
            value_hex = cbor2.dumps(item["elementValue"]).hex()
            claims_lines.append(f'{item["elementIdentifier"]} = "{value_hex}"')
    claims = "\n".join(claims_lines)
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

{claims}
"""
    )


def _accept(credential: bytes, issuer_key: ec.EllipticCurvePrivateKey, transcript: bytes) -> None:
    """Prove and verify over the constructed credential, the acceptance check."""
    from pylongfellow import mdoc

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
    items: dict[str, list[dict[str, Any]]],
    ca_key: ec.EllipticCurvePrivateKey,
    ca_cn: str,
    acceptance_transcript: bytes,
    *,
    trusted: bool,
) -> None:
    """Construct one credential entry: fresh keys, a leaf under ``ca_key``, and its files."""
    issuer_key = ec.generate_private_key(ec.SECP256R1())
    device_key = ec.generate_private_key(ec.SECP256R1())
    leaf = _make_certificate(
        f"zk-age-verifier {name} issuer", issuer_key.public_key(), ca_cn, ca_key, ca=False
    )
    credential = _rebuild_credential(
        doc_type,
        items,
        issuer_key,
        device_key,
        leaf.public_bytes(serialization.Encoding.DER),
        acceptance_transcript,
    )
    _accept(credential, issuer_key, acceptance_transcript)
    print(f"acceptance: prove/verify round-trip over {name} succeeded")

    entry = CREDENTIALS_DIR / name
    entry.mkdir(exist_ok=True)
    (entry / "credential.cbor").write_bytes(credential)
    (entry / "leaf.pem").write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    (entry / "device-key.pem").write_bytes(
        device_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    _write_manifest(entry, doc_type, items, issuer_key, trusted=trusted)
    print(f"wrote {entry}")


def main() -> None:
    """Regenerate the certificate family and the constructed credentials."""
    template_dir = CREDENTIALS_DIR / TEMPLATE_ENTRY
    template = cbor2.loads((template_dir / "credential.cbor").read_bytes())
    template_manifest = tomllib.loads((template_dir / "manifest.toml").read_text())
    captured_transcript = (template_dir / template_manifest["device"]["transcript"]).read_bytes()
    _check_encoding_against_template(template["documents"][0], captured_transcript)
    print("DeviceAuthentication encoding validated against the template's device signature")

    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_cn = "zk-age-verifier test CA"
    ca_cert = _make_certificate(ca_cn, ca_key.public_key(), ca_cn, ca_key, ca=True)

    # The second CA is discarded with the run: no PEM of it is written, so a leaf
    # it signs chains to no configured anchor.
    untrusted_ca_key = ec.generate_private_key(ec.SECP256R1())
    untrusted_ca_cn = "zk-age-verifier untrusted CA"

    handover = hashlib.sha256(b"zk-age-verifier constructed-credential generation").digest()
    acceptance_transcript = cbor2.dumps([None, None, ["dcapi", handover]])

    doc_type, items = _template_items(template)
    mdl_items: dict[str, list[dict[str, Any]]] = {
        MDL_NAMESPACE: [{"digestID": 0, "elementIdentifier": "age_over_18", "elementValue": True}]
    }
    _build_entry("eu-av", doc_type, items, ca_key, ca_cn, acceptance_transcript, trusted=True)
    _build_entry("mdl", MDL_DOC_TYPE, mdl_items, ca_key, ca_cn, acceptance_transcript, trusted=True)
    _build_entry(
        "eu-av-untrusted",
        doc_type,
        items,
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
    vendored_leaf = _make_certificate(
        "zk-age-verifier vendored issuer", vendored_issuer_pub, ca_cn, ca_key, ca=False
    )
    (CREDENTIALS_DIR / "test-anchor.pem").write_bytes(
        ca_cert.public_bytes(serialization.Encoding.PEM)
    )
    (template_dir / "leaf.pem").write_bytes(vendored_leaf.public_bytes(serialization.Encoding.PEM))
    print(f"wrote {CREDENTIALS_DIR / 'test-anchor.pem'}")
    print(f"wrote {template_dir / 'leaf.pem'}")


if __name__ == "__main__":
    main()
