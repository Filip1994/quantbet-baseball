"""Official MLB point-in-time pregame evidence.

The Stats API source is free/public, but model admission still requires immutable
raw archival and an actual provider timestamp. Historical `timecode` requests
must never be treated as if the requested time were the returned snapshot time.
"""

from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .evidence import EvidenceError
from .raw_archive import ArchiveReceipt, RawPayloadArchive

_BASE_URL = "https://statsapi.mlb.com/api"
_PROVIDER = "official-mlb-stats-api"
_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL,
    "https://quantbet-baseball/official-mlb-pregame-snapshot/v1",
)


class OfficialMLBError(RuntimeError):
    """Raised when official MLB evidence cannot be fetched or canonicalized."""


def _iso_timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _metadata_timestamp(value: Any) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise EvidenceError("MLB feed metaData.timeStamp is required")
    try:
        return datetime.strptime(raw, "%Y%m%d_%H%M%S").replace(tzinfo=UTC)
    except ValueError as exc:
        raise EvidenceError("MLB feed metaData.timeStamp is invalid") from exc


def _positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be a positive integer")
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be a positive integer") from exc
    if number <= 0:
        raise EvidenceError(f"{field} must be a positive integer")
    return number


def _optional_positive_int(value: Any, field: str) -> int | None:
    if value in (None, ""):
        return None
    return _positive_int(value, field)


def _optional_float(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        raise EvidenceError(f"{field} must be numeric")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EvidenceError(f"{field} must be numeric") from exc
    if not math.isfinite(number):
        raise EvidenceError(f"{field} must be finite")
    return number


def _string(value: Any) -> str:
    return str(value or "").strip()


def _id_tuple(values: Any) -> tuple[int, ...]:
    if not isinstance(values, list):
        return ()
    result: list[int] = []
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item > 0:
            result.append(item)
    return tuple(result)


def _nested(mapping: Any, *keys: str) -> Any:
    current = mapping
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _checksum(value: str) -> str:
    raw = str(value or "").strip()
    if len(raw) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in raw):
        raise EvidenceError("source_payload_checksum must be a SHA-256 hex digest")
    return raw


@dataclass(frozen=True, slots=True)
class OfficialMLBPregameSnapshot:
    snapshot_id: str
    mlb_game_pk: int
    provider: str
    source_observed_at: str
    retrieved_at: str
    scheduled_first_pitch: str
    requested_timecode: str | None
    status_abstract: str
    status_detailed: str
    day_night: str
    away_team_id: int
    away_team_name: str
    home_team_id: int
    home_team_name: str
    away_record_wins: int | None
    away_record_losses: int | None
    away_record_games_played: int | None
    away_record_win_pct: float | None
    home_record_wins: int | None
    home_record_losses: int | None
    home_record_games_played: int | None
    home_record_win_pct: float | None
    away_probable_pitcher_id: int | None
    away_probable_pitcher_name: str | None
    home_probable_pitcher_id: int | None
    home_probable_pitcher_name: str | None
    away_batting_order_ids: tuple[int, ...]
    home_batting_order_ids: tuple[int, ...]
    away_bullpen_ids: tuple[int, ...]
    home_bullpen_ids: tuple[int, ...]
    lineup_state: str
    venue_id: int
    venue_name: str
    roof_type: str | None
    turf_type: str | None
    elevation_ft: float | None
    latitude: float | None
    longitude: float | None
    field_azimuth_deg: float | None
    left_line_ft: float | None
    left_center_ft: float | None
    center_ft: float | None
    right_center_ft: float | None
    right_line_ft: float | None
    venue_timezone: str | None
    venue_utc_offset_at_game: float | None
    source_payload_ref: str
    source_payload_checksum: str
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.provider != _PROVIDER:
            raise EvidenceError("official MLB provider is unsupported")
        for field in (
            "snapshot_id",
            "status_abstract",
            "status_detailed",
            "away_team_name",
            "home_team_name",
            "venue_name",
            "source_payload_ref",
            "schema_version",
        ):
            if not _string(getattr(self, field)):
                raise EvidenceError(f"{field} must be non-empty")
        _positive_int(self.mlb_game_pk, "mlb_game_pk")
        _positive_int(self.away_team_id, "away_team_id")
        _positive_int(self.home_team_id, "home_team_id")
        _positive_int(self.venue_id, "venue_id")
        observed = _iso_timestamp(self.source_observed_at, "source_observed_at")
        retrieved = _iso_timestamp(self.retrieved_at, "retrieved_at")
        kickoff = _iso_timestamp(self.scheduled_first_pitch, "scheduled_first_pitch")
        if observed >= kickoff:
            raise EvidenceError("official MLB pregame snapshot must precede first pitch")
        if retrieved < observed:
            raise EvidenceError("retrieved_at cannot precede source_observed_at")
        _checksum(self.source_payload_checksum)
        if self.lineup_state not in {"ABSENT", "PARTIAL", "POPULATED"}:
            raise EvidenceError("lineup_state is unsupported")
        for field in (
            "latitude",
            "longitude",
            "field_azimuth_deg",
            "elevation_ft",
            "left_line_ft",
            "left_center_ft",
            "center_ft",
            "right_center_ft",
            "right_line_ft",
            "venue_utc_offset_at_game",
        ):
            value = getattr(self, field)
            if value is not None and not math.isfinite(float(value)):
                raise EvidenceError(f"{field} must be finite")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise EvidenceError("latitude is invalid")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise EvidenceError("longitude is invalid")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _lineup_state(away: tuple[int, ...], home: tuple[int, ...]) -> str:
    if not away and not home:
        return "ABSENT"
    if len(away) >= 9 and len(home) >= 9:
        return "POPULATED"
    return "PARTIAL"


