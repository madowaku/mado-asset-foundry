"""M0.8.2k: capture contracts and visual promotion with real valid PNG fixtures.

Subprocess behavior is mocked in CI. Real desktop capture requires opt-in.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from PIL import Image, ImageDraw
from typer.testing import CliRunner

from mado_asset_foundry.cli import app
from mado_asset_foundry.skills.adapters.effekseer_vfx_dogfood import (
    RealGodotFilmstripDogfood, _validate_capture,
)
from mado_asset_foundry.skills.adapters.effekseer_vfx_skill import (
    RUBRIC, SKILL_PATHS, UPSTREAM_REF, VfxSkillBridgeError,
)

EFFECT = "VFX_Hit_Spark"
EID = "b" * 32


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding="utf-8")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def picture(path: Path, scene: int, *, w: int = 256, h: int = 256):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (w, h), (8, 12, 22))
    if scene:
        ImageDraw.Draw(img).ellipse((24 + scene * 18, 90, 72 + scene * 18, 140), fill=(240, 180, 30))
    img.save(path)


def setup(tmp_path: Path, monkeypatch):
    checkout = tmp_path / "skill"
    for name in SKILL_PATHS:
        path = checkout / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fake skill fixture", encoding="utf-8")
    cmd = checkout / "skills/effekseer-vfx/scripts/vfx.cmd"
    cmd.write_text("@echo off\r\n", encoding="utf-8")
    project = tmp_path / "game"
    (project / "vfx/src").mkdir(parents=True)
    write_json(project / "vfx/vfx_manifest.json", {"test": True})
    root = project / "vfx/work"
    frames = {}
    for number, scene in ((0, 0), (8, 1), (16, 2)):
        relative = f"vfx/previews/strips/runs/sample/frames/{EFFECT}_f{number:03}.png"
        picture(project / relative, scene)
        frames[relative] = sha(project / relative)
    images = {}
    for n in ("strip.png", "keyframes.png"):
        relative = f"vfx/previews/strips/runs/sample/{n}"
        picture(project / relative, 1)
        images[relative] = sha(project / relative)
    overview_relative = "vfx/previews/strips/overview_0.png"
    picture(project / overview_relative, 2)
    overview = {overview_relative: sha(project / overview_relative)}
    for ext, folder in (("efk", "exports"), ("efkefc", "effects")):
        artifact = project / f"vfx/{folder}/{EFFECT}.{ext}"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"compiled" + ext.encode())
    capture = {
        "schema_version": 1, "effect_id": EFFECT, "evidence_id": EID,
        "configuration": {"view": "standard", "profile": "default", "fps": 60, "resolution": [256, 256]},
        "capture": {"status": "complete", "activity_observed": True},
        "images": images, "frames": frames,
    }
    write_json(root / f"captures/{EID}.json", capture)
    write_json(root / f"latest/{EFFECT}_standard_default.json", {"evidence_id": EID})
    write_json(root / "overview.json", {"evidence": {EFFECT: EID}, "images": overview})
    def git(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, UPSTREAM_REF + "\n" if "rev-parse" in cmd else "", "")
    def runner(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 0, json.dumps({
            "ok": True, "effect_id": EFFECT, "verified": True, "issues": [], "evidence_id": EID,
        }), "")
    dogfood = RealGodotFilmstripDogfood(checkout=checkout, runner=runner, git_runner=git)
    log = []
    def command(project_dir, *args):
        log.append(args)
        if args[0] == "doctor":
            return {"ok": True, "modes": {"render": True, "build": True},
                    "workspace": {"initialized": True}, "toolchain": {"godot": "4.6.1.test"}}
        if args[0] == "review":
            return {"ok": True, "evidence": {EFFECT: EID}, "capture": {EFFECT: {"status": "complete"}}}
        if args[0] == "review-handoff":
            return {"ok": True, "effect_id": EFFECT, "evidence_id": EID,
                    "prompt_file": str(root / "handoff/brief.md"), "report_file": str(root / "handoff/report.json")}
        return {"ok": True}
    monkeypatch.setattr(dogfood, "_command", command)
    return dogfood, project, root, checkout, log


def review_submit(root: Path, checkout: Path):
    capture = json.loads((root / f"captures/{EID}.json").read_text())
    scores = {key: 2 for key in RUBRIC}
    review = {
        "evidence_id": EID, "reviewer": "isolated-agent-2", "independence": "host_attested",
        "rubric_sha256": sha(checkout / "skills/effekseer-vfx/assets/review_rubric.json"),
        "image_hashes": capture["images"],
        "observed_frames": [0, 8, 16],
        "report": {
            "id": EFFECT, "scores": scores, "worst": "read",
            "fix": "Strengthen the first two-frame contact flash",
            "verdict": "ship", "observed_frames": [0, 8, 16],
        },
    }
    write_json(root / f"reviews/{EID}.json", review)


def capture(dogfood, project: Path, tmp_path: Path):
    return dogfood.capture(project=project, effect_id=EFFECT,
                           output_dir=tmp_path / "capture", execute=True, allow_window=True)


def test_capture_invokes_actual_review_command_contract_and_pauses_for_reviewer(tmp_path, monkeypatch):
    dogfood, project, root, checkout, log = setup(tmp_path, monkeypatch)
    result = capture(dogfood, project, tmp_path)
    assert result["status"] == "awaiting_independent_review"
    assert result["frame_count"] == 3
    assert [step[0] for step in log] == [
        "doctor", "brief-validate", "lint", "build", "review", "review-handoff",
    ]
    assert ("build", "--ids", EFFECT) in log
    assert ("review", "--ids", EFFECT, "--note", "MAF filmstrip dogfood") in log
    assert ("review-handoff", EFFECT) in log
    data = json.loads(Path(result["manifest"]).read_text())
    assert data["capture"]["fps"] == 60 and data["capture"]["observed_motion"] is True
    assert data["source"]["ref"] == UPSTREAM_REF
    assert data["release_approved"] is False
    assert not (root / f"reviews/{EID}.json").exists()


@pytest.mark.parametrize("execute,window", [(False, False), (True, False), (False, True)])
def test_capture_requires_both_permissions_before_running(tmp_path, monkeypatch, execute, window):
    dogfood, project, _, _, log = setup(tmp_path, monkeypatch)
    with pytest.raises(VfxSkillBridgeError, match="--execute and --allow-window"):
        dogfood.capture(project=project, effect_id=EFFECT, output_dir=tmp_path / "capture",
                        execute=execute, allow_window=window)
    assert not log


def test_capture_rejects_doctor_render_incapability(tmp_path, monkeypatch):
    dogfood, project, _, _, log = setup(tmp_path, monkeypatch)
    def no_render(*args):
        return {"ok": True, "modes": {"render": False, "build": True},
                "workspace": {"initialized": True}}
    monkeypatch.setattr(dogfood, "_command", no_render)
    with pytest.raises(VfxSkillBridgeError, match="doctor"):
        capture(dogfood, project, tmp_path)


def test_capture_fails_closed_on_static_filmstrip(tmp_path, monkeypatch):
    dogfood, project, root, _, _ = setup(tmp_path, monkeypatch)
    record_path = root / f"captures/{EID}.json"
    record = json.loads(record_path.read_text())
    baseline = next(project / name for name in record["frames"] if "_f000.png" in name)
    for name in record["frames"]:
        path = project / name
        path.write_bytes(baseline.read_bytes())
        record["frames"][name] = sha(path)
    write_json(record_path, record)
    with pytest.raises(VfxSkillBridgeError, match="No observable pixel changes"):
        capture(dogfood, project, tmp_path)


def test_capture_rejects_corrupted_png(tmp_path, monkeypatch):
    dogfood, project, root, _, _ = setup(tmp_path, monkeypatch)
    record = json.loads((root / f"captures/{EID}.json").read_text())
    first_name = next(iter(record["images"]))
    (project / first_name).write_bytes(b"not a PNG")
    record["images"][first_name] = sha(project / first_name)
    write_json(root / f"captures/{EID}.json", record)
    with pytest.raises(VfxSkillBridgeError, match="Invalid captured PNG"):
        capture(dogfood, project, tmp_path)


def test_promotion_accepts_matching_independent_review_and_archives_real_png(tmp_path, monkeypatch):
    dogfood, project, root, checkout, log = setup(tmp_path, monkeypatch)
    result = capture(dogfood, project, tmp_path)
    review_submit(root, checkout)
    promotion = dogfood.promote(capture_manifest=result["manifest"],
                               output_dir=tmp_path / "promotion",
                               execute=True, license_reviewed=True)
    assert promotion["status"] == "visual_evidence_promoted"
    assert promotion["archived_images"] == 6
    report = json.loads(Path(promotion["evidence"]).read_text())
    assert report["evidence_id"] == EID
    assert report["release_approved"] is False
    assert report["game_runtime_verified"] is False
    assert report["device_performance_verified"] is False
    assert set(report["artifacts"]) == {"source", "runtime"}
    for name, expected in report["visual_proof_files"].items():
        assert sha(tmp_path / "promotion" / "visual-proof" / name) == expected


def test_promotion_cannot_be_implicit(tmp_path, monkeypatch):
    dogfood, project, root, checkout, _ = setup(tmp_path, monkeypatch)
    result = capture(dogfood, project, tmp_path)
    review_submit(root, checkout)
    with pytest.raises(VfxSkillBridgeError, match="--license-reviewed"):
        dogfood.promote(capture_manifest=result["manifest"], output_dir=tmp_path / "promotion",
                        execute=True, license_reviewed=False)


def test_promotion_blocks_missing_independent_report(tmp_path, monkeypatch):
    dogfood, project, _, _, _ = setup(tmp_path, monkeypatch)
    result = capture(dogfood, project, tmp_path)
    with pytest.raises(VfxSkillBridgeError, match="Missing or oversized evidence"):
        dogfood.promote(capture_manifest=result["manifest"], output_dir=tmp_path / "promotion",
                        execute=True, license_reviewed=True)
    assert not (tmp_path / "promotion/visual-promotion.json").exists()


def test_promotion_blocks_modified_capture_frame(tmp_path, monkeypatch):
    dogfood, project, root, checkout, _ = setup(tmp_path, monkeypatch)
    result = capture(dogfood, project, tmp_path)
    review_submit(root, checkout)
    frame = next(iter(json.loads((root / f"captures/{EID}.json").read_text())["frames"]))
    picture(project / frame, 3)
    with pytest.raises(VfxSkillBridgeError, match="changed file"):
        dogfood.promote(capture_manifest=result["manifest"], output_dir=tmp_path / "promotion",
                        execute=True, license_reviewed=True)


def test_promotion_blocks_capture_receipt_replacement(tmp_path, monkeypatch):
    dogfood, project, root, checkout, _ = setup(tmp_path, monkeypatch)
    result = capture(dogfood, project, tmp_path)
    review_submit(root, checkout)
    path = root / f"captures/{EID}.json"
    data = json.loads(path.read_text())
    data["note"] = "modified after capture"
    write_json(path, data)
    with pytest.raises(VfxSkillBridgeError, match="since dogfood"):
        dogfood.promote(capture_manifest=result["manifest"], output_dir=tmp_path / "promotion",
                        execute=True, license_reviewed=True)


def test_upstream_reviewer_changed_to_different_evidence_blocks_promotion(tmp_path, monkeypatch):
    dogfood, project, root, checkout, _ = setup(tmp_path, monkeypatch)
    result = capture(dogfood, project, tmp_path)
    review_submit(root, checkout)
    orig = dogfood._bridge
    def incompatible():
        adapter = orig()
        class Imposter:
            def check_source(self): return adapter.check_source()
            def run(self, job):
                from mado_asset_foundry.skills.adapters.models import AssetSkillResult
                target = Path(job.output_dir)
                target.mkdir(parents=True)
                report_path = target / "review-bridge-report.json"
                write_json(report_path, {
                    "verified_visual": True,
                    "visual_evidence": {"evidence_id": "c" * 32},
                })
                return AssetSkillResult(
                    skill_id="effekseer-vfx-skill-snapshot", adapter_id="test",
                    capability=job.capability, status="success", input_path=job.input_path,
                    evidence_path=str(report_path), message="imposter",
                )
        return Imposter()
    monkeypatch.setattr(dogfood, "_bridge", incompatible)
    with pytest.raises(VfxSkillBridgeError, match="another capture"):
        dogfood.promote(capture_manifest=result["manifest"], output_dir=tmp_path / "promotion",
                        execute=True, license_reviewed=True)


def test_output_immutable_and_never_overwrites(tmp_path, monkeypatch):
    dogfood, project, root, checkout, _ = setup(tmp_path, monkeypatch)
    result = capture(dogfood, project, tmp_path)
    with pytest.raises(VfxSkillBridgeError, match="new directory"):
        capture(dogfood, project, tmp_path)
    review_submit(root, checkout)
    dogfood.promote(capture_manifest=result["manifest"], output_dir=tmp_path / "promotion",
                    execute=True, license_reviewed=True)
    with pytest.raises(VfxSkillBridgeError, match="new directory"):
        dogfood.promote(capture_manifest=result["manifest"], output_dir=tmp_path / "promotion",
                        execute=True, license_reviewed=True)


def test_cli_capture_requires_explicit_opt_in():
    response = CliRunner().invoke(app, [
        "skill", "vfx-filmstrip-capture", "C:/nothing", "--effect-id", EFFECT,
        "--skill-checkout", "C:/notinstalled", "--output-dir", "C:/no-write",
    ])
    assert response.exit_code == 1
    assert "--execute and --allow-window" in response.output
