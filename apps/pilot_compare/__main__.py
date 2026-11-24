"""Compare two saved pilot runs against the same frozen manifest."""

import argparse
import json
import sys

from .runner import compare_pilots


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("before")
    parser.add_argument("after")
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        report = compare_pilots(args.before, args.after, args.manifest, args.output)
    except (OSError, ValueError):
        print(
            "Comparison failed: check frozen inputs and a new output path.",
            file=sys.stderr,
        )
        return 2
    print(
        json.dumps(
            {"cases": report["cases"], "transitions": report["transitions"]},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
