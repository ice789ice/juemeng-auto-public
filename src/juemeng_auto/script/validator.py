from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import EpisodeStoryboard, StoryboardDataError


MAX_SEGMENT_DURATION_SECONDS = 30.0
MAX_CHARACTERS_PER_SHOT = 20
MAX_CHARACTER_NAME_LENGTH = 80
MAX_SHOT_TEXT_LENGTH = 1_000
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def validate_storyboard(data: Any) -> tuple[EpisodeStoryboard | None, list[ValidationIssue]]:
    try:
        storyboard = EpisodeStoryboard.from_dict(data)
    except StoryboardDataError as exc:
        return None, [ValidationIssue("structure", str(exc))]

    issues: list[ValidationIssue] = []
    segment_ids: set[str] = set()
    shot_ids: set[str] = set()

    for segment_index, segment in enumerate(storyboard.segments):
        segment_path = f"segments[{segment_index}]"
        if segment.segment_id in segment_ids:
            issues.append(ValidationIssue(segment_path, "segment_id 重复"))
        segment_ids.add(segment.segment_id)
        if not ID_PATTERN.fullmatch(segment.segment_id):
            issues.append(
                ValidationIssue(
                    f"{segment_path}.segment_id",
                    "只能包含英文字母、数字、下划线、连字符，且最长64字符",
                )
            )

        if segment.duration > MAX_SEGMENT_DURATION_SECONDS:
            issues.append(
                ValidationIssue(segment_path, "segment 总时长不能超过30秒")
            )

        shot_total = 0.0
        for shot_index, shot in enumerate(segment.shots):
            shot_path = f"{segment_path}.shots[{shot_index}]"
            shot_total += shot.duration
            if shot.shot_id in shot_ids:
                issues.append(ValidationIssue(shot_path, "shot_id 必须全剧唯一"))
            shot_ids.add(shot.shot_id)
            if not ID_PATTERN.fullmatch(shot.shot_id):
                issues.append(
                    ValidationIssue(
                        f"{shot_path}.shot_id",
                        "只能包含英文字母、数字、下划线、连字符，且最长64字符",
                    )
                )
            if len(shot.characters) > MAX_CHARACTERS_PER_SHOT:
                issues.append(
                    ValidationIssue(
                        f"{shot_path}.characters",
                        f"角色数量异常，单镜头不能超过{MAX_CHARACTERS_PER_SHOT}个",
                    )
                )
            for character_index, character in enumerate(shot.characters):
                if len(character) > MAX_CHARACTER_NAME_LENGTH:
                    issues.append(
                        ValidationIssue(
                            f"{shot_path}.characters[{character_index}]",
                            f"角色名称异常，不能超过{MAX_CHARACTER_NAME_LENGTH}字符",
                        )
                    )
            for field_name in (
                "scene",
                "blocking",
                "action",
                "expression",
                "camera",
                "dialogue",
                "prompt",
            ):
                if len(getattr(shot, field_name)) > MAX_SHOT_TEXT_LENGTH:
                    issues.append(
                        ValidationIssue(
                            f"{shot_path}.{field_name}",
                            f"内容异常，不能超过{MAX_SHOT_TEXT_LENGTH}字符",
                        )
                    )

        if abs(segment.duration - shot_total) > 0.001:
            issues.append(
                ValidationIssue(
                    segment_path,
                    f"duration={segment.duration:g}，但 shots 合计为{shot_total:g}秒",
                )
            )

    expected_orders = list(range(1, len(storyboard.segments) + 1))
    actual_orders = [segment.order for segment in storyboard.segments]
    if actual_orders != expected_orders:
        issues.append(
            ValidationIssue("segments", "order 必须按1、2、3连续排列")
        )

    return storyboard, issues


def validate_storyboard_file(path: Path) -> tuple[EpisodeStoryboard | None, list[ValidationIssue]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return None, [ValidationIssue("file", f"文件不存在：{path}")]
    except json.JSONDecodeError as exc:
        return None, [
            ValidationIssue("json", f"第{exc.lineno}行第{exc.colno}列：{exc.msg}")
        ]
    return validate_storyboard(data)