def canonical_pregame_snapshot(
    payload: dict[str, Any],
    receipt: ArchiveReceipt,
    *,
    requested_timecode: str | None = None,
) -> OfficialMLBPregameSnapshot:
    game_pk = _positive_int(payload.get("gamePk"), "gamePk")
    game_data = payload.get("gameData")
    live_data = payload.get("liveData")
    metadata = payload.get("metaData")
    if not isinstance(game_data, dict) or not isinstance(live_data, dict):
        raise EvidenceError("MLB game feed is missing gameData/liveData")
    if not isinstance(metadata, dict):
        raise EvidenceError("MLB game feed is missing metaData")

    observed = _metadata_timestamp(metadata.get("timeStamp"))
    retrieved = _iso_timestamp(receipt.captured_at, "receipt.captured_at")
    kickoff = _iso_timestamp(
        _string(_nested(game_data, "datetime", "dateTime")),
        "gameData.datetime.dateTime",
    )

    teams = game_data.get("teams") or {}
    away_team = teams.get("away") or {}
    home_team = teams.get("home") or {}
    probable = game_data.get("probablePitchers") or {}
    away_probable = probable.get("away") or {}
    home_probable = probable.get("home") or {}

    boxscore_teams = _nested(live_data, "boxscore", "teams") or {}
    away_box = boxscore_teams.get("away") or {}
    home_box = boxscore_teams.get("home") or {}
    away_order = _id_tuple(away_box.get("battingOrder"))
    home_order = _id_tuple(home_box.get("battingOrder"))

    venue = game_data.get("venue") or {}
    field = venue.get("fieldInfo") or {}
    location = venue.get("location") or {}
    coordinates = location.get("defaultCoordinates") or {}
    timezone = venue.get("timeZone") or {}

    away_record = away_team.get("record") or {}
    home_record = home_team.get("record") or {}

    identity = {
        "game_pk": game_pk,
        "source_observed_at": observed.isoformat(),
        "source_payload_checksum": receipt.checksum,
    }
    snapshot_id = str(
        uuid.uuid5(
            _NAMESPACE,
            json.dumps(identity, sort_keys=True, separators=(",", ":")),
        )
    )

    return OfficialMLBPregameSnapshot(
        snapshot_id=snapshot_id,
        mlb_game_pk=game_pk,
        provider=_PROVIDER,
        source_observed_at=observed.isoformat(),
        retrieved_at=retrieved.isoformat(),
        scheduled_first_pitch=kickoff.isoformat(),
        requested_timecode=_string(requested_timecode) or None,
        status_abstract=_string(_nested(game_data, "status", "abstractGameState"))
        or "UNKNOWN",
        status_detailed=_string(_nested(game_data, "status", "detailedState"))
        or "UNKNOWN",
        day_night=_string(_nested(game_data, "datetime", "dayNight")) or "UNKNOWN",
        away_team_id=_positive_int(away_team.get("id"), "away_team.id"),
        away_team_name=_string(away_team.get("name")),
        home_team_id=_positive_int(home_team.get("id"), "home_team.id"),
        home_team_name=_string(home_team.get("name")),
        away_record_wins=_optional_positive_int(
            away_record.get("wins"), "away_record.wins"
        ),
        away_record_losses=_optional_positive_int(
            away_record.get("losses"), "away_record.losses"
        ),
        away_record_games_played=_optional_positive_int(
            away_record.get("gamesPlayed"), "away_record.gamesPlayed"
        ),
        away_record_win_pct=_optional_float(
            away_record.get("winningPercentage"), "away_record.winningPercentage"
        ),
        home_record_wins=_optional_positive_int(
            home_record.get("wins"), "home_record.wins"
        ),
        home_record_losses=_optional_positive_int(
            home_record.get("losses"), "home_record.losses"
        ),
        home_record_games_played=_optional_positive_int(
            home_record.get("gamesPlayed"), "home_record.gamesPlayed"
        ),
        home_record_win_pct=_optional_float(
            home_record.get("winningPercentage"), "home_record.winningPercentage"
        ),
        away_probable_pitcher_id=_optional_positive_int(
            away_probable.get("id"), "away_probable.id"
        ),
        away_probable_pitcher_name=_string(away_probable.get("fullName")) or None,
        home_probable_pitcher_id=_optional_positive_int(
            home_probable.get("id"), "home_probable.id"
        ),
        home_probable_pitcher_name=_string(home_probable.get("fullName")) or None,
        away_batting_order_ids=away_order,
        home_batting_order_ids=home_order,
        away_bullpen_ids=_id_tuple(away_box.get("bullpen")),
        home_bullpen_ids=_id_tuple(home_box.get("bullpen")),
        lineup_state=_lineup_state(away_order, home_order),
        venue_id=_positive_int(venue.get("id"), "venue.id"),
        venue_name=_string(venue.get("name")),
        roof_type=_string(field.get("roofType")) or None,
        turf_type=_string(field.get("turfType")) or None,
        elevation_ft=_optional_float(location.get("elevation"), "venue.elevation"),
        latitude=_optional_float(coordinates.get("latitude"), "venue.latitude"),
        longitude=_optional_float(coordinates.get("longitude"), "venue.longitude"),
        field_azimuth_deg=_optional_float(
            location.get("azimuthAngle"), "venue.azimuthAngle"
        ),
        left_line_ft=_optional_float(field.get("leftLine"), "venue.leftLine"),
        left_center_ft=_optional_float(field.get("leftCenter"), "venue.leftCenter"),
        center_ft=_optional_float(field.get("center"), "venue.center"),
        right_center_ft=_optional_float(
            field.get("rightCenter"), "venue.rightCenter"
        ),
        right_line_ft=_optional_float(field.get("rightLine"), "venue.rightLine"),
        venue_timezone=_string(timezone.get("id")) or None,
        venue_utc_offset_at_game=_optional_float(
            timezone.get("offsetAtGameTime"), "venue.offsetAtGameTime"
        ),
        source_payload_ref=receipt.ref,
        source_payload_checksum=_checksum(receipt.checksum),
    )


