from __future__ import annotations

import copy
import re
from typing import Any

from .script.schema import storyboard_content_json_schema
from .wardrobe_state import WARDROBE_STATES


BRIEF_VERSION = "0.1"
ASSET_KINDS = ("character", "location", "wardrobe", "prop")
LLM_ASSET_KINDS = ("character", "location", "prop")
ASSET_CLASSIFICATIONS = (
    "possible_reuse",
    "possible_new_or_changed",
    "uncertain",
    "confirmed_existing",
)
ASSET_REQUIREMENT_ID_PATTERN = re.compile(r"^(EP[0-9]{2,})-ASSET-[0-9]{3,}$")
WARDROBE_REQUIREMENT_ID_PATTERN = re.compile(
    r"^(EP[0-9]{2,})-WARDROBE-[0-9]{3,}$"
)


class ProductionBriefError(ValueError):
    pass


def production_brief_analysis_schema() -> dict[str, Any]:
    """Structured Output for one Episode; classification remains local Python work."""

    string = {"type": "string"}
    requirement = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "requirement_id": {
                "type": "string",
                "pattern": r"^EP[0-9]{2,}-ASSET-[0-9]{3,}$",
            },
            "kind": {"type": "string", "enum": list(LLM_ASSET_KINDS)},
            "name": string,
            "canonical_name_hint": string,
            "candidate_asset_id": string,
            "change_note": string,
            "evidence": string,
            "human_question": string,
        },
        "required": [
            "requirement_id",
            "kind",
            "name",
            "canonical_name_hint",
            "candidate_asset_id",
            "change_note",
            "evidence",
            "human_question",
        ],
    }
    wardrobe_requirement = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "requirement_id": {
                "type": "string",
                "pattern": r"^EP[0-9]{2,}-WARDROBE-[0-9]{3,}$",
            },
            "character": {"type": "string", "minLength": 1},
            "wardrobe_state": {
                "type": "string",
                "enum": list(WARDROBE_STATES),
            },
            "evidence": string,
            "uncertainty_reason": string,
        },
        "required": [
            "requirement_id",
            "character",
            "wardrobe_state",
            "evidence",
            "uncertainty_reason",
        ],
    }
    storyboard_content = storyboard_content_json_schema()
    segments = copy.deepcopy(storyboard_content["properties"]["segments"])
    segment_item = segments["items"]
    segment_item["properties"].update(
        {
            "required_asset_requirement_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": r"^EP[0-9]{2,}-ASSET-[0-9]{3,}$",
                },
            },
            "required_wardrobe_requirement_ids": {
                "type": "array",
                "items": {
                    "type": "string",
                    "pattern": r"^EP[0-9]{2,}-WARDROBE-[0-9]{3,}$",
                },
            },
        }
    )
    segment_item["required"].extend(
        [
            "required_asset_requirement_ids",
            "required_wardrobe_requirement_ids",
        ]
    )
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string", "minLength": 1},
            "asset_requirements": {
                "type": "array",
                "items": requirement,
            },
            "wardrobe_requirements": {
                "type": "array",
                "items": wardrobe_requirement,
            },
            "segments": segments,
        },
        "required": [
            "summary",
            "asset_requirements",
            "wardrobe_requirements",
            "segments",
        ],
    }


def _requirement_episode(
    requirement_id: str, pattern: re.Pattern[str]
) -> str | None:
    match = pattern.fullmatch(requirement_id)
    return match.group(1) if match else None


