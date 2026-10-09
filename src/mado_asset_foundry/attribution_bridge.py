"""M0.9.1: evidence-verified attribution and Godot PNG import bridge."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .asset_sources import (
    AssetSubmission, _local_file, _sha256, evaluate_submission,
    get_source, load_source_registry,
)
from .io import write_json


class InputEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    submission: str
    report: str


class BridgePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: str = "0.1"
    project_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    assets: list[InputEntry] = Field(min_length=1)


def _read_object(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return data


def _display(text: str) -> str:
    return " ".join(text.replace("<", "&lt;").replace(">", "&gt;").replace("[", r"\[").replace("]", r"\]").split())


def compile_godot_import(
    plan_path: str | Path,
    *,
    output_root: str | Path = "runs/asset-godot",
    force: bool = False,
) -> tuple[dict, Path]:
    """Create a static Godot project, never execute Godot or publish assets."""
    plan_file = Path(plan_path).resolve()
    plan = BridgePlan.model_validate(_read_object(plan_file))
    output = Path(output_root) / plan.project_id
    staging = output.parent / f".{plan.project_id}.tmp"
    if output.exists() and not force:
        raise FileExistsError(f"Godot project already exists: {output}")
    if staging.exists():
        raise FileExistsError(f"Staging directory already exists: {staging}")

    registry = load_source_registry()
    entries: list[tuple[AssetSubmission, dict, Path]] = []
    seen: set[str] = set()
    for item in plan.assets:
        submission_file = _local_file(plan_file.parent, item.submission)
        report_file = _local_file(plan_file.parent, item.report)
        submission = AssetSubmission.model_validate(yaml.safe_load(submission_file.read_text(encoding="utf-8")))
        report = _read_object(report_file)
        if submission.asset_id in seen:
            raise ValueError(f"Duplicate asset_id: {submission.asset_id}")
        seen.add(submission.asset_id)
        source = get_source(registry, submission.source_id)
        local_file = _local_file(submission_file.parent, submission.local_file)
        if local_file.suffix.lower() != ".png":
            raise ValueError(f"Only PNG is supported by this bridge: {submission.asset_id}")
        from PIL import Image
        with Image.open(local_file) as img:
            if img.format != "PNG":
                raise ValueError(f"File is not a PNG: {submission.asset_id}")
            img.verify()
        evidence_hash = None
        if submission.license_evidence_file:
            evidence_hash = _sha256(_local_file(submission_file.parent, submission.license_evidence_file))
        has_evidence = bool(evidence_hash or submission.license_evidence_url)
        current_state, _, _ = evaluate_submission(submission, source, has_evidence=has_evidence)
        if current_state != "eligible" or submission.use_case != "game_embedding":
            raise ValueError(f"Current license gate does not permit game embedding: {submission.asset_id}")
        compared = {
            "asset_id": submission.asset_id, "source_id": submission.source_id,
            "title": submission.title, "creator": submission.creator,
            "local_file": submission.local_file, "asset_url": submission.asset_url,
            "sha256": _sha256(local_file), "license_spdx": submission.license_spdx,
            "license_evidence_url": submission.license_evidence_url,
            "license_evidence_file": submission.license_evidence_file,
            "license_evidence_sha256": evidence_hash,
            "attribution": submission.attribution,
            "reviewed_by_human": True, "use_case": "game_embedding",
            "commercial": submission.commercial,
            "status": "eligible", "publication_approved": False,
        }
        if any(report.get(key) != value for key, value in compared.items()):
            raise ValueError(f"Intake evidence is stale or mismatched: {submission.asset_id}")
        if source.discovery_mode == "manual":
            from .asset_sources import _host_allowed, _https_host
            if not submission.asset_url or not _host_allowed(_https_host(submission.asset_url), source.allowed_hosts):
                raise ValueError(f"Invalid origin URL: {submission.asset_id}")
            if submission.license_evidence_url and not _host_allowed(_https_host(submission.license_evidence_url), source.allowed_hosts):
                raise ValueError(f"Invalid license URL: {submission.asset_id}")
        entries.append((submission, report, local_file))

    entries.sort(key=lambda pair: pair[0].asset_id)
    staging.parent.mkdir(parents=True, exist_ok=True)
    try:
        (staging / "assets").mkdir(parents=True)
        (staging / "evidence").mkdir()
        manifest = []
        credits = ["# Asset credits", "", "This document records asset origins and stated licenses. It does not authorize redistribution.", ""]
        for submission, report, source_file in entries:
            name = f"{submission.asset_id}.png"
            destination = staging / "assets" / name
            shutil.copyfile(source_file, destination)
            if _sha256(destination) != report["sha256"]:
                raise ValueError(f"File changed during copy: {submission.asset_id}")
            manifest.append({
                "asset_id": submission.asset_id, "path": f"res://assets/{name}",
                "sha256": report["sha256"], "source_id": submission.source_id,
                "asset_url": submission.asset_url, "license_spdx": submission.license_spdx,
                "creator": submission.creator, "license_evidence_url": submission.license_evidence_url,
            })
            credits += [
                f"## {_display(submission.title)} ({submission.asset_id})",
                f"- Creator: {_display(submission.creator)}",
                f"- Source: {_display(submission.source_id)}",
                f"- License (operator verified): {_display(submission.license_spdx)}",
                f"- Asset URL: {_display(submission.asset_url or 'local')}",
                f"- License evidence: {_display(submission.license_evidence_url or submission.license_evidence_file or 'not supplied')}",
                f"- Attribution: {_display(submission.attribution or 'none specified')}",
                "",
            ]
        (staging / "CREDITS.md").write_text("\n".join(credits).rstrip() + "\n", encoding="utf-8")
        (staging / "project.godot").write_text(
            '; MAF-M0.9.1 generated project\nconfig_version=5\n[application]\nconfig/name="MAF Imported Assets"\n[rendering]\nrenderer/rendering_method="gl_compatibility"\n',
            encoding="utf-8",
        )
        write_json(staging / "asset_manifest.json", {
            "schema_version": "0.1", "project_id": plan.project_id,
            "publication_approved": False, "asset_count": len(manifest),
            "assets": manifest,
        })
        write_json(staging / "evidence" / "bridge-report.json", {
            "schema_version": "0.1", "project_id": plan.project_id,
            "status": "compiled", "asset_count": len(manifest),
            "network_accessed": False, "godot_executed": False,
            "publication_approved": False,
            "assets": [{"asset_id": x["asset_id"], "sha256": x["sha256"]} for x in manifest],
        })
        if output.exists():
            # Fail-safe approach: preserve prior result until all new files have been built.
            backup = output.parent / f".{plan.project_id}.backup"
            if backup.exists():
                raise FileExistsError(f"Backup already exists: {backup}")
            output.rename(backup)
            try:
                staging.rename(output)
            except Exception:
                backup.rename(output)
                raise
            shutil.rmtree(backup)
        else:
            staging.rename(output)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    return _read_object(output / "evidence" / "bridge-report.json"), output
