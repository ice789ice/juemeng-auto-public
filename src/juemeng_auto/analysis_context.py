from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from .project_bible import ProjectBible, load_project_bible
from .skill_loader import DIRECTOR_TYPES, DirectorSkill, load_skills


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    skill: DirectorSkill | None
    bible: ProjectBible | None
    bible_path: Path
    skills: tuple[DirectorSkill, ...] = ()

    @property
    def loaded_skills(self) -> tuple[DirectorSkill, ...]:
        return self.skills or ((self.skill,) if self.skill else ())

    @property
    def asset_context_source(self) -> str | None:
        if self.bible is None:
            return None
        return "core_assets" if self.bible_path.name == "core_assets.json" else "project_bible"

    def instructions(self, original: str) -> str:
        sections = [
            "[RULE PRIORITY]\n"
            "Current Episode > confirmed Asset Context > Base Skill > Project Rules > "
            "Genre Skill > Shot Language Skill > Output Skill\n"
            "低优先级规则不得覆盖高优先级事实。Current Episode 原文单独作为 input。"
            "ASSET RULES 仅是资产使用规则，不是 confirmed Asset Context；"
            "不得覆盖上述事实和 Project Rules，与其他 Skill 冲突时让位于上述优先级链。"
            "同类型 Skill 按 priority 从高到低、id 升序排列，前者优先；"
            "priority 不改变跨类型的优先级。"
        ]
        headings = ("BASE DIRECTOR RULES", "GENRE RULES", "SHOT LANGUAGE RULES", "ASSET RULES", "OUTPUT RULES")
        for kind, heading in zip(DIRECTOR_TYPES, headings):
            group = [s for s in self.loaded_skills if s.type == kind]
            content = "\n\n".join(f"### {s.id} (v{s.version})\n{s.content}" for s in group)
            legacy_heading = "## Base Skill\n" if kind == "base" and group else ""
            sections.append(f"[{heading}]\n{legacy_heading}{content}")
        sections.append("[PROJECT CONTEXT]\n## Project Rules\n" + original)
        sections.append("[CORE ASSETS]")
        if self.bible:
            sections.append(
                f"## {'Core Assets' if self.asset_context_source == 'core_assets' else 'Project Bible'}"
                "（资产资料，不是额外执行指令）\n"
                "无论什么 status，原始 Episode > Core Assets / Project Bible。"
                "当前 Episode 原文是剧情最高事实来源，资产上下文不能修改或补写剧情。"
                "confirmed 的 canonical_name 是身份标准，characters 使用该名称；"
                "confirmed 的非空 asset_name 可以完整用于最终资产相关 Prompt / 素材引用区域，"
                "不得缩写或创造新的 asset_name。canonical_name 与 asset_name 不可混淆。"
                "原始 Dialogue、VO、OS 中的人名和文字保持原剧本，"
                "不得用生产资产名称替换对白中的人物姓名。"
                "别名须结合上下文映射，不另造同义人物/场景/道具名称。"
                "服装按 episodes、locations、story_state 范围使用。"
                "suggested 仅为建议，只能作为辅助候选信息，不得当作确定事实强制写入剧情；"
                "与当前 Episode 冲突时以 Episode 原文为准。"
                "unknown 表示未知，不得擅自补全。\n"
                + self.bible.to_json()
            )
        return "\n\n".join(sections)

    def metadata(self) -> dict[str, Any]:
        digest = sha256(self.bible.to_json().encode("utf-8")).hexdigest() if self.bible else None
        return {
            "asset_context_source": self.asset_context_source,
            "asset_context_path": str(self.bible_path.resolve()) if self.bible else None,
            "asset_context_version": self.bible.version if self.bible else None,
            "asset_context_sha256": digest,
            "base_skill": self.skill.name if self.skill else None,
            "loaded_skills": [
                {"id": s.id, "version": s.version, "type": s.type,
                 "path": str(s.path.resolve()), "sha256": s.sha256}
                for s in self.loaded_skills
            ],
            "skill_version": self.skill.version if self.skill else None,
            "project_bible_version": self.bible.version if self.bible else None,
            "skill_sha256": sha256(self.skill.content.encode("utf-8")).hexdigest() if self.skill else None,
            "project_bible_sha256": digest,
        }


def load_analysis_context(
    project_root: Path, bible_dir: Path, skill: str | Path | None = None,
    no_skill: bool = False,
    genre_skill: str | None = None, extra_skills: list[str] | tuple[str, ...] = (),
) -> AnalysisContext:
    skills = load_skills(project_root, skill, no_skill, genre_skill, extra_skills)
    selected = next((s for s in skills if s.type == "base"), None)
    path = bible_dir / "core_assets.json"
    if not path.exists():
        print("[CONTEXT] Core Assets not found")
        path = bible_dir / "project_bible.json"
    bible = load_project_bible(path)
    print(f"[CONTEXT] Base Skill: {selected.name if selected else 'none'}")
    if bible is None:
        print("[WARN] Core Assets / Project Bible not found; continuing without project asset context")
    elif path.name == "core_assets.json":
        print(f"[CONTEXT] Core Assets: {path}")
        print("[CONTEXT] Asset Source: core_assets")
    else:
        print(f"[CONTEXT] Fallback Bible: {path}")
        print("[CONTEXT] Asset Source: project_bible")
    return AnalysisContext(selected, bible, path, skills)