def canonical_pregame_snapshot_json(snapshot: OfficialMLBPregameSnapshot) -> str:
    return json.dumps(
        snapshot.to_dict(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _http_transport(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "quantbet-baseball/official-mlb-evidence",
        },
        method="GET",
    )
    try:
        with urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise OfficialMLBError(f"official MLB HTTP {response.status}")
            body = response.read(4_000_000)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise OfficialMLBError("official MLB request failed") from exc
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OfficialMLBError("official MLB returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise OfficialMLBError("official MLB returned a non-object payload")
    return payload


class OfficialMLBStatsClient:
    """Small archived client for official MLB schedule/feed evidence."""

    def __init__(
        self,
        *,
        raw_archive: RawPayloadArchive,
        transport: Callable[[str], dict[str, Any]] | None = None,
        base_url: str = _BASE_URL,
    ) -> None:
        self.raw_archive = raw_archive
        self.transport = transport or _http_transport
        self.base_url = base_url.rstrip("/")

    def schedule_with_receipt(
        self,
        date_iso: str,
        *,
        captured_at: datetime | None = None,
    ) -> tuple[dict[str, Any], ArchiveReceipt]:
        params = {
            "sportId": "1",
            "date": date_iso,
            "hydrate": "probablePitcher,team,venue",
        }
        url = f"{self.base_url}/v1/schedule?{urlencode(params)}"
        payload = self.transport(url)
        receipt = self.raw_archive.archive(
            "official-mlb/v1/schedule",
            params,
            payload,
            captured_at=captured_at,
        )
        return payload, receipt

    def game_feed_with_receipt(
        self,
        game_pk: int,
        *,
        timecode: str | None = None,
        captured_at: datetime | None = None,
    ) -> tuple[dict[str, Any], ArchiveReceipt]:
        game_pk = _positive_int(game_pk, "game_pk")
        params: dict[str, Any] = {}
        if _string(timecode):
            params["timecode"] = _string(timecode)
        suffix = f"?{urlencode(params)}" if params else ""
        endpoint = f"/v1.1/game/{game_pk}/feed/live"
        payload = self.transport(f"{self.base_url}{endpoint}{suffix}")
        receipt = self.raw_archive.archive(
            f"official-mlb{endpoint}",
            params,
            payload,
            captured_at=captured_at,
        )
        return payload, receipt

    def pregame_snapshot(
        self,
        game_pk: int,
        *,
        timecode: str | None = None,
        captured_at: datetime | None = None,
    ) -> OfficialMLBPregameSnapshot:
        payload, receipt = self.game_feed_with_receipt(
            game_pk,
            timecode=timecode,
            captured_at=captured_at,
        )
        return canonical_pregame_snapshot(
            payload,
            receipt,
            requested_timecode=timecode,
        )


def source_payload_digest(payload: dict[str, Any]) -> str:
    """Deterministic helper for audit/replay tests; archive checksum remains authoritative."""

    raw = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