def _validate_reference_list(
    value: Any,
    *,
    path: str,
    expected_episode_id: str | None,
    own_ids: set[str],
    other_ids: set[str],
    pattern: re.Pattern[str],
) -> list[str]:
    if not isinstance(value, list):
        return [f"{path} 必须是数组"]
    issues: list[str] = []
    seen: set[str] = set()
    for index, requirement_id in enumerate(value):
        item_path = f"{path}[{index}]"
        if not isinstance(requirement_id, str):
            issues.append(f"{item_path} 必须是字符串")
            continue
        if requirement_id in seen:
            issues.append(f"{path} 不允许重复 ID：{requirement_id}")
            continue
        seen.add(requirement_id)
        if requirement_id in other_ids:
            issues.append(f"{item_path} requirement type 错误：{requirement_id}")
            continue
        reference_episode = _requirement_episode(requirement_id, pattern)
        if reference_episode is None:
            issues.append(f"{item_path} 格式错误：{requirement_id}")
            continue
        if expected_episode_id and reference_episode != expected_episode_id:
            issues.append(f"{item_path} 不得引用其他 Episode：{requirement_id}")
            continue
        if requirement_id not in own_ids:
            issues.append(f"{item_path} 引用不存在的 ID：{requirement_id}")
    return issues


def validate_analysis_payload(
    data: Any, expected_episode_id: str | None = None
) -> list[str]:
    if not isinstance(data, dict):
        return ["analysis 必须是对象"]
    issues: list[str] = []
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        issues.append("summary 必须是非空字符串")
    requirements = data.get("asset_requirements")
    if not isinstance(requirements, list):
        issues.append("asset_requirements 必须是数组")
    else:
        required = (
            "requirement_id",
            "kind",
            "name",
            "canonical_name_hint",
            "candidate_asset_id",
            "change_note",
            "evidence",
            "human_question",
        )
        for index, item in enumerate(requirements):
            if not isinstance(item, dict):
                issues.append(f"asset_requirements[{index}] 必须是对象")
                continue
            requirement_id = item.get("requirement_id")
            if not isinstance(requirement_id, str) or not requirement_id.strip():
                issues.append(f"asset_requirements[{index}].requirement_id 必须是非空字符串")
            elif not ASSET_REQUIREMENT_ID_PATTERN.fullmatch(requirement_id):
                issues.append(f"asset_requirements[{index}].requirement_id 格式错误")
            elif expected_episode_id and _requirement_episode(
                requirement_id, ASSET_REQUIREMENT_ID_PATTERN
            ) != expected_episode_id:
                issues.append(
                    f"asset_requirements[{index}].requirement_id 不得属于其他 Episode"
                )
            if item.get("kind") not in LLM_ASSET_KINDS:
                issues.append(f"asset_requirements[{index}].kind 不受支持")
            for field in required[2:]:
                if not isinstance(item.get(field), str):
                    issues.append(
                        f"asset_requirements[{index}].{field} 必须是字符串"
                    )
    wardrobe = data.get("wardrobe_requirements")
    if not isinstance(wardrobe, list):
        issues.append("wardrobe_requirements 必须是数组")
    else:
        for index, item in enumerate(wardrobe):
            if not isinstance(item, dict):
                issues.append(f"wardrobe_requirements[{index}] 必须是对象")
                continue
            requirement_id = item.get("requirement_id")
            if not isinstance(requirement_id, str) or not requirement_id.strip():
                issues.append(
                    f"wardrobe_requirements[{index}].requirement_id 必须是非空字符串"
                )
            elif not WARDROBE_REQUIREMENT_ID_PATTERN.fullmatch(requirement_id):
                issues.append(f"wardrobe_requirements[{index}].requirement_id 格式错误")
            elif expected_episode_id and _requirement_episode(
                requirement_id, WARDROBE_REQUIREMENT_ID_PATTERN
            ) != expected_episode_id:
                issues.append(
                    f"wardrobe_requirements[{index}].requirement_id 不得属于其他 Episode"
                )
            character = item.get("character")
            if not isinstance(character, str) or not character.strip():
                issues.append(
                    f"wardrobe_requirements[{index}].character 必须是非空字符串"
                )
            if item.get("wardrobe_state") not in WARDROBE_STATES:
                issues.append(
                    f"wardrobe_requirements[{index}].wardrobe_state 不受支持"
                )
            for field in ("evidence", "uncertainty_reason"):
                if not isinstance(item.get(field), str):
                    issues.append(
                        f"wardrobe_requirements[{index}].{field} 必须是字符串"
                    )
    segments = data.get("segments")
    if not isinstance(segments, list) or not segments:
        issues.append("segments 必须是非空数组")
        return issues

    requirement_records = requirements if isinstance(requirements, list) else []
    wardrobe_records = wardrobe if isinstance(wardrobe, list) else []
    asset_ids = {
        item["requirement_id"]
        for item in requirement_records
        if isinstance(item, dict) and isinstance(item.get("requirement_id"), str)
    }
    wardrobe_ids = {
        item["requirement_id"]
        for item in wardrobe_records
        if isinstance(item, dict) and isinstance(item.get("requirement_id"), str)
    }
    if isinstance(requirements, list) and len(asset_ids) != len(requirement_records):
        issues.append("asset_requirements.requirement_id 不允许重复")
    if isinstance(wardrobe, list) and len(wardrobe_ids) != len(wardrobe_records):
        issues.append("wardrobe_requirements.requirement_id 不允许重复")

    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            continue
        segment_id = segment.get("segment_id")
        segment_episode = None
        if isinstance(segment_id, str):
            match = re.match(r"^(EP[0-9]{2,})-SEG", segment_id)
            segment_episode = match.group(1) if match else None
        episode_id = expected_episode_id or segment_episode
        issues.extend(
            _validate_reference_list(
                segment.get("required_asset_requirement_ids"),
                path=f"segments[{index}].required_asset_requirement_ids",
                expected_episode_id=episode_id,
                own_ids=asset_ids,
                other_ids=wardrobe_ids,
                pattern=ASSET_REQUIREMENT_ID_PATTERN,
            )
        )
        issues.extend(
            _validate_reference_list(
                segment.get("required_wardrobe_requirement_ids"),
                path=f"segments[{index}].required_wardrobe_requirement_ids",
                expected_episode_id=episode_id,
                own_ids=wardrobe_ids,
                other_ids=asset_ids,
                pattern=WARDROBE_REQUIREMENT_ID_PATTERN,
            )
        )
    return issues


