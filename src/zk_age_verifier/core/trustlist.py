"""Trust anchors: resolve a presented DS certificate to an issuer public key.

Every configured source collapses at startup into one set of anchor
certificates. A presented certificate is accepted if it is one of those anchors
(fingerprint match) or was directly issued by one; either way its P-256 public
key coordinates are returned, the only value the trust layer feeds the proof
check. The credential's own issuer signature is validated inside the ZK proof.
This module only decides which issuer key the proof is allowed to satisfy.

ETSI list handling extracts certificates from the XML and stops there: TSL
semantics and XAdES signature validation are out of scope, so an ETSI source is
trusted by its pinned path or URL, not by a checked list signature.
"""

import base64
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from urllib.request import urlopen
from xml.etree import ElementTree

from cryptography import x509
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from zk_age_verifier.config import ConfigError, TrustSource


class UntrustedIssuer(Exception):
    """Raised when a presented certificate resolves to no trusted anchor."""


@dataclass(frozen=True)
class AnchorSet:
    """A resolved set of trust anchors.

    Attributes:
        anchors: The trusted certificates.
    """

    anchors: tuple[x509.Certificate, ...]

    def resolve(self, cert: x509.Certificate) -> tuple[int, int]:
        """Return the issuer key of a presented certificate the anchors vouch for.

        The certificate is accepted if it is itself an anchor (SHA-256
        fingerprint match) or was directly issued by one, and is within its own
        validity window in either case. A presented certificate must carry a
        keyUsage extension asserting digitalSignature; an anchor accepted as the
        issuer of a chained leaf must assert keyCertSign.

        Args:
            cert: The presented DS certificate from the proof's ``msoX5chain``.

        Returns:
            The issuer P-256 public key as ``(x, y)``.

        Raises:
            UntrustedIssuer: No anchor accepts the certificate, or its key is
                not P-256.
        """
        if not self._accepts(cert):
            raise UntrustedIssuer("no anchor accepts the presented certificate")
        public_key = cert.public_key()
        if not (
            isinstance(public_key, ec.EllipticCurvePublicKey)
            and isinstance(public_key.curve, ec.SECP256R1)
        ):
            raise UntrustedIssuer("presented certificate key is not P-256")
        numbers = public_key.public_numbers()
        return numbers.x, numbers.y

    def _accepts(self, cert: x509.Certificate) -> bool:
        """Report whether an anchor vouches for a certificate within its validity."""
        now = datetime.now(UTC)
        if not (cert.not_valid_before_utc <= now <= cert.not_valid_after_utc):
            return False
        if not _key_usage_permits(cert, "digital_signature"):
            return False
        fingerprint = cert.fingerprint(hashes.SHA256())
        if any(fingerprint == anchor.fingerprint(hashes.SHA256()) for anchor in self.anchors):
            return True
        for anchor in self.anchors:
            if not _key_usage_permits(anchor, "key_cert_sign"):
                continue
            try:
                cert.verify_directly_issued_by(anchor)
            except (ValueError, TypeError, InvalidSignature):
                continue
            return True
        return False


def _key_usage_permits(cert: x509.Certificate, bit: str) -> bool:
    """Report whether a certificate's keyUsage extension asserts the named bit.

    A certificate carrying no keyUsage extension asserts nothing.

    Args:
        cert: The certificate to inspect.
        bit: The ``KeyUsage`` attribute name, e.g. ``"digital_signature"``.

    Returns:
        Whether the extension is present and asserts the bit.
    """
    try:
        key_usage = cert.extensions.get_extension_for_class(x509.KeyUsage)
    except x509.ExtensionNotFound:
        return False
    return bool(getattr(key_usage.value, bit))


def load_anchors(sources: list[TrustSource]) -> AnchorSet:
    """Collapse every trust source into one anchor set.

    Args:
        sources: The configured trust sources.

    Returns:
        The combined anchor set.

    Raises:
        ConfigError: The configured sources resolve to zero anchors — an empty
            set would boot cleanly and then reject every presentation.
    """
    anchors: list[x509.Certificate] = []
    for source in sources:
        if source.pem is not None:
            anchors.extend(_load_pem(source.pem))
        else:
            anchors.extend(_load_etsi_xml(cast(str, source.etsi_xml)))
    if not anchors:
        raise ConfigError("trust sources resolved to no anchors; check the [trust] source paths")
    return AnchorSet(tuple(anchors))


def _load_pem(location: str) -> list[x509.Certificate]:
    """Load anchors from a PEM file or a directory of ``*.pem`` files."""
    path = Path(location)
    files = sorted(path.glob("*.pem")) if path.is_dir() else [path]
    anchors: list[x509.Certificate] = []
    for file in files:
        anchors.extend(x509.load_pem_x509_certificates(file.read_bytes()))
    return anchors


def _load_etsi_xml(location: str) -> list[x509.Certificate]:
    """Fetch and parse an ETSI list from a path or URL, extracting its certificates.

    Raises:
        ConfigError: The location is an ``http`` URL. A trust list fetched
            over plain http can be replaced in transit, so only ``https``
            URLs and local file paths are accepted.
    """
    scheme = urlsplit(location).scheme
    if scheme == "http":
        raise ConfigError(
            f"trust source url uses scheme {scheme!r}; https or a file path is required"
        )
    if scheme == "https":
        with urlopen(location) as response:  # noqa: S310 - operator-configured startup fetch
            data = response.read()
    else:
        data = Path(location).read_bytes()
    root = ElementTree.fromstring(data)
    anchors: list[x509.Certificate] = []
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1] == "X509Certificate" and element.text:
            der = base64.b64decode("".join(element.text.split()))
            anchors.append(x509.load_der_x509_certificate(der))
    return anchors
