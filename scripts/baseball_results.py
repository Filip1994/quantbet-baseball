from __future__ import annotations

import argparse
import json
from pathlib import Path

from quantbot.baseball.results import collect_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Baseball game results")
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--date", action="append", dest="dates", required=True)
    parser.add_argument("--output", type=Path, default=Path("data/baseball/results.jsonl"))
    args = parser.parse_args()
    print(json.dumps(collect_results(args.root, args.dates, args.output), indent=2))


if __name__ == "__main__":
    main()
