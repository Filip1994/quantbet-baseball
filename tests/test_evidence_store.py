from datetime import datetime, timezone

import pytest

from quantbot.baseball.evidence import EvidenceError, OddsObservation, PickEvent
from quantbot.baseball.evidence_store import EvidenceStore


KICKOFF = "2026-09-20T19:00:00+00:00"


def observation(odds=2.1, observation_id="o-1"):
    return OddsObservation(
        observation_id=observation_id,
        game_id="game-1",
        market_family="moneyline",
        line=None,
        selection="home",
        bookmaker="book-a",
        decimal_odds=odds,
        raw_price=str(odds),
        observed_at="2026-09-20T17:00:00+00:00",
        retrieved_at="2026-09-20T17:00:01+00:00",
        source_payload_ref="payload-1",
        source_payload_checksum="a" * 64,
        schema_version="1.0",
        market_status="open",
        kickoff_at=KICKOFF,
    )


def test_exact_duplicate_is_idempotent():
    store = EvidenceStore()
    record = observation()
    assert store.append_observation(record) is True
    assert store.append_observation(record) is False
    assert store.stats().observations == 1


def test_conflicting_duplicate_is_rejected():
    store = EvidenceStore()
    store.append_observation(observation())
    with pytest.raises(EvidenceError):
        store.append_observation(observation(2.2))


def test_records_are_returned_deterministically():
    store = EvidenceStore()
    store.append_observation(observation(observation_id="o-2"))
    store.append_observation(observation(observation_id="o-1"))
    assert [item.observation_id for item in store.observations()] == ["o-1", "o-2"]
