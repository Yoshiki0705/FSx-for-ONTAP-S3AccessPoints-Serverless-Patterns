"""Checksums and the comparison that gates deletion."""

from __future__ import annotations

import base64
import hashlib

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from shared.archive_verify import checksums as C

CRC64_NVME_CHECK = 0xAE8B14860A799888  # CRC-64/NVME of b"123456789"


def test_crc64nvme_known_check_value_pure():
    assert C.crc64nvme_update_pure(0, b"123456789") == CRC64_NVME_CHECK


def test_crc64nvme_known_check_value_active_implementation():
    assert C.crc64nvme_update(0, b"123456789") == CRC64_NVME_CHECK


def test_awscrt_agrees_with_the_pure_reference():
    crt = pytest.importorskip("awscrt.checksums")
    data = bytes(range(256)) * 1000
    assert crt.crc64nvme(data) == C.crc64nvme_update_pure(0, data)


@settings(deadline=None, max_examples=60)
@given(data=st.binary(max_size=4096), split=st.integers(min_value=0, max_value=4096))
def test_chunking_does_not_change_the_crc(data, split):
    split = min(split, len(data))
    one_shot = C.crc64nvme_update_pure(0, data)
    chunked = C.crc64nvme_update_pure(C.crc64nvme_update_pure(0, data[:split]), data[split:])
    assert one_shot == chunked


def test_crc64_base64_is_big_endian_eight_bytes():
    assert C.crc64_to_b64(CRC64_NVME_CHECK) == base64.b64encode(bytes.fromhex("ae8b14860a799888")).decode()
    assert len(base64.b64decode(C.crc64_to_b64(1))) == 8


def test_hash_stream_matches_hashlib_and_counts_bytes():
    chunks = [b"abc", b"", b"defgh" * 1000]
    digest = C.hash_stream(iter(chunks))
    whole = b"".join(chunks)
    assert digest.size == len(whole)
    assert digest.sha256_hex == hashlib.sha256(whole).hexdigest()
    assert base64.b64decode(digest.sha256_b64) == hashlib.sha256(whole).digest()
    assert digest.crc64nvme_b64 == C.crc64_to_b64(C.crc64nvme_update_pure(0, whole))


def test_algorithm_follows_size():
    assert C.expected_algorithm(False) == C.SHA256
    assert C.expected_algorithm(True) == C.CRC64NVME


def _head(**over):
    base = {"ContentLength": 5, "ChecksumSHA256": "AAA=", "ChecksumCRC64NVME": "BBB=", "ChecksumType": "FULL_OBJECT"}
    base.update(over)
    return base


def _verify(head, algorithm=C.SHA256, size=5):
    return C.verify_head(head, size=size, sha256_b64="AAA=", crc64nvme_b64="BBB=", algorithm=algorithm)


def test_verify_match_sha256_and_crc():
    assert _verify(_head()) == (True, "match")
    assert _verify(_head(), C.CRC64NVME)[0] is True


def test_verify_size_mismatch():
    ok, reason = _verify(_head(ContentLength=6))
    assert not ok and "size" in reason


def test_verify_checksum_absent_is_a_failure_not_a_pass():
    head = _head()
    del head["ChecksumSHA256"]
    ok, reason = _verify(head)
    assert not ok and "absent" in reason


def test_verify_composite_cannot_be_compared():
    ok, reason = _verify(_head(ChecksumType="COMPOSITE"))
    assert not ok and "COMPOSITE" in reason


def test_verify_value_mismatch():
    ok, reason = _verify(_head(ChecksumSHA256="ZZZ="))
    assert not ok and "differs" in reason


def test_verify_unknown_algorithm():
    assert _verify(_head(), "MD5")[0] is False


def test_verify_uses_the_checksum_of_the_requested_algorithm_only():
    # A matching SHA256 must not vouch for a CRC64NVME check.
    ok, _ = _verify(_head(ChecksumCRC64NVME="WRONG="), C.CRC64NVME)
    assert not ok
