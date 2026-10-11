"""Offline and mocked acceptance for MAF-M1.3.1 GLB/PBR/Godot bridge."""
from __future__ import annotations

import hashlib
import json
import struct
import subprocess
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from mado_asset_foundry.cli import app
from mado_asset_foundry.glb_godot_qa import (
    inspect_pbr, inspect_probe, validate_probe, verify_glb_godot,
)


def synthetic_glb() -> bytes:
    """Create an original, self-contained indexed triangle in GLB 2.0."""
    xyz = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    triangle = struct.pack("<3H", 0, 1, 2)
    binary = xyz + triangle + b"\x00\x00"
    document = {
        "asset": {"version": "2.0"},
        "scene": 0, "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "MAF Synthetic Triangle"}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(xyz), "target": 34962},
            {"buffer": 0, "byteOffset": len(xyz), "byteLength": len(triangle), "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3,
             "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
        "materials": [{
            "name": "Original MAF Metal Test",
            "pbrMetallicRoughness": {"baseColorFactor": [0.8, 0.5, 0.2, 1],
                                     "metallicFactor": 0.35, "roughnessFactor": 0.7},
            "doubleSided": True,
        }],
        "meshes": [{"primitives": [{
            "attributes": {"POSITION": 0}, "indices": 1, "material": 0, "mode": 4,
        }]}],
    }
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((-len(payload)) % 4)
    total = 12 + 8 + len(payload) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<I4s", len(payload), b"JSON") + payload
            + struct.pack("<I4s", len(binary), b"BIN\x00") + binary)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def probe_fixture(root: Path) -> Path:
    root.mkdir()
    inputs = root / "inputs"
    inputs.mkdir()
    source = inputs / "source.png"
    Image.new("RGB", (16, 16), (40, 80, 120)).save(source)
    workflow = inputs / "workflow-api.json"
    workflow.write_text('{"1":{"class_type":"Trellis2ShapeStage","inputs":{}}}')
    submitted = inputs / "submitted-prompt.json"
    submitted.write_text('{"2":{"class_type":"SaveGLB","inputs":{}}}')
    glb = synthetic_glb()
    (root / "asset.glb").write_bytes(glb)
    report = {
        "schema_version": "1.3", "status": "awaiting_3d_qa",
        "structural_glb_valid": True, "asset_paths": ["asset.glb"],
        "glb_sha256": _sha(glb),
        "input_sha256": _sha(source.read_bytes()),
        "workflow_sha256": _sha(workflow.read_bytes()),
        "submitted_prompt_sha256": _sha(submitted.read_bytes()),
        "publication_approved": False, "license_review_required": True,
        "runtime_qa_passed": False, "visual_qa_passed": False,
    }
    (root / "evidence.json").write_text(json.dumps(report), encoding="utf-8")
    return root


def good_runtime() -> dict:
    return {
        "status": "passed", "mesh_instances": 1, "surfaces": 1, "vertices": 3,
        "materials": [{
            "type": "StandardMaterial3D", "metallic": 0.35, "roughness": 0.7,
            "albedo_texture": False, "normal_texture": False,
        }],
        "errors": [],
    }


def test_pbr_baseline_and_manual_gate() -> None:
    result = inspect_pbr(synthetic_glb())
    assert result["mesh_count"] == 1
    assert result["surface_count"] == 1
    assert result["vertex_count"] == 3
    assert result["materials"][0]["metallic"] == pytest.approx(0.35)
    assert "material_0:normal_texture_missing" in result["warnings"]
    assert result["aesthetic_quality_verified"] is False
    with pytest.raises(ValueError, match="Strict PBR"):
        inspect_pbr(synthetic_glb(), require_textures=True)


def test_rejects_broken_glb_chunks() -> None:
    intact = synthetic_glb()
    with pytest.raises(ValueError, match="size|header"):
        inspect_pbr(intact[:-1])
    missing_bin = intact[:-4]
    missing_bin = missing_bin[:8] + struct.pack("<I", len(missing_bin)) + missing_bin[12:]
    with pytest.raises(ValueError, match="BIN"):
        inspect_pbr(missing_bin)


