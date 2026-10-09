from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from PIL import Image
from typer.testing import CliRunner

import mado_asset_foundry.runtime_import_qa as runtime
from mado_asset_foundry.asset_sources import intake_asset
from mado_asset_foundry.attribution_bridge import compile_godot_import
from mado_asset_foundry.cli import app

runner = CliRunner()


def setup_project(tmp_path: Path, *, license_id: str = "CC0-1.0") -> tuple[Path, Path, Path, Path]:
    assets = tmp_path / "input"
    assets.mkdir()
    img = assets / "icon.png"
    Image.new("RGBA", (12, 9), (220, 100, 30, 255)).save(img)
    license_file = assets / "LICENSE.txt"
    license_file.write_text("Synthetic fixture license: CC0", encoding="utf-8")
    sub = assets / "submission.yaml"
    sub.write_text(yaml.safe_dump({
        "asset_id": "sample-icon", "source_id": "local", "title": "Sample Icon",
        "creator": "MAF QA Fixture", "local_file": "icon.png",
        "license_spdx": license_id, "license_evidence_file": "LICENSE.txt",
        "reviewed_by_human": True, "use_case": "game_embedding",
    }), encoding="utf-8")
    intake_asset(sub, output_root=tmp_path / "reports")
    plan = tmp_path / "plan.json"
    plan.write_text(json.dumps({
        "project_id": "sample-project",
        "assets": [{
            "submission": "input/submission.yaml",
            "report": "reports/sample-icon/report.json"
        }],
    }), encoding="utf-8")
    _, project = compile_godot_import(plan, output_root=tmp_path / "projects")
    return plan, project, img, license_file


def fake_binary_ok(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(runtime, "_resolve_binary", lambda _: "godot")

    def execute(args: list[str], *, cwd: Path, timeout: int):
        calls.append(args)
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "4.6.1.stable\n", "")
        if "--script" in args:
            manifest = json.loads((cwd / "runtime_manifest.json").read_text(encoding="utf-8"))
            textures = [{
                "asset_id": item["asset_id"], "width": item["width"],
                "height": item["height"],
            } for item in manifest["assets"]]
            result = {
                "status": "passed", "asset_count": len(textures),
                "loaded_count": len(textures), "assets": textures, "errors": [],
            }
            (cwd / "evidence" / "runtime-import.json").write_text(
                json.dumps(result), encoding="utf-8"
            )
        return subprocess.CompletedProcess(args, 0, "mock-ok\n", "")

    monkeypatch.setattr(runtime, "_command", execute)
    return calls


def test_runtime_success_verifies_licensed_sources_and_godot_textures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    calls = fake_binary_ok(monkeypatch)
    report, evidence = runtime.verify_godot_import(
        plan, project, godot_bin="godot", output_root=tmp_path / "qa"
    )
    assert report["status"] == "passed"
    assert report["license_evidence_gate"] == "passed"
    assert report["input_integrity_gate"] == "passed"
    assert report["publication_approved"] is False
    assert report["loaded_count"] == 1
    assert report["runtime"]["assets"] == [
        {"asset_id": "sample-icon", "width": 12, "height": 9}
    ]
    assert any("--import" in args for args in calls)
    assert any("--script" in args for args in calls)
    assert (evidence / "import.stdout.txt").exists()


@pytest.mark.parametrize("target", ["CREDITS.md", "asset_manifest.json", "assets/sample-icon.png", "project.godot"])
def test_tampered_artifacts_block_before_any_runtime(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str,
) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    path = project / target
    path.write_bytes(path.read_bytes() + b"changed")
    calls = fake_binary_ok(monkeypatch)
    with pytest.raises(ValueError, match="file mismatch"):
        runtime.verify_godot_import(plan, project, godot_bin="godot", output_root=tmp_path / "qa")
    assert calls == []


def test_added_plugin_blocks_before_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    (project / "addons").mkdir()
    (project / "addons" / "evil.gd").write_text("extends EditorPlugin", encoding="utf-8")
    calls = fake_binary_ok(monkeypatch)
    with pytest.raises(ValueError, match="inventory mismatch"):
        runtime.verify_godot_import(plan, project, godot_bin="godot", output_root=tmp_path / "qa")
    assert calls == []


