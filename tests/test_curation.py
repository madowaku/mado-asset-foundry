import json
from pathlib import Path

from mado_asset_foundry.curation import apply_curation, summarize_run
from mado_asset_foundry.io import load_run, write_json
from mado_asset_foundry.models import AssetRecord, CurationDecision, FoundryRun


def make_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run_001"
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "metadata").mkdir()
    run = FoundryRun(
        run_id="run_001",
        recipe_id="recipe",
        provider="fixture",
        model="fixture",
        requested_count=1,
        assets=[AssetRecord(asset_id="asset_0001", recipe_id="recipe", provider="fixture", model="fixture")],
    )
    write_json(run_dir / "run.json", run.model_dump(mode="json"))
    write_json(run_dir / "metadata" / "asset_0001.json", {"asset_id": "asset_0001"})
    return run_dir


def test_apply_curation_updates_run_and_metadata(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    updated = apply_curation(run_dir, "asset_0001", decision=CurationDecision.KEEP, favorite=True)
    asset = updated.assets[0]
    assert asset.curation_decision == CurationDecision.KEEP
    assert asset.state == "selected"
    assert asset.favorite is True

    persisted = load_run(run_dir / "run.json")
    assert persisted.assets[0].curation_decision == CurationDecision.KEEP
    metadata = json.loads((run_dir / "metadata" / "asset_0001.json").read_text())
    assert metadata["curation_decision"] == "keep"
    assert metadata["favorite"] is True


def test_summary_counts_decisions_and_favorites(tmp_path: Path) -> None:
    run_dir = make_run(tmp_path)
    run = apply_curation(run_dir, "asset_0001", decision=CurationDecision.MAYBE, favorite=True)
    summary = summarize_run(run)
    assert summary["maybe"] == 1
    assert summary["favorite"] == 1
    assert summary["reviewed"] == 1
