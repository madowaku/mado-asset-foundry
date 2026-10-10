"""Offline contracts for MAF-M1.3. No ComfyUI service or model download needed."""
from __future__ import annotations

import json
import struct
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from mado_asset_foundry.cli import app
from mado_asset_foundry.comfy3d import (
    Comfy3DClient, inspect_glb, load_api_graph, plan_comfy3d, run_comfy3d,
)


def source_image(path: Path) -> Path:
    Image.new("RGBA", (32, 32), (100, 200, 80, 255)).save(path)
    return path


def api_graph(path: Path) -> Path:
    path.write_text(json.dumps({
        "4": {"class_type": "LoadImage", "inputs": {"image": "example.png"}},
        "5": {"class_type": "Trellis2ShapeStage", "inputs": {"voxel": ["4", 0]}},
        "6": {"class_type": "SaveGLB", "inputs": {
            "mesh": ["5", 0], "filename_prefix": "3d/original",
        }},
    }), encoding="utf-8")
    return path


def sample_glb() -> bytes:
    manifest = json.dumps({
        "asset": {"version": "2.0"},
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
        "materials": [{"name": "sample"}],
    }, separators=(",", ":")).encode("utf-8")
    manifest += b" " * ((-len(manifest)) % 4)
    return struct.pack("<4sII", b"glTF", 2, len(manifest) + 20) + (
        struct.pack("<I4s", len(manifest), b"JSON") + manifest
    )


class MockComfy(Comfy3DClient):
    def __init__(self, *, broken: str | None = None) -> None:
        super().__init__()
        self.sent: dict | None = None
        self.broken = broken
        self.calls: list[tuple[str, str]] = []

    def _request(self, method: str, path: str, *,
                 payload: bytes | None = None, content_type: str | None = None,
                 limit: int = 8 * 1024 * 1024) -> bytes:
        self.calls.append((method, path.split("?")[0]))
        if path == "/upload/image":
            assert content_type and "multipart/form-data" in content_type
            assert b"Content-Disposition" in (payload or b"")
            return json.dumps({"name": "maf-upload.png", "type": "input", "subfolder": ""}).encode()
        if path == "/prompt":
            self.sent = json.loads(payload or b"{}")["prompt"]
            return json.dumps({"prompt_id": "known-prompt"}).encode()
        if path == "/history/known-prompt":
            if self.broken == "execution":
                return json.dumps({"known-prompt": {
                    "status": {"status_str": "error", "completed": False},
                }}).encode()
            filename = "../escape.glb" if self.broken == "traversal" else "asset_00001_.glb"
            return json.dumps({"known-prompt": {
                "status": {"status_str": "success", "completed": True},
                "outputs": {"6": {"3d": [{
                    "filename": filename, "subfolder": "maf3d", "type": "output",
                }]}},
            }}).encode()
        if path.startswith("/view?"):
            return sample_glb()
        raise AssertionError(f"Unexpected network call: {method} {path}")


def test_plan_offline_no_service(tmp_path: Path) -> None:
    png = source_image(tmp_path / "in.png")
    graph = api_graph(tmp_path / "api.json")
    plan = plan_comfy3d(png, graph)
    assert plan["model_family"] == "trellis2"
    assert plan["image_node"] == "4"
    assert plan["save_node"] == "6"
    assert plan["execution"] == "not_started"
    assert not plan["publication_approved"]
    assert len(plan["workflow_sha256"]) == 64


def test_ui_workflow_is_rejected(tmp_path: Path) -> None:
    file = tmp_path / "visual.json"
    file.write_text('{"nodes": [], "links": []}', encoding="utf-8")
    with pytest.raises(ValueError, match="Export Workflow"):
        load_api_graph(file)


def test_rejects_non_native_and_unconnected_mesh(tmp_path: Path) -> None:
    file = api_graph(tmp_path / "api.json")
    obj = json.loads(file.read_text())
    obj["5"]["class_type"] = "UntrustedCustomModel"
    file.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="native"):
        load_api_graph(file)
    obj["5"]["class_type"] = "Trellis2ShapeStage"
    obj["6"]["inputs"]["mesh"] = "not-linked"
    file.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="connected mesh"):
        load_api_graph(file)


