"""Print or save a deletion-free local artifact cleanup candidate report."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_engine_v2.cleanup_dry_run import scan_cleanup_candidates, validate_report_path  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only local cleanup candidate report; no deletion mode exists.")
    parser.add_argument("--root", default=str(ROOT), help="Repository/local artifact root to scan")
    parser.add_argument("--report", help="Optional JSON destination outside reviews/, output/, and scratch/")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = scan_cleanup_candidates(args.root)
        rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
        if args.report:
            path = validate_report_path(args.root, args.report)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as output:
                output.write(rendered)
            print(path)
        else:
            print(rendered, end="")
        return 0
    except (OSError, ValueError) as error:
        print(f"DRY_RUN_BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
