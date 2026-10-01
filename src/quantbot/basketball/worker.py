from __future__ import annotations

import json
from quantbot.basketball.config import BOOKMAKER_ALLOWLIST, PRIMARY_MARKETS, BENCHMARK_MARKETS, EXCLUDED_MARKETS


def main() -> None:
    print(json.dumps({
        "service": "quantbet-basketball",
        "mode": "paper-pilot",
        "live_analysis": False,
        "bookmakers": sorted(BOOKMAKER_ALLOWLIST),
        "primary_markets": list(PRIMARY_MARKETS),
        "benchmark_markets": list(BENCHMARK_MARKETS),
        "excluded_markets": list(EXCLUDED_MARKETS),
        "status": "scaffold_ready",
    }))


if __name__ == "__main__":
    main()
