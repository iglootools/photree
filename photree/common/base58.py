"""Base58 encoding and decoding (Bitcoin alphabet)."""

from __future__ import annotations

import functools

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58_encode(data: bytes) -> str:
    """Encode *data* as a base58 string (Bitcoin alphabet)."""
    n = int.from_bytes(data, "big")
    result: list[str] = []
    while n > 0:
        n, remainder = divmod(n, 58)
        result.append(BASE58_ALPHABET[remainder])
    leading_zeros = len(data) - len(data.lstrip(b"\x00"))
    return BASE58_ALPHABET[0] * leading_zeros + "".join(reversed(result))


def base58_decode(s: str) -> bytes:
    """Decode a base58 string back to bytes."""
    n = functools.reduce(lambda acc, c: acc * 58 + BASE58_ALPHABET.index(c), s, 0)
    leading_ones = len(s) - len(s.lstrip(BASE58_ALPHABET[0]))
    byte_length = max((n.bit_length() + 7) // 8, 1) if n else 0
    return b"\x00" * leading_ones + (n.to_bytes(byte_length, "big") if n else b"")
