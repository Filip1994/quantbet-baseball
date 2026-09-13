from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantbot.baseball.baseline import evaluate_implied_probability


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the raw implied-probability baseball baseline"
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("data/baseball/training/moneyline_dataset.jsonl"),
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_implied_probability(args.dataset), indent=2))


if __name__ == "__main__":
    main()
