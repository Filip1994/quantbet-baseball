from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, UTC
from pathlib import Path


def main() -> None:
    root = Path(".")
    snapshot_dir = root / "data" / "baseball" / "snapshots"
    rows = []
    for path in sorted(snapshot_dir.glob("*.jsonl")):
        with path.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)

    leagues = Counter()
    bookmakers = Counter()
    markets = Counter()
    games = {}
    errors = Counter()
    snapshots_by_day = Counter()

    for row in rows:
        day = str(row.get("captured_at", ""))[:10] or "UNKNOWN"
        snapshots_by_day[day] += 1
        league = str(row.get("league") or "UNKNOWN")
        leagues[league] += 1
        game_id = row.get("game_id")
        if game_id is not None:
            games[str(game_id)] = row
        if row.get("odds_error"):
            errors[str(row["odds_error"])] += 1
        odds = row.get("odds") or {}
        for name in odds.get("bookmaker_names") or []:
            bookmakers[str(name)] += 1
        for name in odds.get("market_names") or []:
            markets[str(name)] += 1

    generated = datetime.now(UTC).isoformat()
    out = root / "data" / "baseball" / "LIVE_API_AUDIT.md"
    lines = [
        "# QuantBet Baseball — Live API Audit",
        "",
        f"Generated: `{generated}`",
        "",
        "## Executive summary",
        "",
        f"- Snapshot rows collected: **{len(rows)}**",
        f"- Unique games observed: **{len(games)}**",
        f"- Leagues observed: **{len(leagues)}**",
        f"- Bookmakers observed: **{len(bookmakers)}**",
        f"- Distinct market names observed: **{len(markets)}**",
        f"- Odds/API errors recorded: **{sum(errors.values())}**",
        "",
        "## Leagues",
        "",
        "| League | Snapshot rows |",
        "|---|---:|",
    ]
    lines += [f"| {k} | {v} |" for k, v in leagues.most_common()]
    lines += ["", "## Bookmakers returned by API", "", "| Bookmaker | Snapshot appearances |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in bookmakers.most_common()]
    lines += ["", "## Markets returned by API", "", "| Market | Snapshot appearances |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in markets.most_common()]
    lines += ["", "## Snapshot days", "", "| Date | Rows |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in sorted(snapshots_by_day.items())]
    lines += ["", "## API errors", ""]
    if errors:
        lines += [f"- `{k}` — {v}" for k, v in errors.most_common()]
    else:
        lines.append("None recorded.")
    lines += [
        "",
        "## Interpretation",
        "",
        "This report is based on the actual snapshots returned by API-Sports Baseball, not the configured bookmaker allow-list. A bookmaker is only considered available when its name appears in a live response.",
        "",
        "The current collector is a data-footprint stage. It does not constitute a validated betting model, and no real-money staking is enabled.",
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
