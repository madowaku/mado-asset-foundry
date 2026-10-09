from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from PIL import Image
from typer.testing import CliRunner

from mado_asset_foundry.asset_sources import intake_asset
from mado_asset_foundry.attribution_bridge import compile_godot_import
from mado_asset_foundry.cli import app

runner = CliRunner()


def prepared(tmp_path: Path, **overrides: object) -> tuple[Path, Path, Path]:
    source_dir = tmp_path / "input"
    source_dir.mkdir(exist_ok=True)
    image = source_dir / "icon.png"
    Image.new("RGBA", (8, 8), (0, 50, 100, 255)).save(image)
    (source_dir / "LICENSE.txt").write_text("test fixture: CC0", encoding="utf-8")
    data: dict = {
        "asset_id": "test-icon", "source_id": "local", "title": "Test Icon",
        "creator": "Tester", "local_file": "icon.png",
        "license_spdx": "CC0-1.0", "license_evidence_file": "LICENSE.txt",
        "reviewed_by_human": True, "use_case": "game_embedding",
    }
    data.update(overrides)
    sub = source_dir / "submission.yaml"
    sub.write_text(yaml.safe_dump(data), encoding="utf-8")
    report, report_path = intake_asset(sub, output_root=tmp_path / "reports")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "project_id": "test-game",
        "assets": [{"submission": "input/submission.yaml", "report": "reports/test-icon/report.json"}],
    }), encoding="utf-8")
    return plan, image, report_path


def test_build_godot_project_and_credits(tmp_path: Path) -> None:
    plan, image, _ = prepared(tmp_path)
    result, output = compile_godot_import(plan, output_root=tmp_path / "out")
    assert result["status"] == "compiled"
    assert result["publication_approved"] is False
    assert (output / "project.godot").exists()
    assert "Tester" in (output / "CREDITS.md").read_text(encoding="utf-8")
    assert (output / "assets" / "test-icon.png").read_bytes() == image.read_bytes()
    assert json.loads((output / "asset_manifest.json").read_text())["asset_count"] == 1


def test_reject_changed_source_hash(tmp_path: Path) -> None:
    plan, image, _ = prepared(tmp_path)
    Image.new("RGBA", (8, 8), (255, 0, 0, 255)).save(image)
    with pytest.raises(ValueError, match="stale"):
        compile_godot_import(plan, output_root=tmp_path / "out")


def test_reject_changed_license_evidence(tmp_path: Path) -> None:
    plan, _, _ = prepared(tmp_path)
    (tmp_path / "input" / "LICENSE.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        compile_godot_import(plan, output_root=tmp_path / "out")


def test_reject_unreviewed_or_nc(tmp_path: Path) -> None:
    plan, _, _ = prepared(tmp_path)
    submission = tmp_path / "input" / "submission.yaml"
    data = yaml.safe_load(submission.read_text())
    data["reviewed_by_human"] = False
    submission.write_text(yaml.safe_dump(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Current license gate"):
        compile_godot_import(plan, output_root=tmp_path / "out")


def test_reject_forced_eligible_status(tmp_path: Path) -> None:
    plan, _, report_path = prepared(tmp_path, license_spdx="Custom License")
    report = json.loads(report_path.read_text())
    report["status"] = "eligible"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="Current license gate"):
        compile_godot_import(plan, output_root=tmp_path / "out")


def test_reject_outside_path(tmp_path: Path) -> None:
    plan, _, _ = prepared(tmp_path)
    data = json.loads(plan.read_text())
    data["assets"][0]["submission"] = "../outside.yaml"
    plan.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        compile_godot_import(plan, output_root=tmp_path / "out")


def test_no_overwrite_and_force(tmp_path: Path) -> None:
    plan, _, _ = prepared(tmp_path)
    compile_godot_import(plan, output_root=tmp_path / "out")
    with pytest.raises(FileExistsError):
        compile_godot_import(plan, output_root=tmp_path / "out")
    report, _ = compile_godot_import(plan, output_root=tmp_path / "out", force=True)
    assert report["asset_count"] == 1


def test_reject_asset_pack_redistribution(tmp_path: Path) -> None:
    plan, _, _ = prepared(tmp_path, use_case="asset_pack_redistribution")
    with pytest.raises(ValueError, match="game embedding"):
        compile_godot_import(plan, output_root=tmp_path / "out")


def test_cli(tmp_path: Path) -> None:
    plan, _, _ = prepared(tmp_path)
    result = runner.invoke(app, ["asset-godot", "compile", str(plan), "--output-root", str(tmp_path / "out")])
    assert result.exit_code == 0, result.output
    assert "Godot executed: NO" in result.output
