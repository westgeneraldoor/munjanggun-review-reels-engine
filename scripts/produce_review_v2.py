"""The only official v2 production entry point: preflight -> html -> durable render job."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import secrets
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
from video_engine_v2.render_job import (  # noqa: E402
    RenderJobError,
    create_job_record,
    job_record_path,
    read_job,
    refresh_progress,
    sha256_file,
    update_job,
    utc_now,
)
from video_engine_v2.manual_review import (  # noqa: E402
    ManualReviewViolation,
    record_html_review,
    record_render_review,
    record_voice_review,
)


def configure_utf8_output() -> None:
    """Keep Korean paths printable when a Windows runner defaults to cp1252."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def run_utf8_capture(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run a Python child with a UTF-8 stdout contract on every Windows locale."""
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
    )


def spawn_background_process(command: list[str], *, cwd: Path) -> int:
    """Start a child independent of this foreground orchestration process."""
    environment = os.environ.copy()
    environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    options: dict[str, object] = {
        "cwd": cwd,
        "env": environment,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": True,
    }
    if os.name == "nt":
        options["creationflags"] = (
            getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
    else:
        options["start_new_session"] = True
    return subprocess.Popen(command, **options).pid


def _new_job_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{timestamp}-{secrets.token_hex(4)}"


def _expected_frames(sync_manifest_path: str | Path) -> int:
    try:
        payload = json.loads(Path(sync_manifest_path).read_text(encoding="utf-8"))
        audio = payload.get("audio", {})
        duration = audio.get("final_voice_duration_sec", payload.get("final_voice_duration_sec"))
        value = float(duration)
    except (OSError, ValueError, TypeError, json.JSONDecodeError, AttributeError) as error:
        raise RenderJobError("SYNC_DURATION_INVALID") from error
    if not math.isfinite(value) or value <= 0:
        raise RenderJobError("SYNC_DURATION_INVALID")
    return math.ceil(value * int(FINAL_RENDER_PRESET["fps"]))


def _render_bindings(receipt: dict, receipt_path: Path) -> dict:
    renderer = (ROOT / "render_html_preview_v2.js").resolve()
    keys = (
        "package_path",
        "html_path",
        "html_sha256",
        "html_artifact_evidence_path",
        "html_artifact_evidence_sha256",
        "html_approval_path",
        "html_approval_sha256",
        "sync_manifest_path",
        "sync_manifest_sha256",
        "privacy_manifest_path",
        "privacy_manifest_sha256",
        "output_path",
        "preset",
        "render_dependencies",
    )
    bindings = {key: receipt[key] for key in keys if key in receipt}
    bindings.update(
        {
            "receipt_path": str(receipt_path.resolve()),
            "receipt_sha256": sha256_file(receipt_path),
            "renderer_script_path": str(renderer),
            "renderer_script_sha256": sha256_file(renderer),
        }
    )
    return bindings


def process_is_running(pid: int) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel32.GetExitCodeProcess.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _queued_job_is_stale(job: dict, *, grace_seconds: float = 10.0) -> bool:
    try:
        created_at = datetime.fromisoformat(job["created_at"])
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - created_at.astimezone(timezone.utc)).total_seconds() >= grace_seconds
    except (KeyError, TypeError, ValueError):
        return True


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
    preflight.add_argument("--one-shot-html", action="store_true", help="Require the HTML-only one-shot recipe contract")
    html = commands.add_parser("html", help="Build an approved HTML preview through the hard gate")
    _common_arguments(html, include_recipes=True)
    html.add_argument("--engine-font", help="repository-contained font dependency injection")
    html.add_argument("--one-shot-html", action="store_true", help="Require the HTML-only one-shot recipe contract")
    render = commands.add_parser("render", help="Render an already approved HTML preview at the final preset")
    _common_arguments(render, include_recipes=False)
    render.add_argument("--html", required=True)
    render.add_argument("--out", required=True)
    render.add_argument("--engine-font", help="repository-contained font dependency injection")
    render_start = commands.add_parser("render-start", help="Start a durable background render job and return immediately")
    _common_arguments(render_start, include_recipes=False)
    render_start.add_argument("--html", required=True)
    render_start.add_argument("--out", required=True)
    render_start.add_argument("--engine-font", help="repository-contained font dependency injection")
    render_status = commands.add_parser("render-status", help="Read durable render progress without waiting for completion")
    render_status.add_argument("--package", required=True)
    render_status.add_argument("--job-id", required=True)
    for command_name, help_text in (
        ("voice-review-record", "Record hash-bound manual voice audition evidence"),
        ("html-review-record", "Record hash-bound manual HTML frame review evidence"),
        ("render-review-record", "Record hash-bound manual final-render review evidence"),
    ):
        review = commands.add_parser(command_name, help=help_text)
        review.add_argument("--package", required=True)
        review.add_argument("--reviewer", required=True)
        review.add_argument("--evidence-reference", required=True)
        review.add_argument("--check", action="append", default=[])
        if command_name == "voice-review-record":
            review.add_argument("--voice", required=True)
            review.add_argument("--srt", required=True)
            review.add_argument("--tts-report", required=True)
        elif command_name == "html-review-record":
            review.add_argument("--html", required=True)
        else:
            review.add_argument("--mp4", required=True)
            review.add_argument("--post-qa-report", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    configure_utf8_output()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "voice-review-record":
            path = record_voice_review(
                package_dir=args.package,
                voice_path=args.voice,
                srt_path=args.srt,
                tts_report_path=args.tts_report,
                reviewer=args.reviewer,
                evidence_reference=args.evidence_reference,
                checks=args.check,
            )
            print(path)
            return 0
        if args.command == "html-review-record":
            path = record_html_review(
                package_dir=args.package,
                html_path=args.html,
                reviewer=args.reviewer,
                evidence_reference=args.evidence_reference,
                checks=args.check,
            )
            print(path)
            return 0
        if args.command == "render-review-record":
            path = record_render_review(
                package_dir=args.package,
                mp4_path=args.mp4,
                post_qa_report_path=args.post_qa_report,
                reviewer=args.reviewer,
                evidence_reference=args.evidence_reference,
                checks=args.check,
            )
            print(path)
            return 0
        if args.command == "preflight":
            create_sync_manifest(
                package_dir=args.package,
                planning_path=args.planning,
                edit_path=args.edit,
                privacy_manifest_path=args.privacy_manifest,
                sync_manifest_path=args.sync_manifest,
                allow_one_shot_html_contract=args.one_shot_html,
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
                allow_one_shot_html_contract=args.one_shot_html,
            )
            receipt_path = write_gate_receipt(args.package, receipt)
            command = [sys.executable, str(ROOT / "build_html_preview_v2.py"), "--recipe", args.edit, "--gate-receipt", str(receipt_path)]
            if args.engine_font:
                command.extend(["--engine-font", args.engine_font])
            result = run_utf8_capture(command, cwd=ROOT)
            if result.stdout:
                print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            if result.returncode != 0:
                return result.returncode
            output_lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
            if not output_lines:
                print("GATE_BLOCKED: HTML_OUTPUT_PATH_MISSING", file=sys.stderr)
                return 2
            html_path = Path(output_lines[-1]).resolve()
            qa_command = [
                "node",
                str(ROOT / "scripts" / "html-preview-qa.mjs"),
                "--html",
                str(html_path),
                "--edit",
                str(Path(args.edit).resolve()),
            ]
            return subprocess.run(qa_command, cwd=ROOT).returncode
        if args.command == "render-status":
            package = Path(args.package).resolve()
            job_path = job_record_path(package, args.job_id)
            job = read_job(job_path)
            if job["state"] == "queued" and job.get("worker_pid") is None and _queued_job_is_stale(job):
                progress = refresh_progress(job_path)
                update_job(
                    job_path,
                    state="failed",
                    completed_at=utc_now(),
                    rendered_frames=progress["rendered_frames"],
                    failure={"code": "WORKER_DID_NOT_START", "message": "worker did not record startup within 10 seconds"},
                    exit_code=2,
                )
            elif job["state"] == "running" and isinstance(job.get("worker_pid"), int) and not process_is_running(job["worker_pid"]):
                progress = refresh_progress(job_path)
                update_job(
                    job_path,
                    state="failed",
                    completed_at=utc_now(),
                    rendered_frames=progress["rendered_frames"],
                    failure={"code": "WORKER_EXITED_WITHOUT_STATUS", "message": "worker process ended before recording a terminal state"},
                    exit_code=2,
                )
            print(json.dumps(refresh_progress(job_path), ensure_ascii=False, indent=2))
            return 0
        receipt = validate_render_gate(
            package_dir=args.package,
            html_path=args.html,
            output_path=args.out,
            sync_manifest_path=args.sync_manifest,
            privacy_manifest_path=args.privacy_manifest,
            preset=FINAL_RENDER_PRESET,
            engine_font_path=args.engine_font,
        )
        if args.command == "render-start":
            output = Path(args.out).resolve()
            frame_dir = output.parent / f"{output.stem}_frames"
            if frame_dir.exists():
                raise RenderJobError("RETRY_REQUIRES_NEW_OUTPUT")
        receipt_path = write_gate_receipt(args.package, receipt)
        if args.command == "render-start":
            job_id = _new_job_id()
            job_path = create_job_record(
                package_dir=args.package,
                job_id=job_id,
                bindings=_render_bindings(receipt, receipt_path),
                receipt_path=receipt_path,
                output_path=args.out,
                expected_frames=_expected_frames(args.sync_manifest),
            )
            try:
                worker_pid = spawn_background_process(
                    [sys.executable, str(ROOT / "scripts" / "render_review_v2_job.py"), "--job", str(job_path)],
                    cwd=ROOT,
                )
            except OSError as error:
                update_job(
                    job_path,
                    state="failed",
                    completed_at=utc_now(),
                    failure={"code": "WORKER_START_FAILED", "message": f"{type(error).__name__}: {error}"},
                    exit_code=2,
                )
                print(json.dumps(refresh_progress(job_path), ensure_ascii=False, indent=2), file=sys.stderr)
                return 2
            print(
                json.dumps(
                    {
                        "job_id": job_id,
                        "state": "queued",
                        "worker_pid": worker_pid,
                        "status_path": str(job_path),
                        "status_command": f'python scripts/produce_review_v2.py render-status --package "{Path(args.package).resolve()}" --job-id "{job_id}"',
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0
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
    except (GateViolation, RenderJobError, ManualReviewViolation) as error:
        print(f"GATE_BLOCKED: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
