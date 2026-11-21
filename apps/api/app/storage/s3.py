import boto3


class S3Storage:
    """S3-compatible blob storage (AWS S3, MinIO, ...). The bucket must already exist."""

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        access_key: str | None = None,
        secret_key: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )

    def save(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)

    def read(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def list_prefix(self, prefix: str) -> list[str]:
        keys: list[str] = []
        pages = self.client.get_paginator("list_objects_v2").paginate(
            Bucket=self.bucket, Prefix=prefix
        )
        for page in pages:
            keys.extend(o["Key"] for o in page.get("Contents", []))
        return keys

    def delete_prefix(self, prefix: str) -> int:
        keys = self.list_prefix(prefix)
        for i in range(0, len(keys), 1000):
            self.client.delete_objects(
                Bucket=self.bucket,
                Delete={"Objects": [{"Key": k} for k in keys[i : i + 1000]]},
            )
        return len(keys)
