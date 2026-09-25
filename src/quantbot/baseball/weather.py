"""Point-in-time stadium weather evidence for Baseball research."""

from __future__ import annotations

import json
import math
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from .raw_archive import ArchiveReceipt, RawPayloadArchive

_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
_HOURLY_FIELDS = (
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
    "weather_code",
)
_CLOSED_ROOF = {
    "closed",
    "dome",
    "fixed dome",
    "fixed_dome",
    "indoor",
    "retractable closed",
    "retractable_closed",
}


class WeatherEvidenceError(ValueError):
    """Raised when weather evidence cannot be made point-in-time and canonical."""


@dataclass(frozen=True, slots=True)
class VenueWeatherRequest:
    game_id: str
    latitude: float
    longitude: float
    kickoff_at: str
    roof_status: str

    def __post_init__(self) -> None:
        if not self.game_id.strip():
            raise WeatherEvidenceError("game_id must be non-empty")
        if not math.isfinite(self.latitude) or not -90 <= self.latitude <= 90:
            raise WeatherEvidenceError("latitude is invalid")
        if not math.isfinite(self.longitude) or not -180 <= self.longitude <= 180:
            raise WeatherEvidenceError("longitude is invalid")
        _timestamp(self.kickoff_at, "kickoff_at")
        if not self.roof_status.strip():
            raise WeatherEvidenceError("roof_status must be non-empty")


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    game_id: str
    provider: str
    latitude: float
    longitude: float
    roof_status: str
    forecast_for_at: str
    captured_at: str
    temperature_c: float
    relative_humidity_pct: float
    dew_point_c: float
    precipitation_probability_pct: float
    precipitation_mm: float
    surface_pressure_hpa: float
    cloud_cover_pct: float
    wind_speed_kph: float
    wind_direction_deg: float
    wind_gusts_kph: float
    weather_code: int
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.provider != "open-meteo":
            raise WeatherEvidenceError("provider is unsupported")
        for field in (
            "game_id",
            "roof_status",
            "source_payload_ref",
            "source_payload_checksum",
            "schema_version",
        ):
            if not str(getattr(self, field)).strip():
                raise WeatherEvidenceError(f"{field} must be non-empty")
        forecast_for = _timestamp(self.forecast_for_at, "forecast_for_at")
        captured = _timestamp(self.captured_at, "captured_at")
        if captured >= forecast_for:
            raise WeatherEvidenceError(
                "weather snapshot must be captured before the forecast target"
            )
        if len(self.source_payload_checksum) != 64:
            raise WeatherEvidenceError("source_payload_checksum must be SHA-256")
        for field in (
            "temperature_c",
            "relative_humidity_pct",
            "dew_point_c",
            "precipitation_probability_pct",
            "precipitation_mm",
            "surface_pressure_hpa",
            "cloud_cover_pct",
            "wind_speed_kph",
            "wind_direction_deg",
            "wind_gusts_kph",
        ):
            if not math.isfinite(float(getattr(self, field))):
                raise WeatherEvidenceError(f"{field} must be finite")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise WeatherEvidenceError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise WeatherEvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def weather_applicable(roof_status: str) -> bool:
    normalized = " ".join(roof_status.strip().casefold().replace("-", " ").split())
    return normalized not in _CLOSED_ROOF


def _open_meteo_transport(url: str) -> dict[str, Any]:
    with urlopen(url, timeout=20) as response:
        raw = response.read().decode("utf-8")
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise WeatherEvidenceError("Open-Meteo returned a non-object payload")
    return payload


