"""MAF-M0.9.3: Godot rendered gallery QA and human-controlled attribution review."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageStat
from pydantic import BaseModel, ConfigDict, Field

from .asset_sources import _local_file, _sha256
from .attribution_bridge import BridgePlan, _read_object, compile_godot_import
from .io import write_json
from .runtime_import_qa import (
    _compare_generated_project, _resolve_binary, _command, _commit_evidence,
    verify_godot_import,
)

GALLERY_GD = "extends SceneTree\n\nconst INPUT := \"res://asset_manifest.json\"\nconst REPORT := \"res://evidence/gallery-runtime.json\"\nconst SCREENSHOT := \"res://evidence/gallery.png\"\n\nfunc _initialize() -> void:\n    call_deferred(\"_capture\")\n\nfunc _capture() -> void:\n    var report: Dictionary = {\"status\": \"failed\", \"loaded_count\": 0, \"asset_count\": 0, \"errors\": []}\n    var manifest: Variant = JSON.parse_string(FileAccess.get_file_as_string(INPUT))\n    if typeof(manifest) != TYPE_DICTIONARY:\n        report[\"errors\"].append(\"invalid_manifest\")\n        _finish(report, 1)\n        return\n    var assets: Variant = manifest.get(\"assets\", [])\n    if typeof(assets) != TYPE_ARRAY or assets.size() == 0 or assets.size() > 8:\n        report[\"errors\"].append(\"invalid_asset_count\")\n        _finish(report, 1)\n        return\n    report[\"asset_count\"] = assets.size()\n\n    var viewport: Window = get_root()\n    viewport.size = Vector2i(960, 540)\n    var background := ColorRect.new()\n    background.color = Color(\"#111827\")\n    background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)\n    viewport.add_child(background)\n\n    var heading := Label.new()\n    heading.text = \"MADO Asset Foundry | Visual QA Gallery\"\n    heading.position = Vector2(28, 14)\n    heading.add_theme_font_size_override(\"font_size\", 24)\n    background.add_child(heading)\n    var footer := Label.new()\n    footer.text = \"Visual review required | not a release approval\"\n    footer.position = Vector2(28, 510)\n    background.add_child(footer)\n\n    for idx in range(assets.size()):\n        var entry: Variant = assets[idx]\n        var resource_path: String = str(entry.get(\"path\", \"\"))\n        var id: String = str(entry.get(\"asset_id\", \"\"))\n        var texture: Texture2D = ResourceLoader.load(resource_path) as Texture2D\n        if texture == null:\n            report[\"errors\"].append(\"texture_load_failed:\" + id)\n            continue\n        var card := ColorRect.new()\n        card.color = Color(\"#243244\")\n        card.position = Vector2(28 + (idx % 4) * 230, 66 + (idx / 4) * 214)\n        card.size = Vector2(216, 198)\n        background.add_child(card)\n        var icon := TextureRect.new()\n        icon.position = Vector2(35, 10)\n        icon.size = Vector2(146, 146)\n        icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE\n        icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED\n        icon.texture_filter = CanvasItem.TEXTURE_FILTER_NEAREST\n        icon.texture = texture\n        card.add_child(icon)\n        var text := Label.new()\n        text.text = id\n        text.position = Vector2(8, 163)\n        text.size = Vector2(200, 26)\n        text.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER\n        text.clip_text = true\n        card.add_child(text)\n        report[\"loaded_count\"] += 1\n\n    if not report[\"errors\"].is_empty() or report[\"loaded_count\"] != report[\"asset_count\"]:\n        _finish(report, 1)\n        return\n\n    await process_frame\n    await process_frame\n    await RenderingServer.frame_post_draw\n    var shot: Image = viewport.get_texture().get_image()\n    if shot.is_empty() or shot.get_width() != 960 or shot.get_height() != 540:\n        report[\"errors\"].append(\"invalid_viewport_capture\")\n        _finish(report, 1)\n        return\n    var image_err: Error = shot.save_png(SCREENSHOT)\n    if image_err != OK:\n        report[\"errors\"].append(\"image_write_failed:\" + str(image_err))\n        _finish(report, 1)\n        return\n    report[\"status\"] = \"captured\"\n    report[\"width\"] = shot.get_width()\n    report[\"height\"] = shot.get_height()\n    _finish(report, 0)\n\nfunc _finish(report: Dictionary, code: int) -> void:\n    DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(\"res://evidence\"))\n    var file: FileAccess = FileAccess.open(REPORT, FileAccess.WRITE)\n    if file == null:\n        push_error(\"cannot_write_gallery_evidence\")\n        quit(1)\n        return\n    file.store_string(JSON.stringify(report, \"\\t\"))\n    file.close()\n    print(\"MAF_GALLERY_REPORT=\" + JSON.stringify(report))\n    quit(code)\n" 


class GalleryReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = "0.1"
    project_id: str
    reviewer: str = Field(min_length=3)
    screenshot_sha256: str
    credits_sha256: str
    manifest_sha256: str
    visual_approved: bool = False
    attribution_approved: bool = False
    rights_approved_for_game_embedding: bool = False
    notes: str = Field(min_length=5)


def _validate_plan_project(plan_path: Path, project_path: Path, workspace: Path) -> tuple[BridgePlan, Path, dict]:
    plan = BridgePlan.model_validate(_read_object(plan_path))
    if project_path.is_symlink():
        raise ValueError("Project directory may not be a symlink")
    actual = project_path.resolve()
    if actual.name != plan.project_id:
        raise ValueError("Project directory does not match project_id")
    _, canonical = compile_godot_import(plan_path, output_root=workspace / "canonical")
    _compare_generated_project(actual, canonical)
    manifest = _read_object(canonical / "asset_manifest.json")
    return plan, canonical, manifest


def _evidence_entries(plan: BridgePlan, plan_file: Path, manifest: dict) -> list[dict[str, Any]]:
    input_reports: dict[str, dict] = {}
    for entry in plan.assets:
        path = _local_file(plan_file.parent, entry.report)
        record = _read_object(path)
        input_reports[record["asset_id"]] = {
            "intake_report_sha256": _sha256(path),
            "license_evidence_sha256": record.get("license_evidence_sha256"),
            "license_evidence_url": record.get("license_evidence_url"),
            "attribution": record.get("attribution"),
            "reviewed_by_human": record.get("reviewed_by_human"),
        }
    return [
        {
            "asset_id": item["asset_id"], "source_id": item["source_id"],
            "license_spdx": item["license_spdx"], "sha256": item["sha256"],
            **input_reports[item["asset_id"]],
        }
        for item in manifest["assets"]
    ]


def render_gallery(
    plan_path: str | Path,
    project_dir: str | Path,
    *,
    godot_bin: str,
    output_root: str | Path = "evidence/asset-gallery",
    force: bool = False,
    timeout: int = 120,
    virtual_display: bool = False,
) -> tuple[dict, Path]:
    """Capture a rendered PNG after passing the M0.9.2 real engine and license gate."""
    if not 1 <= timeout <= 600:
        raise ValueError("timeout must be between 1 and 600 seconds")
    plan_file = Path(plan_path).resolve()
    target_root = Path(output_root)
    parsed = BridgePlan.model_validate(_read_object(plan_file))
    target = target_root / parsed.project_id
    staging = target_root / f".{parsed.project_id}.tmp"
    if target.exists() and not force:
        raise FileExistsError(f"Gallery evidence already exists: {target}")
    if staging.exists():
        raise FileExistsError(f"Gallery staging exists: {staging}")

    with tempfile.TemporaryDirectory(prefix="maf-gallery-") as tmp:
        workspace = Path(tmp)
        plan, canonical, manifest = _validate_plan_project(
            plan_file, Path(project_dir), workspace
        )
        count = manifest["asset_count"]
        if not isinstance(count, int) or not 1 <= count <= 8:
            raise ValueError("M0.9.3 supports 1 to 8 PNG assets in one visual gallery")

        # Real Godot resource load verification is mandatory, never inferred from
        # a stale report. The canonical compilation repeats the license gate.
        runtime, runtime_dir = verify_godot_import(
            plan_file, project_dir, godot_bin=godot_bin,
            output_root=workspace / "runtime",
            timeout=timeout,
        )
        if runtime["status"] != "passed":
            raise ValueError(
                "M0.9.2 runtime QA did not pass: " +
                str(runtime.get("failure_reason"))
            )
        binary = _resolve_binary(godot_bin)
        xvr = shutil.which("xvfb-run") if virtual_display else None
        if virtual_display and not xvr:
            raise FileNotFoundError("xvfb-run is required for --virtual-display")
        (canonical / "gallery_capture.gd").write_text(GALLERY_GD + "\n", encoding="utf-8")
        # A normal display is required for pixel rendering; --headless is not
        # accepted here because a structural import isn't a visual capture.
        (canonical / "project.godot").write_text(
            (canonical / "project.godot").read_text(encoding="utf-8") +
            '\n[display]\nwindow/size/viewport_width=960\nwindow/size/viewport_height=540\n'
            'window/size/window_width_override=960\nwindow/size/window_height_override=540\n',
            encoding="utf-8",
        )
        argv = [binary, "--path", ".", "--script", "res://gallery_capture.gd"]
        if xvr:
            argv = [xvr, "-a", *argv]

        target_root.mkdir(parents=True, exist_ok=True)
        staging.mkdir()
        report: dict[str, Any] = {
            "schema_version": "0.1", "project_id": plan.project_id,
            "status": "failed", "visual_review": "not_approved",
            "attribution_release_gate": "human_review_required",
            "publication_approved": False, "asset_pack_redistribution_approved": False,
            "license_evidence_gate": "passed", "runtime_import_gate": "passed",
            "godot_version": runtime["godot_version"], "asset_count": count,
            "credits_sha256": _sha256(canonical / "CREDITS.md"),
            "manifest_sha256": _sha256(canonical / "asset_manifest.json"),
            "screenshot_sha256": None, "screenshot_dimensions": None,
            "preview_variation": None,
            "runtime_report_sha256": _sha256(runtime_dir / "report.json"),
            "assets": _evidence_entries(plan, plan_file, manifest),
            "command": argv, "returncode": None, "failure_reason": None,
        }
        try:
            try:
                proc = _command(argv, cwd=canonical, timeout=timeout)
                report["returncode"] = proc.returncode
                (staging / "gallery.stdout.txt").write_text(proc.stdout, encoding="utf-8")
                (staging / "gallery.stderr.txt").write_text(proc.stderr, encoding="utf-8")
                capture_file = canonical / "evidence" / "gallery-runtime.json"
                screenshot = canonical / "evidence" / "gallery.png"
                valid = False
                if capture_file.is_file():
                    captured = _read_object(capture_file)
                    valid = (
                        captured.get("status") == "captured"
                        and captured.get("asset_count") == count
                        and captured.get("loaded_count") == count
                        and captured.get("errors") == []
                        and captured.get("width") == 960
                        and captured.get("height") == 540
                    )
                if proc.returncode == 0 and valid and screenshot.is_file():
                    with Image.open(screenshot) as img:
                        if img.format != "PNG" or img.size != (960, 540):
                            report["failure_reason"] = "Invalid gallery screenshot format or size"
                        else:
                            deviation = max(ImageStat.Stat(img.convert("RGB")).stddev)
                            report["preview_variation"] = round(deviation, 3)
                            if deviation < 4:
                                report["failure_reason"] = "Gallery is nearly uniform; renderer may be blank"
                            else:
                                shutil.copyfile(screenshot, staging / "gallery.png")
                                report["screenshot_sha256"] = _sha256(staging / "gallery.png")
                                report["screenshot_dimensions"] = [960, 540]
                                report["status"] = "captured"
                else:
                    report["failure_reason"] = "Godot did not provide a valid rendered gallery"
            except (subprocess.TimeoutExpired, OSError, ValueError, json.JSONDecodeError) as exc:
                report["failure_reason"] = f"Gallery renderer failed: {exc}"
            write_json(staging / "report.json", report)
            (staging / "CREDITS.md").write_bytes((canonical / "CREDITS.md").read_bytes())
            _commit_evidence(staging, target, force=force)
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
    return _read_object(target / "report.json"), target


def review_release(
    plan_path: str | Path,
    project_dir: str | Path,
    gallery_dir: str | Path,
    *,
    review_path: str | Path | None = None,
    output_path: str | Path | None = None,
    force: bool = False,
) -> tuple[dict, Path | None]:
    """Verify a human review binds to a real captured gallery and fresh rights.

    Does not upload, publish, or authorize standalone asset redistribution.
    """
    plan_file = Path(plan_path).resolve()
    folder = Path(gallery_dir)
    if folder.is_symlink():
        raise ValueError("Gallery evidence directory may not be a symlink")
    evidence = _read_object(folder / "report.json")
    screenshot = folder / "gallery.png"
    credits = folder / "CREDITS.md"
    with tempfile.TemporaryDirectory(prefix="maf-release-gate-") as tmp:
        plan, canonical, manifest = _validate_plan_project(
            plan_file, Path(project_dir), Path(tmp)
        )
        if evidence.get("project_id") != plan.project_id:
            raise ValueError("Gallery project ID mismatch")
        if evidence.get("status") != "captured":
            raise ValueError("Gallery must be successfully captured")
        if screenshot.is_symlink() or credits.is_symlink():
            raise ValueError("Gallery artifacts cannot be symlinks")
        if not screenshot.is_file() or not credits.is_file():
            raise ValueError("Gallery screenshot or credits missing")
        if _sha256(screenshot) != evidence.get("screenshot_sha256"):
            raise ValueError("Gallery screenshot hash mismatch")
        if _sha256(credits) != evidence.get("credits_sha256"):
            raise ValueError("Gallery credits hash mismatch")
        if _sha256(canonical / "CREDITS.md") != evidence.get("credits_sha256"):
            raise ValueError("Attribution changed since gallery capture")
        if _sha256(canonical / "asset_manifest.json") != evidence.get("manifest_sha256"):
            raise ValueError("Asset manifest changed since gallery capture")
        if evidence.get("assets") != _evidence_entries(plan, plan_file, manifest):
            raise ValueError("License/asset intake evidence changed since gallery capture")
        with Image.open(screenshot) as image:
            if image.format != "PNG" or image.size != (960, 540):
                raise ValueError("Invalid gallery screenshot")

        reasons = []
        reviewer = None
        if review_path is None:
            reasons.append("Human visual, attribution, and embedding-rights review required")
        else:
            review = GalleryReview.model_validate(_read_object(Path(review_path)))
            reviewer = review.reviewer
            if review.project_id != plan.project_id:
                reasons.append("Review project ID mismatch")
            if review.screenshot_sha256 != evidence.get("screenshot_sha256"):
                reasons.append("Review screenshot hash mismatch")
            if review.credits_sha256 != evidence.get("credits_sha256"):
                reasons.append("Review credits hash mismatch")
            if review.manifest_sha256 != evidence.get("manifest_sha256"):
                reasons.append("Review manifest hash mismatch")
            if not review.visual_approved:
                reasons.append("Visual review not approved")
            if not review.attribution_approved:
                reasons.append("Credits review not approved")
            if not review.rights_approved_for_game_embedding:
                reasons.append("Game embedding rights not approved by reviewer")
        report = {
            "schema_version": "0.1", "project_id": plan.project_id,
            "status": "human_review_required" if reasons else "human_release_review_passed",
            "reviewer": reviewer, "reasons": reasons,
            "gallery_sha256": evidence["screenshot_sha256"],
            "credits_sha256": evidence["credits_sha256"],
            "manifest_sha256": evidence["manifest_sha256"],
            "asset_count": manifest["asset_count"],
            "publication_approved": False,
            "asset_pack_redistribution_approved": False,
            "no_publication_performed": True,
            "notes": "Human-reviewed for game embedding only; publication policies remain separate.",
        }
    destination = Path(output_path) if output_path else None
    if destination:
        if destination.exists() and not force:
            raise FileExistsError(f"Release review report already exists: {destination}")
        write_json(destination, report)
    return report, destination
