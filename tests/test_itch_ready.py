import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from mado_asset_foundry.io import load_recipe, write_json, write_recipe_snapshot
from mado_asset_foundry.itch_ready import compile_itch_ready_pack
from mado_asset_foundry.models import AssetRecord, FoundryRun, QAStatus, RefinementStatus
from mado_asset_foundry.packaging import compile_product


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_normalized(path: Path, index: int) -> None:
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4 + index, 5, 26, 27 - index), fill=(50 * index, 100, 180, 255))
    image.save(path, format="PNG")


def make_packaged_run(tmp_path: Path, *, public_license: bool) -> Path:
    run_dir = tmp_path / "run_itch"
    (run_dir / "refined").mkdir(parents=True)
    (run_dir / "metadata").mkdir()

    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    if public_license:
        assert recipe.product is not None
        recipe.product.license_id = "TEST-PUBLIC"
        recipe.product.license_status = "public"
        recipe.product.license_text = (
            "Test public distribution license for automated fixture validation only. "
            "Redistribution is allowed inside this isolated test fixture."
        )
    write_recipe_snapshot(run_dir / "recipe.yaml", recipe)

    assets = []
    for index, subject in enumerate(["red potion", "blue potion", "forest mushroom"], start=1):
        asset_id = f"asset_{index:04d}"
        refined = run_dir / "refined" / f"{asset_id}.png"
        make_normalized(refined, index)
        assets.append(
            AssetRecord(
                asset_id=asset_id,
                recipe_id=recipe.id,
                provider="fixture",
                model="fixture",
                subject=subject,
                qa_status=QAStatus.PASS,
                refinement_status=RefinementStatus.NORMALIZED,
                refined_path=str(refined),
                refined_sha256=sha256(refined),
            )
        )
        write_json(run_dir / "metadata" / f"{asset_id}.json", {"asset_id": asset_id})

    run = FoundryRun(
        run_id="run_itch",
        recipe_id=recipe.id,
        provider="fixture",
        model="fixture",
        requested_count=len(assets),
        assets=assets,
    )
    write_json(run_dir / "run.json", run.model_dump(mode="json"))
    compile_product(run_dir)
    return run_dir


def test_itch_ready_pack_generates_listing_visuals_and_upload(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path, public_license=True)
    report = compile_itch_ready_pack(run_dir)

    assert report.ready is True
    release_dir = Path(report.release_dir)
    assert (release_dir / "READY.json").exists()
    assert (release_dir / "listing.json").exists()
    assert (release_dir / "description.md").exists()
    assert (release_dir / "release-checklist.md").exists()
    assert Path(report.upload_zip).exists()
    assert len(report.screenshot_paths) == 3

    with Image.open(report.cover_path) as image:
        assert image.size == (630, 500)
    for screenshot in report.screenshot_paths:
        with Image.open(screenshot) as image:
            assert image.size == (960, 540)

    listing = json.loads((release_dir / "listing.json").read_text())
    assert listing["classification"] == "Assets"
    assert listing["upload_type"] == "Graphical Assets"
    assert listing["visibility_during_setup"] == "Draft"
    assert listing["platform_flags"] == []
    assert listing["generative_ai_disclosure"]["contains_generative_ai"] is True
    assert "graphics" in listing["generative_ai_disclosure"]["content_types"]


def test_draft_license_blocks_public_readiness_but_still_builds_pack(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path, public_license=False)
    report = compile_itch_ready_pack(run_dir)

    assert report.ready is False
    assert "license_not_public" in report.blockers
    assert "draft_license_identifier" in report.blockers
    ready = json.loads((Path(report.release_dir) / "READY.json").read_text())
    assert ready["human_publish_required"] is True
    assert ready["public_publish_automated"] is False


def test_itch_ready_detects_tampered_product_zip(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path, public_license=True)
    packaging = json.loads((run_dir / "packaging" / "report.json").read_text())
    zip_path = Path(packaging["zip_path"])
    zip_path.write_bytes(zip_path.read_bytes() + b"tamper")

    with pytest.raises(ValueError, match="SHA-256"):
        compile_itch_ready_pack(run_dir)


def test_itch_ready_does_not_overwrite_without_force(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path, public_license=True)
    compile_itch_ready_pack(run_dir)

    with pytest.raises(FileExistsError):
        compile_itch_ready_pack(run_dir)


def test_itch_ready_force_rebuild_is_stable_for_upload_zip(tmp_path: Path) -> None:
    run_dir = make_packaged_run(tmp_path, public_license=True)
    first = compile_itch_ready_pack(run_dir)
    first_digest = first.upload_zip_sha256

    second = compile_itch_ready_pack(run_dir, force=True)
    assert second.upload_zip_sha256 == first_digest
