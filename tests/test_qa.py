from pathlib import Path

from PIL import Image, ImageDraw

from mado_asset_foundry.io import load_recipe, load_run, write_json, write_recipe_snapshot
from mado_asset_foundry.models import (
    AssetRecord,
    CurationDecision,
    FoundryRun,
    QAStatus,
)
from mado_asset_foundry.qa import run_image_qa


def make_icon(path: Path, *, clipped: bool = False, opaque: bool = False) -> None:
    background = (20, 30, 40, 255) if opaque else (0, 0, 0, 0)
    image = Image.new("RGBA", (64, 64), background)
    draw = ImageDraw.Draw(image)
    box = (0, 14, 40, 50) if clipped else (16, 16, 48, 48)
    draw.rectangle(box, fill=(180, 80, 60, 255))
    image.save(path, format="PNG")


def make_run(tmp_path: Path, decisions: list[CurationDecision]) -> Path:
    run_dir = tmp_path / "run_qa"
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "metadata").mkdir()

    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    recipe.generation.render_size = "64x64"
    write_recipe_snapshot(run_dir / "recipe.yaml", recipe)

    assets = []
    for index, decision in enumerate(decisions, start=1):
        asset_id = f"asset_{index:04d}"
        assets.append(
            AssetRecord(
                asset_id=asset_id,
                recipe_id=recipe.id,
                provider="fixture",
                model="fixture",
                curation_decision=decision,
                source_path=str(run_dir / "raw" / f"{asset_id}.png"),
            )
        )
        write_json(run_dir / "metadata" / f"{asset_id}.json", {"asset_id": asset_id})

    run = FoundryRun(
        run_id="run_qa",
        recipe_id=recipe.id,
        provider="fixture",
        model="fixture",
        requested_count=len(assets),
        assets=assets,
    )
    write_json(run_dir / "run.json", run.model_dump(mode="json"))
    return run_dir


def test_qa_only_checks_kept_assets_and_passes_clean_icon(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [CurationDecision.KEEP, CurationDecision.REJECT])
    make_icon(run_dir / "raw" / "asset_0001.png")
    make_icon(run_dir / "raw" / "asset_0002.png")

    report = run_image_qa(run_dir)
    assert report.selected_count == 1
    assert report.pass_count == 1
    assert report.fail_count == 0
    assert (run_dir / "qa" / "asset_0001.json").exists()
    assert not (run_dir / "qa" / "asset_0002.json").exists()

    persisted = load_run(run_dir / "run.json")
    assert persisted.assets[0].qa_status == QAStatus.PASS
    assert persisted.assets[0].state == "qa_passed"
    assert persisted.assets[1].qa_status is None


def test_qa_warns_for_exact_duplicates_and_clipped_edges(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [CurationDecision.KEEP, CurationDecision.KEEP])
    first = run_dir / "raw" / "asset_0001.png"
    second = run_dir / "raw" / "asset_0002.png"
    make_icon(first, clipped=True)
    second.write_bytes(first.read_bytes())

    report = run_image_qa(run_dir)
    assert report.warn_count == 2
    for asset_report in report.reports:
        statuses = {check.check: check.status for check in asset_report.checks}
        assert statuses["exact_duplicate"] == QAStatus.WARN
        assert statuses["edge_clipping"] == QAStatus.WARN


def test_qa_fails_opaque_image_when_transparency_required(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [CurationDecision.KEEP])
    make_icon(run_dir / "raw" / "asset_0001.png", opaque=True)

    report = run_image_qa(run_dir)
    assert report.fail_count == 1
    checks = {check.check: check for check in report.reports[0].checks}
    assert checks["transparency"].status == QAStatus.FAIL

    persisted = load_run(run_dir / "run.json")
    assert persisted.assets[0].state == "qa_failed"


def test_qa_fails_missing_source(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [CurationDecision.KEEP])
    report = run_image_qa(run_dir)
    assert report.fail_count == 1
    assert report.reports[0].checks[0].check == "file_exists"
    assert report.reports[0].checks[0].status == QAStatus.FAIL


def test_qa_fails_wrong_source_dimensions(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [CurationDecision.KEEP])
    image = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
    image.save(run_dir / "raw" / "asset_0001.png", format="PNG")

    report = run_image_qa(run_dir)
    assert report.fail_count == 1
    checks = {check.check: check for check in report.reports[0].checks}
    assert checks["dimensions"].status == QAStatus.FAIL


def test_qa_fails_wrong_file_format(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path, [CurationDecision.KEEP])
    image = Image.new("RGB", (64, 64), (20, 30, 40))
    image.save(run_dir / "raw" / "asset_0001.png", format="JPEG")

    report = run_image_qa(run_dir)
    assert report.fail_count == 1
    checks = {check.check: check for check in report.reports[0].checks}
    assert checks["file_format"].status == QAStatus.FAIL
