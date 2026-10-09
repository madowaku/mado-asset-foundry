from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw
from typer.testing import CliRunner

import mado_asset_foundry.asset_flow as flow
from mado_asset_foundry.asset_sources import _sha256
from mado_asset_foundry.attribution_bridge import BridgePlan, _read_object
from mado_asset_foundry.cli import app
from mado_asset_foundry.io import write_json
from mado_asset_foundry.visual_gallery import _evidence_entries

runner = CliRunner()


def source_recipe(tmp_path: Path, *, reviewed: bool = True, count: int = 2) -> Path:
    directory = tmp_path / "sources"
    directory.mkdir()
    entries: list[str] = []
    for i in range(count):
        folder = directory / f"icon{i}"
        folder.mkdir()
        image = Image.new("RGBA", (32, 32), (50 + 60 * i, 180, 100, 255))
        image.save(folder / "source.png")
        (folder / "LICENSE.txt").write_text("Original QA fixture CC0-1.0", encoding="utf-8")
        (folder / "submission.yaml").write_text(yaml.safe_dump({
            "asset_id": f"icon-{i}", "source_id": "local",
            "title": f"Icon {i}", "creator": "MAF fixture",
            "local_file": "source.png", "license_spdx": "CC0-1.0",
            "license_evidence_file": "LICENSE.txt",
            "reviewed_by_human": reviewed, "use_case": "game_embedding",
        }), encoding="utf-8")
        entries.append(f"sources/icon{i}/submission.yaml")
    recipe = tmp_path / "flow.yaml"
    recipe.write_text(yaml.safe_dump({
        "schema_version": "0.1", "flow_id": "forest-test",
        "submissions": entries,
    }), encoding="utf-8")
    return recipe


def fake_engine(monkeypatch: pytest.MonkeyPatch, *, runtime_fail: bool = False) -> list[str]:
    steps: list[str] = []

    def runtime(plan_path, project_dir, *, godot_bin, output_root, timeout):
        steps.append("runtime")
        folder = Path(output_root) / "forest-test"
        folder.mkdir(parents=True)
        result = {
            "status": "failed" if runtime_fail else "passed",
            "godot_version": "4.6.1.stable",
            "failure_reason": "synthetic failure" if runtime_fail else None,
        }
        write_json(folder / "report.json", result)
        return result, folder

    def render(plan_path, project_dir, *, godot_bin, output_root, timeout, virtual_display):
        steps.append("gallery")
        plan_path = Path(plan_path)
        project_dir = Path(project_dir)
        folder = Path(output_root) / "forest-test"
        folder.mkdir(parents=True)
        image = Image.new("RGB", (960, 540), (10, 20, 30))
        draw = ImageDraw.Draw(image)
        draw.rectangle((50, 100, 300, 400), fill=(190, 100, 80))
        image.save(folder / "gallery.png")
        shutil.copyfile(project_dir / "CREDITS.md", folder / "CREDITS.md")
        plan = BridgePlan.model_validate(_read_object(plan_path))
        manifest = _read_object(project_dir / "asset_manifest.json")
        record = {
            "status": "captured", "project_id": plan.project_id,
            "screenshot_sha256": _sha256(folder / "gallery.png"),
            "credits_sha256": _sha256(folder / "CREDITS.md"),
            "manifest_sha256": _sha256(project_dir / "asset_manifest.json"),
            "assets": _evidence_entries(plan, plan_path, manifest),
        }
        write_json(folder / "report.json", record)
        return record, folder

    monkeypatch.setattr(flow, "verify_godot_import", runtime)
    monkeypatch.setattr(flow, "render_gallery", render)
    return steps


def review_document(folder: Path, destination: Path, *, visual: bool = True) -> Path:
    gallery = _read_object(folder / "gallery" / "forest-test" / "report.json")
    write_json(destination, {
        "schema_version": "0.1",
        "project_id": "forest-test",
        "reviewer": "human qa reviewer",
        "screenshot_sha256": gallery["screenshot_sha256"],
        "credits_sha256": gallery["credits_sha256"],
        "manifest_sha256": gallery["manifest_sha256"],
        "visual_approved": visual,
        "attribution_approved": True,
        "rights_approved_for_game_embedding": True,
        "notes": "I inspected this demonstration screenshot, credits and rights.",
    })
    return destination


