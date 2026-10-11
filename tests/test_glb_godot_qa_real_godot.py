"""Real Godot GLB import smoke; skipped if Godot was not installed explicitly."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from mado_asset_foundry.glb_godot_qa import verify_glb_godot
from test_glb_godot_qa import probe_fixture


@pytest.mark.skipif(shutil.which("godot") is None, reason="Godot binary not on PATH")
def test_real_godot_glb_mesh_and_material_import(tmp_path: Path) -> None:
    probe = probe_fixture(tmp_path / "comfy3d-test")
    report, output = verify_glb_godot(
        probe, godot_bin="godot", workspace=tmp_path / "qa",
        timeout=180,
    )
    detail = "\n".join(
        (output / filename).read_text(encoding="utf-8", errors="replace")
        if (output / filename).exists() else ""
        for filename in ("import.stdout.txt", "import.stderr.txt",
                         "verify.stdout.txt", "verify.stderr.txt")
    )
    assert report["status"] == "awaiting_visual_review", (
        f"{report['failure']}\n{detail}"
    )
    assert report["godot_version"].startswith("4.")
    assert report["godot_runtime"]["surfaces"] >= 1
    assert report["godot_runtime"]["vertices"] >= 3
    assert report["godot_runtime"]["materials"][0]["type"] != "none"
    assert report["publication_approved"] is False
