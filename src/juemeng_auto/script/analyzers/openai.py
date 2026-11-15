from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from juemeng_auto.analysis_context import AnalysisContext
from juemeng_auto.runtime_budget import RuntimeBudget, build_runtime_pacing_reference

from ..schema import storyboard_json_schema
from ..postprocess import normalize_segment_durations
from ..validator import validate_storyboard


class OpenAIAnalyzerError(RuntimeError):
    pass


class OpenAIStoryboardAnalyzer:
    """使用 OpenAI Responses API Structured Outputs 的单集分析器。"""

    def __init__(
        self,
        api_key: str,
        model: str,
        instructions: str,
        debug_dir: Path,
        client: Any | None = None,
        context: AnalysisContext | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.instructions = context.instructions(instructions) if context else instructions
        self.run_metadata = {"provider": "openai", **(context.metadata() if context else {})}
        self.debug_dir = debug_dir
        self._client = client

    def analyze(
        self,
        episode_id: str,
        script: str,
        *,
        runtime_budget: RuntimeBudget | None = None,
    ) -> dict[str, Any]:
        response: Any | None = None
        try:
            client = self._client or self._create_client()
            instructions = self.instructions
            if runtime_budget is not None:
                instructions += "\n\n" + build_runtime_pacing_reference(runtime_budget)
            response = client.responses.create(
                model=self.model,
                instructions=instructions,
                input=(
                    f"请分析单集 {episode_id}。严格忠实于以下剧本，并仅按 "
                    "storyboard_json_v1 Schema 返回结果。\n\n"
                    f"{script}"
                ),
                text={
                    "format": {
                        "type": "json_schema",
                        "name": "storyboard_json_v1",
                        "description": "单集短剧的分段与镜头设计",
                        "strict": True,
                        "schema": storyboard_json_schema(),
                    }
                },
                max_output_tokens=20_000,
                store=False,
            )
            output_text = getattr(response, "output_text", "")
            if not isinstance(output_text, str) or not output_text.strip():
                raise OpenAIAnalyzerError("OpenAI 响应没有 output_text")
            data = json.loads(output_text)
            if not isinstance(data, dict):
                raise OpenAIAnalyzerError("OpenAI Structured Output 顶层不是对象")
            # 集标识由输入决定，与 Xiaomi 及 analyze_service 的后处理保持一致。
            data["episode_id"] = episode_id
            # 分段时长由 shots 合计确定，先规范化再校验，与 Xiaomi 保持一致。
            normalize_segment_durations(data)
            _, issues = validate_storyboard(data)
            if issues:
                details = "; ".join(str(issue) for issue in issues)
                raise OpenAIAnalyzerError(f"返回 JSON 未通过业务校验：{details}")
            return data
        except Exception:
            # Suppress provider text and chained exceptions, which may contain secrets.
            raise OpenAIAnalyzerError("Storyboard analysis failed; check input and provider configuration") from None

    def _create_client(self) -> Any:
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise OpenAIAnalyzerError(
                "缺少 openai SDK，请运行 pip install -r requirements.txt"
            ) from exc
        return OpenAI(api_key=self.api_key)

    def _save_failure(self, episode_id, response, error):
        """Public edition intentionally discards provider diagnostics."""
        return Path("diagnostics-disabled")
