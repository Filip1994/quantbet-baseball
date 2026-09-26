import json
from pathlib import Path

from quantbot.baseball import api
from quantbot.baseball.api import BaseballAPIClient
from quantbot.baseball.config import BaseballSettings
from quantbot.baseball.raw_archive import LocalRawPayloadArchive


class _Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def _settings(tmp_path: Path) -> BaseballSettings:
    return BaseballSettings(
        api_key="test-key",
        api_base_url="https://example.invalid",
        api_request_budget=10,
        api_max_attempts=1,
        api_retry_base_seconds=0.0,
        cache_dir=tmp_path / "cache",
        raw_archive_dir=tmp_path / "raw",
        timezone_name="UTC",
        paper_mode=True,
    )


def test_team_statistics_supports_verified_object_response(
    monkeypatch, tmp_path
) -> None:
    payload = {
        "errors": [],
        "response": {
            "team": {"id": 22, "name": "Example Team"},
            "league": {"id": 1, "season": 2026},
            "games": {"played": {"all": 10, "home": 5, "away": 5}},
        },
    }
    monkeypatch.setattr(api, "urlopen", lambda *_a, **_k: _Response(payload))
    client = BaseballAPIClient(
        _settings(tmp_path),
        raw_archive=LocalRawPayloadArchive(tmp_path / "archive"),
    )

    response, receipt = client.team_statistics_with_receipt(22, 1, 2026)

    assert response["team"]["id"] == 22
    assert client.request_count == 1
    assert receipt.source if hasattr(receipt, "source") else receipt.ref
    assert len(receipt.checksum) == 64
