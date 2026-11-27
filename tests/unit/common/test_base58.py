import uuid

from photree.common.base58 import base58_decode, base58_encode


class TestBase58:
    def test_roundtrip(self) -> None:
        data = uuid.uuid4().bytes
        assert base58_decode(base58_encode(data)) == data

    def test_known_value(self) -> None:
        data = b"\x00\x01"
        encoded = base58_encode(data)
        assert encoded.startswith("1")
        assert base58_decode(encoded) == data

    def test_empty_input(self) -> None:
        assert base58_encode(b"") == ""

    def test_leading_zeros(self) -> None:
        data = b"\x00\x00\x01"
        encoded = base58_encode(data)
        assert encoded.startswith("11")
        assert base58_decode(encoded) == data
