from __future__ import annotations

import json
import unittest

from quantbot.baseball.signal_record import serialize_signal_record, validate_signal_record


class SignalRecordTests(unittest.TestCase):
    def _record(self) -> dict[str, object]:
        return {
            "game_id": "g1",
            "generated_at": "2026-09-15T12:00:00+00:00",
            "decision": "PASS",
            "reason": "uncertainty_gate_not_met",
            "edge": 0.04,
            "expected_value": 0.08,
            "fair_decimal_odds": 1.8,
        }

    def test_valid_record(self) -> None:
        self.assertTrue(validate_signal_record(self._record()))

    def test_naive_timestamp_is_rejected(self) -> None:
        record = self._record()
        record["generated_at"] = "2026-09-15T12:00:00"
        self.assertFalse(validate_signal_record(record))

    def test_invalid_decision_is_rejected(self) -> None:
        record = self._record()
        record["decision"] = "MAYBE"
        self.assertFalse(validate_signal_record(record))

    def test_nonfinite_metric_is_rejected(self) -> None:
        record = self._record()
        record["edge"] = float("nan")
        self.assertFalse(validate_signal_record(record))

    def test_serialization_is_deterministic_jsonl(self) -> None:
        serialized = serialize_signal_record(self._record())
        self.assertIsNotNone(serialized)
        self.assertEqual(json.loads(serialized), self._record())
        self.assertEqual(serialized, serialize_signal_record(self._record()))

    def test_invalid_record_serializes_to_none(self) -> None:
        self.assertIsNone(serialize_signal_record({}))


if __name__ == "__main__":
    unittest.main()
