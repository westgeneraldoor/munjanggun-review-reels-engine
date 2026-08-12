"""Detached worker for one evidence-bound review-reel render job."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_engine_v2.production_gate import FINAL_RENDER_PRESET  # noqa: E402
from video_engine_v2.render_job import (  # noqa: E402
    RenderJobError,
    read_job,
    refresh_progress,
    sha256_file,
    update_job,
    utc_now,
)


def _validate_bound_inputs(job: dict) -> None:
    bindings = job["bindings"]
    pairs = (
        ("receipt_path", "receipt_sha256"),
        ("html_path", "html_sha256"),
        ("sync_manifest_path", "sync_manifest_sha256"),
        ("privacy_manifest_path", "privacy_manifest_sha256"),
        ("renderer_script_path", "renderer_script_sha256"),
    )
    for path_key, hash_key in pairs:
        path_value = bindings.get(path_key)
        expected_hash = bindings.get(hash_key)
        if not isinstance(path_value, str) or not isinstance(expected_hash, str):
            raise RenderJobError("BOUND_INPUT_INVALID")
        path = Path(path_value)
        if not path.is_file() or sha256_file(path) != expected_hash:
            raise RenderJobError("BOUND_INPUT_CHANGED")


def build_render_command(job: dict) -> list[str]:
    bindings = job["bindings"]
    if bindings.get("preset") != FINAL_RENDER_PRESET:
        raise RenderJobError("FINAL_PRESET_INVALID")
    renderer = Path(bindings["renderer_script_path"]).resolve()
    if renderer != (ROOT / "render_html_preview_v2.js").resolve():
        raise RenderJobError("RENDERER_SCRIPT_INVALID")
    command = [
        "node",
        str(renderer),
        "--html",
        bindings["html_path"],
        "--out",
        bindings["output_path"],
        "--gate-receipt",
        bindings["receipt_path"],
    ]
    for key, value in FINAL_RENDER_PRESET.items():
        if key in {"video_codec", "pixel_format"}:
            continue
        command.extend(["--" + key.replace("_", "-"), str(value)])
    return command


def _mark_failed(job_path: Path, *, code: str, message: str, exit_code: int) -> None:
    try:
        progress = refresh_progress(job_path)
        update_job(
            job_path,
            state="failed",
            completed_at=utc_now(),
            rendered_frames=progress["rendered_frames"],
            output_evidence=None,
            failure={"code": code, "message": message},
            exit_code=exit_code,
        )
    except RenderJobError:
        # A corrupt/tampered record is intentionally not overwritten as if it were trusted evidence.
        pass


def run_job(
    job_path: str | Path,
    *,
    command_builder: Callable[[dict], list[str]] = build_render_command,
) -> int:
    path = Path(job_path).resolve()
    try:
        job = read_job(path)
        update_job(path, state="running", worker_pid=os.getpid(), started_at=utc_now())
        _validate_bound_inputs(job)
        command = command_builder(job)
        log_path = Path(job["log_path"])
        log_path.parent.mkdir(parents=True, exist_ok=True)
        environment = os.environ.copy()
        environment.update({"PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                command,
                cwd=ROOT,
                env=environment,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
            update_job(path, renderer_pid=process.pid)
            exit_code = process.wait()

        progress = refresh_progress(path)
        if exit_code != 0:
            _mark_failed(path, code="RENDERER_EXIT_NONZERO", message=f"renderer exited with {exit_code}", exit_code=exit_code)
            return exit_code
        output = Path(job["bindings"]["output_path"])
        if not output.is_file() or output.stat().st_size <= 0:
            _mark_failed(path, code="OUTPUT_MISSING_AFTER_RENDER", message="renderer exited successfully without a final MP4", exit_code=2)
            return 2
        if progress["rendered_frames"] != job["expected_frames"]:
            _mark_failed(
                path,
                code="FRAME_COUNT_MISMATCH",
                message=f"expected {job['expected_frames']} frames, found {progress['rendered_frames']}",
                exit_code=2,
            )
            return 2
        update_job(
            path,
            state="succeeded",
            completed_at=utc_now(),
            rendered_frames=progress["rendered_frames"],
            output_evidence={
                "path": str(output.resolve()),
                "bytes": output.stat().st_size,
                "sha256": sha256_file(output),
            },
            failure=None,
            exit_code=0,
        )
        return 0
    except RenderJobError as error:
        _mark_failed(path, code=str(error), message=str(error), exit_code=2)
        return 2
    except Exception as error:  # pragma: no cover - last-resort evidence boundary
        _mark_failed(path, code="WORKER_EXCEPTION", message=f"{type(error).__name__}: {error}", exit_code=2)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Internal fixed-command worker for an official render job")
    parser.add_argument("--job", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run_job(args.job)


if __name__ == "__main__":
    raise SystemExit(main())
