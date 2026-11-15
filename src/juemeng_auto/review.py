from __future__ import annotations

import json
import re
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from .script.models import EpisodeStoryboard


REVIEW_VERSION = "1.0"


class ReviewError(RuntimeError):
    pass


def _canonical_json_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def prompt_sha256(prompt: str) -> str:
    return sha256(prompt.encode("utf-8")).hexdigest()


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ReviewError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReviewError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReviewError(f"{label} must be a JSON object: {path}")
    return payload


def _storyboard_sha256(storyboard_path: Path) -> str:
    return _canonical_json_sha256(
        _load_json_object(storyboard_path, "storyboard.json")
    )


def _validate_run_metadata(metadata: dict[str, Any]) -> None:
    for key in ("episode", "provider", "model", "source_path", "source_sha256"):
        if not isinstance(metadata.get(key), str) or not metadata[key].strip():
            raise ReviewError(f"run_metadata.json is missing {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", metadata["source_sha256"]):
        raise ReviewError("run_metadata.json source_sha256 is invalid")
    if not isinstance(metadata.get("loaded_skills"), list):
        raise ReviewError("run_metadata.json is missing loaded_skills")
    if "asset_context_sha256" not in metadata:
        raise ReviewError("run_metadata.json is missing asset_context_sha256")

    source_path = Path(metadata["source_path"])
    try:
        current_source_sha256 = sha256(source_path.read_bytes()).hexdigest()
    except OSError as exc:
        raise ReviewError(f"Episode source cannot be read: {source_path}") from exc
    if current_source_sha256 != metadata["source_sha256"]:
        raise ReviewError("Episode source changed since storyboard analysis")


def _context_fingerprint(storyboard_path: Path) -> dict[str, str]:
    metadata_path = storyboard_path.resolve().parent / "run_metadata.json"
    metadata = _load_json_object(metadata_path, "run_metadata.json")
    _validate_run_metadata(metadata)
    return {"run_metadata_sha256": _canonical_json_sha256(metadata)}


def _derived_prompts(storyboard: EpisodeStoryboard) -> list[dict[str, str]]:
    return [
        {
            "segment_id": segment.segment_id,
            "prompt_sha256": prompt_sha256(segment.prompt),
        }
        for segment in storyboard.segments
    ]


def build_review_artifact(
    storyboard_path: Path, storyboard: EpisodeStoryboard
) -> dict[str, Any]:
    return {
        "version": REVIEW_VERSION,
        "episode_id": storyboard.episode_id,
        "status": "approved",
        "storyboard_sha256": _storyboard_sha256(storyboard_path),
        "derived_prompts": _derived_prompts(storyboard),
        "reviewed_at": datetime.now().astimezone().isoformat(),
        "context_fingerprint": _context_fingerprint(storyboard_path),
    }


def write_review_artifact(
    storyboard_path: Path, artifact: dict[str, Any]
) -> Path:
    review_path = storyboard_path.resolve().parent / "review.json"
    temporary = review_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporary.replace(review_path)
    return review_path


def review_artifact_sha256(artifact: dict[str, Any]) -> str:
    return _canonical_json_sha256(artifact)


def verify_approved_review(
    storyboard_path: Path, storyboard: EpisodeStoryboard
) -> dict[str, Any]:
    review_path = storyboard_path.resolve().parent / "review.json"
    try:
        review = _load_json_object(review_path, "review.json")
    except ReviewError as exc:
        raise ReviewError(
            f"Review required: approved review.json not found or invalid ({exc})"
        ) from exc

    if review.get("status") != "approved":
        raise ReviewError("Review required: review.json status is not approved")

    try:
        current_storyboard_sha256 = _storyboard_sha256(storyboard_path)
        current_context_fingerprint = _context_fingerprint(storyboard_path)
    except ReviewError as exc:
        raise ReviewError(f"Review is stale / content changed: Context ({exc})") from exc

    changed: list[str] = []
    if (
        review.get("version") != REVIEW_VERSION
        or review.get("episode_id") != storyboard.episode_id
        or review.get("storyboard_sha256") != current_storyboard_sha256
    ):
        changed.append("Storyboard")
    if review.get("derived_prompts") != _derived_prompts(storyboard):
        changed.append("Prompt")
    if review.get("context_fingerprint") != current_context_fingerprint:
        changed.append("Context")
    if changed:
        raise ReviewError(
            "Review is stale / content changed: " + ", ".join(changed)
        )
    return review


def print_review_preview(
    storyboard_path: Path,
    storyboard: EpisodeStoryboard,
    artifact: dict[str, Any],
) -> None:
    print(f"Storyboard: {storyboard_path.resolve()}")
    print(f"Storyboard SHA256: {artifact['storyboard_sha256']}")
    print(
        "Context SHA256: "
        f"{artifact['context_fingerprint']['run_metadata_sha256']}"
    )
    print("\n===== STORYBOARD =====")
    print(storyboard_path.read_text(encoding="utf-8-sig"))
    print("===== BUILDER-DERIVED JUEMENG PROMPTS =====")
    for index, (segment, prompt_record) in enumerate(
        zip(storyboard.segments, artifact["derived_prompts"], strict=True), start=1
    ):
        print(
            f"\n===== {index}/{len(storyboard.segments)} "
            f"segment {segment.order} / {segment.segment_id} ====="
        )
        print(f"Prompt SHA256: {prompt_record['prompt_sha256']}")
        print(segment.prompt)
