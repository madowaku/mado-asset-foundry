import base64
from types import SimpleNamespace

from mado_asset_foundry.providers.base import ImageGenerationRequest
from mado_asset_foundry.providers.openai_image import OpenAIImageProvider


def test_openai_provider_decodes_base64_and_passes_request_fields() -> None:
    calls = []

    class Images:
        def generate(self, **kwargs):
            calls.append(kwargs)
            item = SimpleNamespace(
                b64_json=base64.b64encode(b"png-bytes").decode(),
                revised_prompt="revised",
            )
            usage = SimpleNamespace(
                model_dump=lambda: {"input_tokens": 7, "output_tokens": 196, "total_tokens": 203}
            )
            return SimpleNamespace(data=[item], _request_id="req_fixture", usage=usage)

    client = SimpleNamespace(images=Images())
    provider = OpenAIImageProvider(client=client)
    request = ImageGenerationRequest(
        model="gpt-image-2.5-flare",
        prompt="forest icon",
        count=1,
        size="1024x1024",
        quality="low",
        background="transparent",
        output_format="png",
    )

    result = provider.generate(request)
    assert result[0].content == b"png-bytes"
    assert result[0].provider_metadata["request_id"] == "req_fixture"
    assert result[0].provider_metadata["usage"]["output_tokens"] == 196
    assert calls[0]["model"] == "gpt-image-2.5-flare"
    assert calls[0]["background"] == "transparent"
