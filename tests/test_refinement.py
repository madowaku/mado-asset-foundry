import hashlib
import json
from pathlib import Path

from PIL import Image, ImageDraw

from mado_asset_foundry.io import load_recipe, load_run, write_json, write_recipe_snapshot
from mado_asset_foundry.models import (
    AssetRecord,
    CurationDecision,
    FoundryRun,
    QAStatus,
    RefinementStatus,
)
from mado_asset_foundry.refinement import refine_run


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_source(path: Path, *, transparent: bool = False, many_colors: bool = False) -> None:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    if transparent:
        image.save(path, format="PNG")
        return

    draw = ImageDraw.Draw(image)
    if many_colors:
        for x in range(12, 52):
            color = ((x * 13) % 256, (x * 29) % 256, (x * 47) % 256, 255)
            draw.line((x, 12, x, 51), fill=color)
    else:
        draw.rectangle((12, 18, 51, 45), fill=(180, 80, 60, 255))
    image.save(path, format="PNG")


def make_run(tmp_path: Path, qa_statuses: list[QAStatus | None]) -> Path:
    run_dir = tmp_path / "run_refine"
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "metadata").mkdir()

    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    recipe.generation.render_size = "64x64"
    write_recipe_snapshot(run_dir / "recipe.yaml", recipe)

    assets = []
    for index, qa_status in enumerate(qa_statuses, start=1):
        asset_id = f"asset_{index:04d}"
        assets.append(
            AssetRecord(
                asset_id=asset_id,
                recipe_id=recipe.id,
                provider="fixture",
                model="fixture",
                curation_decision=CurationDecision.KEEP,
                qa_status=qa_status,
                source_path=str(run_dir / "raw" / f"{asset_id}.png"),
            )
        )
        write_json(run_dir / "metadata" / f"{asset_id}.json", {"asset_id": asset_id})

    run = FoundryRun(
        run_id="run_refine",
        recipe_id=recipe.id,
        provider="fixture",
        model="fixture",
        requested_count=len(assets),
        assets=assets,
    )
    write_json(run_dir / "run.json", run.model_dump(mode="json"))
    return run_dir


def test_refine_normalizes_qa_passed_asset_without_mutating_raw(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [QAStatus.PASS])
    raw = run_dir / "raw" / "asset_0001.png"
    make_source(raw, many_colors=True)
    before = sha256(raw)

    report = refine_run(run_dir)

    assert report.eligible_count == 1
    assert report.normalized_count == 1
    assert report.failed_count == 0
    assert sha256(raw) == before

    output = run_dir / "refined" / "asset_0001.png"
    assert output.exists()
    with Image.open(output) as image:
        assert image.size == (32, 32)
        assert image.mode == "RGBA"
        alpha_box = image.getchannel("A").getbbox()
        assert alpha_box is not None
        assert alpha_box[0] >= 2
        assert alpha_box[1] >= 2
        assert alpha_box[2] <= 30
        assert alpha_box[3] <= 30
        visible_colors = {
            pixel[:3]
            for pixel in image.getdata()
            if pixel[3] > 0
        }
        assert len(visible_colors) <= 16

    persisted = load_run(run_dir / "run.json")
    asset = persisted.assets[0]
    assert asset.refinement_status == RefinementStatus.NORMALIZED
    assert asset.state == "normalized"
    assert asset.refined_sha256
    assert (run_dir / "refinement" / "asset_0001.json").exists()


def test_refine_accepts_qa_warning(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [QAStatus.WARN])
    make_source(run_dir / "raw" / "asset_0001.png")

    report = refine_run(run_dir)
    assert report.normalized_count == 1


def test_refine_skips_asset_without_qa_pass(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [QAStatus.FAIL, None])
    make_source(run_dir / "raw" / "asset_0001.png")
    make_source(run_dir / "raw" / "asset_0002.png")

    report = refine_run(run_dir)
    assert report.eligible_count == 0
    assert report.skipped_count == 2
    assert not list((run_dir / "refined").glob("*.png"))

    persisted = load_run(run_dir / "run.json")
    assert all(asset.refinement_status == RefinementStatus.SKIPPED for asset in persisted.assets)
    metadata = json.loads((run_dir / "metadata" / "asset_0001.json").read_text())
    assert metadata["refinement_status"] == "skipped"
    assert "refinement_report_path" in metadata


def test_refine_fails_fully_transparent_asset(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [QAStatus.PASS])
    make_source(run_dir / "raw" / "asset_0001.png", transparent=True)

    report = refine_run(run_dir)
    assert report.failed_count == 1
    assert report.reports[0].status == RefinementStatus.FAILED

    persisted = load_run(run_dir / "run.json")
    assert persisted.assets[0].state == "refine_failed"


def test_refine_does_not_overwrite_without_force(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [QAStatus.PASS])
    make_source(run_dir / "raw" / "asset_0001.png")

    first = refine_run(run_dir)
    assert first.normalized_count == 1
    output = run_dir / "refined" / "asset_0001.png"
    first_digest = sha256(output)

    second = refine_run(run_dir)
    assert second.skipped_count == 1
    assert sha256(output) == first_digest
