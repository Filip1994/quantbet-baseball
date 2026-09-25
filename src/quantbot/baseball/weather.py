"""Point-in-time stadium weather capture for Baseball research."""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Callable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .evidence import EvidenceError
from .raw_archive import ArchiveReceipt, RawPayloadArchive

_HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "precipitation_probability",
    "precipitation",
    "surface_pressure",
    "cloud_cover",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)
_ROOF_STATES = {
    "OUTDOOR",
    "RETRACTABLE_OPEN",
    "RETRACTABLE_CLOSED",
    "DOME",
    "UNKNOWN",
}


def _timestamp(value: str, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{field} must be a non-empty ISO-8601 string")
    text = value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _finite_optional(value: Any, field: str) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be numeric or null") from exc
    if not math.isfinite(number):
        raise EvidenceError(f"{field} must be finite")
    return number


def _weather_applies(roof_state: str) -> bool | None:
    if roof_state in {"OUTDOOR", "RETRACTABLE_OPEN"}:
        return True
    if roof_state in {"RETRACTABLE_CLOSED", "DOME"}:
        return False
    return None


@dataclass(frozen=True, slots=True)
class WeatherForecastObservation:
    game_id: str
    latitude: float
    longitude: float
    roof_state: str
    weather_applies_to_play: bool | None
    kickoff_at: str
    forecast_valid_at: str
    captured_at: str
    sample_offset_seconds: float
    temperature_c: float | None
    relative_humidity_pct: float | None
    dew_point_c: float | None
    precipitation_probability_pct: float | None
    precipitation_mm: float | None
    surface_pressure_hpa: float | None
    cloud_cover_pct: float | None
    wind_speed_10m_kmh: float | None
    wind_direction_10m_deg: float | None
    wind_gusts_10m_kmh: float | None
    source_payload_ref: str
    source_payload_checksum: str
    provider: str = "open-meteo"
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.game_id.strip():
            raise EvidenceError("game_id must be non-empty")
        if self.roof_state not in _ROOF_STATES:
            raise EvidenceError("roof_state is unsupported")
        if self.weather_applies_to_play != _weather_applies(self.roof_state):
            raise EvidenceError("weather applicability does not match roof state")
        kickoff = _timestamp(self.kickoff_at, "kickoff_at")
        valid = _timestamp(self.forecast_valid_at, "forecast_valid_at")
        captured = _timestamp(self.captured_at, "captured_at")
        if captured >= kickoff:
            raise EvidenceError("weather forecast must be captured before kickoff")
        expected_offset = abs((valid - kickoff).total_seconds())
        if not math.isclose(
            float(self.sample_offset_seconds),
            expected_offset,
            rel_tol=0.0,
            abs_tol=0.001,
        ):
            raise EvidenceError("sample_offset_seconds does not match forecast time")
        if expected_offset > 3600:
            raise EvidenceError("nearest weather sample is too far from kickoff")
        if not -90 <= float(self.latitude) <= 90:
            raise EvidenceError("latitude is invalid")
        if not -180 <= float(self.longitude) <= 180:
            raise EvidenceError("longitude is invalid")
        for field in (
            "temperature_c",
            "relative_humidity_pct",
            "dew_point_c",
            "precipitation_probability_pct",
            "precipitation_mm",
            "surface_pressure_hpa",
            "cloud_cover_pct",
            "wind_speed_10m_kmh",
            "wind_direction_10m_deg",
            "wind_gusts_10m_kmh",
        ):
            _finite_optional(getattr(self, field), field)
        if len(self.source_payload_checksum) != 64:
            raise EvidenceError("weather source checksum must be SHA-256 hex")
        if any(
            char not in "0123456789abcdefABCDEF"
            for char in self.source_payload_checksum
        ):
            raise EvidenceError("weather source checksum must be SHA-256 hex")
        if not self.source_payload_ref.strip():
            raise EvidenceError("weather source payload ref must be non-empty")

    def to_feature_payload(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "roof_state": self.roof_state,
            "applies_to_play": self.weather_applies_to_play,
            "forecast_valid_at": self.forecast_valid_at,
            "sample_offset_seconds": self.sample_offset_seconds,
            "temperature_c": self.temperature_c,
            "relative_humidity_pct": self.relative_humidity_pct,
            "dew_point_c": self.dew_point_c,
            "precipitation_probability_pct": self.precipitation_probability_pct,
            "precipitation_mm": self.precipitation_mm,
            "surface_pressure_hpa": self.surface_pressure_hpa,
            "cloud_cover_pct": self.cloud_cover_pct,
            "wind_speed_10m_kmh": self.wind_speed_10m_kmh,
            "wind_direction_10m_deg": self.wind_direction_10m_deg,
            "wind_gusts_10m_kmh": self.wind_gusts_10m_kmh,
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class OpenMeteoWeatherClient:
    def __init__(
        self,
        *,
        archive: RawPayloadArchive,
        base_url: str = "https://api.open-meteo.com/v1/forecast",
        opener: Callable[[Request], bytes] | None = None,
    ) -> None:
        self.archive = archive
        self.base_url = base_url.rstrip("/")
        self.opener = opener or self._read

    @staticmethod
    def _read(request: Request) -> bytes:
        with urlopen(request, timeout=20) as response:
            return response.read()

    def forecast_for_game(
        self,
        *,
        game_id: str,
        latitude: float,
        longitude: float,
        kickoff_at: str,
        roof_state: str = "UNKNOWN",
    ) -> WeatherForecastObservation:
        kickoff = _timestamp(kickoff_at, "kickoff_at")
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "hourly": ",".join(_HOURLY_VARIABLES),
            "timezone": "UTC",
            "start_date": kickoff.date().isoformat(),
            "end_date": kickoff.date().isoformat(),
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }
        request = Request(
            f"{self.base_url}?{urlencode(params)}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        raw = self.opener(request)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise EvidenceError("Open-Meteo returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise EvidenceError("Open-Meteo response must be an object")

        receipt = self.archive.archive("forecast", params, payload)
        return canonical_weather_observation(
            game_id=game_id,
            latitude=latitude,
            longitude=longitude,
            kickoff_at=kickoff_at,
            roof_state=roof_state,
            payload=payload,
            receipt=receipt,
        )


def canonical_weather_observation(
    *,
    game_id: str,
    latitude: float,
    longitude: float,
    kickoff_at: str,
    roof_state: str,
    payload: dict[str, Any],
    receipt: ArchiveReceipt,
) -> WeatherForecastObservation:
    kickoff = _timestamp(kickoff_at, "kickoff_at")
    if roof_state not in _ROOF_STATES:
        raise EvidenceError("roof_state is unsupported")

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise EvidenceError("Open-Meteo hourly payload is missing")
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        raise EvidenceError("Open-Meteo hourly time series is missing")

    parsed_times: list[datetime] = []
    for value in times:
        text = str(value or "").strip()
        if not text:
            raise EvidenceError("Open-Meteo returned an empty hourly timestamp")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        parsed_times.append(parsed.astimezone(UTC))

    index = min(
        range(len(parsed_times)),
        key=lambda item: abs((parsed_times[item] - kickoff).total_seconds()),
    )
    valid = parsed_times[index]
    offset = abs((valid - kickoff).total_seconds())

    def value(name: str) -> float | None:
        series = hourly.get(name)
        if not isinstance(series, list) or index >= len(series):
            return None
        return _finite_optional(series[index], name)

    return WeatherForecastObservation(
        game_id=str(game_id),
        latitude=float(latitude),
        longitude=float(longitude),
        roof_state=roof_state,
        weather_applies_to_play=_weather_applies(roof_state),
        kickoff_at=kickoff.isoformat(),
        forecast_valid_at=valid.isoformat(),
        captured_at=receipt.captured_at,
        sample_offset_seconds=offset,
        temperature_c=value("temperature_2m"),
        relative_humidity_pct=value("relative_humidity_2m"),
        dew_point_c=value("dew_point_2m"),
        precipitation_probability_pct=value("precipitation_probability"),
        precipitation_mm=value("precipitation"),
        surface_pressure_hpa=value("surface_pressure"),
        cloud_cover_pct=value("cloud_cover"),
        wind_speed_10m_kmh=value("wind_speed_10m"),
        wind_direction_10m_deg=value("wind_direction_10m"),
        wind_gusts_10m_kmh=value("wind_gusts_10m"),
        source_payload_ref=receipt.ref,
        source_payload_checksum=receipt.checksum,
    )