def test_full_flow_snapshots_and_waits_for_human(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path)
    steps = fake_engine(monkeypatch)
    summary, folder = flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")
    assert steps == ["runtime", "gallery"]
    assert summary["status"] == "awaiting_human_review"
    assert summary["source_count"] == 2
    assert summary["publication_approved"] is False
    assert summary["human_review_required"] is True
    assert sorted(item["asset_id"] for item in summary["assets"]) == ["icon-0", "icon-1"]
    assert (folder / "godot" / "forest-test" / "project.godot").exists()
    assert (folder / "gallery" / "forest-test" / "gallery.png").exists()
    assert (folder / "inputs" / "icon-0" / "LICENSE.txt").exists()
    assert flow.inspect_asset_flow(folder)["review_status"] == "not_submitted"


def test_review_flow_does_not_publish(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path)
    fake_engine(monkeypatch)
    _, folder = flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")
    approved = review_document(folder, tmp_path / "review.json")
    result, evidence = flow.review_asset_flow(folder, review_path=approved)
    assert result["status"] == "human_release_review_passed"
    assert result["publication_approved"] is False
    assert evidence.is_file()
    assert flow.inspect_asset_flow(folder)["review_status"] == "human_release_review_passed"


def test_negative_human_review_remains_blocked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path)
    fake_engine(monkeypatch)
    _, folder = flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")
    attestation = review_document(folder, tmp_path / "review.json", visual=False)
    result, _ = flow.review_asset_flow(folder, review_path=attestation)
    assert result["status"] == "human_review_required"


def test_gate_blocks_unreviewed_before_godot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path, reviewed=False)
    steps = fake_engine(monkeypatch)
    with pytest.raises(ValueError, match="License intake blocked"):
        flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")
    assert not steps
    assert not (tmp_path / "runs" / "forest-test").exists()
    assert not (tmp_path / "runs" / ".forest-test.tmp").exists()


def test_runtime_fail_closed_before_gallery(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path)
    steps = fake_engine(monkeypatch, runtime_fail=True)
    with pytest.raises(ValueError, match="Godot resource QA failed"):
        flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")
    assert steps == ["runtime"]


def test_no_silent_overwrite_and_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path)
    fake_engine(monkeypatch)
    flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")
    with pytest.raises(FileExistsError, match="already exists"):
        flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")
    summary, _ = flow.run_asset_flow(
        recipe, godot_bin="godot", workspace=tmp_path / "runs", force=True
    )
    assert summary["status"] == "awaiting_human_review"


def test_review_rejects_edited_gallery_and_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path)
    fake_engine(monkeypatch)
    _, folder = flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")
    review = review_document(folder, tmp_path / "review.json")
    with (folder / "gallery" / "forest-test" / "gallery.png").open("ab") as out:
        out.write(b"tampered")
    with pytest.raises(ValueError, match="Gallery image has changed"):
        flow.review_asset_flow(folder, review_path=review)


def test_reject_duplicate_asset_identity(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path)
    data = yaml.safe_load(recipe.read_text(encoding="utf-8"))
    data["submissions"].append(data["submissions"][0])
    recipe.write_text(yaml.safe_dump(data), encoding="utf-8")
    fake_engine(monkeypatch)
    with pytest.raises(ValueError, match="Duplicate input submission"):
        flow.run_asset_flow(recipe, godot_bin="godot", workspace=tmp_path / "runs")


def test_cli_flow_run_inspect_review(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipe = source_recipe(tmp_path)
    fake_engine(monkeypatch)
    runs = tmp_path / "runs"
    run = runner.invoke(app, [
        "asset-godot", "flow", "run", str(recipe),
        "--godot-bin", "godot", "--workspace", str(runs),
    ])
    assert run.exit_code == 0, run.output
    assert "awaiting_human_review" in run.output
    folder = runs / "forest-test"
    inspect = runner.invoke(app, ["asset-godot", "flow", "inspect", str(folder)])
    assert inspect.exit_code == 0, inspect.output
    assert "not_submitted" in inspect.output
    review = review_document(folder, tmp_path / "review.json")
    result = runner.invoke(app, [
        "asset-godot", "flow", "review", str(folder), "--review", str(review)
    ])
    assert result.exit_code == 0, result.output
    assert "human_release_review_passed" in result.output
    assert "Publication approved: NO" in result.output
