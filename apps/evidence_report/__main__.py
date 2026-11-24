"""Export a revalidated offline pixel-evidence report."""

import argparse
import json
import sys

from .renderer import build_report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = build_report(args.run_dir, args.output)
    except (OSError, ValueError) as exc:
        print(f"report export failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
