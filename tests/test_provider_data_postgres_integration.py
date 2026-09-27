import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import psycopg
import pytest

from quantbot.baseball.db import apply_migrations
from quantbot.baseball.provider_data import StandingSnapshot, TeamStatisticsSnapshot
from quantbot.baseball.provider_data_repository import PostgreSQLProviderDataRepository


def _standing(*, observed_at: str, win_pct: float) -> StandingSnapshot:
    return StandingSnapshot(
        snapshot_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"pit-standing-{observed_at}")),
        provider="api-sports-baseball",
        league_id=1,
        season=2026,
        team_id=990001,
        team_name="PIT Test Club",
        observed_at=observed_at,
        games_played=100,
        wins=int(round(win_pct * 100)),
        losses=100 - int(round(win_pct * 100)),
        win_percentage=win_pct,
        loss_percentage=1.0 - win_pct,
        runs_for=450.0,
        runs_against=420.0,
        position=1,
        stage=None,
        group_name=None,
        source_payload_ref=f"s3://raw/standing-{observed_at}.json",
        source_payload_checksum=("a" if win_pct < 0.6 else "b") * 64,
    )


def _team_stats(*, observed_at: str, win_pct: float) -> TeamStatisticsSnapshot:
    return TeamStatisticsSnapshot(
        snapshot_id=str(
            uuid.uuid5(uuid.NAMESPACE_URL, f"pit-team-stats-{observed_at}")
        ),
        provider="api-sports-baseball",
        league_id=1,
        season=2026,
        team_id=990001,
        team_name="PIT Test Club",
        observed_at=observed_at,
        games_played_all=100,
        games_played_home=50,
        games_played_away=50,
        wins_all=int(round(win_pct * 100)),
        wins_home=30,
        wins_away=25,
        win_pct_all=win_pct,
        win_pct_home=0.60,
        win_pct_away=0.50,
        losses_all=100 - int(round(win_pct * 100)),
        losses_home=20,
        losses_away=25,
        loss_pct_all=1.0 - win_pct,
        loss_pct_home=0.40,
        loss_pct_away=0.50,
        runs_for_total_all=450.0,
        runs_for_total_home=240.0,
        runs_for_total_away=210.0,
        runs_for_avg_all=4.5,
        runs_for_avg_home=4.8,
        runs_for_avg_away=4.2,
        runs_against_total_all=420.0,
        runs_against_total_home=200.0,
        runs_against_total_away=220.0,
        runs_against_avg_all=4.2,
        runs_against_avg_home=4.0,
        runs_against_avg_away=4.4,
        source_payload_ref=f"s3://raw/team-stats-{observed_at}.json",
        source_payload_checksum=("c" if win_pct < 0.6 else "d") * 64,
    )


def test_provider_repository_reads_team_strength_as_of_cutoff() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    early_time = "2026-09-20T12:00:00+00:00"
    late_time = "2026-09-20T16:00:00+00:00"

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLProviderDataRepository(connection)
        assert (
            repository.append_standings(
                (_standing(observed_at=early_time, win_pct=0.55),)
            )
            == 1
        )
        assert (
            repository.append_standings(
                (_standing(observed_at=late_time, win_pct=0.62),)
            )
            == 1
        )
        assert repository.append_team_statistics(
            _team_stats(observed_at=early_time, win_pct=0.55)
        )
        assert repository.append_team_statistics(
            _team_stats(observed_at=late_time, win_pct=0.62)
        )

        before_late_standing = repository.latest_standing(
            league_id=1,
            season=2026,
            team_id=990001,
            as_of=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
        )
        after_late_standing = repository.latest_standing(
            league_id=1,
            season=2026,
            team_id=990001,
            as_of=datetime(2026, 9, 20, 17, 0, tzinfo=UTC),
        )
        before_late_stats = repository.latest_team_statistics(
            league_id=1,
            season=2026,
            team_id=990001,
            as_of=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
        )
        after_late_stats = repository.latest_team_statistics(
            league_id=1,
            season=2026,
            team_id=990001,
            as_of=datetime(2026, 9, 20, 17, 0, tzinfo=UTC),
        )

    assert before_late_standing is not None
    assert before_late_standing.win_percentage == pytest.approx(0.55)
    assert after_late_standing is not None
    assert after_late_standing.win_percentage == pytest.approx(0.62)
    assert before_late_stats is not None
    assert before_late_stats.win_pct_all == pytest.approx(0.55)
    assert after_late_stats is not None
    assert after_late_stats.win_pct_all == pytest.approx(0.62)
    assert before_late_stats.compact_features() == {
        "sample_games": 100,
        "win_pct": 0.55,
        "runs_per_game": 4.5,
        "runs_allowed_per_game": 4.2,
        "run_differential_per_game": pytest.approx(0.3),
    }


def test_provider_repository_rejects_naive_as_of() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL is required for PostgreSQL integration testing")
    apply_migrations(Path("."), database_url)

    with psycopg.connect(database_url) as connection:
        repository = PostgreSQLProviderDataRepository(connection)
        with pytest.raises(ValueError, match="timezone-aware"):
            repository.latest_team_statistics(
                league_id=1,
                season=2026,
                team_id=990001,
                as_of=datetime(2026, 9, 20, 14, 0),  # noqa: DTZ001 - intentional
            )
