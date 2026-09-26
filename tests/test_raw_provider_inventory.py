import io
import json
from pathlib import Path

from quantbot.baseball import raw_provider_inventory
from quantbot.baseball.raw_archive import S3RawPayloadArchive


class FakeS3Client:
    def __init__(self) -> None:
        self.objects = {
            "api-sports-baseball/2026-09-26/a_teams_statistics_x.json": {
                "captured_at": "2026-09-26T01:00:00+00:00",
                "endpoint": "teams/statistics",
                "params": {"team": 22, "league": 1, "season": 2026},
                "payload": {
                    "response": {
                        "games": {"played": 100},
                        "runs": {"for": 500, "against": 450},
                    }
                },
            },
            "api-sports-baseball/2026-09-26/b_odds_bets_x.json": {
                "captured_at": "2026-09-26T01:00:01+00:00",
                "endpoint": "odds/bets",
                "params": {},
                "payload": {
                    "response": [
                        {"id": 1, "name": "Home/Away"},
                        {"id": 2, "name": "Over/Under"},
                    ]
                },
            },
        }

    def list_objects_v2(self, **kwargs):
        prefix = kwargs["Prefix"]
        return {
            "Contents": [
                {"Key": key}
                for key in sorted(self.objects)
                if key.startswith(prefix)
            ]
        }

    def get_object(self, **kwargs):
        body = json.dumps(self.objects[kwargs["Key"]]).encode("utf-8")
        return {"Body": io.BytesIO(body)}


def test_raw_provider_inventory_uses_archive_only(monkeypatch) -> None:
    archive = S3RawPayloadArchive(client=FakeS3Client(), bucket="raw")
    monkeypatch.setattr(
        raw_provider_inventory,
        "archive_from_env",
        lambda *_args, **_kwargs: archive,
    )

    result = raw_provider_inventory.run_raw_provider_inventory(
        Path("."),
        day="2026-09-26",
    )

    assert result["status"] == "COMPLETE"
    assert result["provider_requests"] == 0
    assert result["objects_scanned"] == 2
    assert result["relevant_objects"] == 2

    team = next(
        item for item in result["summaries"]
        if item["endpoint"] == "teams/statistics"
    )
    assert team["response_type"] == "dict"
    assert "games.played" in team["leaf_paths"]
    assert "runs.for" in team["leaf_paths"]

    bets = next(
        item for item in result["summaries"]
        if item["endpoint"] == "odds/bets"
    )
    assert bets["markets"] == [
        {"id": 1, "name": "Home/Away"},
        {"id": 2, "name": "Over/Under"},
    ]
