"""CLI for the only official review-reels one-shot Gemini TTS/SRT path."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_engine_v2.current_artifacts import CurrentArtifactsViolation  # noqa: E402
from video_engine_v2.one_shot_tts import (  # noqa: E402
    OneShotTTSViolation,
    calibrate_one_shot_timeline,
    generate_one_shot_tts,
)
from video_engine_v2.reels_qa import validate_review_reels_one_shot_authoring  # noqa: E402


def _read_recipe(path: str, *, code: str) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise OneShotTTSViolation(code) from error
    if not isinstance(value, dict):
        raise OneShotTTSViolation(code)
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate hash-bound Gemini/Sulafat voice and SRT for one-shot HTML")
    parser.add_argument("--package", required=True)
    parser.add_argument("--planning", required=True)
    parser.add_argument("--edit", required=True)
    parser.add_argument("--script", required=True)
    parser.add_argument("--calibrate-from-voice")
    parser.add_argument("--calibrate-from-report")
    parser.add_argument("--alignment")
    parser.add_argument("--lead-in-sec", type=float, default=0.4)
    args = parser.parse_args(argv)
    try:
        authoring = validate_review_reels_one_shot_authoring(
            _read_recipe(args.planning, code="PLANNING_RECIPE_INVALID"),
            _read_recipe(args.edit, code="EDIT_RECIPE_INVALID"),
        )
        if not authoring["ok"]:
            codes = ",".join(
                sorted({str(issue.get("code") or "") for issue in authoring["issues"]})
            )
            raise OneShotTTSViolation(f"AUTHORING_CHECK_FAILED:{codes}")
        calibration_inputs = (
            args.calibrate_from_voice,
            args.calibrate_from_report,
            args.alignment,
        )
        if any(calibration_inputs) and not all(calibration_inputs):
            parser.error(
                "--calibrate-from-voice, --calibrate-from-report, and --alignment must be supplied together"
            )
        if all(calibration_inputs):
            result = calibrate_one_shot_timeline(
                package_dir=args.package,
                planning_path=args.planning,
                edit_path=args.edit,
                script_path=args.script,
                source_voice_path=args.calibrate_from_voice,
                source_report_path=args.calibrate_from_report,
                alignment_path=args.alignment,
                lead_in_sec=args.lead_in_sec,
            )
        else:
            result = generate_one_shot_tts(
                package_dir=args.package,
                planning_path=args.planning,
                edit_path=args.edit,
                script_path=args.script,
            )
    except (OneShotTTSViolation, CurrentArtifactsViolation) as exc:
        print(f"GATE_BLOCKED: {exc}", file=sys.stderr)
        return 2
    for name in ("script", "edit", "srt", "voice", "tts_report"):
        print(f"{name}={result[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
