from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
import yaml

from mado_asset_foundry.threejs_studio import compile_worldplan, verify_studio_export


def plan(tmp_path: Path, **changes: object) -> Path:
    raw = {
        "plan_id": "smoke", "name": "Smoke Town",
        "placements": [{"id": "tree-1", "kind": "tree", "asset_hint": "tree",
                        "x": 1, "z": -2, "rotation": 0.5}],
    }
    raw.update(changes)
    path = tmp_path / "plan.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return path


def exported(tmp_path: Path, run: Path, *, glb_length_corrupt: bool = False) -> tuple[Path, Path]:
    wp = json.loads((run / "worldplan.json").read_text())
    map_file = tmp_path / "map.mapproj.json"
    p = wp["placements"][0]
    map_file.write_text(json.dumps({
        "format": "mapproj", "version": 1,
        "placements": [{"id": p["id"], "x": p["x"], "z": p["z"],
                        "ry": p["rotation"], "assetRef": {"source": "site", "slug": "tree"}}],
    }), encoding="utf-8")
    glb = tmp_path / "map.glb"
    chunk = b"{}  "
    glb.write_bytes(struct.pack("<4sII", b"glTF", 2, 999 if glb_length_corrupt else 24)
                    + struct.pack("<I4s", len(chunk), b"JSON") + chunk)
    return map_file, glb


def ledger(tmp_path: Path, *, reviewed: bool = True) -> Path:
    (tmp_path / "LICENSE.txt").write_text("Synthetic license evidence fixture", encoding="utf-8")
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps({"assets": [{
        "slug": "tree", "asset_url": "https://threejsassets.com/assets/tree",
        "license_label": "free-commercial", "evidence_file": "LICENSE.txt",
        "reviewed_by_human": reviewed, "game_embedding_allowed": True,
        "standalone_redistribution_allowed": False,
    }]}), encoding="utf-8")
    return path


def test_compiler_deterministic_and_no_remote_or_license_promotion(tmp_path: Path):
    src = plan(tmp_path)
    data, run = compile_worldplan(src, output_root=tmp_path / "runs")
    wp = json.loads((run / "worldplan.json").read_text())
    assert wp["schemaVersion"] == 1
    assert wp["placements"][0]["rotation"] == .5
    assert data["candidate_count"] == 0
    assert data["network_accessed"] is False
    assert data["license_approved"] is False
    assert data["publication_approved"] is False
    with pytest.raises(FileExistsError):
        compile_worldplan(src, output_root=tmp_path / "runs")


def test_exact_candidate_coverage_is_not_actual_entitlement(tmp_path: Path):
    catalog = tmp_path / "catalog.json"
    catalog.write_text(json.dumps({"assets": [{
        "slug": "tree", "name": "A tree", "category": "nature",
        "tier": "free", "entitled": True,
    }]}), encoding="utf-8")
    data, _ = compile_worldplan(plan(tmp_path), catalog_path=catalog,
                                output_root=tmp_path / "runs")
    assert data["candidate_count"] == 1
    assert data["studio_seed_verified"] is False


def test_reject_duplicate_ids_and_nonfinite(tmp_path: Path):
    with pytest.raises(ValueError, match="Duplicate id"):
        compile_worldplan(plan(tmp_path, placements=[
            {"id": "same", "kind": "tree", "asset_hint": "tree", "x": 0, "z": 0},
            {"id": "same", "kind": "tree", "asset_hint": "tree", "x": 2, "z": 2},
        ]), output_root=tmp_path / "runs")
    with pytest.raises(ValueError):
        compile_worldplan(plan(tmp_path, placements=[
            {"id": "x", "kind": "tree", "asset_hint": "tree", "x": float("nan"), "z": 0},
        ]), output_root=tmp_path / "runs")


def test_export_review_gates_and_hashes(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run)
    result, path = verify_studio_export(run, map_data=map_file, glb=glb, license_ledger=ledger(tmp_path))
    assert path.is_file()
    assert result["status"] == "awaiting_godot_runtime_and_visual_qa"
    assert result["structural_match"] is True
    assert result["godot_runtime_verified"] is False
    assert result["publication_approved"] is False
    with pytest.raises(FileExistsError):
        verify_studio_export(run, map_data=map_file, glb=glb)


def test_export_missing_ledger_stays_blocked(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run)
    result, _ = verify_studio_export(run, map_data=map_file, glb=glb)
    assert result["status"] == "blocked_for_review"


