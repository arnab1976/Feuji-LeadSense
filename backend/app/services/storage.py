"""Uploads, exports and backups. Local filesystem or S3."""
from __future__ import annotations

import os
from pathlib import Path

from app.core.config import settings


def save(key: str, content: bytes) -> str:
    if settings.storage_backend == "s3" and settings.s3_bucket:
        import boto3
        boto3.client("s3").put_object(Bucket=settings.s3_bucket, Key=key, Body=content)
        return f"s3://{settings.s3_bucket}/{key}"
    base = Path(settings.local_storage_dir)
    path = base / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return str(path)


def load(key: str) -> bytes:
    if key.startswith("s3://"):
        import boto3
        bucket, _, obj = key[5:].partition("/")
        return boto3.client("s3").get_object(Bucket=bucket, Key=obj)["Body"].read()
    return Path(key).read_bytes()


def exists(key: str) -> bool:
    return key.startswith("s3://") or os.path.exists(key)
