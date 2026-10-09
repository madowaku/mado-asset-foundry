from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from PIL import Image, ImageDraw
from typer.testing import CliRunner

import mado_asset_foundry.visual_gallery as gallery
from mado_asset_foundry.asset_sources import intake_asset
from mado_asset_foundry.attribution_bridge import compile_godot_import
from mado_asset_foundry.cli import app
from mado_asset_foundry.io import write_json

runner = CliRunner()


def setup_input(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    source = input_dir / "icon.png"
    Image.new("RGBA", (24, 24), (0, 200, 120, 255)).save(source)
    license_path = input_dir / "LICENSE.txt"
    license_path.write_text("MAF original synthetic test: CC0-1.0", encoding="utf-8")
    submission = input_dir / "submission.yaml"
    submission.write_text(yaml.safe_dump({
        "asset_id": "test-icon", "source_id": "local", "title": "Original asset",
        "creator": "Test creator", "local_file": "icon.png",
        "license_spdx": "CC0-1.0", "license_evidence_file": "LICENSE.txt",
        "reviewed_by_human": True, "use_case": "game_embedding",
    }), encoding="utf-8")
    intake_asset(submission, output_root=tmp_path / "reports")
    plan = tmp_path / "plan.json"
    write_json(plan, {
        "project_id": "test-gallery",
        "assets": [{"submission": "input/submission.yaml", "report": "reports/test-icon/report.json"}],
    })
    _, project = compile_godot_import(plan, output_root=tmp_path / "projects")
    return plan, project, source, license_path


def fake_render(monkeypatch: pytest.MonkeyPatch, *, blank: bool = False, fail: bool = False) -> list:
    calls = []
    monkeypatch.setattr(gallery, "_resolve_binary", lambda _: "godot")

    def fake_runtime(plan, project, *, godot_bin, output_root, timeout):
        folder = Path(output_root) / "test-gallery"
        folder.mkdir(parents=True)
        write_json(folder / "report.json", {
            "status": "passed", "godot_version": "4.6.1.stable",
        })
        return {"status": "passed", "godot_version": "4.6.1.stable"}, folder

    def fake_command(args, *, cwd, timeout):
        calls.append(args)
        if "--import" in args:
            return subprocess.CompletedProcess(args, 0, "import-ok", "")
        if fail:
            return subprocess.CompletedProcess(args, 1, "", "renderer failed")
        image = Image.new("RGB", (960, 540), (10, 10, 10))
        if not blank:
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 200, 200), fill=(210, 80, 120))
        image.save(cwd / "evidence" / "gallery.png")
        write_json(cwd / "evidence" / "gallery-runtime.json", {
            "status": "captured", "asset_count": 1,
            "loaded_count": 1, "errors": [],
            "width": 960, "height": 540,
        })
        return subprocess.CompletedProcess(args, 0, "captured", "")

    monkeypatch.setattr(gallery, "verify_godot_import", fake_runtime)
    monkeypatch.setattr(gallery, "_command", fake_command)
    return calls


def reviewed(evidence: Path, path: Path, **changes) -> Path:
    report = json.loads((evidence / "report.json").read_text(encoding="utf-8"))
    review = {
        "project_id": report["project_id"], "reviewer": "human qa reviewer",
        "screenshot_sha256": report["screenshot_sha256"],
        "credits_sha256": report["credits_sha256"],
        "manifest_sha256": report["manifest_sha256"],
        "visual_approved": True, "attribution_approved": True,
        "rights_approved_for_game_embedding": True,
        "notes": "Inspected the gallery preview, attribution, and source rights.",
    }
    review.update(changes)
    write_json(path, review)
    return path


