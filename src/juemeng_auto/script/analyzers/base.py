from __future__ import annotations

from typing import Any, Protocol

from juemeng_auto.runtime_budget import RuntimeBudget


class BaseAnalyzer(Protocol):
    """剧本分析器边界；未来 OpenAI 实现只需遵守此接口。"""

    def analyze(
        self,
        episode_id: str,
        script: str,
        *,
        runtime_budget: RuntimeBudget | None = None,
    ) -> dict[str, Any]:
        """将一集原始剧本转换成 Storyboard v1.0 字典。"""
        ...


# 兼容已使用的名称；BaseAnalyzer 是正式公共接口名。
StoryboardAnalyzer = BaseAnalyzer
