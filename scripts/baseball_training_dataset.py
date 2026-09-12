from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantbot.baseball.training_dataset import build_from_files


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a leakage-safe Baseball moneyline dataset")
    parser.add_argument("--observations", type=Path, default=Path("data/baseball/market_observations.jsonl"))
    parser.add_argument("--results", type=Path, required=True, help="JSONL of resolved game records")
    parser.add_argument("--output", type=Path, default=Path("data/baseball/training/moneyline_dataset.jsonl"))
    args = parser.parse_args()
    summary = build_from_files(args.observations, args.results, args.output)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
