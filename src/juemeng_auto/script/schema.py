from __future__ import annotations

from typing import Any


def storyboard_json_schema() -> dict[str, Any]:
    """Responses API Structured Outputs 使用的 Storyboard JSON v1.0 Schema。"""
    shot = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "shot_id": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
            },
            "duration": {"type": "number", "exclusiveMinimum": 0},
            "scene": {"type": "string", "minLength": 1, "maxLength": 1000},
            "characters": {
                "type": "array",
                "maxItems": 20,
                "items": {"type": "string", "minLength": 1, "maxLength": 80},
            },
            "blocking": {"type": "string", "minLength": 1, "maxLength": 1000},
            "action": {"type": "string", "minLength": 1, "maxLength": 1000},
            "expression": {"type": "string", "minLength": 1, "maxLength": 1000},
            "camera": {"type": "string", "minLength": 1, "maxLength": 1000},
            "dialogue": {"type": "string", "maxLength": 1000},
            "prompt": {"type": "string", "minLength": 1, "maxLength": 1000},
        },
        "required": [
            "shot_id", "duration", "scene", "characters", "blocking",
            "action", "expression", "camera", "dialogue", "prompt"
        ],
    }
    segment = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "segment_id": {
                "type": "string",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
            },
            "order": {"type": "integer"},
            "duration": {"type": "number"},
            "summary": {"type": "string"},
            "prompt": {"type": "string"},
            "shots": {"type": "array", "minItems": 1, "items": shot},
        },
        "required": ["segment_id", "order", "duration", "summary", "prompt", "shots"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "schema_version": {"type": "string", "enum": ["1.0"]},
            "episode_id": {"type": "string"},
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "segments": {"type": "array", "items": segment},
        },
        "required": ["schema_version", "episode_id", "title", "summary", "segments"],
    }


def storyboard_content_json_schema() -> dict[str, Any]:
    """模型生成的内容部分；标识、标题和版本由程序负责。"""
    full_schema = storyboard_json_schema()
    properties = full_schema["properties"]
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": properties["summary"],
            "segments": properties["segments"],
        },
        "required": ["summary", "segments"],
    }
