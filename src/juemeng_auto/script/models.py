from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class StoryboardDataError(ValueError):
    """JSON 无法转换成分镜数据模型。"""


def _object(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StoryboardDataError(f"{path} 必须是对象")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise StoryboardDataError(f"{path} 必须是数组")
    return value


def _text(data: dict[str, Any], key: str, path: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise StoryboardDataError(f"{path}.{key} 必须是非空字符串")
    return value.strip()


def _seconds(data: dict[str, Any], key: str, path: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise StoryboardDataError(f"{path}.{key} 必须是秒数")
    if value <= 0:
        raise StoryboardDataError(f"{path}.{key} 必须大于0")
    return float(value)


@dataclass(frozen=True, slots=True)
class Shot:
    shot_id: str
    duration: float
    scene: str
    characters: tuple[str, ...]
    blocking: str
    action: str
    expression: str
    camera: str
    dialogue: str
    prompt: str

    @classmethod
    def from_dict(cls, value: Any, path: str = "shot") -> "Shot":
        data = _object(value, path)
        raw_characters = _array(data.get("characters"), f"{path}.characters")
        characters: list[str] = []
        for index, character in enumerate(raw_characters):
            if not isinstance(character, str) or not character.strip():
                raise StoryboardDataError(
                    f"{path}.characters[{index}] 必须是非空字符串"
                )
            characters.append(character.strip())

        dialogue = data.get("dialogue")
        if not isinstance(dialogue, str):
            raise StoryboardDataError(f"{path}.dialogue 必须是字符串；无对白时用空字符串")

        return cls(
            shot_id=_text(data, "shot_id", path),
            duration=_seconds(data, "duration", path),
            scene=_text(data, "scene", path),
            characters=tuple(characters),
            blocking=_text(data, "blocking", path),
            action=_text(data, "action", path),
            expression=_text(data, "expression", path),
            camera=_text(data, "camera", path),
            dialogue=dialogue.strip(),
            prompt=_text(data, "prompt", path),
        )


@dataclass(frozen=True, slots=True)
class Segment:
    segment_id: str
    order: int
    duration: float
    summary: str
    prompt: str
    shots: tuple[Shot, ...]

    @classmethod
    def from_dict(cls, value: Any, path: str = "segment") -> "Segment":
        data = _object(value, path)
        order = data.get("order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise StoryboardDataError(f"{path}.order 必须是从1开始的整数")
        raw_shots = _array(data.get("shots"), f"{path}.shots")
        if not raw_shots:
            raise StoryboardDataError(f"{path}.shots 不能为空")
        return cls(
            segment_id=_text(data, "segment_id", path),
            order=order,
            duration=_seconds(data, "duration", path),
            summary=_text(data, "summary", path),
            prompt=_text(data, "prompt", path),
            shots=tuple(
                Shot.from_dict(shot, f"{path}.shots[{index}]")
                for index, shot in enumerate(raw_shots)
            ),
        )


@dataclass(frozen=True, slots=True)
class EpisodeStoryboard:
    schema_version: str
    episode_id: str
    title: str
    summary: str
    segments: tuple[Segment, ...]

    @classmethod
    def from_dict(cls, value: Any) -> "EpisodeStoryboard":
        data = _object(value, "root")
        raw_segments = _array(data.get("segments"), "root.segments")
        if not raw_segments:
            raise StoryboardDataError("root.segments 不能为空")
        return cls(
            schema_version=_text(data, "schema_version", "root"),
            episode_id=_text(data, "episode_id", "root"),
            title=_text(data, "title", "root"),
            summary=_text(data, "summary", "root"),
            segments=tuple(
                Segment.from_dict(segment, f"root.segments[{index}]")
                for index, segment in enumerate(raw_segments)
            ),
        )
