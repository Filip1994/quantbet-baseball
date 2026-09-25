import hashlib
import json
from datetime import UTC, datetime

import pytest

from quantbot.baseball.raw_archive import (
    S3RawPayloadArchive,
    archive_from_env,
)


class FakeS3:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def put_object(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_s3_archive_writes_exact_body_and_returns_checksum() -> None:
    client = FakeS3()
    archive = S3RawPayloadArchive(client=client, bucket="baseball-raw")
    captured = datetime(2026, 9, 18, 12, 30, tzinfo=UTC)

    receipt = archive.archive(
        "odds",
        {"game": 123},
        {"response": [{"id": 1}], "errors": []},
        captured_at=captured,
    )

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["Bucket"] == "baseball-raw"
    assert call["ContentType"] == "application/json"
    body = call["Body"]
    assert isinstance(body, bytes)
    assert receipt.checksum == hashlib.sha256(body).hexdigest()
    assert receipt.ref.startswith("s3://baseball-raw/api-sports-baseball/")
    document = json.loads(body)
    assert document["endpoint"] == "odds"
    assert document["params"] == {"game": 123}
    assert document["payload"]["response"] == [{"id": 1}]


def test_partial_bucket_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    names = (
        "BASEBALL_RAW_BUCKET",
        "BASEBALL_RAW_REGION",
        "BASEBALL_RAW_ENDPOINT",
        "BASEBALL_RAW_ACCESS_KEY_ID",
        "BASEBALL_RAW_SECRET_ACCESS_KEY",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BASEBALL_RAW_BUCKET", "configured-only-partially")

    with pytest.raises(RuntimeError, match="Incomplete Baseball raw bucket"):
        archive_from_env(tmp_path, require_remote=True)


def test_remote_archive_is_required_in_production(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    names = (
        "BASEBALL_RAW_BUCKET",
        "BASEBALL_RAW_REGION",
        "BASEBALL_RAW_ENDPOINT",
        "BASEBALL_RAW_ACCESS_KEY_ID",
        "BASEBALL_RAW_SECRET_ACCESS_KEY",
    )
    for name in names:
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(RuntimeError, match="raw payload bucket"):
        archive_from_env(tmp_path, require_remote=True)


def test_s3_archive_supports_separate_provider_namespace() -> None:
    client = FakeS3()
    archive = S3RawPayloadArchive(
        client=client,
        bucket="baseball-raw",
        namespace="open-meteo",
    )

    receipt = archive.archive(
        "forecast",
        {"latitude": 40.0, "longitude": -74.0},
        {"hourly": {"time": ["2026-09-26T18:00"]}},
        captured_at=datetime(2026, 9, 26, 16, 0, tzinfo=UTC),
    )

    assert receipt.ref.startswith("s3://baseball-raw/open-meteo/")
