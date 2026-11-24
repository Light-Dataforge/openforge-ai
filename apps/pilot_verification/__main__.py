"""Verify saved pilot answers against supported pixel geometry, offline."""

import argparse
import json
import sys

from .runner import verify_pilot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        result = verify_pilot(args.run_dir, args.manifest, args.output)
    except (OSError, ValueError) as exc:
        print(f"pilot verification failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