def test_gallery_capture_and_human_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, _ = setup_input(tmp_path)
    calls = fake_render(monkeypatch)
    report, evidence = gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    assert report["status"] == "captured"
    assert report["attribution_release_gate"] == "human_review_required"
    assert report["publication_approved"] is False
    assert report["assets"][0]["license_evidence_sha256"]
    assert report["screenshot_sha256"]
    assert len(calls) == 2 and "--import" in calls[0] and "--headless" not in calls[1]
    assert (evidence / "gallery.png").is_file()
    review_gate, _ = gallery.review_release(plan, project, evidence)
    assert review_gate["status"] == "human_review_required"
    review_file = reviewed(evidence, tmp_path / "review.json")
    gate, written = gallery.review_release(plan, project, evidence, review_path=review_file, output_path=tmp_path / "gate.json")
    assert gate["status"] == "human_release_review_passed"
    assert gate["publication_approved"] is False
    assert written and written.is_file()


def test_gallery_tamper_preflight_no_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, _ = setup_input(tmp_path)
    (project / "CREDITS.md").write_text("tampered", encoding="utf-8")
    calls = fake_render(monkeypatch)
    with pytest.raises(ValueError, match="mismatch"):
        gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    assert not calls


def test_gallery_source_evidence_changed_no_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, license_file = setup_input(tmp_path)
    license_file.write_text("rights removed", encoding="utf-8")
    calls = fake_render(monkeypatch)
    with pytest.raises(ValueError, match="stale"):
        gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    assert not calls


def test_gallery_blank_capture_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, _ = setup_input(tmp_path)
    fake_render(monkeypatch, blank=True)
    report, evidence = gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    assert report["status"] == "failed"
    assert "uniform" in report["failure_reason"]
    assert not (evidence / "gallery.png").exists()


def test_gallery_renderer_error_is_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, _ = setup_input(tmp_path)
    fake_render(monkeypatch, fail=True)
    report, evidence = gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    assert report["status"] == "failed"
    assert "renderer failed" in (evidence / "gallery.stderr.txt").read_text(encoding="utf-8")


def test_release_rejects_modified_screenshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, _ = setup_input(tmp_path)
    fake_render(monkeypatch)
    _, evidence = gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    reviewed(evidence, tmp_path / "review.json")
    with (evidence / "gallery.png").open("ab") as out:
        out.write(b"tampered")
    with pytest.raises(ValueError, match="hash mismatch"):
        gallery.review_release(plan, project, evidence, review_path=tmp_path / "review.json")


def test_release_rejects_review_hash_or_negative_approval(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, _ = setup_input(tmp_path)
    fake_render(monkeypatch)
    _, evidence = gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    rev = reviewed(evidence, tmp_path / "review.json", visual_approved=False, screenshot_sha256="0" * 64)
    result, _ = gallery.review_release(plan, project, evidence, review_path=rev)
    assert result["status"] == "human_review_required"
    assert len(result["reasons"]) == 2


def test_release_rejects_stale_input(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, source, _ = setup_input(tmp_path)
    fake_render(monkeypatch)
    _, evidence = gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    source.write_bytes(b"changed")
    with pytest.raises(Exception):
        gallery.review_release(plan, project, evidence)


def test_cli_gallery_and_release(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, _ = setup_input(tmp_path)
    fake_render(monkeypatch)
    args = ["asset-godot", "gallery", str(plan), str(project), "--godot-bin", "godot", "--output-root", str(tmp_path / "gallery")]
    res = runner.invoke(app, args)
    assert res.exit_code == 0, res.output
    evidence = tmp_path / "gallery" / "test-gallery"
    check = runner.invoke(app, ["asset-godot", "release-check", str(plan), str(project), str(evidence)])
    assert check.exit_code == 2, check.output
    review = reviewed(evidence, tmp_path / "review.json")
    check = runner.invoke(app, ["asset-godot", "release-check", str(plan), str(project), str(evidence), "--review", str(review)])
    assert check.exit_code == 0, check.output
    assert "Publication approved: NO" in check.output


def test_no_silent_gallery_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    plan, project, _, _ = setup_input(tmp_path)
    fake_render(monkeypatch)
    gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
    with pytest.raises(FileExistsError):
        gallery.render_gallery(plan, project, godot_bin="godot", output_root=tmp_path / "gallery")
