from pathlib import Path

import pytest

from mado_asset_foundry.generation import generate_run
from mado_asset_foundry.io import load_recipe, load_run
from mado_asset_foundry.providers.base import GeneratedImage, ImageGenerationRequest


class FakeProvider:
    name = "fixture"

    def __init__(self) -> None:
        self.requests: list[ImageGenerationRequest] = []

    def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]:
        self.requests.append(request)
        return [
            GeneratedImage(
                content=f"fake-png-{len(self.requests)}-{i}".encode(),
                revised_prompt=request.prompt,
                provider_metadata={
                    "request_id": f"req_{len(self.requests)}",
                    "usage": {"input_tokens": 10, "output_tokens": 100, "total_tokens": 110},
                },
            )
            for i in range(request.count)
        ]


def test_generate_run_writes_assets_and_provenance(tmp_path: Path) -> None:
    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    provider = FakeProvider()
    run, run_dir = generate_run(
        recipe,
        workspace=tmp_path,
        count=5,
        run_id="fixture-run",
        provider=provider,
    )

    assert len(run.assets) == 5
    assert len(provider.requests) == 2
    assert (run_dir / "recipe.yaml").exists()
    assert (run_dir / "plan.json").exists()
    assert (run_dir / "run.json").exists()
    assert (run_dir / "requests.json").exists()
    assert len(list((run_dir / "raw").glob("*.png"))) == 5
    assert len(list((run_dir / "metadata").glob("*.json"))) == 5

    loaded = load_run(run_dir / "run.json")
    assert loaded.assets[0].sha256


def test_dry_run_makes_no_provider_calls(tmp_path: Path) -> None:
    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    provider = FakeProvider()
    run, run_dir = generate_run(
        recipe,
        workspace=tmp_path,
        count=3,
        dry_run=True,
        run_id="dry-run",
        provider=provider,
    )

    assert run.dry_run is True
    assert run.assets == []
    assert provider.requests == []
    assert (run_dir / "plan.json").exists()



def test_live_generation_failure_preserves_partial_run_evidence(tmp_path: Path) -> None:
    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    recipe.generation.batch_size = 1

    class FailingProvider:
        name = "fixture"

        def __init__(self) -> None:
            self.calls = 0

        def generate(self, request: ImageGenerationRequest) -> list[GeneratedImage]:
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("fixture provider failure")
            return [GeneratedImage(content=b"first-image")]

    provider = FailingProvider()
    with pytest.raises(RuntimeError, match="fixture provider failure"):
        generate_run(
            recipe,
            workspace=tmp_path,
            count=2,
            run_id="partial-live",
            provider=provider,
        )

    run_dir = tmp_path / "partial-live"
    persisted = load_run(run_dir / "run.json")
    assert len(persisted.assets) == 1
    assert (run_dir / "raw" / "asset_0001.png").exists()
    error = __import__("json").loads((run_dir / "generation-error.json").read_text())
    assert error["generated_assets_before_error"] == 1
    assert error["subject"]
