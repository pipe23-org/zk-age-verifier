from zk_age_verifier.core.encoding import b64url_decode, b64url_encode


def test_round_trip() -> None:
    for data in [b"", b"\x00", b"hello world", bytes(range(256))]:
        assert b64url_decode(b64url_encode(data)) == data


def test_output_is_unpadded() -> None:
    assert b64url_encode(b"\x00") == "AA"
    assert "=" not in b64url_encode(bytes(range(10)))


def test_decode_accepts_padded_and_unpadded() -> None:
    assert b64url_decode("AA==") == b"\x00"
    assert b64url_decode("AA") == b"\x00"


def test_url_safe_alphabet() -> None:
    data = b"\xfb\xff\xbf"
    encoded = b64url_encode(data)
    assert "+" not in encoded
    assert "/" not in encoded
    assert b64url_decode(encoded) == data
