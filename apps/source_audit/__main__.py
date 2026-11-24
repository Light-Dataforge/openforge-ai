"""Compare a saved source inventory against this checkout's observed files."""

import argparse
import json
import sys

from .runner import audit_source


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir")
    args = parser.parse_args()
    try:
        report = audit_source(args.run_dir)
    except (OSError, ValueError):
        print(
            "Source audit failed: check bounded frozen metadata and source files.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(report, sort_keys=True, allow_nan=False))
    return 0 if report["status"] == "matches" else 1


if __name__ == "__main__":
    raise SystemExit(main())
