"""CLI for the only official review-reels one-shot Gemini TTS/SRT path."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from video_engine_v2.one_shot_tts import OneShotTTSViolation, generate_one_shot_tts  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate hash-bound Gemini/Sulafat voice and SRT for one-shot HTML")
    parser.add_argument("--package", required=True)
    parser.add_argument("--planning", required=True)
    parser.add_argument("--script", required=True)
    args = parser.parse_args(argv)
    try:
        result = generate_one_shot_tts(
            package_dir=args.package,
            planning_path=args.planning,
            script_path=args.script,
        )
    except OneShotTTSViolation as exc:
        print(f"GATE_BLOCKED: {exc}", file=sys.stderr)
        return 2
    for name in ("script", "srt", "voice", "tts_report"):
        print(f"{name}={result[name]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
