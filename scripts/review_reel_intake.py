"""Official CLI for review-reel routing and canonical package intake."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_engine_v2.current_artifacts import CurrentArtifactsViolation  # noqa: E402
from video_engine_v2.review_reel_intake import (  # noqa: E402
    IntakeViolation,
    active_package_status,
    create_canonical_package,
    create_canonical_package_from_material_bank,
    inspect_material_bank_candidate,
    quarantine_active_selection,
    record_photo_review,
    resolve_active_package,
    route_user_command,
    run_one_shot_html,
    shortlist_material_bank_candidates,
    workflow_next,
    write_recipe_scaffold,
    fork_active_recipe_for_voice_reuse,
    check_active_voice_reuse,
)
from video_engine_v2.qa_guidance import explain_error  # noqa: E402


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
    route.add_argument("--output-root", help="Optional output root used only to detect an active review-reel package")
    explain = commands.add_parser("explain-error", help="Explain one known gate code and its safe repair")
    explain.add_argument("--code", required=True)
    status = commands.add_parser("status", help="Show the active canonical identity and next safe action")
    status.add_argument("--output-root", required=True)
    next_step = commands.add_parser(
        "workflow-next",
        help="Return the next legal command or explicit approval wait for the active package",
    )
    next_step.add_argument("--output-root", required=True)
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
    candidate_check = commands.add_parser(
        "candidate-check",
        help="Read-only check for official or legacy use before selecting a candidate",
    )
    candidate_check.add_argument("--output-root", required=True)
    candidate_check.add_argument("--reviews-root", required=True)
    candidate_check.add_argument("--material-bank", required=True, help="private candidate JSONL")
    candidate_check.add_argument("--candidate-id", required=True)
    candidate_shortlist = commands.add_parser(
        "candidate-shortlist",
        help="Read-only ranked audit using product policy and legacy identity evidence",
    )
    candidate_shortlist.add_argument("--output-root", required=True)
    candidate_shortlist.add_argument("--reviews-root", required=True)
    candidate_shortlist.add_argument("--material-bank", required=True, help="private candidate JSONL")
    candidate_shortlist.add_argument("--limit", type=int, default=10)
    quarantine = commands.add_parser(
        "quarantine-active-selection",
        help="Recoverably quarantine one mistaken empty pre-photo active package",
    )
    quarantine.add_argument("--output-root", required=True)
    quarantine.add_argument("--reviews-root", required=True)
    quarantine.add_argument("--expected-content-id", required=True)
    quarantine.add_argument(
        "--reason-code",
        required=True,
        choices=("duplicate_existing_review", "policy_excluded", "wrong_selection"),
    )
    photo_review = commands.add_parser(
        "photo-review",
        help="Bind complete photo decisions and privacy evidence to the active package",
    )
    photo_review.add_argument("--output-root", required=True)
    photo_review.add_argument("--expected-content-id", required=True)
    photo_review.add_argument("--selection", required=True)
    photo_review.add_argument("--privacy-manifest", required=True)
    scaffold = commands.add_parser(
        "recipe-scaffold",
        help="Create a complete, QA-synchronized planning/edit starting point after photo review",
    )
    scaffold.add_argument("--output-root", required=True)
    scaffold.add_argument("--expected-content-id", required=True)
    recipe_fork = commands.add_parser(
        "recipe-fork-reuse-voice",
        help="Create the next immutable-safe planning/edit revision while retaining current voice evidence",
    )
    recipe_fork.add_argument("--output-root", required=True)
    recipe_fork.add_argument("--expected-content-id", required=True)
    recipe_fork.add_argument("--planning", required=True)
    recipe_fork.add_argument("--edit", required=True)
    reuse_check = commands.add_parser(
        "voice-reuse-check",
        help="Read-only proof that a revised edit can retain the current voice/SRT/report",
    )
    reuse_check.add_argument("--output-root", required=True)
    reuse_check.add_argument("--expected-content-id", required=True)
    reuse_check.add_argument("--edit", required=True)
    one_shot = commands.add_parser("one-shot-html", help="Resolve the active package and run official one-shot HTML")
    one_shot.add_argument("--output-root", required=True)
    one_shot.add_argument("--expected-content-id", required=True)
    one_shot.add_argument("--planning", required=True)
    one_shot.add_argument("--edit", required=True)
    one_shot.add_argument("--privacy-manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "route":
            active_review_reel_package = False
            if args.output_root:
                try:
                    resolve_active_package(args.output_root)
                    active_review_reel_package = True
                except IntakeViolation:
                    active_review_reel_package = False
            print(
                json.dumps(
                    route_user_command(
                        args.user_command,
                        active_review_reel_package=active_review_reel_package,
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "explain-error":
            print(json.dumps(explain_error(args.code), ensure_ascii=False))
            return 0
        if args.command == "status":
            print(json.dumps(active_package_status(args.output_root), ensure_ascii=False))
            return 0
        if args.command == "workflow-next":
            print(json.dumps(workflow_next(args.output_root), ensure_ascii=False))
            return 0
        if args.command == "candidate-check":
            print(
                json.dumps(
                    inspect_material_bank_candidate(
                        output_root=args.output_root,
                        reviews_root=args.reviews_root,
                        material_bank_path=args.material_bank,
                        candidate_id=args.candidate_id,
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "candidate-shortlist":
            print(
                json.dumps(
                    shortlist_material_bank_candidates(
                        output_root=args.output_root,
                        reviews_root=args.reviews_root,
                        material_bank_path=args.material_bank,
                        limit=args.limit,
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "quarantine-active-selection":
            print(
                json.dumps(
                    quarantine_active_selection(
                        output_root=args.output_root,
                        reviews_root=args.reviews_root,
                        expected_content_id=args.expected_content_id,
                        reason_code=args.reason_code,
                    ),
                    ensure_ascii=False,
                )
            )
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
                        "content_id": str(package.metadata.get("content_id") or ""),
                        "package": str(package.package_dir),
                        "image_directory": str(package.image_dir),
                        "reused_existing": package.reused_existing,
                        "next_action": "place_photos_then_run_photo_review",
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "photo-review":
            package = record_photo_review(
                output_root=args.output_root,
                expected_content_id=args.expected_content_id,
                selection_path=args.selection,
                privacy_manifest_path=args.privacy_manifest,
            )
            print(
                json.dumps(
                    {
                        "workflow": "review_reel_production",
                        "state": package.metadata["lifecycle_state"],
                        "package": str(package.package_dir),
                        "photo_checked": package.metadata["approvals"]["photo_checked"],
                        "html_scope_authorized": False,
                        "mp4_scope_authorized": False,
                    },
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "recipe-scaffold":
            print(
                json.dumps(
                    write_recipe_scaffold(
                        output_root=args.output_root,
                        expected_content_id=args.expected_content_id,
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "recipe-fork-reuse-voice":
            print(
                json.dumps(
                    fork_active_recipe_for_voice_reuse(
                        output_root=args.output_root,
                        expected_content_id=args.expected_content_id,
                        planning_path=args.planning,
                        edit_path=args.edit,
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        if args.command == "voice-reuse-check":
            print(
                json.dumps(
                    check_active_voice_reuse(
                        output_root=args.output_root,
                        expected_content_id=args.expected_content_id,
                        edit_path=args.edit,
                    ),
                    ensure_ascii=False,
                )
            )
            return 0
        return run_one_shot_html(
            output_root=args.output_root,
            expected_content_id=args.expected_content_id,
            planning_path=args.planning,
            edit_path=args.edit,
            privacy_manifest_path=args.privacy_manifest,
        )
    except (IntakeViolation, CurrentArtifactsViolation) as error:
        print(f"INTAKE_BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
