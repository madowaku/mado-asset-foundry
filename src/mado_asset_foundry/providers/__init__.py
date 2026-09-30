from __future__ import annotations

from .base import ImageProvider
from .openai_image import OpenAIImageProvider


def get_image_provider(name: str) -> ImageProvider:
    normalized = name.strip().lower()
    if normalized in {"openai-image", "imagegen", "openai"}:
        return OpenAIImageProvider()
    raise ValueError(f"unknown image provider: {name}")
