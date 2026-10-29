import boto3
import pytest
from moto import mock_aws

from app.storage.s3 import S3Storage


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="test-bucket")
        yield S3Storage(bucket="test-bucket")


def test_save_and_delete(storage):
    storage.save("u/1.pdf", b"data")
    body = storage.client.get_object(Bucket="test-bucket", Key="u/1.pdf")["Body"].read()
    assert body == b"data"

    storage.delete("u/1.pdf")
    assert "Contents" not in storage.client.list_objects_v2(Bucket="test-bucket")


def test_delete_missing_key_is_ok(storage):
    storage.delete("nope")