def test_rejects_untrusted_probe_states(tmp_path: Path) -> None:
    root = probe_fixture(tmp_path / "comfy3d-probe")
    data = json.loads((root / "evidence.json").read_text())
    data["status"] = "failed"
    (root / "evidence.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="awaiting_3d_qa"):
        validate_probe(root)
    data["status"] = "awaiting_3d_qa"
    data["publication_approved"] = True
    (root / "evidence.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="awaiting_3d_qa"):
        validate_probe(root)


@pytest.mark.parametrize("changed", [
    "asset.glb", "inputs/source.png",
    "inputs/workflow-api.json", "inputs/submitted-prompt.json",
])
def test_rejects_mutated_source_or_evidence(tmp_path: Path, changed: str) -> None:
    root = probe_fixture(tmp_path / "comfy3d-probe")
    with (root / changed).open("ab") as file:
        file.write(b"tamper")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        inspect_probe(root)


def test_symlinked_glb_rejected(tmp_path: Path) -> None:
    root = probe_fixture(tmp_path / "comfy3d-probe")
    file = root / "asset.glb"
    other = tmp_path / "outside.glb"
    other.write_bytes(file.read_bytes())
    file.unlink()
    file.symlink_to(other)
    with pytest.raises(ValueError, match="symlinked"):
        validate_probe(root)


def test_plan_cli_never_launches_godot(tmp_path: Path) -> None:
    root = probe_fixture(tmp_path / "comfy3d-probe")
    result = CliRunner().invoke(app, ["comfy3d", "glb-inspect", str(root)])
    assert result.exit_code == 0, result.output
    assert '"godot_executed": false' in result.output
    assert '"publication_approved": false' in result.output


def test_fake_engine_success_not_release_approval(tmp_path: Path) -> None:
    root = probe_fixture(tmp_path / "comfy3d-probe")
    commands = []

    def fake(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        commands.append(args)
        assert (cwd / "verify_glb.gd").is_file()
        assert (cwd / "asset.glb").read_bytes() == synthetic_glb()
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "4.6.1.stable.official\n", "")
        if "--import" in args:
            return subprocess.CompletedProcess(args, 0, "Imported\n", "")
        output = cwd / "evidence"
        output.mkdir()
        (output / "glb-runtime.json").write_text(json.dumps(good_runtime()))
        return subprocess.CompletedProcess(args, 0, "Verified\n", "")

    report, target = verify_glb_godot(
        root, godot_bin="python", workspace=tmp_path / "qa", runner=fake,
    )
    assert report["status"] == "awaiting_visual_review"
    assert report["godot_executed"] is True
    assert report["visual_review_passed"] is False
    assert report["publication_approved"] is False
    assert report["license_review_required"] is True
    assert report["godot_runtime"]["mesh_instances"] == 1
    assert len(commands) == 3
    assert (target / "report.json").is_file()
    assert (target / "verify.stdout.txt").is_file()
    with pytest.raises(FileExistsError, match="already exists"):
        verify_glb_godot(root, godot_bin="python", workspace=tmp_path / "qa", runner=fake)


def test_fake_engine_cannot_pass_without_runtime_report(tmp_path: Path) -> None:
    root = probe_fixture(tmp_path / "comfy3d-probe")

    def fake(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args, 0, "4.6.1\n" if "--version" in args else "ok\n", "",
        )

    report, target = verify_glb_godot(
        root, godot_bin="python", workspace=tmp_path / "qa", runner=fake,
    )
    assert report["status"] == "failed"
    assert "resource or mesh/material" in report["failure"]
    assert (target / "report.json").is_file()


def test_godot_qa_refuses_corrupt_probe_before_engine(tmp_path: Path) -> None:
    root = probe_fixture(tmp_path / "comfy3d-probe")
    (root / "asset.glb").write_bytes(b"tampered")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        verify_glb_godot(root, godot_bin="python", workspace=tmp_path / "qa")
    assert not (tmp_path / "qa").exists()



def mutate_glb(document_mutator) -> bytes:
    original = synthetic_glb()
    document_size = struct.unpack_from("<I", original, 12)[0]
    document = json.loads(original[20:20 + document_size])
    document_mutator(document)
    binary = original[28 + document_size:]
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((-len(payload)) % 4)
    total = 12 + 8 + len(payload) + 8 + len(binary)
    return (struct.pack("<4sII", b"glTF", 2, total)
            + struct.pack("<I4s", len(payload), b"JSON") + payload
            + struct.pack("<I4s", len(binary), b"BIN\x00") + binary)


def test_rejects_out_of_bound_accessor_bytes() -> None:
    broken = mutate_glb(lambda doc: doc["bufferViews"][0].update(byteLength=4))
    with pytest.raises(ValueError, match="extends beyond"):
        inspect_pbr(broken)


def test_rejects_out_of_range_roughness_factor() -> None:
    broken = mutate_glb(
        lambda doc: doc["materials"][0]["pbrMetallicRoughness"].update(roughnessFactor=1.5)
    )
    with pytest.raises(ValueError, match="roughnessFactor"):
        inspect_pbr(broken)


def test_rejects_external_binary_and_images() -> None:
    binary_uri = mutate_glb(lambda doc: doc["buffers"][0].update(uri="https://example.com/mesh.bin"))
    with pytest.raises(ValueError, match="embedded GLB buffer"):
        inspect_pbr(binary_uri)
    image_uri = mutate_glb(
        lambda doc: doc.update(images=[{"uri": "https://example.com/texture.png"}])
    )
    with pytest.raises(ValueError, match="external"):
        inspect_pbr(image_uri)


def test_engine_report_without_material_data_fails(tmp_path: Path) -> None:
    root = probe_fixture(tmp_path / "comfy3d-probe")

    def fake(args: list[str], cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "4.6.1\n", "")
        if "--script" in args:
            runtime = good_runtime()
            runtime["materials"][0]["type"] = "none"
            evidence = cwd / "evidence"
            evidence.mkdir()
            (evidence / "glb-runtime.json").write_text(json.dumps(runtime))
        return subprocess.CompletedProcess(args, 0, "", "")

    report, output = verify_glb_godot(
        root, godot_bin="python", workspace=tmp_path / "qa", runner=fake
    )
    assert report["status"] == "failed"
    assert "mesh/material verification failed" in report["failure"]
    assert (output / "report.json").is_file()
