from __future__ import annotations

import base64
import hashlib


_PEPPER = "wappkit-social-distributor::repo-secret-obf::v1"


def _keystream(label: str, length: int) -> bytes:
    seed = f"{_PEPPER}:{label}".encode("utf-8")
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(seed + counter.to_bytes(4, "big")).digest())
        counter += 1
    return bytes(out[:length])


def encode_secret(value: str, label: str) -> str:
    raw = value.encode("utf-8")
    key = _keystream(label, len(raw))
    cipher = bytes(a ^ b for a, b in zip(raw, key))
    return base64.urlsafe_b64encode(cipher).decode("ascii")


def decode_secret(value: str, label: str) -> str:
    raw = base64.urlsafe_b64decode(value.encode("ascii"))
    key = _keystream(label, len(raw))
    plain = bytes(a ^ b for a, b in zip(raw, key))
    return plain.decode("utf-8")
