"""Real end-to-end MAF-M0.9 dogfood using original synthetic PNG fixtures."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw

from mado_asset_foundry.asset_flow import inspect_asset_flow, run_asset_flow
from mado_asset_foundry.io import write_json
from mado_asset_foundry.visual_gallery import review_release


@pytest.mark.skipif(
    shutil.which("godot") is None or shutil.which("xvfb-run") is None,
    reason="Godot 4 and Xvfb are required for actual graphical dogfood",
)
def test_real_asset_flow_two_icons_and_review_gate(tmp_path: Path) -> None:
    inputs = tmp_path / "inputs"
    ids = ("ember", "moss")
    manifests: list[str] = []
    for index, asset_id in enumerate(ids):
        folder = inputs / asset_id
        folder.mkdir(parents=True)
        image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        if index == 0:
            draw.ellipse((8, 8, 56, 56), fill=(244, 125, 61, 255))
        else:
            draw.polygon([(32, 5), (58, 52), (6, 52)], fill=(76, 204, 141, 255))
        image.save(folder / "icon.png")
        (folder / "LICENSE.txt").write_text(
            "Synthetic MADO-created fixture, CC0-1.0 dedication", encoding="utf-8"
        )
        (folder / "submission.yaml").write_text(yaml.safe_dump({
            "schema_version": "0.1",
            "asset_id": asset_id,
            "source_id": "local",
            "title": f"Original {asset_id} test icon",
            "creator": "MADO test harness",
            "local_file": "icon.png",
            "license_spdx": "CC0-1.0",
            "license_evidence_file": "LICENSE.txt",
            "reviewed_by_human": True,
            "use_case": "game_embedding",
        }), encoding="utf-8")
        manifests.append(f"inputs/{asset_id}/submission.yaml")
    recipe = tmp_path / "flow.yaml"
    recipe.write_text(yaml.safe_dump({
        "schema_version": "0.1",
        "flow_id": "mado-two-icon-dogfood",
        "submissions": manifests,
    }), encoding="utf-8")

    result, folder = run_asset_flow(
        recipe,
        godot_bin="godot",
        workspace=tmp_path / "runs",
        virtual_display=True,
        timeout=120,
    )
    assert result["status"] == "awaiting_human_review"
    assert result["source_count"] == 2
    assert result["godot_runtime"] == "passed"
    assert result["visual_gallery"] == "captured"
    assert result["publication_approved"] is False
    assert inspect_asset_flow(folder)["review_status"] == "not_submitted"
    gallery_dir = folder / result["output_paths"]["gallery"]
    with Image.open(gallery_dir / "gallery.png") as screenshot:
        assert screenshot.format == "PNG"
        assert screenshot.size == (960, 540)
    release, _ = review_release(
        folder / "plan.json", folder / "godot" / result["flow_id"],
        gallery_dir,
    )
    assert release["status"] == "human_review_required"
    assert release["publication_approved"] is False

    # Only synthetic original assets are copied to the CI artifact.
    published_artifact = Path("runs/ci-asset-flow")
    published_artifact.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(gallery_dir / "gallery.png", published_artifact / "gallery.png")
    shutil.copyfile(gallery_dir / "CREDITS.md", published_artifact / "CREDITS.md")
    shutil.copyfile(folder / "summary.json", published_artifact / "summary.json")
    write_json(published_artifact / "test-evidence.json", {
        "schema_version": "0.1",
        "status": "passed",
        "asset_count": 2,
        "engine_version": result["godot_version"],
        "human_review_required": True,
        "publication_approved": False,
    })