def test_export_rejects_tampered_worldplan(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run)
    (run / "worldplan.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="changed"):
        verify_studio_export(run, map_data=map_file, glb=glb)


def test_export_rejects_invalid_glb(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run, glb_length_corrupt=True)
    with pytest.raises(ValueError, match="GLB"):
        verify_studio_export(run, map_data=map_file, glb=glb)


def test_export_rejects_url_spoofing_and_evidence_escape(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run)
    lic = ledger(tmp_path)
    data = json.loads(lic.read_text())
    data["assets"][0]["asset_url"] = "https://threejsassets.com.bad.invalid/a"
    lic.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        verify_studio_export(run, map_data=map_file, glb=glb, license_ledger=lic)
    data["assets"][0]["asset_url"] = "https://threejsassets.com/assets/tree"
    data["assets"][0]["evidence_file"] = "../outside.txt"
    lic.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="within"):
        verify_studio_export(run, map_data=map_file, glb=glb, license_ledger=lic)


def test_unreviewed_ledger_blocks_export(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run)
    result, _ = verify_studio_export(
        run, map_data=map_file, glb=glb, license_ledger=ledger(tmp_path, reviewed=False)
    )
    assert result["status"] == "blocked_for_review"


def test_skipped_placement_blocks_export(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run)
    json_data = json.loads(map_file.read_text())
    json_data["placements"] = []
    map_file.write_text(json.dumps(json_data), encoding="utf-8")
    result, _ = verify_studio_export(
        run, map_data=map_file, glb=glb, license_ledger=ledger(tmp_path)
    )
    assert result["missing_ids"] == ["tree-1"]
    assert result["status"] == "blocked_for_review"


def test_local_asset_references_do_not_inherit_site_rights(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run)
    doc = json.loads(map_file.read_text())
    doc["placements"][0]["assetRef"] = {"source": "local", "projectId": "my-own"}
    map_file.write_text(json.dumps(doc), encoding="utf-8")
    result, _ = verify_studio_export(
        run, map_data=map_file, glb=glb, license_ledger=ledger(tmp_path)
    )
    assert result["local_assets_requiring_separate_rights_review"] == ["tree-1"]
    assert result["status"] == "blocked_for_review"


def test_symlinked_license_evidence_blocked(tmp_path: Path):
    _, run = compile_worldplan(plan(tmp_path), output_root=tmp_path / "runs")
    map_file, glb = exported(tmp_path, run)
    lic = ledger(tmp_path)
    try:
        (tmp_path / "shortcut.txt").symlink_to(tmp_path / "LICENSE.txt")
    except (NotImplementedError, OSError):
        pytest.skip("Symlink unavailable")
    data = json.loads(lic.read_text())
    data["assets"][0]["evidence_file"] = "shortcut.txt"
    lic.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="Symlink"):
        verify_studio_export(run, map_data=map_file, glb=glb, license_ledger=lic)


def test_authenticated_api_snapshot_without_downloads(tmp_path: Path):
    api = tmp_path / "api.json"
    api.write_text(json.dumps({
        "data": [{"slug": "tree", "name": "Test tree", "category": "nature",
                  "tier": "free", "entitled": True,
                  "preview_url": "https://example.invalid/preview.glb",
                  "download_url": "https://example.invalid/download.glb"}],
        "pagination": {"limit": 100, "offset": 0, "total": 1, "has_more": False},
    }), encoding="utf-8")
    result, folder = compile_worldplan(
        plan(tmp_path), catalog_path=api, output_root=tmp_path / "runs")
    assert result["candidate_count"] == 1
    assert result["catalog_source_type"] == "authenticated_api_snapshot_unverified"
    assert "download_url" not in (folder / "report.json").read_text()


def test_incomplete_or_public_catalog_rejected(tmp_path: Path):
    api = tmp_path / "api.json"
    page = {"data": [{"slug": "tree", "name": "Tree", "category": "nature",
                      "tier": "free", "entitled": True}],
            "pagination": {"offset": 0, "total": 2, "has_more": True}}
    api.write_text(json.dumps(page), encoding="utf-8")
    with pytest.raises(ValueError, match="Incomplete"):
        compile_worldplan(plan(tmp_path), catalog_path=api, output_root=tmp_path / "runs")
    page["pagination"] = {"offset": 0, "total": 1, "has_more": False}
    del page["data"][0]["entitled"]
    api.write_text(json.dumps(page), encoding="utf-8")
    with pytest.raises(ValueError, match="authenticated"):
        compile_worldplan(plan(tmp_path), catalog_path=api, output_root=tmp_path / "runs")