def test_changed_license_evidence_blocks_before_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, project, _, evidence_file = setup_project(tmp_path)
    evidence_file.write_text("changed license", encoding="utf-8")
    calls = fake_binary_ok(monkeypatch)
    with pytest.raises(ValueError, match="stale"):
        runtime.verify_godot_import(plan, project, godot_bin="godot", output_root=tmp_path / "qa")
    assert calls == []


def test_changed_source_blocks_before_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, project, source, _ = setup_project(tmp_path)
    Image.new("RGBA", (12, 9), (0, 0, 0, 255)).save(source)
    calls = fake_binary_ok(monkeypatch)
    with pytest.raises(ValueError, match="stale"):
        runtime.verify_godot_import(plan, project, godot_bin="godot", output_root=tmp_path / "qa")
    assert calls == []


def test_license_review_gate_blocks_before_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    sub = tmp_path / "input" / "submission.yaml"
    data = yaml.safe_load(sub.read_text(encoding="utf-8"))
    data["reviewed_by_human"] = False
    sub.write_text(yaml.safe_dump(data), encoding="utf-8")
    calls = fake_binary_ok(monkeypatch)
    with pytest.raises(ValueError, match="Current license gate"):
        runtime.verify_godot_import(plan, project, godot_bin="godot", output_root=tmp_path / "qa")
    assert calls == []


def test_import_failure_creates_truthful_evidence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    monkeypatch.setattr(runtime, "_resolve_binary", lambda _: "godot")

    def failing(args: list[str], *, cwd: Path, timeout: int):
        if "--version" in args:
            return subprocess.CompletedProcess(args, 0, "4.6.1.stable\n", "")
        return subprocess.CompletedProcess(args, 3, "", "import failure\n")

    monkeypatch.setattr(runtime, "_command", failing)
    report, evidence = runtime.verify_godot_import(
        plan, project, godot_bin="godot", output_root=tmp_path / "qa"
    )
    assert report["status"] == "failed"
    assert report["godot_executed"] is True
    assert report["failure_reason"] == "Godot import process failed"
    assert "import failure" in (evidence / "import.stderr.txt").read_text(encoding="utf-8")


def test_untrusted_zero_exit_without_runtime_report_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    monkeypatch.setattr(runtime, "_resolve_binary", lambda _: "godot")
    monkeypatch.setattr(
        runtime, "_command",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 0, "4.6.1.stable\n" if "--version" in args else "ok", ""
        ),
    )
    report, _ = runtime.verify_godot_import(
        plan, project, godot_bin="godot", output_root=tmp_path / "qa"
    )
    assert report["status"] == "failed"
    assert report["loaded_count"] == 0


def test_godot_3_never_imports(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    monkeypatch.setattr(runtime, "_resolve_binary", lambda _: "godot")
    calls = []

    def old_version(args: list[str], **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "3.6.stable", "")

    monkeypatch.setattr(runtime, "_command", old_version)
    report, _ = runtime.verify_godot_import(
        plan, project, godot_bin="godot", output_root=tmp_path / "qa"
    )
    assert report["status"] == "failed"
    assert "4.2+" in report["failure_reason"]
    assert len(calls) == 1


def test_no_overwrite_without_force(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    fake_binary_ok(monkeypatch)
    runtime.verify_godot_import(plan, project, godot_bin="godot", output_root=tmp_path / "qa")
    with pytest.raises(FileExistsError, match="already exists"):
        runtime.verify_godot_import(plan, project, godot_bin="godot", output_root=tmp_path / "qa")
    report, _ = runtime.verify_godot_import(
        plan, project, godot_bin="godot", output_root=tmp_path / "qa", force=True
    )
    assert report["status"] == "passed"


def test_cli_success_and_failures(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan, project, _, _ = setup_project(tmp_path)
    fake_binary_ok(monkeypatch)
    cmd = ["asset-godot", "qa", str(plan), str(project),
           "--godot-bin", "godot", "--output-root", str(tmp_path / "qa")]
    result = runner.invoke(app, cmd)
    assert result.exit_code == 0, result.output
    assert "Status: passed" in result.output
    result = runner.invoke(app, cmd)
    assert result.exit_code == 1, result.output
    assert "already exists" in result.output
