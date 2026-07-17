"""Base64url without padding, the encoding used for every binary wire field."""

import base64


def b64url_encode(data: bytes) -> str:
    """Encode bytes as base64url without padding.

    Args:
        data: The bytes to encode.

    Returns:
        The base64url text, ``=`` padding stripped.
    """
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def b64url_decode(data: str) -> bytes:
    """Decode base64url text, accepting padded or unpadded input.

    Args:
        data: The base64url text, with or without ``=`` padding.

    Returns:
        The decoded bytes.
    """
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)
