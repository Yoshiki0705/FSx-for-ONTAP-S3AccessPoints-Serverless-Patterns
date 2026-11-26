"""Checksums that S3 reports for archived objects, computed from a byte stream.

S3 returns ``ChecksumSHA256`` and ``ChecksumCRC64NVME`` as base64 of the raw
big-endian digest. The ledger stores the same base64 form, so a comparison is a
string comparison and nothing is converted at verification time.

CRC-64/NVME parameters: reflected polynomial ``0x9A6C9329AC4BC9B5``, initial value
and final XOR all ones. The check value for ``b"123456789"`` is
``0xAE8B14860A799888``. ``awscrt`` is used when it is importable (it is orders of
magnitude faster); the pure Python table is the fallback and the reference the tests
compare against.
"""

from __future__ import annotations

import base64
import hashlib
import logging
from dataclasses import dataclass
from typing import Iterable

logger = logging.getLogger(__name__)

_POLY_REFLECTED = 0x9A6C9329AC4BC9B5
_MASK = 0xFFFFFFFFFFFFFFFF

try:  # pragma: no cover - exercised only where awscrt is installed
    from awscrt import checksums as _crt_checksums
except Exception:  # noqa: BLE001 - any import failure means "use the fallback"
    _crt_checksums = None


def _build_table() -> tuple[int, ...]:
    table = []
    for i in range(256):
        crc = i
        for _ in range(8):
            crc = (crc >> 1) ^ _POLY_REFLECTED if crc & 1 else crc >> 1
        table.append(crc)
    return tuple(table)


_TABLE = _build_table()


def crc64nvme_update_pure(crc: int, data: bytes) -> int:
    """Advance a CRC-64/NVME running value (pure Python reference).

    ``crc`` is the *finalized* value of the preceding bytes (0 for none), the same
    convention ``awscrt`` uses, so the two implementations are interchangeable.
    """
    state = crc ^ _MASK
    table = _TABLE
    for byte in data:
        state = table[(state ^ byte) & 0xFF] ^ (state >> 8)
    return state ^ _MASK


def crc64nvme_update(crc: int, data: bytes) -> int:
    """Advance a CRC-64/NVME running value, using awscrt when available."""
    if _crt_checksums is not None:  # pragma: no cover
        return _crt_checksums.crc64nvme(data, crc)
    return crc64nvme_update_pure(crc, data)


def using_awscrt() -> bool:
    """True when the fast implementation is active."""
    return _crt_checksums is not None


def crc64_to_b64(value: int) -> str:
    """Base64 of the big-endian 8-byte digest, the form S3 returns."""
    return base64.b64encode(value.to_bytes(8, "big")).decode("ascii")


def sha256_hex_to_b64(hex_digest: str) -> str:
    """Convert a SHA-256 hex digest to the base64 form S3 returns."""
    return base64.b64encode(bytes.fromhex(hex_digest)).decode("ascii")


@dataclass(frozen=True)
class FileDigest:
    """Digest of one file as read through the Access Point."""

    size: int
    sha256_hex: str
    sha256_b64: str
    crc64nvme_b64: str

    def as_ledger(self) -> dict:
        return {
            "sha256": self.sha256_hex,
            "sha256B64": self.sha256_b64,
            "crc64nvme": self.crc64nvme_b64,
        }


def hash_stream(chunks: Iterable[bytes]) -> FileDigest:
    """Read a chunk iterator once and return both digests plus the byte count."""
    sha = hashlib.sha256()
    crc = 0
    size = 0
    for chunk in chunks:
        sha.update(chunk)
        crc = crc64nvme_update(crc, chunk)
        size += len(chunk)
    hex_digest = sha.hexdigest()
    return FileDigest(
        size=size,
        sha256_hex=hex_digest,
        sha256_b64=sha256_hex_to_b64(hex_digest),
        crc64nvme_b64=crc64_to_b64(crc),
    )


# Algorithm names as used in this pattern and in the S3 API.
SHA256 = "SHA256"
CRC64NVME = "CRC64NVME"


def expected_algorithm(is_large: bool) -> str:
    """Single-request copies use SHA256; multipart copies use CRC64NVME.

    A multipart SHA256 is COMPOSITE (a checksum of part checksums) and cannot equal
    the SHA-256 of the whole file; CRC64NVME is FULL_OBJECT for multipart as well.
    """
    return CRC64NVME if is_large else SHA256


def verify_head(
    head: dict,
    *,
    size: int,
    sha256_b64: str,
    crc64nvme_b64: str,
    algorithm: str,
) -> tuple[bool, str]:
    """Compare a ``HeadObject`` (``ChecksumMode=ENABLED``) response with the ledger.

    Returns ``(ok, reason)``. ``ok`` is True only when the size matches, the
    checksum for ``algorithm`` is present, its type is not COMPOSITE, and its value
    equals the one computed from the source file. A missing checksum is a mismatch,
    never a pass: an object stored without one cannot be verified.
    """
    if int(head.get("ContentLength", -1)) != int(size):
        return False, f"size differs: archive={head.get('ContentLength')} ledger={size}"
    if algorithm == SHA256:
        actual, expected, field = head.get("ChecksumSHA256"), sha256_b64, "ChecksumSHA256"
    elif algorithm == CRC64NVME:
        actual, expected, field = head.get("ChecksumCRC64NVME"), crc64nvme_b64, "ChecksumCRC64NVME"
    else:
        return False, f"unsupported algorithm {algorithm!r}"
    if not actual:
        return False, f"{field} absent on the archived object"
    if head.get("ChecksumType") == "COMPOSITE":
        return False, f"{field} is COMPOSITE and cannot be compared with a whole-file digest"
    if actual != expected:
        return False, f"{field} differs: archive={actual} ledger={expected}"
    return True, "match"
