"""Contract tests: all upstream execution is simulated, no Godot/installer is launched."""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mado_asset_foundry.cli import app
from mado_asset_foundry.skills.adapters.catalog import get_adapter_definition, has_execution_adapter
from mado_asset_foundry.skills.adapters.effekseer_vfx_skill import (
    UPSTREAM_REF, RUBRIC, SKILL_ID, SKILL_PATHS, EffekseerVfxSkillReviewBridge,
    VfxSkillBridgeError,
)
from mado_asset_foundry.skills.adapters.models import AssetSkillJob
from mado_asset_foundry.skills.scanner import scan_skill


EFFECT = "VFX_Hit_Spark"
EID = "a" * 32


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _create(tmp_path: Path):
    checkout = tmp_path / "checkout"
    for name in SKILL_PATHS:
        f = checkout / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("MIT license and pinned skill test contents", encoding="utf-8")
    windows_entry = checkout / "skills/effekseer-vfx/scripts/vfx.cmd"
    windows_entry.write_text("@echo off\r\n", encoding="utf-8")
    project = tmp_path / "game"
    (project / "vfx/src").mkdir(parents=True)
    _json(project / "vfx/vfx_manifest.json", {"ignored_by_bridge": True})
    game_artifacts = {
        "vfx/effects/VFX_Hit_Spark.efkefc": b"source-effekseer",
        "vfx/exports/VFX_Hit_Spark.efk": b"runtime-effekseer",
        "vfx/previews/strips/VFX_Hit_Spark.png": b"\x89PNG\r\n\x1a\n" + b"F" * 128,
        "vfx/previews/strips/frames/VFX_Hit_Spark_f0.png": b"\x89PNG\r\n\x1a\n" + b"G" * 128,
        "vfx/previews/strips/overview_0.png": b"\x89PNG\r\n\x1a\n" + b"O" * 128,
    }
    for name, content in game_artifacts.items():
        path = project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    image = "vfx/previews/strips/VFX_Hit_Spark.png"
    frame = "vfx/previews/strips/frames/VFX_Hit_Spark_f0.png"
    overview = "vfx/previews/strips/overview_0.png"
    root = project / "vfx/work"
    capture = {
        "schema_version": 1, "effect_id": EFFECT, "evidence_id": EID,
        "capture": {"status": "complete"},
        "configuration": {"view": "standard", "profile": "default"},
        "images": {image: _sha(project / image)},
        "frames": {frame: _sha(project / frame)},
    }
    _json(root / f"captures/{EID}.json", capture)
    scores = {key: 2 for key in RUBRIC}
    review = {
        "evidence_id": EID, "reviewer": "agent:independent-reviewer",
        "independence": "host_attested",
        "image_hashes": capture["images"],
        "rubric_sha256": _sha(checkout / "skills/effekseer-vfx/assets/review_rubric.json"),
        "observed_frames": [0],
        "report": {"id": EFFECT, "scores": scores, "worst": "read",
                   "fix": "Keep the first contact flash distinct on frame 0",
                   "verdict": "ship", "observed_frames": [0]},
    }
    _json(root / f"reviews/{EID}.json", review)
    _json(root / f"latest/{EFFECT}_standard_default.json", {"evidence_id": EID})
    _json(root / "overview.json", {
        "evidence": {EFFECT: EID}, "images": {overview: _sha(project / overview)},
    })
    return checkout, project, root


def _git_ok(command, **kwargs):
    if "rev-parse" in command:
        return subprocess.CompletedProcess(command, 0, UPSTREAM_REF + "\n", "")
    return subprocess.CompletedProcess(command, 0, "", "")


def _upstream(verified=True, issues=None, *, code=None):
    result = {
        "ok": True, "effect_id": EFFECT, "verified": verified,
        "issues": [] if issues is None else issues, "evidence_id": EID if verified else None,
    }
    return subprocess.CompletedProcess(["upstream"], int(not verified) if code is None else code,
                                       json.dumps(result), "")


