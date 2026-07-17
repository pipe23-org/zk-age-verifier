from datetime import UTC, datetime, timedelta

import cbor2
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.x509.oid import NameOID

from zk_age_verifier.core.engine.mdoc_zk import (
    MalformedPresentation,
    StandardMdocNotAccepted,
    ZkDocument,
    parse_device_response,
)

DOC_TYPE = "eu.europa.ec.av.1"
ZK_SYSTEM_ID = "longfellow-libzk-v1_7_1_4151_4096_deadbeef"
TIMESTAMP = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)


def _leaf_cert_der() -> bytes:
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "DS")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(TIMESTAMP - timedelta(days=1))
        .not_valid_after(TIMESTAMP + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(Encoding.DER)


def _document_data(**overrides: object) -> bytes:
    data = {
        "zkSystemId": ZK_SYSTEM_ID,
        "docType": DOC_TYPE,
        "timestamp": TIMESTAMP,
        "issuerSigned": {DOC_TYPE: [{"elementIdentifier": "age_over_18", "elementValue": True}]},
        "deviceSigned": {},
        "msoX5chain": _leaf_cert_der(),
    }
    data.update(overrides)
    return cbor2.dumps(data)


def _zk_document(**overrides: object) -> dict[str, object]:
    doc: dict[str, object] = {
        "proof": b"proof-bytes",
        "documentData": cbor2.CBORTag(24, _document_data()),
    }
    doc.update(overrides)
    return doc


def _device_response(**overrides: object) -> bytes:
    response: dict[str, object] = {
        "version": "1.0",
        "status": 0,
        "zkDocuments": [_zk_document()],
    }
    response.update(overrides)
    return cbor2.dumps(response)


def test_parse_device_response_happy() -> None:
    document = parse_device_response(_device_response())
    assert isinstance(document, ZkDocument)
    assert document.proof == b"proof-bytes"
    assert document.zk_system_id == ZK_SYSTEM_ID
    assert document.doc_type == DOC_TYPE
    assert document.timestamp == TIMESTAMP
    assert document.issuer_signed[DOC_TYPE] == [
        {"elementIdentifier": "age_over_18", "elementValue": True}
    ]
    assert isinstance(document.mso_x5chain, x509.Certificate)


def test_parse_device_response_not_cbor() -> None:
    with pytest.raises(MalformedPresentation):
        parse_device_response(b"\x9f")


def test_parse_device_response_not_a_map() -> None:
    with pytest.raises(MalformedPresentation):
        parse_device_response(cbor2.dumps(5))


def test_parse_device_response_standard_documents() -> None:
    with pytest.raises(StandardMdocNotAccepted):
        parse_device_response(cbor2.dumps({"documents": [{"docType": DOC_TYPE}]}))


def test_parse_device_response_missing_zk_documents() -> None:
    with pytest.raises(MalformedPresentation):
        parse_device_response(cbor2.dumps({"version": "1.0"}))


def test_parse_device_response_empty_zk_documents() -> None:
    with pytest.raises(MalformedPresentation):
        parse_device_response(_device_response(zkDocuments=[]))


def test_parse_device_response_document_not_a_map() -> None:
    with pytest.raises(MalformedPresentation):
        parse_device_response(_device_response(zkDocuments=[5]))


def test_parse_device_response_document_data_untagged() -> None:
    doc = _zk_document(documentData=_document_data())
    with pytest.raises(MalformedPresentation):
        parse_device_response(_device_response(zkDocuments=[doc]))


def test_parse_device_response_missing_field() -> None:
    doc = _zk_document()
    del doc["proof"]
    with pytest.raises(MalformedPresentation):
        parse_device_response(_device_response(zkDocuments=[doc]))


def test_parse_device_response_wrong_field_type() -> None:
    doc = _zk_document(documentData=cbor2.CBORTag(24, _document_data(docType=42)))
    with pytest.raises(MalformedPresentation):
        parse_device_response(_device_response(zkDocuments=[doc]))


def test_parse_device_response_x5chain_as_array() -> None:
    doc = _zk_document(
        documentData=cbor2.CBORTag(24, _document_data(msoX5chain=[_leaf_cert_der()]))
    )
    document = parse_device_response(_device_response(zkDocuments=[doc]))
    assert isinstance(document.mso_x5chain, x509.Certificate)


def test_parse_device_response_device_signed_populated() -> None:
    populated = {DOC_TYPE: [{"elementIdentifier": "nym", "elementValue": "x"}]}
    doc = _zk_document(documentData=cbor2.CBORTag(24, _document_data(deviceSigned=populated)))
    document = parse_device_response(_device_response(zkDocuments=[doc]))
    assert document.device_signed == populated
