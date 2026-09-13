from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _load(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def evaluate_implied_probability(path: Path) -> dict[str, Any]:
    rows = sorted(_load(path), key=lambda row: row.get("captured_at", ""))
    if not rows:
        return {"rows": 0, "brier_score": None, "log_loss": None, "accuracy": None}
    brier = 0.0
    log_loss = 0.0
    correct = 0
    for row in rows:
        p = min(max(float(row["implied_probability"]), 1e-12), 1 - 1e-12)
        y = int(row["target"])
        brier += (p - y) ** 2
        log_loss -= y * math.log(p) + (1 - y) * math.log(1 - p)
        correct += int((p >= 0.5) == bool(y))
    n = len(rows)
    return {"rows": n, "games": len({str(row.get("game_id")) for row in rows}), "brier_score": brier / n, "log_loss": log_loss / n, "accuracy": correct / n, "baseline": "raw_implied_probability", "warning": "descriptive baseline; not a profitability claim"}