def _bridge(tmp_path, *, upstream=None, git=None):
    checkout, project, root = _create(tmp_path)
    calls = []
    def runner(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return upstream if upstream is not None else _upstream()
    adapter = EffekseerVfxSkillReviewBridge(checkout=checkout, runner=runner, git_runner=git or _git_ok)
    job = AssetSkillJob(capability="vfx_visual_review", input_path=str(project),
                        output_dir=str(tmp_path / "maf-evidence"),
                        options={"effect_id": EFFECT, "execute": True})
    return adapter, job, calls, checkout, project, root


def test_snapshot_scans_license_and_review_taxonomy(tmp_path):
    manifest, _, _ = scan_skill(
        "fixtures/skills/effekseer-vfx-skill-snapshot",
        manifest_dir=tmp_path / "manifests", evidence_dir=tmp_path / "scan",
    )
    assert manifest.source.upstream_ref == UPSTREAM_REF
    assert manifest.license.spdx == "MIT"
    assert "vfx_visual_review" in manifest.capabilities
    definition = get_adapter_definition(SKILL_ID)
    assert definition is not None and definition.execution_implemented
    assert definition.capabilities == ["vfx_visual_review"]
    assert has_execution_adapter(SKILL_ID)


def test_success_reconciles_godot_filmstrip_reviewer_and_compiled_artifacts(tmp_path):
    adapter, job, calls, _, project, _ = _bridge(tmp_path)
    result = adapter.run(job)
    assert result.status == "success"
    assert result.metadata["verified_visual"] is True
    assert result.metadata["game_runtime_verified"] is False
    assert len(calls) == 1
    argv, opts = calls[0]
    assert argv[-4:] == ["--project", str(project), "effect-verify", EFFECT]
    assert opts["cwd"] == project and opts["stdin"] == subprocess.DEVNULL
    report = json.loads(Path(result.evidence_path).read_text())
    assert report["status"] == "verified_visual"
    assert not report["release_approved"]
    assert set(report["visual_evidence"]["scores"]) == RUBRIC
    assert len(report["visual_evidence"]["capture_images"]) == 1
    assert len(report["visual_evidence"]["capture_frames"]) == 1
    assert len(report["visual_evidence"]["overview_images"]) == 1
    assert set(report["visual_evidence"]["artifacts"]) == {"source", "runtime"}


def test_not_verified_is_hold_not_success(tmp_path):
    adapter, job, calls, _, _, _ = _bridge(tmp_path, upstream=_upstream(False, ["missing_independent_review"]))
    result = adapter.run(job)
    assert result.status == "skipped"
    assert json.loads(Path(result.evidence_path).read_text())["status"] == "hold_not_verified"
    assert len(calls) == 1


def test_execution_is_opt_in_before_upstream_source_inspection(tmp_path):
    adapter, job, calls, _, _, _ = _bridge(tmp_path)
    job.options["execute"] = False
    with pytest.raises(VfxSkillBridgeError, match="--execute"):
        adapter.run(job)
    assert not calls and not Path(job.output_dir).exists()


@pytest.mark.parametrize("bad_effect", ["VFX_../etc", "VFX_", "VFX_A && echo bad", "foo"])
def test_effect_id_rejects_injection_before_execution(tmp_path, bad_effect):
    adapter, job, calls, _, _, _ = _bridge(tmp_path)
    job.options["effect_id"] = bad_effect
    with pytest.raises(VfxSkillBridgeError, match="effect ID"):
        adapter.run(job)
    assert not calls


def test_source_checkout_rejects_wrong_revision(tmp_path):
    def wrong_git(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "0" * 40 if "rev-parse" in command else "", "")
    adapter, job, calls, _, _, _ = _bridge(tmp_path, git=wrong_git)
    with pytest.raises(VfxSkillBridgeError, match="pinned"):
        adapter.run(job)
    assert not calls


def test_source_checkout_rejects_dirty_sources(tmp_path):
    def dirty_git(command, **kwargs):
        return subprocess.CompletedProcess(command, 0,
            UPSTREAM_REF if "rev-parse" in command else " M skills/effekseer-vfx/scripts/vfx", "")
    adapter, job, calls, _, _, _ = _bridge(tmp_path, git=dirty_git)
    with pytest.raises(VfxSkillBridgeError, match="dirty"):
        adapter.run(job)
    assert not calls


def test_changed_png_prevents_promotion_without_evidence_output(tmp_path):
    adapter, job, _, _, project, _ = _bridge(tmp_path)
    (project / "vfx/previews/strips/VFX_Hit_Spark.png").write_bytes(b"tampered image")
    with pytest.raises(VfxSkillBridgeError, match="changed"):
        adapter.run(job)
    assert not Path(job.output_dir).exists()


def test_review_submitted_by_author_cannot_pass(tmp_path):
    adapter, job, _, _, _, root = _bridge(tmp_path)
    path = root / f"reviews/{EID}.json"
    data = json.loads(path.read_text())
    data["reviewer"] = "author"
    _json(path, data)
    with pytest.raises(VfxSkillBridgeError, match="Independent reviewer"):
        adapter.run(job)


def test_review_with_low_score_cannot_pass(tmp_path):
    adapter, job, _, _, _, root = _bridge(tmp_path)
    path = root / f"reviews/{EID}.json"
    data = json.loads(path.read_text())
    data["report"]["scores"]["read"] = 1
    data["report"]["verdict"] = "iterate"
    _json(path, data)
    with pytest.raises(VfxSkillBridgeError, match="Eight visual quality scores"):
        adapter.run(job)


def test_review_loses_rubric_integrity(tmp_path):
    adapter, job, _, _, _, root = _bridge(tmp_path)
    path = root / f"reviews/{EID}.json"
    data = json.loads(path.read_text())
    data["rubric_sha256"] = "0" * 64
    _json(path, data)
    with pytest.raises(VfxSkillBridgeError, match="rubric"):
        adapter.run(job)


def test_symlink_capture_cannot_escape_project(tmp_path):
    adapter, job, _, _, project, root = _bridge(tmp_path)
    image = "vfx/previews/strips/VFX_Hit_Spark.png"
    outsider = tmp_path / "outside.png"
    outsider.write_bytes(b"outside")
    (project / image).unlink()
    try:
        (project / image).symlink_to(outsider)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks require elevated permission on this system")
    record = json.loads((root / f"captures/{EID}.json").read_text())
    record["images"][image] = _sha(outsider)
    _json(root / f"captures/{EID}.json", record)
    with pytest.raises(VfxSkillBridgeError, match="filmstrip"):
        adapter.run(job)


def test_unverified_upstream_cannot_return_success_exit_status_with_verified_true(tmp_path):
    adapter, job, _, _, _, _ = _bridge(tmp_path, upstream=_upstream(True, ["review_changed"], code=0))
    with pytest.raises(VfxSkillBridgeError, match="contradicts"):
        adapter.run(job)


def test_output_is_immutable(tmp_path):
    adapter, job, _, _, _, _ = _bridge(tmp_path)
    assert adapter.run(job).status == "success"
    with pytest.raises(VfxSkillBridgeError, match="fresh evidence"):
        adapter.run(job)


def test_cli_requires_explicit_execute_flag(tmp_path):
    result = CliRunner().invoke(app, [
        "skill", "vfx-skill-review-bridge", str(tmp_path / "game"),
        "--effect-id", EFFECT, "--skill-checkout", str(tmp_path / "checkout"),
        "--output-dir", str(tmp_path / "out"),
    ])
    assert result.exit_code == 1
    assert "--execute" in result.output
