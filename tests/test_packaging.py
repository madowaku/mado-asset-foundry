import hashlib
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from mado_asset_foundry.io import load_recipe, load_run, write_json, write_recipe_snapshot
from mado_asset_foundry.models import AssetRecord, FoundryRun, QAStatus, RefinementStatus
from mado_asset_foundry.packaging import compile_product


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_normalized(path: Path, index: int) -> None:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4 + index, 5, 26, 27 - index), fill=(60 * index, 90, 180, 255))
    image.save(path, format="PNG")


def make_run(tmp_path: Path, *, count: int = 3, include_product: bool = True) -> Path:
    run_dir = tmp_path / "run_package"
    (run_dir / "refined").mkdir(parents=True)
    (run_dir / "metadata").mkdir()

    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    if not include_product:
        recipe.product = None
    write_recipe_snapshot(run_dir / "recipe.yaml", recipe)

    assets = []
    subjects = ["red potion", "blue potion", "forest mushroom"]
    for index in range(1, count + 1):
        asset_id = f"asset_{index:04d}"
        refined = run_dir / "refined" / f"{asset_id}.png"
        make_normalized(refined, index)
        assets.append(
            AssetRecord(
                asset_id=asset_id,
                recipe_id=recipe.id,
                provider="fixture",
                model="fixture",
                subject=subjects[(index - 1) % len(subjects)],
                qa_status=QAStatus.PASS,
                refinement_status=RefinementStatus.NORMALIZED,
                refined_path=str(refined),
                refined_sha256=sha256(refined),
            )
        )
        write_json(run_dir / "metadata" / f"{asset_id}.json", {"asset_id": asset_id})

    run = FoundryRun(
        run_id="run_package",
        recipe_id=recipe.id,
        provider="fixture",
        model="fixture",
        requested_count=count,
        assets=assets,
    )
    write_json(run_dir / "run.json", run.model_dump(mode="json"))
    return run_dir


def test_package_compiles_complete_product_and_zip(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    report = compile_product(run_dir)

    product_dir = Path(report.product_dir)
    assert report.asset_count == 3
    assert product_dir.exists()
    assert (product_dir / "sprite_sheet.png").exists()
    assert (product_dir / "preview" / "contact_sheet.png").exists()
    assert (product_dir / "README.md").exists()
    assert (product_dir / "LICENSE.txt").exists()
    assert (product_dir / "MANIFEST.json").exists()
    assert (product_dir / "PRODUCT.json").exists()
    assert len(list((product_dir / "assets").glob("*.png"))) == 3

    with Image.open(product_dir / "sprite_sheet.png") as image:
        assert image.size == (96, 32)
    with Image.open(product_dir / "preview" / "contact_sheet.png") as image:
        assert image.size == (384, 128)

    manifest = json.loads((product_dir / "MANIFEST.json").read_text())
    assert manifest["asset_count"] == 3
    assert manifest["source_run"] == "run_package"
    assert manifest["license_id"] == "MADO-DOGFOOD-DRAFT"

    zip_path = Path(report.zip_path)
    assert zip_path.exists()
    assert report.zip_sha256 == sha256(zip_path)
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
    assert "forest-alchemy-icons-0.1.0/MANIFEST.json" in names
    assert "forest-alchemy-icons-0.1.0/sprite_sheet.png" in names

    persisted = load_run(run_dir / "run.json")
    assert all(asset.state == "packaged" for asset in persisted.assets)
    assert all("forest-alchemy-icons@0.1.0" in asset.packaged_products for asset in persisted.assets)


def test_package_requires_product_config(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, include_product=False)
    with pytest.raises(ValueError, match="recipe.product"):
        compile_product(run_dir)


def test_package_requires_normalized_assets(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, count=1)
    run = load_run(run_dir / "run.json")
    run.assets[0].refinement_status = RefinementStatus.SKIPPED
    write_json(run_dir / "run.json", run.model_dump(mode="json"))

    with pytest.raises(ValueError, match="no normalized assets"):
        compile_product(run_dir)


def test_package_does_not_overwrite_without_force(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    compile_product(run_dir)

    with pytest.raises(FileExistsError):
        compile_product(run_dir)


def test_package_zip_is_reproducible(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    first = compile_product(run_dir)
    first_digest = first.zip_sha256

    second = compile_product(run_dir, force=True)
    assert second.zip_sha256 == first_digest
