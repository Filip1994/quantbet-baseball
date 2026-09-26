from dataclasses import replace

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.game_history import (
    canonical_game_history,
    derive_team_schedule_features,
)
from quantbot.baseball.raw_archive import ArchiveReceipt


def _receipt(at: str, checksum: str = "a" * 64) -> ArchiveReceipt:
    return ArchiveReceipt(
        ref=f"s3://raw/{at}.json",
        checksum=checksum,
        captured_at=at,
    )


def _row(
    game_id: int,
    first_pitch: str,
    *,
    home_id: int,
    away_id: int,
    status_short: str = "FT",
    home_total: int | None = 5,
    away_total: int | None = 3,
    home_extra: int | None = None,
    away_extra: int | None = None,
) -> dict:
    return {
        "id": game_id,
        "date": first_pitch,
        "time": first_pitch[11:16],
        "timestamp": 1,
        "timezone": "UTC",
        "status": {
            "long": "Finished" if status_short == "FT" else "Not Started",
            "short": status_short,
        },
        "league": {"id": 1, "name": "MLB", "season": 2026},
        "teams": {
            "home": {"id": home_id, "name": f"Team {home_id}"},
            "away": {"id": away_id, "name": f"Team {away_id}"},
        },
        "scores": {
            "home": {
                "hits": 10 if home_total is not None else None,
                "errors": 1 if home_total is not None else None,
                "innings": {
                    "1": 1 if home_total is not None else None,
                    "9": 0 if home_total is not None else None,
                    "extra": home_extra,
                },
                "total": home_total,
            },
            "away": {
                "hits": 8 if away_total is not None else None,
                "errors": 0 if away_total is not None else None,
                "innings": {
                    "1": 0 if away_total is not None else None,
                    "9": 0 if away_total is not None else None,
                    "extra": away_extra,
                },
                "total": away_total,
            },
        },
    }


def _snapshot(row: dict, observed_at: str, checksum: str = "a" * 64):
    return canonical_game_history(
        [row],
        _receipt(observed_at, checksum),
        league_id=1,
        season=2026,
    )[0]


def test_game_history_captures_verified_score_detail_and_extra_innings() -> None:
    record = _snapshot(
        _row(
            185629,
            "2026-09-08T00:10:00+00:00",
            home_id=31,
            away_id=33,
            home_total=5,
            away_total=4,
            home_extra=2,
            away_extra=1,
        ),
        "2026-09-08T03:00:00+00:00",
    )

    assert record.provider_game_id == 185629
    assert record.home_score == 5
    assert record.away_score == 4
    assert record.home_hits == 10
    assert record.away_errors == 0
    assert record.home_innings["extra"] == 2
    assert record.away_innings["extra"] == 1
    assert record.went_extra_innings is True
    assert record.total_runs == 9


def test_nonfinal_game_does_not_fabricate_result_or_extra_context() -> None:
    record = _snapshot(
        _row(
            200000,
            "2026-09-27T17:00:00+00:00",
            home_id=10,
            away_id=20,
            status_short="NS",
            home_total=None,
            away_total=None,
        ),
        "2026-09-26T08:00:00+00:00",
    )

    assert record.home_score is None
    assert record.away_score is None
    assert record.went_extra_innings is None
    assert record.total_runs is None


def test_schedule_features_use_only_point_in_time_known_snapshots() -> None:
    prior_old = _snapshot(
        _row(
            100,
            "2026-09-24T17:00:00+00:00",
            home_id=10,
            away_id=30,
            home_extra=0,
            away_extra=1,
        ),
        "2026-09-24T21:00:00+00:00",
        "a" * 64,
    )
    # Same provider game observed again after the decision cutoff; must be ignored.
    prior_future_observation = replace(
        prior_old,
        snapshot_id="future-observation",
        observed_at="2026-09-26T16:30:00+00:00",
        home_score=99,
    )
    prior_recent = _snapshot(
        _row(
            101,
            "2026-09-25T17:00:00+00:00",
            home_id=40,
            away_id=10,
        ),
        "2026-09-25T21:00:00+00:00",
        "b" * 64,
    )
    target = _snapshot(
        _row(
            102,
            "2026-09-26T17:00:00+00:00",
            home_id=10,
            away_id=40,
            status_short="NS",
            home_total=None,
            away_total=None,
        ),
        "2026-09-26T08:00:00+00:00",
        "c" * 64,
    )

    features = derive_team_schedule_features(
        target=target,
        team_id=10,
        history=[prior_old, prior_future_observation, prior_recent],
        cutoff_at="2026-09-26T16:00:00+00:00",
    )

    assert features.previous_game_id == 101
    assert features.hours_since_previous_first_pitch == 24.0
    assert features.utc_calendar_days_off == 0
    assert features.games_last_72h == 2
    assert features.games_last_168h == 2
    assert features.current_site == "HOME"
    assert features.current_site_streak_games == 1
    assert features.same_opponent_consecutive_games == 2
    assert features.source_games_considered == 2


def test_schedule_features_expose_previous_extra_innings_without_future_data() -> None:
    prior = _snapshot(
        _row(
            110,
            "2026-09-25T17:00:00+00:00",
            home_id=10,
            away_id=40,
            home_extra=2,
            away_extra=1,
        ),
        "2026-09-25T22:00:00+00:00",
    )
    target = _snapshot(
        _row(
            111,
            "2026-09-26T17:00:00+00:00",
            home_id=40,
            away_id=10,
            status_short="NS",
            home_total=None,
            away_total=None,
        ),
        "2026-09-26T08:00:00+00:00",
        "b" * 64,
    )

    features = derive_team_schedule_features(
        target=target,
        team_id=10,
        history=[prior],
        cutoff_at="2026-09-26T16:00:00+00:00",
    )

    assert features.previous_game_went_extra_innings is True
    assert features.same_opponent_consecutive_games == 2


def test_target_schedule_must_itself_exist_by_cutoff() -> None:
    target = _snapshot(
        _row(
            120,
            "2026-09-26T17:00:00+00:00",
            home_id=10,
            away_id=20,
            status_short="NS",
            home_total=None,
            away_total=None,
        ),
        "2026-09-26T16:30:00+00:00",
    )

    with pytest.raises(EvidenceError, match="target schedule snapshot exceeds"):
        derive_team_schedule_features(
            target=target,
            team_id=10,
            history=[],
            cutoff_at="2026-09-26T16:00:00+00:00",
        )


def test_same_day_schedule_marks_only_inferred_doubleheader() -> None:
    first = _snapshot(
        _row(
            130,
            "2026-09-26T15:00:00+00:00",
            home_id=10,
            away_id=20,
            status_short="NS",
            home_total=None,
            away_total=None,
        ),
        "2026-09-26T08:00:00+00:00",
    )
    target = _snapshot(
        _row(
            131,
            "2026-09-26T21:00:00+00:00",
            home_id=10,
            away_id=20,
            status_short="NS",
            home_total=None,
            away_total=None,
        ),
        "2026-09-26T08:00:00+00:00",
        "b" * 64,
    )

    features = derive_team_schedule_features(
        target=target,
        team_id=10,
        history=[first],
        cutoff_at="2026-09-26T14:00:00+00:00",
    )

    assert features.same_utc_day_games == 2
    assert features.inferred_doubleheader is True
