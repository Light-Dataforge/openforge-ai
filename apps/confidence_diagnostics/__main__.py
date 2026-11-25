"""Describe confidence bins and whole-tie-group selective risk for exact answers."""

import argparse
import json
import sys

from core.evaluation.diagnostics import diagnose


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("references")
    parser.add_argument("predictions")
    parser.add_argument("--bins", type=int, default=10)
    args = parser.parse_args()
    try:
        report = diagnose(args.references, args.predictions, bins=args.bins)
    except (OSError, ValueError):
        print(
            "Diagnostics failed: check bounded inputs and bin count.", file=sys.stderr
        )
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
