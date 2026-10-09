"""Real Godot graphical preview smoke via a virtual X11 display."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image

from mado_asset_foundry.asset_sources import intake_asset
from mado_asset_foundry.attribution_bridge import compile_godot_import
from mado_asset_foundry.visual_gallery import render_gallery, review_release
from mado_asset_foundry.io import write_json


@pytest.mark.skipif(
    shutil.which("godot") is None or shutil.which("xvfb-run") is None,
    reason="Requires Godot and Xvfb for a real visual render",
)
def test_real_godot_gallery_screenshot(tmp_path: Path) -> None:
    inp = tmp_path / "inputs"
    inp.mkdir()
    Image.new("RGBA", (32, 32), (240, 120, 60, 255)).save(inp / "icon.png")
    (inp / "LICENSE.txt").write_text("Original synthetic MAF fixture, CC0-1.0", encoding="utf-8")
    (inp / "submission.yaml").write_text(yaml.safe_dump({
        "asset_id": "godot-preview", "source_id": "local",
        "title": "Godot rendered preview", "creator": "MAF",
        "local_file": "icon.png", "license_spdx": "CC0-1.0",
        "license_evidence_file": "LICENSE.txt",
        "reviewed_by_human": True, "use_case": "game_embedding",
    }), encoding="utf-8")
    intake_asset(inp / "submission.yaml", output_root=tmp_path / "reports")
    plan = tmp_path / "plan.json"
    write_json(plan, {
        "project_id": "gallery-live",
        "assets": [{"submission": "inputs/submission.yaml", "report": "reports/godot-preview/report.json"}],
    })
    _, project = compile_godot_import(plan, output_root=tmp_path / "projects")
    result, evidence = render_gallery(
        plan, project, godot_bin="godot", virtual_display=True,
        output_root=tmp_path / "gallery", timeout=120,
    )
    assert result["status"] == "captured", (
        f"{result['failure_reason']}\n"
        f"{(evidence / 'gallery.stderr.txt').read_text(encoding='utf-8')}"
    )
    assert result["screenshot_dimensions"] == [960, 540]
    assert result["preview_variation"] > 4
    review, _ = review_release(plan, project, evidence)
    assert review["status"] == "human_review_required"
