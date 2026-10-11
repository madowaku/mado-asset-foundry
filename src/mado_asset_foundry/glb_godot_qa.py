"""MAF-M1.3.1: provenance-gated GLB PBR inspection and real Godot import QA.

Consumes *only* M1.3 ComfyUI probe evidence, never third-party Godot projects
or scripts. Structural/PBR checks are deterministic and do not claim aesthetic,
legal, gameplay or rendering approval.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable

from .comfy3d import MAX_GLB_BYTES, inspect_glb
from .io import write_json
from .runtime_import_qa import _command, _resolve_binary

QA_SCRIPT = r'''extends SceneTree

const MODEL := "res://asset.glb"
const OUTPUT := "res://evidence/glb-runtime.json"

func _initialize() -> void:
    call_deferred("_inspect")

func _inspect() -> void:
    var report: Dictionary = {
        "status": "failed", "mesh_instances": 0, "surfaces": 0,
        "vertices": 0, "materials": [], "errors": []
    }
    var packed: PackedScene = ResourceLoader.load(MODEL) as PackedScene
    if packed == null:
        report["errors"].append("glb_resource_not_packed_scene")
        _finish(report, 1)
        return
    var root: Node = packed.instantiate()
    if root == null or not root is Node3D:
        report["errors"].append("glb_scene_instantiation_failed")
        _finish(report, 1)
        return
    var pending: Array[Node] = [root]
    while not pending.is_empty():
        var current: Node = pending.pop_back()
        if current is MeshInstance3D:
            var instance: MeshInstance3D = current as MeshInstance3D
            var mesh: Mesh = instance.mesh
            if mesh != null:
                report["mesh_instances"] += 1
                for surface in range(mesh.get_surface_count()):
                    var arrays: Array = mesh.surface_get_arrays(surface)
                    var points: PackedVector3Array = arrays[Mesh.ARRAY_VERTEX]
                    if points.is_empty():
                        report["errors"].append("empty_surface_vertices")
                    report["vertices"] += points.size()
                    report["surfaces"] += 1
                    var material: Material = instance.material_override
                    if material == null:
                        material = instance.get_surface_override_material(surface)
                    if material == null:
                        material = mesh.surface_get_material(surface)
                    var entry: Dictionary = {
                        "type": "none", "metallic": null, "roughness": null,
                        "albedo_texture": false, "metallic_texture": false,
                        "roughness_texture": false, "normal_texture": false,
                        "orm_texture": false
                    }
                    if material != null:
                        entry["type"] = material.get_class()
                        if material is BaseMaterial3D:
                            var pbr: BaseMaterial3D = material as BaseMaterial3D
                            entry["metallic"] = pbr.metallic
                            entry["roughness"] = pbr.roughness
                            entry["albedo_texture"] = pbr.albedo_texture != null
                            entry["metallic_texture"] = pbr.metallic_texture != null
                            entry["roughness_texture"] = pbr.roughness_texture != null
                            entry["normal_texture"] = pbr.normal_texture != null
                            entry["orm_texture"] = pbr.orm_texture != null
                    report["materials"].append(entry)
        for child in current.get_children():
            pending.append(child)
    root.free()
    if report["errors"].is_empty() and report["mesh_instances"] > 0 \
            and report["surfaces"] > 0 and report["vertices"] > 0 \
            and report["materials"].size() == report["surfaces"]:
        report["status"] = "passed"
        _finish(report, 0)
    else:
        report["errors"].append("empty_or_invalid_mesh_scene")
        _finish(report, 1)

func _finish(report: Dictionary, code: int) -> void:
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://evidence"))
    var file: FileAccess = FileAccess.open(OUTPUT, FileAccess.WRITE)
    if file == null:
        push_error("cannot_write_glb_runtime_evidence")
        quit(1)
        return
    file.store_string(JSON.stringify(report, "\t"))
    file.close()
    print("MAF_GLB_RUNTIME=" + JSON.stringify(report))
    quit(code)
'''

Runner = Callable[[list[str], Path, int], subprocess.CompletedProcess[str]]
SLUG = re.compile(r"[a-z0-9][a-z0-9-]{0,63}")


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Required regular file missing or symlinked: {path}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    source = _local_file(path)
    if source.stat().st_size > 8 * 1024 * 1024:
        raise ValueError("Evidence JSON exceeds 8 MiB")
    try:
        result = json.loads(source.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError(f"Invalid JSON evidence: {source}") from exc
    if not isinstance(result, dict):
        raise ValueError(f"Evidence must be a JSON object: {source}")
    return result


def _digest_matches(path: Path, expected: object, label: str) -> str:
    if not isinstance(expected, str) or not re.fullmatch("[0-9a-f]{64}", expected):
        raise ValueError(f"{label} has an invalid SHA-256 in evidence")
    actual = _sha(_local_file(path))
    if actual != expected:
        raise ValueError(f"{label} SHA-256 mismatch")
    return actual


def _find_source(input_dir: Path) -> Path:
    matches = [input_dir / ("source" + extension)
               for extension in (".png", ".jpg", ".webp")
               if (input_dir / ("source" + extension)).exists()
               or (input_dir / ("source" + extension)).is_symlink()]
    if len(matches) != 1:
        raise ValueError("Expected exactly one source image snapshot")
    return _local_file(matches[0])


def validate_probe(probe_dir: str | Path) -> tuple[dict[str, Any], Path, dict[str, str]]:
    """Reject stale/mutable source snapshots before any Godot subprocess."""
    folder = Path(probe_dir)
    if folder.is_symlink() or not folder.is_dir() or not SLUG.fullmatch(folder.name):
        raise ValueError("Input must be a non-symlinked M1.3 probe run directory")
    if (folder / "inputs").is_symlink():
        raise ValueError("Probe inputs cannot be symlinked")
    record = _load_json(folder / "evidence.json")
    if (record.get("schema_version") != "1.3"
            or record.get("status") != "awaiting_3d_qa"
            or record.get("structural_glb_valid") is not True
            or record.get("asset_paths") != ["asset.glb"]
            or record.get("publication_approved") is not False
            or record.get("license_review_required") is not True
            or record.get("runtime_qa_passed") is not False
            or record.get("visual_qa_passed") is not False):
        raise ValueError("M1.3 probe has not reached the protected awaiting_3d_qa state")
    source = _find_source(folder / "inputs")
    snapshots = {
        "glb_sha256": _digest_matches(folder / "asset.glb", record.get("glb_sha256"), "GLB"),
        "source_sha256": _digest_matches(source, record.get("input_sha256"), "Source image"),
        "workflow_sha256": _digest_matches(
            folder / "inputs" / "workflow-api.json", record.get("workflow_sha256"), "Workflow"
        ),
        "submitted_prompt_sha256": _digest_matches(
            folder / "inputs" / "submitted-prompt.json",
            record.get("submitted_prompt_sha256"), "Submitted prompt"
        ),
        "probe_evidence_sha256": _sha(folder / "evidence.json"),
    }
    glb = _local_file(folder / "asset.glb")
    if glb.stat().st_size > MAX_GLB_BYTES or glb.stat().st_size < 20:
        raise ValueError("Probe GLB is empty or exceeds 100 MiB")
    return record, glb, snapshots


def _texture_ref(material: dict, field: str, count: int) -> bool:
    value = material.get(field)
    if value is None:
        return False
    if (not isinstance(value, dict) or type(value.get("index")) is not int
            or not 0 <= value["index"] < count):
        raise ValueError(f"Invalid {field} reference in GLB material")
    return True


def inspect_pbr(glb: bytes, *, require_textures: bool = False) -> dict[str, Any]:
    """Validate GLB envelope, buffer boundaries, core PBR semantics and texture refs.

    This does not decompress textures, guarantee manifold geometry, or measure
    visual quality. Missing optional maps are explicitly surfaced as warnings.
    """
    structure = inspect_glb(glb)
    document_length = struct.unpack_from("<I", glb, 12)[0]
    raw = glb[20:20 + document_length]
    data = json.loads(raw.decode("utf-8").rstrip(" \x00"))
    if not isinstance(data, dict):
        raise ValueError("GLB JSON document must be an object")
    after_json = 20 + document_length
    if after_json + 8 > len(glb) or glb[after_json + 4:after_json + 8] != b"BIN\x00":
        raise ValueError("GLB must have an embedded BIN chunk")
    bin_length = struct.unpack_from("<I", glb, after_json)[0]
    if after_json + 8 + bin_length != len(glb):
        raise ValueError("GLB BIN chunk size mismatch")
    buffers = data.get("buffers", [])
    if (not isinstance(buffers, list) or len(buffers) != 1
            or not isinstance(buffers[0], dict)
            or "uri" in buffers[0] or type(buffers[0].get("byteLength")) is not int
            or not 1 <= buffers[0]["byteLength"] <= bin_length
            or bin_length - buffers[0]["byteLength"] > 3):
        raise ValueError("Expected one entirely embedded GLB buffer")
    views = data.get("bufferViews", [])
    if not isinstance(views, list):
        raise ValueError("Invalid GLB buffer views")
    for view in views:
        if (not isinstance(view, dict) or view.get("buffer") != 0
                or type(view.get("byteLength")) is not int
                or type(view.get("byteOffset", 0)) is not int
                or view.get("byteOffset", 0) < 0 or view["byteLength"] <= 0
                or view.get("byteOffset", 0) + view["byteLength"] > buffers[0]["byteLength"]):
            raise ValueError("GLB buffer view exceeds embedded BIN data")
    images = data.get("images", [])
    if not isinstance(images, list):
        raise ValueError("Invalid GLB images")
    for image in images:
        if (not isinstance(image, dict) or "uri" in image
                or type(image.get("bufferView")) is not int
                or not 0 <= image["bufferView"] < len(views)
                or image.get("mimeType") not in {"image/png", "image/jpeg", "image/webp"}):
            raise ValueError("GLB image is external or has invalid bufferView")
    textures = data.get("textures", [])
    if not isinstance(textures, list):
        raise ValueError("Invalid GLB textures")
    for texture in textures:
        if (not isinstance(texture, dict) or type(texture.get("source")) is not int
                or not 0 <= texture["source"] < len(images)):
            raise ValueError("GLB texture is missing an embedded image")
    accessors = data.get("accessors", [])
    if not isinstance(accessors, list):
        raise ValueError("Invalid GLB accessors")
    for accessor in accessors:
        if (not isinstance(accessor, dict) or type(accessor.get("count")) is not int
                or accessor["count"] <= 0
                or type(accessor.get("bufferView")) is not int
                or not 0 <= accessor["bufferView"] < len(views)):
            raise ValueError("GLB accessor lacks a valid embedded buffer view")
    materials = data.get("materials", [])
    if not isinstance(materials, list):
        raise ValueError("Invalid GLB materials")
    material_info: list[dict[str, Any]] = []
    warnings: list[str] = []
    for idx, material in enumerate(materials):
        if not isinstance(material, dict):
            raise ValueError("GLB material entry must be an object")
        pbr = material.get("pbrMetallicRoughness", {})
        if not isinstance(pbr, dict):
            raise ValueError("Invalid pbrMetallicRoughness")
        for key in ("metallicFactor", "roughnessFactor"):
            value = pbr.get(key, 1.0)
            if isinstance(value, bool) or not isinstance(value, (float, int)) or not 0 <= value <= 1:
                raise ValueError(f"{key} outside [0,1] on material {idx}")
        color = pbr.get("baseColorFactor", [1, 1, 1, 1])
        if (not isinstance(color, list) or len(color) != 4
                or any(isinstance(x, bool) or not isinstance(x, (float, int))
                       or not 0 <= x <= 1 for x in color)):
            raise ValueError(f"Invalid baseColorFactor on material {idx}")
        base = _texture_ref(pbr, "baseColorTexture", len(textures))
        orm = _texture_ref(pbr, "metallicRoughnessTexture", len(textures))
        normal = _texture_ref(material, "normalTexture", len(textures))
        occlusion = _texture_ref(material, "occlusionTexture", len(textures))
        material_info.append({
            "index": idx, "name": str(material.get("name", ""))[:128],
            "metallic": pbr.get("metallicFactor", 1.0),
            "roughness": pbr.get("roughnessFactor", 1.0),
            "base_color_texture": base, "metallic_roughness_texture": orm,
            "normal_texture": normal, "occlusion_texture": occlusion,
        })
        if not base:
            warnings.append(f"material_{idx}:base_color_texture_missing")
        if not orm:
            warnings.append(f"material_{idx}:metallic_roughness_texture_missing")
        if not normal:
            warnings.append(f"material_{idx}:normal_texture_missing")
    surface_count = 0
    vertex_count = 0
    unassigned = 0
    for mesh in data["meshes"]:
        for primitive in mesh["primitives"]:
            if not isinstance(primitive, dict) or primitive.get("mode", 4) != 4:
                raise ValueError("Only triangle mesh primitives are supported")
            attr = primitive.get("attributes")
            position = attr.get("POSITION") if isinstance(attr, dict) else None
            if (type(position) is not int or not 0 <= position < len(accessors)
                    or accessors[position].get("type") != "VEC3"):
                raise ValueError("Triangle primitive missing position accessor")
            vertex_count += accessors[position]["count"]
            mat_id = primitive.get("material")
            if mat_id is None:
                unassigned += 1
            elif type(mat_id) is not int or not 0 <= mat_id < len(materials):
                raise ValueError("Invalid primitive material reference")
            surface_count += 1
    if unassigned:
        warnings.append(f"{unassigned}_surfaces_without_explicit_material")
    if not material_info:
        warnings.append("no_pbr_materials")
    if require_textures and (
        unassigned > 0 or not material_info or
        any(not item["base_color_texture"] or not item["metallic_roughness_texture"]
            for item in material_info)
    ):
        raise ValueError("Strict PBR gate requires explicit materials with base color and metallic-roughness textures")
    return {
        **structure, "surface_count": surface_count, "vertex_count": vertex_count,
        "materials": material_info, "warnings": warnings,
        "strict_textures_required": require_textures,
        "structural_pbr_gate": "passed_with_warnings" if warnings else "passed",
        "aesthetic_quality_verified": False,
    }


def _write_project(path: Path, glb: Path) -> str:
    path.mkdir()
    (path / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="MAF Isolated GLB QA"\n'
        '[rendering]\nrenderer/rendering_method="gl_compatibility"\n'
        'renderer/rendering_method.mobile="gl_compatibility"\n', encoding="utf-8"
    )
    shutil.copyfile(glb, path / "asset.glb")
    (path / "verify_glb.gd").write_text(QA_SCRIPT + "\n", encoding="utf-8")
    return _sha(path / "verify_glb.gd")


def inspect_probe(probe_dir: str | Path, *, require_textures: bool = False) -> dict[str, Any]:
    _, glb, checksums = validate_probe(probe_dir)
    pbr = inspect_pbr(glb.read_bytes(), require_textures=require_textures)
    return {
        "schema_version": "1.3.1", "probe_id": Path(probe_dir).name,
        "input_integrity": "passed", "glb_sha256": checksums["glb_sha256"],
        "pbr": pbr, "godot_executed": False, "visual_review_required": True,
        "license_review_required": True, "publication_approved": False,
    }


def verify_glb_godot(
    probe_dir: str | Path,
    *,
    godot_bin: str,
    workspace: str | Path = "runs/comfy3d-godot-qa",
    run_id: str | None = None,
    require_textures: bool = False,
    timeout: int = 120,
    runner: Runner | None = None,
) -> tuple[dict[str, Any], Path]:
    if not 1 <= timeout <= 600:
        raise ValueError("Godot QA timeout must be 1 to 600 seconds")
    _, glb, checksums = validate_probe(probe_dir)
    pbr = inspect_pbr(glb.read_bytes(), require_textures=require_textures)
    run_name = run_id or Path(probe_dir).name
    if not SLUG.fullmatch(run_name):
        raise ValueError("Invalid Godot QA run ID")
    binary = _resolve_binary(godot_bin)
    output_root = Path(workspace).absolute()
    if output_root.is_symlink() or output_root.parent.is_symlink():
        raise ValueError("QA workspace cannot be a symlink")
    destination = output_root / run_name
    staging = output_root / ("." + run_name + ".tmp")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Godot GLB QA already exists: {destination}")
    if staging.exists() or staging.is_symlink():
        raise FileExistsError(f"Godot GLB QA staging already exists: {staging}")
    output_root.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    report: dict[str, Any] = {
        "schema_version": "1.3.1", "probe_id": Path(probe_dir).name,
        "run_id": run_name, "status": "failed", "stage": "not_started",
        "input_integrity": "passed", "glb_sha256": checksums["glb_sha256"],
        "source_evidence": checksums, "pbr": pbr, "godot_version": None,
        "godot_executed": False, "godot_runtime": None,
        "checks": [], "failure": None, "visual_review_required": True,
        "visual_review_passed": False, "license_review_required": True,
        "publication_approved": False, "asset_pack_redistribution_approved": False,
    }
    run = runner or (lambda args, cwd, seconds: _command(args, cwd=cwd, timeout=seconds))
    try:
        with tempfile.TemporaryDirectory(prefix="maf-glb-godot-") as temp:
            project = Path(temp) / "canonical"
            report["qa_script_sha256"] = _write_project(project, glb)
            if _sha(project / "asset.glb") != checksums["glb_sha256"]:
                raise ValueError("GLB snapshot changed during isolated project creation")

            def execute(stage: str, args: list[str]) -> subprocess.CompletedProcess[str]:
                report["stage"] = stage
                result = run(args, project, timeout)
                (staging / f"{stage}.stdout.txt").write_text(result.stdout, encoding="utf-8")
                (staging / f"{stage}.stderr.txt").write_text(result.stderr, encoding="utf-8")
                report["checks"].append({"stage": stage, "argv": args, "returncode": result.returncode})
                return result

            version = execute("version", [binary, "--version"])
            lines = (version.stdout or version.stderr).strip().splitlines()
            report["godot_version"] = lines[0] if lines else ""
            match = re.match(r"^4\.(\d+)", report["godot_version"])
            if version.returncode != 0 or match is None or int(match.group(1)) < 2:
                raise RuntimeError("Godot 4.2+ is required")
            result = execute("import", [binary, "--headless", "--path", ".", "--import"])
            report["godot_executed"] = True
            if result.returncode != 0:
                raise RuntimeError("Godot failed to import the generated GLB project")
            result = execute(
                "verify", [binary, "--headless", "--path", ".",
                           "--script", "res://verify_glb.gd"],
            )
            generated = project / "evidence" / "glb-runtime.json"
            if generated.is_file() and not generated.is_symlink():
                report["godot_runtime"] = _load_json(generated)
            runtime = report["godot_runtime"]
            if (result.returncode != 0 or not isinstance(runtime, dict)
                    or runtime.get("status") != "passed"
                    or runtime.get("errors") != []
                    or type(runtime.get("mesh_instances")) is not int
                    or runtime["mesh_instances"] < 1
                    or type(runtime.get("surfaces")) is not int
                    or runtime["surfaces"] < 1
                    or type(runtime.get("vertices")) is not int
                    or runtime["vertices"] < 3
                    or not isinstance(runtime.get("materials"), list)
                    or len(runtime["materials"]) != runtime["surfaces"]):
                raise RuntimeError("Godot GLB resource or mesh/material verification failed")
            write_json(staging / "godot-runtime.json", runtime)
            report["status"] = "awaiting_visual_review"
            report["stage"] = "completed"
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        write_json(staging / "report.json", report)
        staging.rename(destination)
    return report, destination
