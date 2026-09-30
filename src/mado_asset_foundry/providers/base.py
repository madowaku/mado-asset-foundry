from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ImageGenerationRequest:
    model: str
    prompt: str
    count: int
    size: str
    quality: str
    background: str
    output_format: str


@dataclass(frozen=True)
class GeneratedImage:
    content: bytes
    revised_prompt: str | None = None
    provider_metadata: dict[str, object] = field(default_factory=dict)


class ImageProvider(Protocol):
    name: str

    def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]: ...
