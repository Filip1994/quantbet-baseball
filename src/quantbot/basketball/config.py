from __future__ import annotations

BOOKMAKER_ALLOWLIST = {"1xbet", "bet365"}

MARKETS = {
    "FT": 4,
    "1H": 5,
    "Q1": 16,
    "Q2": 45,
    "Q3": 46,
}

PRIMARY_MARKETS = ("1H", "Q1", "Q2", "Q3")
BENCHMARK_MARKETS = ("FT",)
EXCLUDED_MARKETS = ("Q4",)

PAPER_ONLY = True
LIVE_ANALYSIS = False
