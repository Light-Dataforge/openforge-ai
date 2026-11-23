"""Run with python -m core.evaluation REFERENCES PREDICTIONS."""

import argparse
import json
import sys

from .metrics import evaluate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("references")
    parser.add_argument("predictions")
    args = parser.parse_args()
    try:
        result = evaluate(args.references, args.predictions)
    except (OSError, ValueError) as exc:
        print(f"evaluation failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
