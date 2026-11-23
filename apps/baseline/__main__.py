"""Run a small frozen local VLM pilot without paid services."""

import argparse
import json
import sys

from .runner import run_pilot


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-download", action="store_true")
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args()
    try:
        report = run_pilot(
            args.manifest,
            args.output,
            dry_run=args.dry_run,
            allow_download=args.allow_download,
            device=args.device,
            max_new_tokens=args.max_new_tokens,
        )
    except (OSError, ValueError) as exc:
        print(f"pilot failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2, allow_nan=False))
    return 1 if report["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
