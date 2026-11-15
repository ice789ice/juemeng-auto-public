from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class ConfigurationError(ValueError):
    pass


DEFAULT_AI_PROVIDER = "openai"
AI_PROVIDERS = ("mock", "openai")


def resolve_ai_provider(project_root: Path, provider: str | None = None) -> str:
    load_project_env(project_root)
    selected = provider if provider is not None else (
        os.getenv("DEFAULT_AI_PROVIDER", "").strip() or DEFAULT_AI_PROVIDER
    )
    if selected not in AI_PROVIDERS:
        raise ConfigurationError("AI provider must be openai or mock")
    return selected


def get_ai_model(project_root: Path, provider: str, model: str | None = None) -> str:
    if provider == "openai":
        return OpenAISettings.from_environment(project_root, model=model).model
    return "mock"


def load_env_file(path: Path) -> None:
    """轻量读取 .env；不覆盖终端中已经设置的环境变量。"""
    if not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


def load_project_env(project_root: Path) -> None:
    """Load the project-root .env without overriding process environment."""
    load_env_file(project_root / ".env")


def mask_api_key(api_key: str) -> str:
    """Return a safe, non-reversible display form for an API key."""
    value = api_key.strip()
    if not value:
        return "未配置"
    if len(value) <= 8:
        return "***"
    return f"{value[:3]}...{value[-4:]}"


@dataclass(frozen=True, slots=True)
class OpenAISettings:
    api_key: str
    model: str
    proxy_url: str | None = None

    @classmethod
    def from_environment(cls, project_root: Path, model: str | None = None) -> "OpenAISettings":
        load_project_env(project_root)
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise ConfigurationError(
                "缺少 OPENAI_API_KEY；请复制 .env.example 为 .env 后填写"
            )
        model = (model or os.getenv("OPENAI_MODEL", "gpt-5")).strip() or "gpt-5"
        proxy_url = os.getenv("OPENAI_PROXY_URL", "").strip() or None
        return cls(api_key=api_key, model=model, proxy_url=proxy_url)
