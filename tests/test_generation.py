from pathlib import Path

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
            GeneratedImage(content=f"fake-png-{len(self.requests)}-{i}".encode(), revised_prompt=request.prompt)
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
