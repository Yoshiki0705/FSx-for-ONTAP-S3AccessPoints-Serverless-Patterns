"""copy_between: server-side copy, single request and multipart."""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from shared.exceptions import S3ApHelperError
from shared.s3ap_helper import S3ApHelper


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-northeast-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        c = boto3.client("s3")
        for b in ("src", "dst"):
            c.create_bucket(Bucket=b, CreateBucketConfiguration={"LocationConstraint": "ap-northeast-1"})
        yield c


def test_single_request_copy_keeps_content_and_applies_metadata(s3):
    s3.put_object(Bucket="src", Key="a.txt", Body=b"hello")
    S3ApHelper("src").copy_between(
        "src", "a.txt", "dst", "data/a.txt", {"Metadata": {"source-key": "a.txt"}, "MetadataDirective": "REPLACE"}
    )
    out = s3.get_object(Bucket="dst", Key="data/a.txt")
    assert out["Body"].read() == b"hello"
    assert out["Metadata"] == {"source-key": "a.txt"}


def test_multipart_copy_assembles_all_parts(s3):
    body = bytes(range(256)) * (12 * 1024 * 4)  # 12 MiB
    s3.put_object(Bucket="src", Key="big.bin", Body=body)
    S3ApHelper("src").copy_between(
        "src", "big.bin", "dst", "big.bin", multipart_threshold=1, multipart_chunksize=5 * 1024 * 1024
    )
    assert s3.get_object(Bucket="dst", Key="big.bin")["Body"].read() == body


def test_failed_precondition_is_an_error_and_writes_nothing(s3):
    s3.put_object(Bucket="src", Key="a.txt", Body=b"hello")
    with pytest.raises(S3ApHelperError):
        S3ApHelper("src").copy_between("src", "a.txt", "dst", "a.txt", {"CopySourceIfMatch": '"not-the-etag"'})
    assert "Contents" not in s3.list_objects_v2(Bucket="dst")
