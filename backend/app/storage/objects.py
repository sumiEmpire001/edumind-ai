"""Private S3-compatible storage. No local-disk fallback in the hosted application."""

import boto3
from botocore.config import Config
from fastapi import HTTPException


class ObjectStore:
    def __init__(self, settings):
        if (
            not settings.storage_bucket
            or not settings.storage_access_key
            or not settings.storage_secret_key
        ):
            raise HTTPException(503, "Document storage is not configured.")
        self.bucket = settings.storage_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.storage_endpoint,
            aws_access_key_id=settings.storage_access_key.get_secret_value(),
            aws_secret_access_key=settings.storage_secret_key.get_secret_value(),
            region_name=settings.storage_region,
            config=Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 2}),
        )

    def put(self, key, data, mime):
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime)

    def get(self, key):
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        try:
            data = response["Body"].read(3 * 1024 * 1024 + 1)
        finally:
            response["Body"].close()
        if len(data) > 3 * 1024 * 1024:
            raise ValueError("file_too_large")
        return data

    def delete(self, key):
        self.client.delete_object(Bucket=self.bucket, Key=key)


class BlobStore:
    """Private Vercel Blob alternative for this test deployment."""

    def __init__(self, settings):
        from vercel.blob import BlobCredentials
        from vercel.blob.sync import SyncBlobServiceOptions

        self.options = SyncBlobServiceOptions(
            credentials_factory=lambda: BlobCredentials(
                token=settings.blob_read_write_token.get_secret_value(),
                store_id=settings.blob_store_id,
            )
        )

    def put(self, key, data, mime):
        from vercel.api import session
        from vercel.blob import sync as blob

        with session(service_options=[self.options]):
            blob.put_blob(key, data, access="private", content_type=mime, add_random_suffix=False)

    def get(self, key):
        from vercel.api import session
        from vercel.blob import sync as blob

        with session(service_options=[self.options]):
            result = blob.get_blob(key, access="private")
            return result.body

    def delete(self, key):
        from vercel.api import session
        from vercel.blob import sync as blob

        with session(service_options=[self.options]):
            blob.delete_blob(key)


def configured_store(settings):
    if settings.blob_read_write_token and settings.blob_store_id:
        return BlobStore(settings)
    return ObjectStore(settings)
