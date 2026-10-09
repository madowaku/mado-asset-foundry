"""MAF-M0.9.2: fresh license-evidence gate and real headless Godot import QA.

A Godot process only receives a newly built, known-file-list project; never an
operator-supplied Godot project tree or its potential addons/scripts.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

from .asset_sources import _local_file, _sha256
from .attribution_bridge import BridgePlan, _read_object, compile_godot_import
from .io import write_json


_RUNTIME_SCRIPT = r'''extends SceneTree

const INPUT_PATH := "res://runtime_manifest.json"
const OUTPUT_PATH := "res://evidence/runtime-import.json"

func _init() -> void:
    var result: Dictionary = {
        "status": "failed", "asset_count": 0, "loaded_count": 0,
        "assets": [], "errors": []
    }
    var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(INPUT_PATH))
    if typeof(parsed) != TYPE_DICTIONARY:
        result["errors"].append("invalid_runtime_manifest")
        _finish(result, 1)
        return
    var items: Variant = parsed.get("assets", [])
    if typeof(items) != TYPE_ARRAY:
        result["errors"].append("invalid_asset_list")
        _finish(result, 1)
        return
    result["asset_count"] = items.size()
    for entry in items:
        if typeof(entry) != TYPE_DICTIONARY:
            result["errors"].append("invalid_asset_entry")
            continue
        var path: String = str(entry.get("path", ""))
        var id: String = str(entry.get("asset_id", ""))
        var texture: Texture2D = ResourceLoader.load(path) as Texture2D
        if texture == null:
            result["errors"].append("resource_load_failed:" + id)
            continue
        var width: int = texture.get_width()
        var height: int = texture.get_height()
        if width != int(entry.get("width", 0)) or height != int(entry.get("height", 0)):
            result["errors"].append("dimension_mismatch:" + id)
            continue
        result["assets"].append({
            "asset_id": id, "width": width, "height": height
        })
        result["loaded_count"] += 1
    if result["errors"].is_empty() and result["loaded_count"] == result["asset_count"]:
        result["status"] = "passed"
        _finish(result, 0)
    else:
        _finish(result, 1)

func _finish(result: Dictionary, exit_code: int) -> void:
    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path("res://evidence"))
    var file: FileAccess = FileAccess.open(OUTPUT_PATH, FileAccess.WRITE)
    if file == null:
        push_error("unable_to_write_runtime_report")
        quit(1)
        return
    file.store_string(JSON.stringify(result, "\t"))
    file.close()
    print("MAF_RUNTIME_REPORT=" + JSON.stringify(result))
    quit(exit_code)
'''


def _resolve_binary(value: str) -> str:
    candidate = Path(value)
    if candidate.is_file():
        return str(candidate.resolve())
    located = shutil.which(value)
    if located:
        return located
    raise FileNotFoundError(f"Godot executable not found: {value}")


def _command(argv: list[str], *, cwd: Path, timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                          timeout=timeout, check=False, errors="replace")


def _compare_generated_project(actual: Path, expected: Path) -> None:
    if actual.is_symlink() or not actual.is_dir():
        raise ValueError(f"Godot project is missing or symlinked: {actual}")
    expected_files = {
        path.relative_to(expected).as_posix(): path
        for path in expected.rglob("*") if path.is_file()
    }
    actual_files: dict[str, Path] = {}
    for item in actual.rglob("*"):
        if item.is_symlink():
            raise ValueError(f"Godot project contains a symlink: {item}")
        if item.is_file():
            actual_files[item.relative_to(actual).as_posix()] = item
        elif not item.is_dir():
            raise ValueError(f"Unexpected project entry: {item}")
    if set(actual_files) != set(expected_files):
        missing = sorted(set(expected_files) - set(actual_files))
        extra = sorted(set(actual_files) - set(expected_files))
        raise ValueError(f"Godot project inventory mismatch; missing={missing}, extra={extra}")
    for name in sorted(expected_files):
        if _sha256(expected_files[name]) != _sha256(actual_files[name]):
            raise ValueError(f"Godot project file mismatch: {name}")


def _write_log(directory: Path, step: str, result: subprocess.CompletedProcess[str]) -> None:
    (directory / f"{step}.stdout.txt").write_text(result.stdout, encoding="utf-8")
    (directory / f"{step}.stderr.txt").write_text(result.stderr, encoding="utf-8")


def _commit_evidence(staging: Path, target: Path, *, force: bool) -> None:
    if not target.exists():
        staging.rename(target)
        return
    if not force:
        raise FileExistsError(f"QA evidence already exists: {target}")
    backup = target.parent / (f".{target.name}.backup")
    if backup.exists():
        raise FileExistsError(f"QA evidence backup already exists: {backup}")
    target.rename(backup)
    try:
        staging.rename(target)
    except Exception:
        backup.rename(target)
        raise
    shutil.rmtree(backup)


def verify_godot_import(
    plan_path: str | Path,
    project_dir: str | Path,
    *,
    godot_bin: str,
    output_root: str | Path = "evidence/asset-godot-runtime",
    force: bool = False,
    timeout: int = 120,
) -> tuple[dict, Path]:
    """Run an explicit Godot 4 import and ResourceLoader check after license gating.

    Returns a failed report for runtime errors; invalid/stale licensing fails before
    invoking the Godot binary. Does not approve publishing or standalone resale.
    """
    if not 1 <= timeout <= 600:
        raise ValueError("timeout must be between 1 and 600 seconds")
    plan_file = Path(plan_path).resolve()
    plan = BridgePlan.model_validate(_read_object(plan_file))
    supplied_project = Path(project_dir)
    if supplied_project.is_symlink():
        raise ValueError("Godot project path must not be a symlink")
    actual = supplied_project.resolve()
    if actual.name != plan.project_id:
        raise ValueError("Project directory does not match the plan project_id")

    evidence_root = Path(output_root)
    evidence_target = evidence_root / plan.project_id
    staging = evidence_root / (f".{plan.project_id}.tmp")
    if evidence_target.exists() and not force:
        raise FileExistsError(f"QA evidence already exists: {evidence_target}")
    if staging.exists():
        raise FileExistsError(f"QA staging already exists: {staging}")

    # Recompile from original M0.9 submissions + intake reports. This rechecks
    # the real license gate, source hashes, evidence hashes, and origin metadata.
    with tempfile.TemporaryDirectory(prefix="maf-runtime-") as tmp:
        tmp_dir = Path(tmp)
        bridge_report, clean_project = compile_godot_import(
            plan_file, output_root=tmp_dir / "canonical"
        )
        _compare_generated_project(actual, clean_project)

        # The canonical compile already verified the current report and submission.
        # Keep per-asset license evidence and report identity in the QA ledger.
        intake_evidence: dict[str, dict] = {}
        for input_entry in plan.assets:
            report_file = _local_file(plan_file.parent, input_entry.report)
            record = _read_object(report_file)
            intake_evidence[record["asset_id"]] = {
                "intake_report_sha256": _sha256(report_file),
                "license_evidence_sha256": record.get("license_evidence_sha256"),
                "license_evidence_url": record.get("license_evidence_url"),
                "attribution": record.get("attribution"),
                "asset_url": record.get("asset_url"),
                "reviewed_by_human": record.get("reviewed_by_human"),
                "use_case": record.get("use_case"),
            }
        binary = _resolve_binary(godot_bin)

        asset_manifest = _read_object(clean_project / "asset_manifest.json")
        planned_assets: list[dict] = []
        for entry in asset_manifest["assets"]:
            name = entry["asset_id"] + ".png"
            file_path = clean_project / "assets" / name
            with Image.open(file_path) as image:
                if image.format != "PNG":
                    raise ValueError(f"Invalid PNG: {name}")
                width, height = image.size
            planned_assets.append({
                "asset_id": entry["asset_id"],
                "path": "res://assets/" + name,
                "width": width, "height": height,
            })
        write_json(clean_project / "runtime_manifest.json", {"assets": planned_assets})
        (clean_project / "verify_runtime.gd").write_text(
            _RUNTIME_SCRIPT + "\n", encoding="utf-8"
        )

        evidence_root.mkdir(parents=True, exist_ok=True)
        staging.mkdir()
        try:
            report: dict = {
                "schema_version": "0.1",
                "project_id": plan.project_id,
                "status": "failed",
                "license_evidence_gate": "passed",
                "input_integrity_gate": "passed",
                "godot_executed": False,
                "publication_approved": False,
                "asset_pack_redistribution_approved": False,
                "asset_count": len(planned_assets),
                "loaded_count": 0,
                "godot_version": None,
                "runtime": None,
                "checks": [],
                "assets": [
                    {"asset_id": entry["asset_id"], "sha256": entry["sha256"],
                     "license_spdx": entry["license_spdx"], "source_id": entry["source_id"],
                     **intake_evidence[entry["asset_id"]]}
                    for entry in asset_manifest["assets"]
                ],
                "source_bridge_status": bridge_report["status"],
                "failure_reason": None,
                "commands": [],
            }

            def execute(step: str, args: list[str]) -> subprocess.CompletedProcess[str]:
                report["commands"].append({"step": step, "argv": args})
                result = _command(args, cwd=clean_project, timeout=timeout)
                _write_log(staging, step, result)
                report["checks"].append({"step": step, "returncode": result.returncode})
                return result

            try:
                version = execute("version", [binary, "--version"])
                detected = (version.stdout or version.stderr).strip().splitlines()
                report["godot_version"] = detected[0] if detected else ""
                match = re.match(r"^4\.(\d+)", report["godot_version"])
                if version.returncode != 0 or match is None or int(match.group(1)) < 2:
                    report["failure_reason"] = "Godot 4.2+ is required"
                else:
                    report["godot_executed"] = True
                    imported = execute(
                        "import", [binary, "--headless", "--path", ".", "--import"]
                    )
                    if imported.returncode != 0:
                        report["failure_reason"] = "Godot import process failed"
                    else:
                        verified = execute(
                            "verify", [binary, "--headless", "--path", ".",
                                       "--script", "res://verify_runtime.gd"]
                        )
                        runtime_path = clean_project / "evidence" / "runtime-import.json"
                        if runtime_path.is_file():
                            runtime = _read_object(runtime_path)
                            report["runtime"] = runtime
                            expected_sizes = {
                                item["asset_id"]: (item["width"], item["height"])
                                for item in planned_assets
                            }
                            loaded = runtime.get("assets", [])
                            observed = {}
                            if isinstance(loaded, list):
                                for item in loaded:
                                    if isinstance(item, dict):
                                        observed[item.get("asset_id")] = (
                                            item.get("width"), item.get("height")
                                        )
                            report["loaded_count"] = runtime.get("loaded_count", 0)
                            runtime_valid = (
                                runtime.get("status") == "passed"
                                and runtime.get("asset_count") == len(planned_assets)
                                and runtime.get("loaded_count") == len(planned_assets)
                                and runtime.get("errors") == []
                                and len(loaded) == len(planned_assets)
                                and observed == expected_sizes
                            )
                        else:
                            runtime_valid = False
                        if verified.returncode == 0 and runtime_valid:
                            report["status"] = "passed"
                        else:
                            report["failure_reason"] = "Godot resource verification failed"
            except (subprocess.TimeoutExpired, OSError, ValueError, json.JSONDecodeError) as exc:
                report["failure_reason"] = f"Godot runtime error: {exc}"
            write_json(staging / "report.json", report)
            _commit_evidence(staging, evidence_target, force=force)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    return _read_object(evidence_target / "report.json"), evidence_target
