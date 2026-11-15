from __future__ import annotations

from typing import Any


def normalize_segment_durations(data: dict[str, Any]) -> None:
    """用镜头时长合计覆盖模型生成的分段时长；异常结构留给 validator 报告。"""
    segments = data.get("segments")
    if not isinstance(segments, list):
        return
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        shots = segment.get("shots")
        if not isinstance(shots, list):
            continue
        durations: list[int | float] = []
        for shot in shots:
            if not isinstance(shot, dict):
                break
            duration = shot.get("duration")
            if isinstance(duration, bool) or not isinstance(duration, (int, float)):
                break
            durations.append(duration)
        else:
            segment["duration"] = sum(durations)
