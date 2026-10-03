import io
import re
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from mado_asset_foundry.providers.base import ImageGenerationRequest
from mado_asset_foundry.providers.codex_imagegen import CodexImageGenProvider


def make_png(path: Path) -> None:
    image = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((256, 256, 768, 768), fill=(180, 80, 60, 255))
    image.save(path, format="PNG")


def make_request(count: int = 1) -> ImageGenerationRequest:
    return ImageGenerationRequest(
        model="gpt-image-2",
        prompt="forest alchemy potion icon",
        count=count,
        size="1024x1024",
        quality="low",
        background="transparent",
        output_format="png",
    )


def test_codex_bridge_invokes_one_exec_per_image() -> None:
    calls: list[list[str]] = []

    def runner(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        match = re.search(r"SAVED (maf-output-\d+\.png)", args[-1])
        assert match is not None
        output_name = match.group(1)
        make_png(cwd / output_name)
        return subprocess.CompletedProcess(args, 0, f"SAVED {output_name}\n", "")

    provider = CodexImageGenProvider(
        codex_model="gpt-6-luna",
        codex_binary="codex",
        runner=runner,
    )
    provider._resolve_binary = lambda: "codex"  # type: ignore[method-assign]

    results = provider.generate(make_request(count=2))

    assert len(results) == 2
    assert len(calls) == 2
    assert all("--ephemeral" in call for call in calls)
    assert all("workspace-write" in call for call in calls)
    assert all("gpt-6-luna" in call for call in calls)
    assert results[0].provider_metadata["image_model"] == "gpt-image-2"
    assert results[0].provider_metadata["usage_scope"] == "codex_general_usage"
    with Image.open(io.BytesIO(results[0].content)) as image:
        assert image.size == (1024, 1024)
        assert image.format == "PNG"


def test_codex_bridge_rejects_wrong_image_model() -> None:
    provider = CodexImageGenProvider()
    wrong = ImageGenerationRequest(
        model="gpt-image-2.5-flare",
        prompt="icon",
        count=1,
        size="1024x1024",
        quality="low",
        background="transparent",
        output_format="png",
    )
    with pytest.raises(ValueError, match="gpt-image-2"):
        provider.generate(wrong)


def test_codex_bridge_fails_when_exec_returns_no_png() -> None:
    provider = CodexImageGenProvider(
        runner=lambda args, cwd, timeout: subprocess.CompletedProcess(args, 0, "done", "")
    )
    provider._resolve_binary = lambda: "codex"  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="without materializing a PNG"):
        provider.generate(make_request())


def test_codex_bridge_surfaces_nonzero_exit() -> None:
    provider = CodexImageGenProvider(
        runner=lambda args, cwd, timeout: subprocess.CompletedProcess(
            args, 7, "", "imagegen unavailable"
        )
    )
    provider._resolve_binary = lambda: "codex"  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="exit code 7"):
        provider.generate(make_request())