def test_explicit_node_selection_when_ambiguous(tmp_path: Path) -> None:
    file = api_graph(tmp_path / "api.json")
    obj = json.loads(file.read_text())
    obj["9"] = {"class_type": "LoadImage", "inputs": {"image": "another.png"}}
    file.write_text(json.dumps(obj))
    with pytest.raises(ValueError, match="--image-node"):
        load_api_graph(file)
    _, report = load_api_graph(file, image_node="4")
    assert report["image_node"] == "4"


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:8188", "http://example.com:8188",
    "http://127.0.0.1:8188/path", "http://127.0.0.1:8188?token=x",
    "http://127.0.0.1", "http://admin:pass@127.0.0.1:8188",
])
def test_client_refuses_non_loopback_or_modified_urls(url: str) -> None:
    with pytest.raises(ValueError, match="loopback|localhost"):
        Comfy3DClient(url)


def test_probe_collects_glb_and_keeps_review_fence(tmp_path: Path) -> None:
    png = source_image(tmp_path / "in.png")
    graph = api_graph(tmp_path / "api.json")
    client = MockComfy()
    evidence, folder = run_comfy3d(png, graph, output_dir=tmp_path / "run", client=client)
    assert evidence["status"] == "awaiting_3d_qa"
    assert evidence["structural_glb_valid"] is True
    assert evidence["runtime_qa_passed"] is False
    assert evidence["visual_qa_passed"] is False
    assert evidence["publication_approved"] is False
    assert evidence["license_review_required"] is True
    assert evidence["glb_structure"]["mesh_count"] == 1
    assert (folder / "asset.glb").read_bytes() == sample_glb()
    assert (folder / "evidence.json").is_file()
    assert (folder / "inputs" / "submitted-prompt.json").is_file()
    assert client.sent is not None
    assert client.sent["4"]["inputs"]["image"] == "maf-upload.png"
    assert client.sent["6"]["inputs"]["filename_prefix"].startswith("maf3d/maf-")
    assert [item[1] for item in client.calls] == [
        "/upload/image", "/prompt", "/history/known-prompt", "/view",
    ]
    with pytest.raises(FileExistsError, match="already exists"):
        run_comfy3d(png, graph, output_dir=folder, client=client)


@pytest.mark.parametrize("error", ["execution", "traversal"])
def test_failure_preserves_evidence(tmp_path: Path, error: str) -> None:
    png = source_image(tmp_path / "in.png")
    graph = api_graph(tmp_path / "api.json")
    report, folder = run_comfy3d(
        png, graph, output_dir=tmp_path / "run", client=MockComfy(broken=error)
    )
    assert report["status"] == "failed"
    assert report["prompt_id"] == "known-prompt"
    assert report["asset_paths"] == []
    assert not (folder / "asset.glb").exists()
    persisted = json.loads((folder / "evidence.json").read_text())
    assert persisted["failure"]


def test_malformed_glb_rejected() -> None:
    valid = sample_glb()
    assert inspect_glb(valid)["material_count"] == 1
    with pytest.raises(ValueError, match="header|size"):
        inspect_glb(valid[:-3])
    with pytest.raises(ValueError, match="header|size"):
        inspect_glb(b"NOPE" + valid[4:])


def test_cli_requires_explicit_live(tmp_path: Path) -> None:
    png = source_image(tmp_path / "in.png")
    graph = api_graph(tmp_path / "api.json")
    cli = CliRunner()
    preview = cli.invoke(app, ["comfy3d", "plan", str(png), "--workflow", str(graph)])
    assert preview.exit_code == 0, preview.output
    assert '"execution": "not_started"' in preview.output
    dry = cli.invoke(app, ["comfy3d", "probe", str(png), "--workflow", str(graph)])
    assert dry.exit_code == 1
    assert "--live" in dry.output
    assert not (tmp_path / "run").exists()
