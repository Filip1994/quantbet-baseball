from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any


_REQUIRED = ("game_id", "generated_at", "decision", "reason")


def _timestamp(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.isoformat()


def validate_signal_record(record: Any) -> bool:
    """Validate the minimum immutable envelope for an auditable signal record."""
    if not isinstance(record, dict):
        return False
    if any(
        not isinstance(record.get(field), str) or not record[field].strip()
        for field in _REQUIRED
    ):
        return False
    if record["decision"] not in {"BET", "PASS"}:
        return False
    if _timestamp(record["generated_at"]) is None:
        return False
    for key in ("edge", "expected_value", "fair_decimal_odds"):
        if key in record:
            value = record[key]
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(float(value))
            ):
                return False
    return True


def serialize_signal_record(record: dict[str, Any]) -> str | None:
    """Serialize a validated signal record deterministically as one JSON line."""
    if not validate_signal_record(record):
        return None
    return json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False)
