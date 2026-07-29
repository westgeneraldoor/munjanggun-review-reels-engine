"""The only official v2 production entry point: preflight -> html -> render."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_engine_v2.production_gate import (  # noqa: E402
    FINAL_RENDER_PRESET,
    GateViolation,
    create_sync_manifest,
    validate_html_gate,
    validate_render_gate,
    write_gate_receipt,
)


def configure_utf8_output() -> None:
    """Keep Korean paths printable when a Windows runner defaults to cp1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def _common_arguments(parser: argparse.ArgumentParser, *, include_recipes: bool) -> None:
    parser.add_argument("--package", required=True)
    parser.add_argument("--privacy-manifest", required=True)
    parser.add_argument("--sync-manifest", required=True)
    if include_recipes:
        parser.add_argument("--planning", required=True)
        parser.add_argument("--edit", required=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Official Munjanggun v2 production orchestrator")
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight", help="Create a verified sync manifest without HTML/MP4 output")
    _common_arguments(preflight, include_recipes=True)
    html = commands.add_parser("html", help="Build an approved HTML preview through the hard gate")
    _common_arguments(html, include_recipes=True)
    html.add_argument("--engine-font", help="repository-contained font dependency injection")
    render = commands.add_parser("render", help="Render an already approved HTML preview at the final preset")
    _common_arguments(render, include_recipes=False)
    render.add_argument("--html", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--engine-font", help="repository-contained font dependency injection")
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "preflight":
            create_sync_manifest(
                package_dir=args.package,
                planning_path=args.planning,
                edit_path=args.edit,
                privacy_manifest_path=args.privacy_manifest,
                sync_manifest_path=args.sync_manifest,
            )
            print(Path(args.sync_manifest).resolve())
            return 0
        if args.command == "html":
            receipt = validate_html_gate(
                package_dir=args.package,
                planning_path=args.planning,
                edit_path=args.edit,
                privacy_manifest_path=args.privacy_manifest,
                sync_manifest_path=args.sync_manifest,
            )
            receipt_path = write_gate_receipt(args.package, receipt)
            command = [sys.executable, str(ROOT / "build_html_preview_v2.py"), "--recipe", args.edit, "--gate-receipt", str(receipt_path)]
            if args.engine_font:
                command.extend(["--engine-font", args.engine_font])
            result = subprocess.run(command, cwd=ROOT)
            return result.returncode
        receipt = validate_render_gate(
            package_dir=args.package,
            html_path=args.html,
            output_path=args.out,
            sync_manifest_path=args.sync_manifest,
            privacy_manifest_path=args.privacy_manifest,
            preset=FINAL_RENDER_PRESET,
            engine_font_path=args.engine_font,
        )
        receipt_path = write_gate_receipt(args.package, receipt)
        command = [
            "node",
            str(ROOT / "render_html_preview_v2.js"),
            "--html",
            args.html,
            "--out",
            args.out,
            "--gate-receipt",
            str(receipt_path),
        ]
        for key, value in FINAL_RENDER_PRESET.items():
            if key in {"video_codec", "pixel_format"}:
                continue
            command.extend(["--" + key.replace("_", "-"), str(value)])
        return subprocess.run(command, cwd=ROOT).returncode
    except GateViolation as error:
        print(f"GATE_BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
