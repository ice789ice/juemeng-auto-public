from __future__ import annotations

import re
from typing import Any

from juemeng_auto.runtime_budget import RuntimeBudget


SHOT_DURATION_SECONDS = 3
SHOTS_PER_SEGMENT = 10


class MockStoryboardAnalyzer:
    """确定性本地分析器，仅用于打通流程，不代表最终 AI 分镜质量。"""

    _cameras = (
        "环境全景转人物中景，缓慢推进。",
        "人物面部近景，浅景深捕捉细微反应。",
        "侧面跟拍中景，保持动作方向连续。",
        "过肩镜头切反应特写，维持180度轴线。",
    )

    def analyze(
        self,
        episode_id: str,
        script: str,
        *,
        runtime_budget: RuntimeBudget | None = None,
    ) -> dict[str, Any]:
        lines = self._english_story_lines(script)
        if not lines:
            raise ValueError("Mock 分析器没有在剧本中找到英文原文")

        shots = [
            self._make_shot(episode_id, index, line)
            for index, line in enumerate(lines, start=1)
        ]
        segments: list[dict[str, Any]] = []
        for segment_index, start in enumerate(
            range(0, len(shots), SHOTS_PER_SEGMENT), start=1
        ):
            segment_shots = shots[start : start + SHOTS_PER_SEGMENT]
            segment_id = f"{episode_id.upper()}-SEG{segment_index:02d}"
            for shot_index, shot in enumerate(segment_shots, start=1):
                shot["shot_id"] = f"{segment_id}-S{shot_index:02d}"
            duration = sum(shot["duration"] for shot in segment_shots)
            segments.append(
                {
                    "segment_id": segment_id,
                    "order": segment_index,
                    "duration": duration,
                    "summary": f"Mock拆分第{segment_index}段，共{len(segment_shots)}个镜头。",
                    "prompt": self._build_segment_prompt(segment_shots, duration),
                    "shots": segment_shots,
                }
            )

        return {
            "schema_version": "1.0",
            "episode_id": episode_id,
            "title": f"{episode_id} 本地Mock分镜",
            "summary": "由本地Mock分析器生成，用于验证数据链路；正式制作前需人工审核。",
            "segments": segments,
        }

    @staticmethod
    def _english_story_lines(script: str) -> list[str]:
        return [
            line.strip()
            for line in script.splitlines()
            if line.strip() and re.search(r"[A-Za-z]", line)
        ]

    def _make_shot(self, episode_id: str, index: int, text: str) -> dict[str, Any]:
        characters = self._characters(text)
        dialogue = text if '"' in text else ""
        action = text if not dialogue else f"对应人物说出对白：{text}"
        return {
            "shot_id": f"{episode_id.upper()}-TEMP-S{index:02d}",
            "duration": SHOT_DURATION_SECONDS,
            "scene": "寒冷的酒店房间与门外走廊，夜晚",
            "characters": characters,
            "blocking": self._blocking(characters, text),
            "action": action,
            "expression": self._expression(text),
            "camera": self._cameras[(index - 1) % len(self._cameras)],
            "dialogue": dialogue,
            "prompt": self._shot_prompt(characters, text, index),
        }

    @staticmethod
    def _characters(text: str) -> list[str]:
        names: list[str] = []
        if re.search(r"\bRian\b", text, re.IGNORECASE):
            names.append("Rian")
        if re.search(r"\bSilas\b", text, re.IGNORECASE):
            names.append("Silas")
        if re.search(r"\b(I|me|my)\b", text, re.IGNORECASE):
            names.append("女主角")
        return list(dict.fromkeys(names))

    @staticmethod
    def _blocking(characters: list[str], text: str) -> str:
        people = "、".join(characters) if characters else "当前叙事涉及的人物"
        if "door" in text.lower():
            return f"{people}围绕房门内外调度，保持人物视线和动作方向连续。"
        return f"{people}保持与上一镜连续的站位，在主要动作发生方向留出画面空间。"

    @staticmethod
    def _expression(text: str) -> str:
        lowered = text.lower()
        if any(word in lowered for word in ("murderous", "anger", "shut up")):
            return "强烈愤怒与压迫感。"
        if any(word in lowered for word in ("tears", "heartbreak", "pale")):
            return "脆弱、心碎，情绪明显外露。"
        if any(word in lowered for word in ("gasped", "flying open", "hallucinating")):
            return "震惊、难以置信。"
        return "紧张克制，延续当前剧情情绪。"

    @staticmethod
    def _shot_prompt(characters: list[str], text: str, index: int) -> str:
        people = "、".join(characters) if characters else "剧情主体"
        return (
            f"海外真人短剧写实电影风格，第{index}镜，3秒。"
            f"场景为寒冷的酒店房间与门外走廊，主体：{people}。"
            f"剧情内容：{text} 人物与服装保持连续，无字幕。"
        )

    @staticmethod
    def _build_segment_prompt(shots: list[dict[str, Any]], duration: int) -> str:
        shot_text = " ".join(
            f"镜头{index}（{shot['duration']}秒）：{shot['action']} "
            f"表情：{shot['expression']} 镜头：{shot['camera']}"
            for index, shot in enumerate(shots, start=1)
        )
        return (
            f"海外真人短剧写实电影风格，本段总时长{duration}秒，"
            "镜头时长服务内容与生成可执行性，人物外貌、服装、空间方向连续，无字幕。"
            f"{shot_text}"
        )
