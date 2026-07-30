"""Official CLI for review-reel routing and canonical package intake."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_engine_v2.review_reel_intake import (  # noqa: E402
    IntakeViolation,
    create_canonical_package,
    create_canonical_package_from_material_bank,
    route_user_command,
    run_one_shot_html,
)


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Official review-reel production intake")
    commands = parser.add_subparsers(dest="command", required=True)
    route = commands.add_parser("route", help="Classify a short user request without creating files")
    route.add_argument("--user-command", required=True)
    create = commands.add_parser("create", help="Create or reuse one canonical pre-photo package")
    create.add_argument("--output-root", required=True)
    create.add_argument("--inventory", required=True, help="private review-reel inventory JSON")
    create.add_argument("--record-key", required=True, help="exact selected inventory record_key")
    material = commands.add_parser(
        "create-from-material-bank",
        help="Register one selected candidate_top60 JSONL record and create its canonical package",
    )
    material.add_argument("--output-root", required=True)
    material.add_argument("--reviews-root", required=True)
    material.add_argument("--material-bank", required=True, help="private candidate JSONL")
    material.add_argument("--candidate-id", required=True)
    material.add_argument("--content-slug", required=True)
    one_shot = commands.add_parser("one-shot-html", help="Resolve the active package and run official one-shot HTML")
    one_shot.add_argument("--output-root", required=True)
    one_shot.add_argument("--planning", required=True)
    one_shot.add_argument("--edit", required=True)
    one_shot.add_argument("--privacy-manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "route":
            print(json.dumps(route_user_command(args.user_command), ensure_ascii=False))
            return 0
        if args.command in {"create", "create-from-material-bank"}:
            if args.command == "create":
                package = create_canonical_package(
                    output_root=args.output_root,
                    inventory_path=args.inventory,
                    record_key=args.record_key,
                )
            else:
                package = create_canonical_package_from_material_bank(
                    output_root=args.output_root,
                    reviews_root=args.reviews_root,
                    material_bank_path=args.material_bank,
                    candidate_id=args.candidate_id,
                    content_slug=args.content_slug,
                )
            print(
                json.dumps(
                    {
                        "workflow": "review_reel_production",
                        "state": "photo_intake_pending",
                        "package": str(package.package_dir),
                        "image_directory": str(package.image_dir),
                        "reused_existing": package.reused_existing,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        return run_one_shot_html(
            output_root=args.output_root,
            planning_path=args.planning,
            edit_path=args.edit,
            privacy_manifest_path=args.privacy_manifest,
        )
    except IntakeViolation as error:
        print(f"INTAKE_BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
