from __future__ import annotations

import base64
import os
from typing import Any

from .base import GeneratedImage, ImageGenerationRequest


class OpenAIImageProvider:
    name = "openai-image"

    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _client_or_create(self) -> Any:
        if self._client is not None:
            return self._client
        if not os.getenv("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY is required for the openai-image provider")
        from openai import OpenAI

        self._client = OpenAI()
        return self._client

    def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]:
        response = self._client_or_create().images.generate(
            model=request.model,
            prompt=request.prompt,
            n=request.count,
            size=request.size,
            quality=request.quality,
            background=request.background,
            output_format=request.output_format,
        )

        request_id = getattr(response, "_request_id", None)
        usage_value = getattr(response, "usage", None)
        if hasattr(usage_value, "model_dump"):
            usage_value = usage_value.model_dump()
        if usage_value is not None and not isinstance(usage_value, dict):
            usage_value = None

        shared_metadata: dict[str, object] = {}
        if request_id:
            shared_metadata["request_id"] = request_id
        if usage_value:
            shared_metadata["usage"] = usage_value

        generated: list[GeneratedImage] = []
        for item in response.data or []:
            encoded = getattr(item, "b64_json", None)
            if not encoded and isinstance(item, dict):
                encoded = item.get("b64_json")
            if not encoded:
                raise RuntimeError("OpenAI image response did not include b64_json")

            revised_prompt = getattr(item, "revised_prompt", None)
            if revised_prompt is None and isinstance(item, dict):
                revised_prompt = item.get("revised_prompt")

            generated.append(
                GeneratedImage(
                    content=base64.b64decode(encoded),
                    revised_prompt=revised_prompt,
                    provider_metadata=dict(shared_metadata),
                )
            )

        if len(generated) != request.count:
            raise RuntimeError(f"OpenAI returned {len(generated)} images for requested count {request.count}")
        return generated
