"""Export an offline saved-pilot verification report."""

import argparse
import json
import sys

from .renderer import build_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        summary = build_report(args.run_dir, args.manifest, args.output)
    except (OSError, ValueError):
        print(
            "Report failed: check frozen inputs and a new output path.", file=sys.stderr
        )
        return 2
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