def validate_production_brief(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["Production Brief 必须是对象"]
    issues: list[str] = []
    required_scalars = {
        "version": str,
        "episode_id": str,
        "source_episode": int,
        "summary": str,
        "status": str,
    }
    for field, expected in required_scalars.items():
        value = data.get(field)
        if isinstance(value, bool) or not isinstance(value, expected):
            issues.append(f"{field} 类型错误")
        elif isinstance(value, str) and not value.strip():
            issues.append(f"{field} 不能为空")
    if data.get("version") != BRIEF_VERSION:
        issues.append(f"version 必须是 {BRIEF_VERSION}")

    for field in (
        "people",
        "scenes",
        "wardrobe_or_look_changes",
        "key_props",
        "assets",
        "human_confirmation",
        "segments",
    ):
        if not isinstance(data.get(field), list):
            issues.append(f"{field} 必须是数组")

    source_episode = data.get("source_episode")
    expected_episode_id = (
        f"EP{source_episode:02d}"
        if isinstance(source_episode, int) and not isinstance(source_episode, bool)
        else None
    )
    asset_ids: set[str] = set()
    asset_records = data.get("assets", [])
    if not isinstance(asset_records, list):
        asset_records = []
    for index, asset in enumerate(asset_records):
        if not isinstance(asset, dict):
            issues.append(f"assets[{index}] 必须是对象")
            continue
        if asset.get("kind") not in ASSET_KINDS:
            issues.append(f"assets[{index}].kind 不受支持")
        if asset.get("classification") not in ASSET_CLASSIFICATIONS:
            issues.append(f"assets[{index}].classification 不受支持")
        for field in (
            "requirement_id",
            "source_name",
            "canonical_name",
            "matched_asset_id",
            "asset_name",
            "change_note",
            "evidence",
            "human_question",
            "match_reason",
        ):
            if not isinstance(asset.get(field), str):
                issues.append(f"assets[{index}].{field} 必须是字符串")
        if not isinstance(asset.get("possible_matches"), list):
            issues.append(f"assets[{index}].possible_matches 必须是数组")
        requirement_id = asset.get("requirement_id")
        if isinstance(requirement_id, str):
            if requirement_id in asset_ids:
                issues.append(f"assets requirement_id 重复：{requirement_id}")
            asset_ids.add(requirement_id)
            if not ASSET_REQUIREMENT_ID_PATTERN.fullmatch(requirement_id):
                issues.append(f"assets[{index}].requirement_id 格式错误")
            elif expected_episode_id and _requirement_episode(
                requirement_id, ASSET_REQUIREMENT_ID_PATTERN
            ) != expected_episode_id:
                issues.append(f"assets[{index}].requirement_id 不得属于其他 Episode")

    wardrobe_records = data.get("wardrobe_requirements", [])
    wardrobe_ids: set[str] = set()
    if not isinstance(wardrobe_records, list):
        issues.append("wardrobe_requirements 必须是数组")
        wardrobe_records = []
    for index, asset in enumerate(wardrobe_records):
        if not isinstance(asset, dict):
            issues.append(f"wardrobe_requirements[{index}] 必须是对象")
            continue
        if asset.get("kind") != "wardrobe":
            issues.append(f"wardrobe_requirements[{index}].kind 必须是 wardrobe")
        if asset.get("classification") not in ASSET_CLASSIFICATIONS:
            issues.append(
                f"wardrobe_requirements[{index}].classification 不受支持"
            )
        for field in (
            "requirement_id",
            "source_name",
            "canonical_name",
            "matched_asset_id",
            "asset_name",
            "change_note",
            "evidence",
            "human_question",
            "match_reason",
        ):
            if not isinstance(asset.get(field), str):
                issues.append(f"wardrobe_requirements[{index}].{field} 必须是字符串")
        if not isinstance(asset.get("possible_matches"), list):
            issues.append(
                f"wardrobe_requirements[{index}].possible_matches 必须是数组"
            )
        requirement_id = asset.get("requirement_id")
        if isinstance(requirement_id, str):
            if requirement_id in wardrobe_ids:
                issues.append(
                    f"wardrobe_requirements requirement_id 重复：{requirement_id}"
                )
            wardrobe_ids.add(requirement_id)
            if not WARDROBE_REQUIREMENT_ID_PATTERN.fullmatch(requirement_id):
                issues.append(
                    f"wardrobe_requirements[{index}].requirement_id 格式错误"
                )
            elif expected_episode_id and _requirement_episode(
                requirement_id, WARDROBE_REQUIREMENT_ID_PATTERN
            ) != expected_episode_id:
                issues.append(
                    f"wardrobe_requirements[{index}].requirement_id 不得属于其他 Episode"
                )

    for index, segment in enumerate(data.get("segments", [])):
        if not isinstance(segment, dict):
            issues.append(f"segments[{index}] 必须是对象")
            continue
        for field in ("segment_id", "summary", "ready_prompt"):
            if not isinstance(segment.get(field), str) or not segment[field].strip():
                issues.append(f"segments[{index}].{field} 必须是非空字符串")
        duration = segment.get("duration")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)):
            issues.append(f"segments[{index}].duration 必须是秒数")
        elif duration <= 0 or duration > 30:
            issues.append(f"segments[{index}].duration 必须大于0且不超过30秒")
        if segment.get("order") != index + 1:
            issues.append("segments.order 必须从1连续递增")
        has_asset_dependencies = "required_asset_requirement_ids" in segment
        has_wardrobe_dependencies = (
            "required_wardrobe_requirement_ids" in segment
        )
        if has_asset_dependencies != has_wardrobe_dependencies:
            issues.append(
                f"segments[{index}] 必须同时提供两类 requirement ID 引用"
            )
        elif has_asset_dependencies:
            issues.extend(
                _validate_reference_list(
                    segment.get("required_asset_requirement_ids"),
                    path=f"segments[{index}].required_asset_requirement_ids",
                    expected_episode_id=expected_episode_id,
                    own_ids=asset_ids,
                    other_ids=wardrobe_ids,
                    pattern=ASSET_REQUIREMENT_ID_PATTERN,
                )
            )
            issues.extend(
                _validate_reference_list(
                    segment.get("required_wardrobe_requirement_ids"),
                    path=f"segments[{index}].required_wardrobe_requirement_ids",
                    expected_episode_id=expected_episode_id,
                    own_ids=wardrobe_ids,
                    other_ids=asset_ids,
                    pattern=WARDROBE_REQUIREMENT_ID_PATTERN,
                )
            )
    return issues


