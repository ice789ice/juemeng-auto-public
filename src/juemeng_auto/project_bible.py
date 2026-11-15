from __future__ import annotations

import json
import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import ConfigurationError

ASSET_GROUPS = ("characters", "locations", "props", "wardrobe", "relationships")
STATUSES = ("confirmed", "suggested", "unknown")


def _object(properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "object", "properties": properties,
            "required": list(properties), "additionalProperties": False}


def project_bible_schema() -> dict[str, Any]:
    string = {"type": "string"}
    strings = {"type": "array", "items": string}
    properties: dict[str, Any] = {
        "version": {"type": "string", "enum": ["0.1"]},
        "project": _object({"title": string, "genre": string}),
    }
    for group in ASSET_GROUPS:
        fields = {
            "id": string, "canonical_name": string, "aliases": strings,
            "asset_name": string, "status": {"type": "string", "enum": list(STATUSES)},
            "notes": string,
            "evidence": {"type": "array", "items": _object({
                "episode": {"type": "integer"}, "quote": string,
            })},
        }
        if group == "characters":
            fields["role"] = string
        elif group == "wardrobe":
            fields.update(character=string, episodes={"type": "array", "items": {"type": "integer"}},
                          locations=strings, story_state=string)
        elif group == "relationships":
            fields.update(source=string, target=string, description=string)
        properties[group] = {"type": "array", "items": _object(fields)}
    return _object(properties)


def _validate(value: Any, schema: dict[str, Any], path: str) -> None:
    kind = schema["type"]
    valid = {"object": isinstance(value, dict), "array": isinstance(value, list),
             "string": isinstance(value, str),
             "integer": isinstance(value, int) and not isinstance(value, bool)}[kind]
    if not valid:
        raise ConfigurationError(f"Project Bible {path} 必须为 {kind}")
    if "enum" in schema and value not in schema["enum"]:
        raise ConfigurationError(f"Project Bible {path} 值不受支持")
    if kind == "object":
        for key, child in schema["properties"].items():
            if key not in value:
                raise ConfigurationError(f"Project Bible 缺少 {path}.{key}")
            _validate(value[key], child, f"{path}.{key}")
    elif kind == "array":
        for index, item in enumerate(value):
            _validate(item, schema["items"], f"{path}[{index}]")


@dataclass(frozen=True, slots=True)
class ProjectBible:
    data: dict[str, Any]

    @classmethod
    def from_dict(cls, data: Any) -> "ProjectBible":
        data = copy.deepcopy(data)
        # Evidence and review notes are optional in hand-written Bible files.
        if isinstance(data, dict):
            for group in ASSET_GROUPS:
                if isinstance(data.get(group), list):
                    for item in data[group]:
                        if isinstance(item, dict):
                            item.setdefault("notes", "")
                            item.setdefault("evidence", [])
        _validate(data, project_bible_schema(), "root")
        ids: set[str] = set()
        for group in ASSET_GROUPS:
            for item in data[group]:
                if not item["id"].strip() or item["id"] in ids:
                    raise ConfigurationError("Project Bible 资产 id 必须非空且全局唯一")
                if not item["canonical_name"].strip():
                    raise ConfigurationError("Project Bible canonical_name 不能为空")
                ids.add(item["id"])
        return cls(data)

    @property
    def version(self) -> str:
        return self.data["version"]

    def to_json(self) -> str:
        return json.dumps(self.data, ensure_ascii=False, indent=2)


def load_project_bible(path: Path) -> ProjectBible | None:
    if not path.exists():
        return None
    try:
        return ProjectBible.from_dict(json.loads(path.read_text(encoding="utf-8-sig")))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"无法读取 Project Bible JSON：{path}") from exc


def empty_bible(title: str) -> dict[str, Any]:
    return {"version": "0.1", "project": {"title": title, "genre": ""},
            **{group: [] for group in ASSET_GROUPS}}
