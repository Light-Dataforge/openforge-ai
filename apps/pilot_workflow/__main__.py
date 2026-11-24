"""Run the complete local synthetic pilot workflow (default: no model)."""

import argparse
import json
import sys

from .runner import run_workflow


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args()
    try:
        summary = run_workflow(
            args.output,
            live=args.live,
            allow_download=args.allow_download,
            device=args.device,
            max_new_tokens=args.max_new_tokens,
        )
    except (OSError, ValueError):
        print(
            "Workflow failed; partial artifacts may remain. Check options/output.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(summary, sort_keys=True, allow_nan=False))
    return 1 if summary["source_counts"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
