"""Verified S3-compatible cold archive storage for canonical Baseball rows."""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config


@dataclass(frozen=True, slots=True)
class ColdObjectReceipt:
    ref: str
    checksum: str
    compressed_bytes: int


class ColdArchiveStore(Protocol):
    def put_verified_file(
        self,
        *,
        key: str,
        path: Path,
        checksum: str,
    ) -> ColdObjectReceipt: ...

    def download_file(self, *, ref: str, path: Path) -> None: ...


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class LocalColdArchiveStore:
    """Filesystem-backed adapter used by tests and local replay tooling."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def put_verified_file(
        self,
        *,
        key: str,
        path: Path,
        checksum: str,
    ) -> ColdObjectReceipt:
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copyfile(path, target)
        actual = sha256_file(target)
        if actual != checksum:
            raise RuntimeError("cold archive local read-back checksum mismatch")
        return ColdObjectReceipt(
            ref=target.resolve().as_uri(),
            checksum=actual,
            compressed_bytes=target.stat().st_size,
        )

    def download_file(self, *, ref: str, path: Path) -> None:
        if not ref.startswith("file://"):
            raise ValueError("local cold archive reference must use file://")
        source = Path(ref.removeprefix("file://"))
        shutil.copyfile(source, path)


class S3ColdArchiveStore:
    """S3-compatible verified store reusing the Baseball raw-archive bucket."""

    def __init__(self, *, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def put_verified_file(
        self,
        *,
        key: str,
        path: Path,
        checksum: str,
    ) -> ColdObjectReceipt:
        size = path.stat().st_size
        self.client.upload_file(
            str(path),
            self.bucket,
            key,
            ExtraArgs={
                "ContentType": "application/gzip",
                "Metadata": {
                    "sha256": checksum,
                    "dataset": "quantbet-baseball-cold",
                },
            },
        )
        head = self.client.head_object(Bucket=self.bucket, Key=key)
        if int(head.get("ContentLength") or -1) != size:
            raise RuntimeError("cold archive S3 size verification failed")

        response = self.client.get_object(Bucket=self.bucket, Key=key)
        digest = hashlib.sha256()
        body = response["Body"]
        try:
            for chunk in body.iter_chunks(chunk_size=1024 * 1024):
                if chunk:
                    digest.update(chunk)
        finally:
            body.close()
        actual = digest.hexdigest()
        if actual != checksum:
            raise RuntimeError("cold archive S3 read-back checksum mismatch")

        return ColdObjectReceipt(
            ref=f"s3://{self.bucket}/{key}",
            checksum=actual,
            compressed_bytes=size,
        )

    def download_file(self, *, ref: str, path: Path) -> None:
        prefix = f"s3://{self.bucket}/"
        if not ref.startswith(prefix):
            raise ValueError("cold archive reference points to another bucket")
        key = ref[len(prefix) :]
        self.client.download_file(self.bucket, key, str(path))


_S3_ENV = (
    "BASEBALL_RAW_BUCKET",
    "BASEBALL_RAW_REGION",
    "BASEBALL_RAW_ENDPOINT",
    "BASEBALL_RAW_ACCESS_KEY_ID",
    "BASEBALL_RAW_SECRET_ACCESS_KEY",
)


def cold_store_from_env(
    local_root: Path,
    *,
    require_remote: bool = False,
) -> ColdArchiveStore:
    values = {name: os.getenv(name, "").strip() for name in _S3_ENV}
    configured = [name for name, value in values.items() if value]
    if configured and len(configured) != len(_S3_ENV):
        missing = sorted(name for name, value in values.items() if not value)
        raise RuntimeError(
            "Incomplete Baseball cold archive configuration: " + ", ".join(missing)
        )

    if len(configured) == len(_S3_ENV):
        client = boto3.client(
            "s3",
            endpoint_url=values["BASEBALL_RAW_ENDPOINT"],
            aws_access_key_id=values["BASEBALL_RAW_ACCESS_KEY_ID"],
            aws_secret_access_key=values["BASEBALL_RAW_SECRET_ACCESS_KEY"],
            region_name=values["BASEBALL_RAW_REGION"],
            config=Config(s3={"addressing_style": "virtual"}),
        )
        return S3ColdArchiveStore(
            client=client,
            bucket=values["BASEBALL_RAW_BUCKET"],
        )

    if require_remote:
        raise RuntimeError("Railway cold archive requires the configured raw bucket")
    return LocalColdArchiveStore(local_root)