def render_production_brief_markdown(brief: dict[str, Any]) -> str:
    episode = int(brief["source_episode"])
    lines = [f"# EP{episode:02d} Production Brief", "", "## 剧情摘要", "", brief["summary"], ""]

    def names_section(title: str, values: list[str]) -> None:
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {value}" for value in values] or ["- 无明确项目"])
        lines.append("")

    names_section("本集涉及人物", brief["people"])
    names_section("本集涉及场景", brief["scenes"])
    names_section("本集可能涉及的服装或造型变化", brief["wardrobe_or_look_changes"])
    names_section("本集关键道具", brief["key_props"])

    lines.extend(["## 资产提示", ""])
    headings = (
        ("confirmed_existing", "已确认已有"),
        ("possible_reuse", "可能复用"),
        ("possible_new_or_changed", "可能新增或变化"),
        ("uncertain", "需要人工确认"),
    )
    for classification, heading in headings:
        lines.extend([f"### {heading}", ""])
        matches = [
            asset
            for asset in [
                *brief["assets"],
                *brief.get("wardrobe_requirements", []),
            ]
            if asset["classification"] == classification
        ]
        if not matches:
            lines.append("- 暂无")
        for asset in matches:
            name = asset["canonical_name"] or asset["source_name"]
            detail = asset["change_note"] or asset["match_reason"]
            if classification == "confirmed_existing" and asset["asset_name"]:
                detail = f"使用已有资产 {asset['asset_name']}"
            lines.append(f"- {name}" + (f"：{detail}" if detail else ""))
        lines.append("")

    lines.extend(["## 人工确认清单", ""])
    lines.extend(
        [f"- [ ] {question}" for question in brief["human_confirmation"]]
        or ["- [ ] 本集资产提示已人工复核"]
    )
    lines.append("")

    for segment in brief["segments"]:
        lines.extend(
            [
                f"## Segment {int(segment['order']):02d}",
                "",
                f"预计时长：{segment['duration']:g}s",
                "",
                segment["summary"],
                "",
                "可直接复制到剧梦：",
                "",
                "```text",
                segment["ready_prompt"],
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def render_batch_summary_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        f"# {manifest['batch_id']} Batch Production Summary",
        "",
        f"处理范围：EP{manifest['start']:02d} 至 EP{manifest['end']:02d}",
        "",
        "## Episode 状态",
        "",
    ]
    for episode in manifest["episodes"]:
        number = int(episode["source_episode"])
        if episode["status"] == "ready":
            lines.append(
                f"- EP{number:02d}：已生成 "
                f"[Production Brief](episode_{number:02d}/production_brief.md)"
            )
        else:
            lines.append(f"- EP{number:02d}：失败 - {episode['error']}")

    lines.extend(["", "## 跨集稳定资产匹配", ""])
    stable = manifest.get("stable_asset_matches", [])
    if not stable:
        lines.append("- 暂无已确认的跨集稳定资产匹配")
    else:
        for item in stable:
            episodes = "、".join(f"EP{number:02d}" for number in item["episodes"])
            lines.append(f"- {item['canonical_name']}：{episodes}")
    lines.extend(["", "## 批次临时资产候选", ""])
    temporary = manifest.get("temporary_asset_candidates", [])
    if not temporary:
        lines.append("- 暂无未匹配的临时资产候选")
    else:
        for item in temporary:
            episodes = "、".join(f"EP{number:02d}" for number in item["episodes"])
            lines.append(f"- {item['canonical_name']}（{item['kind']}）：{episodes}")
    lines.extend(
        [
            "",
            "## 使用说明",
            "",
            "逐集阅读 Production Brief，确认资产提示后再复制 Segment Prompt。",
            "本批次没有自动审批、创建或修改任何资产。",
            "",
        ]
    )
    return "\n".join(lines)
