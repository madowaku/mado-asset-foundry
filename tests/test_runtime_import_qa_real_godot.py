"""Optional real Godot 4 engine smoke; installed explicitly by CI, never by MAF."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image

from mado_asset_foundry.asset_sources import intake_asset
from mado_asset_foundry.attribution_bridge import compile_godot_import
from mado_asset_foundry.runtime_import_qa import verify_godot_import


@pytest.mark.skipif(shutil.which("godot") is None, reason="Godot binary not on PATH")
def test_real_godot_headless_import_one_png(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.mkdir()
    Image.new("RGBA", (16, 16), (40, 150, 220, 255)).save(source / "icon.png")
    (source / "LICENSE.txt").write_text(
        "Original synthetic MAF fixture dedicated CC0-1.0.", encoding="utf-8"
    )
    (source / "submission.yaml").write_text(yaml.safe_dump({
        "asset_id": "engine-icon", "source_id": "local",
        "title": "Godot Smoke", "creator": "MAF",
        "local_file": "icon.png", "license_spdx": "CC0-1.0",
        "license_evidence_file": "LICENSE.txt",
        "reviewed_by_human": True, "use_case": "game_embedding",
    }), encoding="utf-8")
    intake_asset(source / "submission.yaml", output_root=tmp_path / "reports")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "project_id": "godot-smoke",
        "assets": [{
            "submission": "input/submission.yaml",
            "report": "reports/engine-icon/report.json"
        }],
    }), encoding="utf-8")
    _, project = compile_godot_import(plan, output_root=tmp_path / "projects")
    report, evidence = verify_godot_import(
        plan, project, godot_bin="godot", output_root=tmp_path / "qa"
    )
    assert report["status"] == "passed", (
        f"{report['failure_reason']}\n"
        f"{(evidence / 'import.stderr.txt').read_text(encoding='utf-8') if (evidence / 'import.stderr.txt').exists() else ''}\n"
        f"{(evidence / 'verify.stderr.txt').read_text(encoding='utf-8') if (evidence / 'verify.stderr.txt').exists() else ''}"
    )
    assert report["loaded_count"] == 1
    assert report["godot_executed"] is True
    assert report["godot_version"].startswith("4.")
