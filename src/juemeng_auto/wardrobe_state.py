from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from .project_bible import ProjectBible


WARDROBE_STATES = ("work", "home", "fishing", "unknown")
WARDROBE_SUFFIXES = {
    "work": "上班",
    "home": "居家",
    "fishing": "钓鱼",
}
WARDROBE_BINDINGS_FILENAME = "wardrobe_bindings.json"
WARDROBE_BINDING_KEY = re.compile(r"[\w-]+:(?:work|home|fishing)\Z")


class WardrobeStateError(ValueError):
    pass


def _normalized_text(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    parts: list[str] = []
    separator = False
    for character in normalized:
        if character.isalnum():
            parts.append(character)
            separator = False
        elif parts and not separator:
            parts.append("_")
            separator = True
    return "".join(parts).strip("_")


def wardrobe_character_id(
    character: str, bible: ProjectBible | None = None
) -> str:
    character = character.strip()
    if not character:
        raise WardrobeStateError("wardrobe character 不能为空")
    normalized = _normalized_text(character)
    if bible is not None:
        matches = []
        for record in bible.data["characters"]:
            names = [record["canonical_name"], *record["aliases"]]
            if normalized in {_normalized_text(name) for name in names}:
                matches.append(record["id"])
        if len(matches) == 1:
            return matches[0].removeprefix("char_")
    identity = _slug(character)
    if not identity:
        raise WardrobeStateError("无法生成 wardrobe character_id")
    return identity


def wardrobe_key(
    character: str,
    wardrobe_state: str,
    bible: ProjectBible | None = None,
) -> str:
    if wardrobe_state not in WARDROBE_STATES:
        raise WardrobeStateError(f"不支持的 wardrobe_state：{wardrobe_state}")
    return f"{wardrobe_character_id(character, bible)}:{wardrobe_state}"


def load_wardrobe_bindings(
    path: Path, bible: ProjectBible | None
) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WardrobeStateError(f"无法读取 wardrobe bindings：{path}") from exc
    if not isinstance(data, dict):
        raise WardrobeStateError("wardrobe_bindings.json 必须是 key 到 Asset ID 的对象")

    wardrobe_ids = (
        {record["id"] for record in bible.data["wardrobe"]}
        if bible is not None
        else set()
    )
    bindings: dict[str, str] = {}
    for key, asset_id in data.items():
        if not isinstance(key, str) or not WARDROBE_BINDING_KEY.fullmatch(key):
            raise WardrobeStateError(f"非法 wardrobe binding key：{key}")
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise WardrobeStateError(f"wardrobe binding {key} 必须指向非空 Asset ID")
        if asset_id not in wardrobe_ids:
            raise WardrobeStateError(
                f"wardrobe binding {key} 指向不存在的 wardrobe Asset ID：{asset_id}"
            )
        bindings[key] = asset_id
    return bindings


def expected_wardrobe_asset_name(character: str, wardrobe_state: str) -> str:
    """Return the deterministic production asset name for a known state."""

    character = character.strip()
    if not character:
        raise WardrobeStateError("wardrobe character 不能为空")
    if wardrobe_state not in WARDROBE_STATES:
        raise WardrobeStateError(f"不支持的 wardrobe_state：{wardrobe_state}")
    suffix = WARDROBE_SUFFIXES.get(wardrobe_state)
    return f"{character}{suffix}" if suffix else ""


def wardrobe_requirement_for_matching(
    item: dict[str, Any],
    *,
    bible: ProjectBible | None = None,
    bindings: dict[str, str] | None = None,
) -> dict[str, str]:
    """Convert constrained LLM wardrobe output into an AssetMatcher requirement."""

    character = item["character"].strip()
    wardrobe_state = item["wardrobe_state"]
    evidence = item["evidence"].strip()
    uncertainty_reason = item["uncertainty_reason"].strip()
    key = wardrobe_key(character, wardrobe_state, bible)
    suggested_name = expected_wardrobe_asset_name(character, wardrobe_state)
    bound_asset_id = (bindings or {}).get(key, "") if wardrobe_state != "unknown" else ""
    bound_asset: dict[str, Any] | None = None
    if bound_asset_id:
        if bible is not None:
            bound_asset = next(
                (
                    record
                    for record in bible.data["wardrobe"]
                    if record["id"] == bound_asset_id
                ),
                None,
            )
        if bound_asset is None:
            raise WardrobeStateError(
                f"wardrobe binding {key} 无法解析 Asset ID：{bound_asset_id}"
            )

    if bound_asset is not None:
        display_name = bound_asset["canonical_name"]
        canonical_name_hint = bound_asset["canonical_name"]
        suggested_name = ""
        question = uncertainty_reason
    elif wardrobe_state == "unknown":
        display_name = f"{character}服装状态待确认"
        canonical_name_hint = ""
        question = uncertainty_reason or f"确认 {character} 当前服装属于哪一种固定状态"
    else:
        display_name = suggested_name
        canonical_name_hint = suggested_name
        question = uncertainty_reason

    return {
        "kind": "wardrobe",
        "name": display_name,
        "canonical_name_hint": canonical_name_hint,
        "candidate_asset_id": bound_asset_id,
        "change_note": "",
        "evidence": evidence,
        "human_question": question,
        "wardrobe_key": key,
        "wardrobe_state": wardrobe_state,
        "suggested_asset_name": suggested_name,
    }


def wardrobe_requirements_for_matching(
    items: list[dict[str, Any]],
    *,
    bible: ProjectBible | None = None,
    bindings: dict[str, str] | None = None,
) -> list[dict[str, str]]:
    return [
        wardrobe_requirement_for_matching(
            item,
            bible=bible,
            bindings=bindings,
        )
        for item in items
    ]
