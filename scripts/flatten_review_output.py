from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from video_engine_v2.output_layout import apply_flatten_plan, create_flatten_plan


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan or apply a recoverable flattening of numeric review packages."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    dry_run = subparsers.add_parser("dry-run")
    dry_run.add_argument("--output-root", required=True)
    dry_run.add_argument("--report", required=True)

    apply = subparsers.add_parser("apply")
    apply.add_argument("--output-root", required=True)
    apply.add_argument("--report", required=True)
    apply.add_argument("--report-sha256", required=True)
    apply.add_argument("--confirm", required=True)

    args = parser.parse_args()
    if args.action == "dry-run":
        result = create_flatten_plan(
            output_root=args.output_root,
            report_path=args.report,
        )
    else:
        result = apply_flatten_plan(
            output_root=args.output_root,
            report_path=args.report,
            report_sha256=args.report_sha256,
            confirm=args.confirm,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
