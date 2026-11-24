"""Generate original synthetic images and inspect pixel-verification evidence."""

import argparse
import json
import sys

from apps.verification_demo.runner import run_demo


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        summary = run_demo(args.output)
    except (OSError, ValueError) as exc:
        print(f"verification demo failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True, indent=2, allow_nan=False))
    return 1 if summary["counts"]["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
