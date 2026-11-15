from __future__ import annotations

import re
import json
from hashlib import sha256
from dataclasses import dataclass, replace
from pathlib import Path

from .config import ConfigurationError

DEFAULT_SKILL = "skills/base/director_base_v0.5.md"
DIRECTOR_TYPES = ("base", "genre", "shot_language", "asset", "output")
SKILL_TYPES = (*DIRECTOR_TYPES, "operator", "editing", "utility")


@dataclass(frozen=True, slots=True)
class DirectorSkill:
    name: str
    version: str | None
    content: str
    path: Path
    id: str = ""
    type: str = "base"
    priority: int = 0
    sha256: str = ""


def load_skill(project_root: Path, skill: str | Path | None = None) -> DirectorSkill:
    """Resolve a project-relative Markdown path or an unambiguous skill stem."""
    value = Path(skill or DEFAULT_SKILL)
    path = value if value.is_absolute() else project_root / value
    if not path.is_file() and len(value.parts) == 1:
        name = value.name if value.suffix.lower() == ".md" else f"{value.name}.md"
        matches = sorted((project_root / "skills").rglob(name))
        if len(matches) > 1:
            raise ConfigurationError(f"Skill 名称不唯一，请指定路径：{value}")
        if matches:
            path = matches[0]
    if not path.is_file():
        raise ConfigurationError(f"找不到 Skill 文件：{path}")
    if path.suffix.lower() != ".md":
        raise ConfigurationError(f"Skill 必须是 Markdown 文件：{path}")
    try:
        raw = path.read_bytes()
        content = raw.decode("utf-8-sig").strip()
    except (OSError, UnicodeError) as exc:
        raise ConfigurationError(f"无法读取 Skill 文件：{path}") from exc
    if not content:
        raise ConfigurationError(f"Skill 文件为空：{path}")
    version = re.search(r"(?:版本\s*[:：]\s*|_v)(\d+(?:\.\d+)+)", content + "\n" + path.stem)
    return DirectorSkill(path.stem, version.group(1) if version else None, content, path,
                         id=path.stem, sha256=sha256(raw).hexdigest())


def load_registry(project_root: Path) -> dict[str, dict]:
    """Read metadata only; imported packages are never scanned or modified."""
    path = project_root / "skills" / "registry.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ConfigurationError(f"无法读取 Skill Registry：{path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("skills"), list):
        raise ConfigurationError("Skill Registry 必须包含 skills 数组")
    registry = {}
    for entry in data["skills"]:
        if not isinstance(entry, dict) or any(
            not isinstance(entry.get(key), str) or not entry[key].strip()
            for key in ("id", "name", "version", "path", "type")
        ):
            raise ConfigurationError("Skill Registry 缺少有效的 id/name/version/path/type")
        if (entry["type"] not in SKILL_TYPES
                or type(entry.get("enabled")) is not bool
                or type(entry.get("priority")) is not int
                or not isinstance(entry.get("applies_to"), list)
                or any(not isinstance(item, str) or not item.strip() for item in entry["applies_to"])):
            raise ConfigurationError(f"Skill Registry 字段无效：{entry['id']}")
        value = Path(entry["path"])
        resolved = (project_root / value).resolve()
        if value.is_absolute() or not resolved.is_relative_to((project_root / "skills").resolve()):
            raise ConfigurationError(f"Registry Skill path 必须位于 skills 目录内：{entry['id']}")
        if entry["id"] in registry:
            raise ConfigurationError(f"重复 Skill id：{entry['id']}")
        registry[entry["id"]] = entry
    return registry


def load_skills(
    project_root: Path, skill: str | Path | None = None, no_skill: bool = False,
    genre_skill: str | None = None, extra_skills: list[str] | tuple[str, ...] = (),
) -> tuple[DirectorSkill, ...]:
    """Select base defaults and explicit IDs, ordered by type, priority DESC, ID."""
    registry = load_registry(project_root)
    selected = []
    ids = []
    if not no_skill:
        if skill is not None:
            if str(skill) in registry:
                if registry[str(skill)]["type"] != "base":
                    raise ConfigurationError("--skill 只能选择 base 类型")
                ids.append(str(skill))
            else:
                # Keep the original custom Markdown interface for existing A/B runs.
                custom = load_skill(project_root, skill)
                matches = [e for e in registry.values()
                           if (project_root / e["path"]).resolve() == custom.path.resolve()]
                if matches:
                    if any(e["type"] != "base" for e in matches):
                        raise ConfigurationError("--skill 只能选择 base 类型")
                    ids.extend(e["id"] for e in matches)
                else:
                    selected.append(custom)
        elif (project_root / "skills" / "registry.json").exists():
            bases = [
                entry for entry in registry.values()
                if entry["type"] == "base"
                and entry["enabled"]
                and "gpt_director" in entry["applies_to"]
            ]
            if bases:
                current = min(bases, key=lambda entry: (-entry["priority"], entry["id"]))
                ids.append(current["id"])
        else:
            selected.append(load_skill(project_root))
    if genre_skill:
        if genre_skill not in registry or registry[genre_skill]["type"] != "genre":
            raise ConfigurationError(f"未知或非 genre Skill：{genre_skill}")
        ids.append(genre_skill)
    ids.extend(extra_skills)
    for skill_id in dict.fromkeys(ids):
        if skill_id not in registry:
            raise ConfigurationError(f"未知 Skill id：{skill_id}")
        entry = registry[skill_id]
        if (not entry["enabled"] or entry["type"] not in DIRECTOR_TYPES
                or "gpt_director" not in entry["applies_to"]
                or (no_skill and entry["type"] == "base")):
            print(f"[SKILL] Skipped: {skill_id} (disabled, excluded type or scope)")
            continue
        loaded = load_skill(project_root, entry["path"])
        selected.append(replace(loaded, id=skill_id, name=entry["name"],
                                version=entry["version"], type=entry["type"],
                                priority=entry["priority"]))
    return tuple(sorted(selected, key=lambda s: (DIRECTOR_TYPES.index(s.type), -s.priority, s.id)))
