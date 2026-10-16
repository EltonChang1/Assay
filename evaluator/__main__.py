"""Run repository-only, developer-authored fixture validation."""

from __future__ import annotations

import argparse
import json

from evaluator import run_milestone


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate exposed development fixtures; accepts no SQL or model input."
    )
    parser.parse_args()
    result = run_milestone()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
