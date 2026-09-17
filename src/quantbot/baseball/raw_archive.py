"""Raw API payload archives for local development and Railway production."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.config import Config


@dataclass(frozen=True, slots=True)
class ArchiveReceipt:
    """Immutable pointer to one archived API response envelope."""

    ref: str
    checksum: str
    captured_at: str


class RawPayloadArchive(Protocol):
    def archive(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        captured_at: datetime | None = None,
    ) -> ArchiveReceipt: ...


def _archive_document(
    endpoint: str,
    params: Mapping[str, Any],
    payload: Mapping[str, Any],
    *,
    captured_at: datetime | None = None,
) -> tuple[datetime, bytes, str]:
    captured = (captured_at or datetime.now(UTC)).astimezone(UTC)
    document = {
        "captured_at": captured.isoformat(),
        "endpoint": endpoint,
        "params": dict(params),
        "payload": dict(payload),
    }
    body = json.dumps(
        document,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    checksum = hashlib.sha256(body).hexdigest()
    return captured, body, checksum


def _object_key(
    endpoint: str,
    params: Mapping[str, Any],
    captured: datetime,
    checksum: str,
) -> str:
    safe_endpoint = endpoint.strip("/").replace("/", "_") or "root"
    request_identity = json.dumps(
        [endpoint, sorted((str(key), str(value)) for key, value in params.items())],
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    request_digest = hashlib.sha256(request_identity).hexdigest()[:12]
    stamp = captured.strftime("%Y%m%dT%H%M%S.%fZ")
    day = captured.strftime("%Y-%m-%d")
    return (
        f"api-sports-baseball/{day}/{stamp}_{safe_endpoint}_"
        f"{request_digest}_{checksum[:12]}.json"
    )


class LocalRawPayloadArchive:
    """Atomic local archive retained for development and replay tooling."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def archive(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        captured_at: datetime | None = None,
    ) -> ArchiveReceipt:
        captured, body, checksum = _archive_document(
            endpoint,
            params,
            payload,
            captured_at=captured_at,
        )
        path = self.root / _object_key(endpoint, params, captured, checksum)
        path.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(body)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)

        return ArchiveReceipt(
            ref=path.resolve().as_uri(),
            checksum=checksum,
            captured_at=captured.isoformat(),
        )


class S3RawPayloadArchive:
    """S3-compatible archive used by the Railway worker."""

    def __init__(self, *, client: Any, bucket: str) -> None:
        self.client = client
        self.bucket = bucket

    def archive(
        self,
        endpoint: str,
        params: Mapping[str, Any],
        payload: Mapping[str, Any],
        *,
        captured_at: datetime | None = None,
    ) -> ArchiveReceipt:
        captured, body, checksum = _archive_document(
            endpoint,
            params,
            payload,
            captured_at=captured_at,
        )
        key = _object_key(endpoint, params, captured, checksum)
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
        )
        return ArchiveReceipt(
            ref=f"s3://{self.bucket}/{key}",
            checksum=checksum,
            captured_at=captured.isoformat(),
        )


_S3_ENV = (
    "BASEBALL_RAW_BUCKET",
    "BASEBALL_RAW_REGION",
    "BASEBALL_RAW_ENDPOINT",
    "BASEBALL_RAW_ACCESS_KEY_ID",
    "BASEBALL_RAW_SECRET_ACCESS_KEY",
)


def archive_from_env(
    local_root: Path,
    *,
    require_remote: bool = False,
) -> RawPayloadArchive:
    """Build the archive adapter and fail closed on partial S3 configuration."""

    values = {name: os.getenv(name, "").strip() for name in _S3_ENV}
    configured = [name for name, value in values.items() if value]

    if configured and len(configured) != len(_S3_ENV):
        missing = sorted(name for name, value in values.items() if not value)
        raise RuntimeError(
            "Incomplete Baseball raw bucket configuration: " + ", ".join(missing)
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
        return S3RawPayloadArchive(
            client=client,
            bucket=values["BASEBALL_RAW_BUCKET"],
        )

    if require_remote:
        raise RuntimeError("Railway raw payload bucket configuration is required")

    return LocalRawPayloadArchive(local_root)
