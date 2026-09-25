import json

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.raw_archive import ArchiveReceipt
from quantbot.baseball.weather import (
    OpenMeteoWeatherClient,
    canonical_weather_observation,
)


class FakeArchive:
    def __init__(self) -> None:
        self.calls = []

    def archive(self, endpoint, params, payload, *, captured_at=None):
        self.calls.append((endpoint, params, payload))
        return ArchiveReceipt(
            ref="s3://baseball-raw/open-meteo/weather.json",
            checksum="c" * 64,
            captured_at="2026-09-26T16:45:00+00:00",
        )


def _payload() -> dict:
    return {
        "hourly": {
            "time": [
                "2026-09-26T17:00",
                "2026-09-26T18:00",
                "2026-09-26T19:00",
            ],
            "temperature_2m": [22.0, 21.0, 20.0],
            "relative_humidity_2m": [45.0, 50.0, 55.0],
            "dew_point_2m": [9.5, 10.2, 11.0],
            "precipitation_probability": [5.0, 10.0, 15.0],
            "precipitation": [0.0, 0.0, 0.1],
            "surface_pressure": [1008.0, 1007.0, 1006.0],
            "cloud_cover": [20.0, 30.0, 40.0],
            "wind_speed_10m": [12.0, 14.0, 16.0],
            "wind_direction_10m": [180.0, 190.0, 200.0],
            "wind_gusts_10m": [20.0, 22.0, 25.0],
        }
    }


def test_canonical_weather_uses_nearest_hour_and_roof_state() -> None:
    record = canonical_weather_observation(
        game_id="123",
        latitude=40.8296,
        longitude=-73.9262,
        kickoff_at="2026-09-26T18:20:00+00:00",
        roof_state="OUTDOOR",
        payload=_payload(),
        receipt=ArchiveReceipt(
            ref="s3://baseball-raw/open-meteo/weather.json",
            checksum="a" * 64,
            captured_at="2026-09-26T16:45:00+00:00",
        ),
    )

    assert record.forecast_valid_at == "2026-09-26T18:00:00+00:00"
    assert record.sample_offset_seconds == 1200.0
    assert record.temperature_c == 21.0
    assert record.wind_speed_10m_kmh == 14.0
    assert record.weather_applies_to_play is True


def test_closed_roof_preserves_weather_but_marks_it_non_applicable() -> None:
    record = canonical_weather_observation(
        game_id="123",
        latitude=25.7781,
        longitude=-80.2197,
        kickoff_at="2026-09-26T18:20:00+00:00",
        roof_state="RETRACTABLE_CLOSED",
        payload=_payload(),
        receipt=ArchiveReceipt(
            ref="s3://baseball-raw/open-meteo/weather.json",
            checksum="b" * 64,
            captured_at="2026-09-26T16:45:00+00:00",
        ),
    )

    assert record.weather_applies_to_play is False
    assert record.temperature_c == 21.0


def test_rejects_weather_captured_after_first_pitch() -> None:
    with pytest.raises(EvidenceError, match="captured before kickoff"):
        canonical_weather_observation(
            game_id="123",
            latitude=40.8296,
            longitude=-73.9262,
            kickoff_at="2026-09-26T18:20:00+00:00",
            roof_state="OUTDOOR",
            payload=_payload(),
            receipt=ArchiveReceipt(
                ref="s3://baseball-raw/open-meteo/weather.json",
                checksum="d" * 64,
                captured_at="2026-09-26T18:21:00+00:00",
            ),
        )


def test_client_archives_raw_forecast_and_requests_utc_hourly_variables() -> None:
    archive = FakeArchive()

    def opener(_request):
        return json.dumps(_payload()).encode("utf-8")

    client = OpenMeteoWeatherClient(
        archive=archive,
        base_url="https://weather.example/v1/forecast",
        opener=opener,
    )
    record = client.forecast_for_game(
        game_id="123",
        latitude=40.8296,
        longitude=-73.9262,
        kickoff_at="2026-09-26T18:20:00+00:00",
        roof_state="OUTDOOR",
    )

    assert len(archive.calls) == 1
    endpoint, params, payload = archive.calls[0]
    assert endpoint == "forecast"
    assert params["timezone"] == "UTC"
    assert "temperature_2m" in params["hourly"]
    assert payload["hourly"]["time"][1] == "2026-09-26T18:00"
    assert record.source_payload_ref.startswith("s3://")