def _utc_hour(value: str) -> datetime:
    raw = str(value).strip()
    if not raw:
        raise WeatherEvidenceError("weather hourly timestamp is empty")
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _numeric(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise WeatherEvidenceError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WeatherEvidenceError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise WeatherEvidenceError(f"{field} must be finite")
    return number


class OpenMeteoWeatherClient:
    """Fetch and archive one live pregame forecast at stadium coordinates."""

    def __init__(
        self,
        *,
        raw_archive: RawPayloadArchive,
        transport: Callable[[str], dict[str, Any]] | None = None,
        base_url: str = _FORECAST_URL,
    ) -> None:
        self.raw_archive = raw_archive
        self.transport = transport or _open_meteo_transport
        self.base_url = base_url.rstrip("?")

    def forecast(
        self,
        request: VenueWeatherRequest,
        *,
        captured_at: datetime | None = None,
    ) -> WeatherSnapshot | None:
        """Return a point-in-time game weather snapshot, or None for a closed roof."""

        if not weather_applicable(request.roof_status):
            return None

        kickoff = _timestamp(request.kickoff_at, "kickoff_at")
        captured = (captured_at or datetime.now(UTC)).astimezone(UTC)
        if captured >= kickoff:
            raise WeatherEvidenceError("weather must be captured before first pitch")

        day = kickoff.date().isoformat()
        params = {
            "latitude": request.latitude,
            "longitude": request.longitude,
            "hourly": ",".join(_HOURLY_FIELDS),
            "timezone": "UTC",
            "start_date": day,
            "end_date": day,
            "temperature_unit": "celsius",
            "wind_speed_unit": "kmh",
            "precipitation_unit": "mm",
        }
        payload = self.transport(f"{self.base_url}?{urlencode(params)}")
        receipt = self.raw_archive.archive(
            "open-meteo/forecast",
            params,
            payload,
            captured_at=captured,
        )
        return canonical_weather_snapshot(request, payload, receipt)


def canonical_weather_snapshot(
    request: VenueWeatherRequest,
    payload: dict[str, Any],
    receipt: ArchiveReceipt,
) -> WeatherSnapshot:
    """Map an archived Open-Meteo response to the hour nearest first pitch."""

    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise WeatherEvidenceError("weather payload has no hourly object")
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        raise WeatherEvidenceError("weather payload has no hourly time series")

    kickoff = _timestamp(request.kickoff_at, "kickoff_at")
    parsed_times = [_utc_hour(str(value)) for value in times]
    index = min(
        range(len(parsed_times)),
        key=lambda idx: abs((parsed_times[idx] - kickoff).total_seconds()),
    )
    forecast_for = parsed_times[index]

    def at(field: str) -> Any:
        values = hourly.get(field)
        if not isinstance(values, list) or index >= len(values):
            raise WeatherEvidenceError(f"weather payload missing {field}")
        return values[index]

    return WeatherSnapshot(
        game_id=request.game_id,
        provider="open-meteo",
        latitude=request.latitude,
        longitude=request.longitude,
        roof_status=request.roof_status,
        forecast_for_at=forecast_for.isoformat(),
        captured_at=receipt.captured_at,
        temperature_c=_numeric(at("temperature_2m"), "temperature_2m"),
        relative_humidity_pct=_numeric(
            at("relative_humidity_2m"), "relative_humidity_2m"
        ),
        dew_point_c=_numeric(at("dew_point_2m"), "dew_point_2m"),
        precipitation_probability_pct=_numeric(
            at("precipitation_probability"), "precipitation_probability"
        ),
        precipitation_mm=_numeric(at("precipitation"), "precipitation"),
        surface_pressure_hpa=_numeric(at("surface_pressure"), "surface_pressure"),
        cloud_cover_pct=_numeric(at("cloud_cover"), "cloud_cover"),
        wind_speed_kph=_numeric(at("wind_speed_10m"), "wind_speed_10m"),
        wind_direction_deg=_numeric(at("wind_direction_10m"), "wind_direction_10m"),
        wind_gusts_kph=_numeric(at("wind_gusts_10m"), "wind_gusts_10m"),
        weather_code=int(_numeric(at("weather_code"), "weather_code")),
        source_payload_ref=receipt.ref,
        source_payload_checksum=receipt.checksum,
    )
