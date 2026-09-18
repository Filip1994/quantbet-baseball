import pytest

from quantbot.baseball.evidence import EvidenceError, OddsObservation
from quantbot.baseball.timeline import (
    closing_observation,
    opening_observation,
    reconstruct_epochs,
    select_observed_price,
)

BASE = {
    "game_id": "g-1",
    "market_family": "moneyline",
    "line": None,
    "selection": "home",
    "bookmaker": "book-a",
    "decimal_odds": 2.1,
    "raw_price": "+110",
    "retrieved_at": "2026-09-14T10:01:00+00:00",
    "source_payload_ref": "payload-1",
    "source_payload_checksum": "abc",
    "schema_version": "1.0",
    "market_status": "open",
    "kickoff_at": "2026-09-14T20:00:00+00:00",
}


def obs(identifier, observed_at, **changes):
    values = dict(BASE, observation_id=identifier, observed_at=observed_at)
    values.update(changes)
    return OddsObservation(**values)


def test_reconstructs_epochs_and_preserves_line_changes():
    records = [
        obs("a", "2026-09-14T10:00:00+00:00"),
        obs("b", "2026-09-14T11:00:00+00:00", line=None, selection="away"),
        obs(
            "c",
            "2026-09-14T12:00:00+00:00",
            market_family="total",
            line=8.5,
            selection="over",
        ),
    ]
    epochs = reconstruct_epochs(records)
    assert len(epochs) == 2
    assert {epoch.line for epoch in epochs} == {None, 8.5}


def test_opening_and_closing_are_observed_only():
    epoch = reconstruct_epochs(
        [
            obs("a", "2026-09-14T10:00:00+00:00"),
            obs("b", "2026-09-14T11:00:00+00:00", decimal_odds=2.2),
        ]
    )[0]
    assert opening_observation(epoch, "home").observation_id == "a"
    assert closing_observation(epoch, "home").observation_id == "b"
    assert (
        select_observed_price(epoch, "home", "2026-09-14T10:30:00+00:00").observation_id
        == "a"
    )
    assert select_observed_price(epoch, "home", "2026-09-14T09:00:00+00:00") is None


def test_conflicting_same_time_quote_is_rejected():
    with pytest.raises(EvidenceError):
        reconstruct_epochs(
            [
                obs("a", "2026-09-14T10:00:00+00:00"),
                obs("b", "2026-09-14T10:00:00+00:00", decimal_odds=2.2),
            ]
        )


def test_post_kickoff_observation_is_rejected_at_contract_boundary():
    with pytest.raises(EvidenceError):
        obs("late", "2026-09-14T20:00:00+00:00")
