from __future__ import annotations

import json
from pathlib import Path

from quantbot.baseball.collection_canary import run_controlled_canary


def main() -> None:
    result = run_controlled_canary(Path("."))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
