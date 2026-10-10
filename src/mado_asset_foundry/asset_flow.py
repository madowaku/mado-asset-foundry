"""MAF-M0.9.4 end-to-end, human-gated asset production dogfood.

A single operator-supplied flow recipe compiles snapshot intake, attribution,
a Godot 4 resource test, and a real rendered gallery. No auto publication.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Callable, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from .asset_sources import AssetSubmission, _local_file, _sha256, intake_asset
from .attribution_bridge import _read_object, compile_godot_import
from .io import write_json
from .runtime_import_qa import _commit_evidence, verify_godot_import
from .visual_gallery import render_gallery, review_release


class AssetFlowSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal["0.1"] = "0.1"
    flow_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    submissions: list[str] = Field(min_length=1, max_length=8)


def _load_spec(path: Path) -> AssetFlowSpec:
    if not path.is_file():
        raise FileNotFoundError(f"Flow recipe not found: {path}")
    try:
        return AssetFlowSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (yaml.YAMLError, UnicodeError) as exc:
        raise ValueError(f"Could not parse flow recipe: {path}") from exc


def _copy_verified(origin: Path, destination: Path) -> str:
    before = _sha256(origin)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(origin, destination)
    if _sha256(destination) != before:
        raise ValueError(f"Input changed while snapshotting: {origin}")
    return before


def run_asset_flow(
    spec_path: str | Path,
    *,
    godot_bin: str,
    workspace: str | Path = "runs/asset-flows",
    virtual_display: bool = False,
    timeout: int = 120,
    force: bool = False,
    progress: Callable[[str, str], None] | None = None,
) -> tuple[dict, Path]:
    """Complete all deterministic stages, stopping before human release review."""
    source = Path(spec_path).resolve()
    spec = _load_spec(source)
    if not 1 <= timeout <= 600:
        raise ValueError("timeout must be 1 to 600 seconds")
    workspace_dir = Path(workspace)
    target = workspace_dir / spec.flow_id
    staging = workspace_dir / f".{spec.flow_id}.tmp"
    if target.exists() and not force:
        raise FileExistsError(f"Asset flow already exists: {target}; use --force")
    if staging.exists():
        raise FileExistsError(f"Asset flow staging already exists: {staging}")
    if len(spec.submissions) != len(set(spec.submissions)):
        raise ValueError("Duplicate input submission paths are not allowed")

    # Validate and snapshot sources under a local run root. All following
    # pipeline stages operate on this immutable-in-practice snapshot only.
    # No external assets are committed to source control.
    workspace_dir.mkdir(parents=True, exist_ok=True)
    staging.mkdir()
    stage = "intake"
    def signal(name: str, state: str) -> None:
        if progress is not None:
            try:
                progress(name, state)
            except Exception:
                # UI reporting must never alter evidence or skip license gates.
                pass

    signal(stage, "running")
    input_evidence: list[dict] = []
    seen_assets: set[str] = set()
    plan_items: list[dict[str, str]] = []
    try:
        for raw in spec.submissions:
            original_submission = _local_file(source.parent, raw)
            original = AssetSubmission.model_validate(
                yaml.safe_load(original_submission.read_text(encoding="utf-8"))
            )
            if original.asset_id in seen_assets:
                raise ValueError(f"Duplicate asset_id in flow: {original.asset_id}")
            seen_assets.add(original.asset_id)
            asset_file = _local_file(original_submission.parent, original.local_file)
            if asset_file.suffix.lower() != ".png":
                raise ValueError(f"Flow supports PNG only: {original.asset_id}")
            saved_dir = staging / "inputs" / original.asset_id
            saved_dir.mkdir(parents=True)
            digest = _copy_verified(asset_file, saved_dir / "asset.png")
            snapshot = original.model_copy(update={"local_file": "asset.png"})
            license_hash = None
            if original.license_evidence_file:
                license_file = _local_file(
                    original_submission.parent, original.license_evidence_file
                )
                license_hash = _copy_verified(license_file, saved_dir / "LICENSE.txt")
                snapshot = snapshot.model_copy(
                    update={"license_evidence_file": "LICENSE.txt"}
                )
            (saved_dir / "submission.yaml").write_text(
                yaml.safe_dump(snapshot.model_dump(mode="json"),
                               allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            report, report_path = intake_asset(
                saved_dir / "submission.yaml",
                output_root=staging / "reports",
            )
            if report["status"] != "eligible":
                raise ValueError(
                    f"License intake blocked {original.asset_id}: "
                    + "; ".join(report["reasons"])
                )
            if original.use_case != "game_embedding":
                raise ValueError(
                    f"Only game_embedding is supported: {original.asset_id}"
                )
            input_evidence.append({
                "asset_id": original.asset_id,
                "submission": raw,
                "original_sha256": digest,
                "original_license_sha256": license_hash,
                "intake_report_sha256": _sha256(report_path),
                "source_id": original.source_id,
                "license_spdx": original.license_spdx,
                "human_verified_at_intake": original.reviewed_by_human,
            })
            plan_items.append({
                "submission": f"inputs/{original.asset_id}/submission.yaml",
                "report": f"reports/{original.asset_id}/report.json",
            })

        signal("intake", "completed")
        stage = "attribution"
        signal(stage, "running")
        write_json(staging / "plan.json", {
            "schema_version": "0.1", "project_id": spec.flow_id,
            "assets": plan_items,
        })
        _, project = compile_godot_import(
            staging / "plan.json", output_root=staging / "godot"
        )
        signal("attribution", "completed")
        stage = "runtime"
        signal(stage, "running")
        runtime, runtime_path = verify_godot_import(
            staging / "plan.json", project, godot_bin=godot_bin,
            output_root=staging / "runtime", timeout=timeout,
        )
        if runtime["status"] != "passed":
            raise ValueError(
                "Godot resource QA failed: " + str(runtime.get("failure_reason"))
            )
        signal("runtime", "completed")
        stage = "gallery"
        signal(stage, "running")
        gallery, gallery_path = render_gallery(
            staging / "plan.json", project, godot_bin=godot_bin,
            output_root=staging / "gallery", timeout=timeout,
            virtual_display=virtual_display,
        )
        if gallery["status"] != "captured":
            raise ValueError(
                "Godot visual capture failed: " + str(gallery.get("failure_reason"))
            )
        signal("gallery", "completed")
        stage = "evidence"
        signal(stage, "running")
        input_evidence.sort(key=lambda x: x["asset_id"])
        summary = {
            "schema_version": "0.1",
            "flow_id": spec.flow_id,
            "status": "awaiting_human_review",
            "intake": "eligible",
            "attribution": "compiled",
            "godot_runtime": "passed",
            "visual_gallery": "captured",
            "source_count": len(input_evidence),
            "assets": input_evidence,
            "godot_version": runtime["godot_version"],
            "plan_sha256": _sha256(staging / "plan.json"),
            "runtime_report_sha256": _sha256(runtime_path / "report.json"),
            "gallery_report_sha256": _sha256(gallery_path / "report.json"),
            "screenshot_sha256": gallery["screenshot_sha256"],
            "credits_sha256": gallery["credits_sha256"],
            "manifest_sha256": gallery["manifest_sha256"],
            "publication_approved": False,
            "asset_pack_redistribution_approved": False,
            "human_review_required": True,
            "output_paths": {
                "plan": "plan.json",
                "project": f"godot/{spec.flow_id}",
                "runtime": f"runtime/{spec.flow_id}/report.json",
                "gallery": f"gallery/{spec.flow_id}",
                "screenshot": f"gallery/{spec.flow_id}/gallery.png",
                "credits": f"gallery/{spec.flow_id}/CREDITS.md",
            },
        }
        write_json(staging / "summary.json", summary)
        _commit_evidence(staging, target, force=force)
        signal("evidence", "completed")
        return _read_object(target / "summary.json"), target
    except Exception:
        signal(stage, "failed")
        if staging.exists():
            shutil.rmtree(staging)
        raise


def inspect_asset_flow(run_dir: str | Path) -> dict:
    folder = Path(run_dir)
    if folder.is_symlink():
        raise ValueError("Flow directory must not be a symlink")
    summary = _read_object(folder / "summary.json")
    flow_id = summary.get("flow_id")
    if (not isinstance(flow_id, str) or not flow_id
            or folder.name != flow_id):
        raise ValueError("Flow summary does not match run directory")
    review_path = folder / "review" / "release-check.json"
    if review_path.exists():
        review = _read_object(review_path)
        summary["review_status"] = review.get("status")
    else:
        summary["review_status"] = "not_submitted"
    return summary


def review_asset_flow(
    run_dir: str | Path,
    *,
    review_path: str | Path,
    force: bool = False,
) -> tuple[dict, Path]:
    """Re-evaluate snapshotted evidence and human review without auto publishing."""
    folder = Path(run_dir)
    summary = inspect_asset_flow(folder)
    flow_id = summary["flow_id"]
    plan = folder / "plan.json"
    project = folder / "godot" / flow_id
    gallery = folder / "gallery" / flow_id
    if _sha256(plan) != summary.get("plan_sha256"):
        raise ValueError("Flow plan has changed since capture")
    if _sha256(folder / "runtime" / flow_id / "report.json") != summary.get("runtime_report_sha256"):
        raise ValueError("Runtime report has changed since capture")
    if _sha256(gallery / "report.json") != summary.get("gallery_report_sha256"):
        raise ValueError("Gallery report has changed since capture")
    if _sha256(gallery / "gallery.png") != summary.get("screenshot_sha256"):
        raise ValueError("Gallery image has changed since capture")
    destination = folder / "review" / "release-check.json"
    gate, path = review_release(
        plan, project, gallery, review_path=review_path,
        output_path=destination, force=force,
    )
    return gate, path
