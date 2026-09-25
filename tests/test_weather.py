from datetime import UTC, datetime

import pytest

from quantbot.baseball.raw_archive import LocalRawPayloadArchive
from quantbot.baseball.weather import (
    OpenMeteoWeatherClient,
    VenueWeatherRequest,
    WeatherEvidenceError,
    canonical_weather_snapshot,
    weather_applicable,
)


def _payload():
    return {
        "hourly": {
            "time": [
                "2030-07-04T18:00",
                "2030-07-04T19:00",
                "2030-07-04T20:00",
            ],
            "temperature_2m": [28.0, 27.5, 26.9],
            "relative_humidity_2m": [52, 55, 58],
            "dew_point_2m": [17.1, 17.6, 18.0],
            "precipitation_probability": [10, 12, 15],
            "precipitation": [0.0, 0.0, 0.2],
            "surface_pressure": [1007.1, 1006.8, 1006.4],
            "cloud_cover": [20, 25, 30],
            "wind_speed_10m": [14.0, 13.0, 12.0],
            "wind_direction_10m": [215, 220, 225],
            "wind_gusts_10m": [24.0, 23.0, 22.0],
            "weather_code": [1, 1, 2],
        }
    }


def _request(roof_status: str = "open") -> VenueWeatherRequest:
    return VenueWeatherRequest(
        game_id="123",
        latitude=40.8296,
        longitude=-73.9262,
        kickoff_at="2030-07-04T19:20:00+00:00",
        roof_status=roof_status,
    )


def test_closed_roof_skips_weather_request(tmp_path) -> None:
    calls = []

    def transport(url: str):
        calls.append(url)
        return _payload()

    client = OpenMeteoWeatherClient(
        raw_archive=LocalRawPayloadArchive(tmp_path),
        transport=transport,
    )

    assert client.forecast(_request("retractable_closed")) is None
    assert calls == []


def test_forecast_uses_nearest_hour_and_archives_payload(tmp_path) -> None:
    calls = []

    def transport(url: str):
        calls.append(url)
        return _payload()

    client = OpenMeteoWeatherClient(
        raw_archive=LocalRawPayloadArchive(tmp_path),
        transport=transport,
    )
    snapshot = client.forecast(
        _request(),
        captured_at=datetime(2030, 7, 4, 16, 0, tzinfo=UTC),
    )

    assert snapshot is not None
    assert snapshot.forecast_for_at == "2030-07-04T19:00:00+00:00"
    assert snapshot.temperature_c == 27.5
    assert snapshot.wind_speed_kph == 13.0
    assert snapshot.wind_direction_deg == 220.0
    assert snapshot.precipitation_probability_pct == 12.0
    assert snapshot.source_payload_ref.startswith("file://")
    assert len(snapshot.source_payload_checksum) == 64
    assert len(calls) == 1
    assert "timezone=UTC" in calls[0]
    assert "temperature_2m" in calls[0]


def test_weather_snapshot_rejects_post_first_pitch_capture(tmp_path) -> None:
    client = OpenMeteoWeatherClient(
        raw_archive=LocalRawPayloadArchive(tmp_path),
        transport=lambda _url: _payload(),
    )

    with pytest.raises(WeatherEvidenceError):
        client.forecast(
            _request(),
            captured_at=datetime(2030, 7, 4, 19, 20, tzinfo=UTC),
        )


def test_canonical_snapshot_requires_complete_hourly_fields(tmp_path) -> None:
    archive = LocalRawPayloadArchive(tmp_path)
    payload = _payload()
    payload["hourly"].pop("wind_gusts_10m")
    receipt = archive.archive(
        "open-meteo/forecast",
        {"latitude": 40.8296, "longitude": -73.9262},
        payload,
        captured_at=datetime(2030, 7, 4, 16, 0, tzinfo=UTC),
    )

    with pytest.raises(WeatherEvidenceError):
        canonical_weather_snapshot(_request(), payload, receipt)


def test_weather_applicability_by_roof() -> None:
    assert weather_applicable("open") is True
    assert weather_applicable("retractable-open") is True
    assert weather_applicable("dome") is False
    assert weather_applicable("fixed_dome") is False
