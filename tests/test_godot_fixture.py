import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from mado_asset_foundry.godot_fixture import build_godot_fixture
from mado_asset_foundry.io import load_recipe, write_json, write_recipe_snapshot
from mado_asset_foundry.models import AssetRecord, FoundryRun, QAStatus, RefinementStatus
from mado_asset_foundry.packaging import compile_product


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_icon(path: Path, index: int) -> None:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 4 + index, 27, 27), fill=(80 * index, 120, 180, 255))
    image.save(path, format="PNG")


def make_packaged_run(tmp_path: Path, *, count: int = 3) -> Path:
    run_dir = tmp_path / "run_godot"
    (run_dir / "refined").mkdir(parents=True)
    (run_dir / "metadata").mkdir()

    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    write_recipe_snapshot(run_dir / "recipe.yaml", recipe)

    assets = []
    for index in range(1, count + 1):
        asset_id = f"asset_{index:04d}"
        refined = run_dir / "refined" / f"{asset_id}.png"
        make_icon(refined, index)
        assets.append(
            AssetRecord(
                asset_id=asset_id,
                recipe_id=recipe.id,
                provider="fixture",
                model="fixture",
                subject=f"icon {index}",
                qa_status=QAStatus.PASS,
                refinement_status=RefinementStatus.NORMALIZED,
                refined_path=str(refined),
                refined_sha256=sha256(refined),
            )
        )
        write_json(run_dir / "metadata" / f"{asset_id}.json", {"asset_id": asset_id})

    run = FoundryRun(
        run_id="run_godot",
        recipe_id=recipe.id,
        provider="fixture",
        model="fixture",
        requested_count=count,
        assets=assets,
    )
    write_json(run_dir / "run.json", run.model_dump(mode="json"))
    compile_product(run_dir)
    return run_dir


def test_build_godot_fixture_consumes_packaged_assets(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path)
    report = build_godot_fixture(run_dir)

    fixture = Path(report.fixture_dir)
    assert report.asset_count == 3
    assert report.verification_status == "not_run"
    assert (fixture / "project.godot").exists()
    assert (fixture / "icon_gallery.tscn").exists()
    assert (fixture / "icon_gallery.gd").exists()
    assert (fixture / "verify.gd").exists()
    assert len(list((fixture / "assets").glob("*.png"))) == 3

    manifest = json.loads((fixture / "asset_manifest.json").read_text())
    assert manifest["asset_count"] == 3
    assert manifest["expected_width"] == 32
    assert manifest["expected_height"] == 32
    assert manifest["source_product"] == "forest-alchemy-icons@0.1.0"

    gallery = (fixture / "icon_gallery.gd").read_text()
    assert "TEXTURE_FILTER_NEAREST" in gallery
    assert "KEY_F12" in gallery

    verifier = (fixture / "verify.gd").read_text()
    assert "texture.get_width()" in verifier
    assert "import-report.json" in verifier


def test_godot_fixture_rejects_tampered_packaged_asset(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path, count=1)
    product_dir = run_dir / "product" / "forest-alchemy-icons-0.1.0"
    packaged_asset = next((product_dir / "assets").glob("*.png"))
    image = Image.open(packaged_asset).convert("RGBA")
    image.putpixel((0, 0), (255, 0, 0, 255))
    image.save(packaged_asset, format="PNG")

    with pytest.raises(ValueError, match="SHA-256"):
        build_godot_fixture(run_dir)


def test_godot_fixture_does_not_overwrite_without_force(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path)
    build_godot_fixture(run_dir)

    with pytest.raises(FileExistsError):
        build_godot_fixture(run_dir)


def test_godot_fixture_force_rebuild_preserves_asset_hashes(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path)
    first = build_godot_fixture(run_dir)
    first_assets = sorted(Path(first.fixture_dir).joinpath("assets").glob("*.png"))
    first_hashes = [sha256(path) for path in first_assets]

    second = build_godot_fixture(run_dir, force=True)
    second_assets = sorted(Path(second.fixture_dir).joinpath("assets").glob("*.png"))
    assert [sha256(path) for path in second_assets] == first_hashes
