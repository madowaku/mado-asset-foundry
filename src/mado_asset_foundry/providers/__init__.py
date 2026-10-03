from __future__ import annotations

from .base import ImageProvider
from .codex_imagegen import CodexImageGenProvider
from .openai_image import OpenAIImageProvider


def get_image_provider(
    name: str,
    *,
    codex_model: str = "gpt-6-luna",
    codex_binary: str = "codex",
    codex_timeout_seconds: int = 420,
) -> ImageProvider:
    normalized = name.strip().lower()
    if normalized in {"openai-image", "imagegen", "openai"}:
        return OpenAIImageProvider()
    if normalized in {"codex-imagegen", "codex"}:
        return CodexImageGenProvider(
            codex_model=codex_model,
            codex_binary=codex_binary,
            timeout_seconds=codex_timeout_seconds,
        )
    raise ValueError(f"unknown image provider: {name}")
