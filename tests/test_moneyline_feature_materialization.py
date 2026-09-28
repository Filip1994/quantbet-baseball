from datetime import UTC, datetime
from types import SimpleNamespace

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.moneyline_feature_materialization import (
    materialize_due_moneyline_v1_features,
)


def _link(game_id: int, first_pitch: str):
    return SimpleNamespace(
        game_id=str(game_id),
        api_sports_provider_game_id=game_id,
        official_mlb_first_pitch=first_pitch,
    )


class _IdentityRepository:
    def __init__(self, links):
        self.links = tuple(links)

    def game_links(self, mapping_version):
        assert mapping_version == "mlb-2030-v1"
        return self.links

    def game_link_for_provider_game(self, **kwargs):
        raise AssertionError("assembler is patched in materialization tests")


class _FeatureRepository:
    def __init__(self, existing=()):
        self.existing = set(existing)

    def latest_for_game_version(self, *, game_id, feature_version, as_of):
        assert feature_version == "moneyline-v1"
        assert as_of.tzinfo is not None
        return object() if game_id in self.existing else None

    def append(self, snapshot):
        raise AssertionError("assembler is patched in materialization tests")


class _UnusedRepository:
    pass


def test_materialization_is_bounded_and_never_calls_provider(monkeypatch) -> None:
    calls = []

    def fake_assemble(*args, provider_game_id, mapping_version, as_of, **kwargs):
        calls.append((provider_game_id, mapping_version, as_of))
        return object(), True

    monkeypatch.setattr(
        "quantbot.baseball.moneyline_feature_materialization."
        "assemble_and_persist_moneyline_v1_feature_snapshot",
        fake_assemble,
    )
    now = datetime(2030, 7, 5, 16, 0, tzinfo=UTC)
    identity = _IdentityRepository(
        (
            _link(1, "2030-07-05T17:00:00+00:00"),
            _link(2, "2030-07-05T17:30:00+00:00"),
        )
    )

    result = materialize_due_moneyline_v1_features(
        _UnusedRepository(),
        identity,
        _UnusedRepository(),
        _UnusedRepository(),
        _FeatureRepository(),
        mapping_version="mlb-2030-v1",
        now=now,
        horizon_minutes=150,
        max_games=1,
    )

    assert result["status"] == "CAPACITY_LIMITED"
    assert result["due_games"] == 2
    assert result["games_considered"] == 1
    assert result["snapshots_inserted"] == 1
    assert result["due_games_unprocessed"] == 1
    assert result["provider_calls"] == 0
    assert [item[0] for item in calls] == [1]


def test_existing_v1_snapshot_is_zero_repeat(monkeypatch) -> None:
    calls = []

    def fake_assemble(*args, **kwargs):
        calls.append(kwargs)
        return object(), True

    monkeypatch.setattr(
        "quantbot.baseball.moneyline_feature_materialization."
        "assemble_and_persist_moneyline_v1_feature_snapshot",
        fake_assemble,
    )

    result = materialize_due_moneyline_v1_features(
        _UnusedRepository(),
        _IdentityRepository((_link(1, "2030-07-05T17:00:00+00:00"),)),
        _UnusedRepository(),
        _UnusedRepository(),
        _FeatureRepository(existing=("1",)),
        mapping_version="mlb-2030-v1",
        now=datetime(2030, 7, 5, 16, 0, tzinfo=UTC),
    )

    assert result["status"] == "COMPLETE"
    assert result["already_materialized"] == 1
    assert result["games_considered"] == 0
    assert result["snapshots_inserted"] == 0
    assert result["provider_calls"] == 0
    assert calls == []


def test_incomplete_evidence_stays_retryable(monkeypatch) -> None:
    def blocked(*args, **kwargs):
        raise EvidenceError("complete team statistics are unavailable by cutoff")

    monkeypatch.setattr(
        "quantbot.baseball.moneyline_feature_materialization."
        "assemble_and_persist_moneyline_v1_feature_snapshot",
        blocked,
    )

    result = materialize_due_moneyline_v1_features(
        _UnusedRepository(),
        _IdentityRepository((_link(1, "2030-07-05T17:00:00+00:00"),)),
        _UnusedRepository(),
        _UnusedRepository(),
        _FeatureRepository(),
        mapping_version="mlb-2030-v1",
        now=datetime(2030, 7, 5, 16, 0, tzinfo=UTC),
    )

    assert result["status"] == "BLOCKED_EVIDENCE"
    assert result["evidence_blocked"] == 1
    assert result["snapshots_inserted"] == 0
    assert result["provider_calls"] == 0


def test_games_outside_horizon_are_not_materialized(monkeypatch) -> None:
    calls = []

    def fake_assemble(*args, **kwargs):
        calls.append(kwargs)
        return object(), True

    monkeypatch.setattr(
        "quantbot.baseball.moneyline_feature_materialization."
        "assemble_and_persist_moneyline_v1_feature_snapshot",
        fake_assemble,
    )

    result = materialize_due_moneyline_v1_features(
        _UnusedRepository(),
        _IdentityRepository((_link(1, "2030-07-05T20:00:00+00:00"),)),
        _UnusedRepository(),
        _UnusedRepository(),
        _FeatureRepository(),
        mapping_version="mlb-2030-v1",
        now=datetime(2030, 7, 5, 16, 0, tzinfo=UTC),
        horizon_minutes=150,
    )

    assert result["status"] == "NO_DUE_GAMES"
    assert result["due_games"] == 0
    assert calls == []
