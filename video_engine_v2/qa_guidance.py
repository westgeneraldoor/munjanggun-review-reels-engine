from __future__ import annotations

from typing import Any


ERROR_GUIDANCE: dict[str, dict[str, str]] = {
    "CANDIDATE_LEGACY_PACKAGE_PRESENT": {
        "authority": "docs/review_reel_production_routing_v1.md",
        "how_to_fix": "Do not allocate this candidate as a new numeric package. Preserve the legacy package, select another eligible candidate, or request an explicit legacy-resolution decision.",
    },
    "ACTIVE_PACKAGE_CONTENT_ID_MISMATCH": {
        "authority": "docs/review_reel_production_routing_v1.md",
        "how_to_fix": "Run workflow-next, confirm the active content_id, and repeat the command with that exact --expected-content-id. Do not edit the pointer by hand.",
    },
    "PHOTO_PRIVACY_CATEGORY_INVALID": {
        "authority": "docs/reels_privacy_asset_qa_rules_v1.md",
        "how_to_fix": "Use only the closed privacy vocabulary. Bare feet, footwear, and apartment building numbers are not privacy blocking categories.",
    },
    "MASKING_FIRST_NOT_APPLIED": {
        "authority": "docs/reels_privacy_asset_qa_rules_v1.md",
        "how_to_fix": "Sanitize the localized identifier first. Exclude for privacy only when a declared masking_infeasible_reason proves the essential subject cannot be preserved.",
    },
    "REVIEW_CAPTURE_COMPOSITION_CHANGED": {
        "authority": "docs/reels_privacy_asset_qa_rules_v1.md",
        "how_to_fix": "Keep the user-supplied review capture dimensions and composition. Mask only the remaining order information inside declared localized regions.",
    },
    "RECIPE_SCAFFOLD_INCOMPLETE": {
        "authority": "docs/review_recipe_contract_v2.md",
        "how_to_fix": "Replace every scaffold pending_fields placeholder with review-grounded content, bind final voice timing and hashes, then set scaffold.status to complete and pending_fields to an empty list.",
    },
    "RECIPE_SCAFFOLD_PLACEHOLDER_REMAINS": {
        "authority": "docs/review_recipe_contract_v2.md",
        "how_to_fix": "Replace every TODO value and placeholder voice hash with review-grounded content and current generated-artifact hashes before marking the scaffold complete.",
    },
    "HOOK_SHOT_CAPTION_ALIGNMENT_INVALID": {
        "authority": "docs/review_reels_visual_edit_standard_v1.md",
        "how_to_fix": "Make the first three result-before-result shot boundaries exactly match three complete caption_chunks and spoken claims.",
    },
    "CAPTION_ACCENT_VOICE_SYNC_INVALID": {
        "authority": "docs/review_reels_visual_edit_standard_v1.md",
        "how_to_fix": "Move caption_accent.start_sec to the estimated spoken onset of the emphasized word inside its caption chunk.",
    },
    "TTS_TEXT_HASH_MISMATCH": {
        "authority": "docs/review_reels_one_shot_contract_v2.md",
        "how_to_fix": "Regenerate official Sulafat TTS and SRT from the finalized script; do not reuse a voice file whose narration hash changed.",
    },
    "REVIEW_EMPHASIS_NOT_IMMEDIATE": {
        "authority": "docs/review_reels_visual_edit_standard_v1.md",
        "how_to_fix": "Start the review underline as the review scene enters and finish the draw within 0.20 seconds.",
    },
    "NARRATION_RHYTHM_MONOTONE": {
        "authority": "docs/review_reels_content_standard_v1.md",
        "how_to_fix": "Rewrite the body so at least one sentence lands far shorter than the rest, the way the golden sample cuts to a three-word beat between long ones. Do not chase ending variety; the same ending repeated is fine when the lengths move.",
    },
    "REVIEW_EMPHASIS_SEGMENT_TEXT_MISMATCH": {
        "authority": "docs/review_reels_visual_edit_standard_v1.md",
        "how_to_fix": "Open the review capture, see how many rendered lines the quote actually wraps onto, and give one segment per line. Each segment needs line_text holding that line's fragment, and joining them must reproduce the quote exactly.",
    },
    "REVIEW_EMPHASIS_SEGMENT_ORDER_INVALID": {
        "authority": "docs/review_reels_visual_edit_standard_v1.md",
        "how_to_fix": "Order underline segments top to bottom as the quote reads, each at its own line height. Repeated or rising top_pct values mean the coordinates were guessed.",
    },
    "FINAL_RESULT_DWELL_INVALID": {
        "authority": "docs/review_reels_visual_edit_standard_v1.md",
        "how_to_fix": "End on the full installed-result asset and keep the final shot visible for the required dwell time.",
    },
}


def explain_error(code: str) -> dict[str, Any]:
    normalized = str(code or "").strip().upper()
    guidance = ERROR_GUIDANCE.get(normalized)
    if guidance is None:
        return {
            "code": normalized,
            "known": False,
            "next_action": "inspect_the_emitting_gate_and_current_authority_document",
        }
    return {"code": normalized, "known": True, **guidance}


def guidance_for_issue(code: str) -> dict[str, str] | None:
    guidance = ERROR_GUIDANCE.get(str(code or "").strip().upper())
    return dict(guidance) if guidance is not None else None
