"""Compare two complete prediction sets using paired task resampling."""

import argparse
import json
import sys

from core.evaluation.paired import compare_predictions


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("references")
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--replicates", type=int, default=1000)
    args = parser.parse_args()
    try:
        result = compare_predictions(
            args.references,
            args.before,
            args.after,
            seed=args.seed,
            replicates=args.replicates,
        )
    except (OSError, ValueError):
        print(
            "Paired evaluation failed: check bounded inputs, seed and draw budget.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
