from datetime import UTC, datetime

import pytest

from quantbot.baseball.evidence import EvidenceError
from quantbot.baseball.odds_poll_evidence import build_odds_poll_attempt
from quantbot.baseball.raw_archive import ArchiveReceipt


def test_build_poll_attempt_preserves_empty_response_provenance() -> None:
    receipt = ArchiveReceipt(
        ref="s3://raw/empty.json",
        checksum="a" * 64,
        captured_at="2030-09-18T17:00:00+00:00",
    )

    first = build_odds_poll_attempt(
        game_id=10,
        kickoff_at=datetime(2030, 9, 18, 19, 0, tzinfo=UTC),
        receipt=receipt,
        response_rows=0,
        raw_market_rows=0,
        canonical_rows=0,
    )
    second = build_odds_poll_attempt(
        game_id=10,
        kickoff_at=datetime(2030, 9, 18, 19, 0, tzinfo=UTC),
        receipt=receipt,
        response_rows=0,
        raw_market_rows=0,
        canonical_rows=0,
    )

    assert first == second
    assert first.response_rows == 0
    assert first.source_payload_ref == "s3://raw/empty.json"
    assert first.source_payload_checksum == "a" * 64


def test_poll_attempt_rejects_post_kickoff_capture() -> None:
    receipt = ArchiveReceipt(
        ref="s3://raw/late.json",
        checksum="b" * 64,
        captured_at="2030-09-18T19:00:00+00:00",
    )

    with pytest.raises(EvidenceError, match="must precede kickoff"):
        build_odds_poll_attempt(
            game_id=10,
            kickoff_at=datetime(2030, 9, 18, 19, 0, tzinfo=UTC),
            receipt=receipt,
            response_rows=0,
            raw_market_rows=0,
            canonical_rows=0,
        )
