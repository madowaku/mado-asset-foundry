"""MAF-M0.8.2k: opt-in real Godot filmstrip dogfood and visual promotion.

Uses the pinned KanaWorks toolchain already installed by the operator. Captures
actual Godot frames, pauses for external independent review, and only promotes
a verified unchanged capture after the M0.8.2j evidence bridge approves it.

No upstream installation, sample fabrication, review submission, or release
approval occurs here.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from ...io import write_json
from .effekseer_vfx_skill import (
    EVIDENCE_RE,
    EffekseerVfxSkillReviewBridge,
    VfxSkillBridgeError,
    _object,
    _sha,
    _snapshot,
)
from .models import AssetSkillJob

SCHEMA = "maf.effekseer-vfx-filmstrip-dogfood.v1"
PROMOTION_SCHEMA = "maf.effekseer-vfx-visual-promotion.v1"
FRAME_PATTERN = re.compile(r"_f(\d+)\.png\Z")
VALID_ID = re.compile(r"VFX_[A-Za-z0-9_]+\Z")


def _sane_project(path: str | Path) -> Path:
    project = Path(path).expanduser().resolve(strict=True)
    if not project.is_dir() or not (project / "vfx/src").is_dir() or not (project / "vfx/vfx_manifest.json").is_file():
        raise VfxSkillBridgeError("Use an initialized KanaWorks VFX game project")
    return project


def _destination(path: str | Path, project: Path, skill: Path) -> Path:
    target = Path(path).expanduser().resolve()
    if target.exists() or target.is_relative_to(project) or target.is_relative_to(skill):
        raise VfxSkillBridgeError("Evidence output must be a new directory outside the game and Skill checkouts")
    return target


def _image_check(path: Path) -> tuple[int, int]:
    if not path.is_file() or path.stat().st_size > 90_000_000:
        raise VfxSkillBridgeError(f"Missing or excessive PNG: {path.name}")
    try:
        with Image.open(path) as im:
            if im.format != "PNG" or min(im.size) < 128 or max(im.size) > 8192:
                raise VfxSkillBridgeError(f"Not a plausible captured PNG: {path.name}")
            dims = im.size
            im.verify()
    except (OSError, Image.DecompressionBombError) as exc:
        raise VfxSkillBridgeError(f"Invalid captured PNG: {path.name}") from exc
    return dims


def _validate_capture(project: Path, effect_id: str, evidence_id: str) -> dict[str, Any]:
    if not isinstance(evidence_id, str) or not EVIDENCE_RE.fullmatch(evidence_id):
        raise VfxSkillBridgeError("Upstream capture did not return a valid evidence ID")
    work = project / "vfx/work"
    capture = _object(work / "captures" / f"{evidence_id}.json")
    pointer = _object(work / "latest" / f"{effect_id}_standard_default.json")
    state = capture.get("capture")
    config = capture.get("configuration")
    if (
        capture.get("effect_id") != effect_id
        or capture.get("evidence_id") != evidence_id
        or pointer.get("evidence_id") != evidence_id
        or not isinstance(state, dict)
        or state.get("status") != "complete"
        or state.get("activity_observed") is not True
        or not isinstance(config, dict)
        or config.get("fps") != 60
        or config.get("view") != "standard"
        or config.get("profile") != "default"
    ):
        raise VfxSkillBridgeError("Godot capture is missing, stale, nonstandard or inactive")
    images = _snapshot(capture.get("images"), project, "capture images")
    frames = _snapshot(capture.get("frames"), project, "capture frames")
    if len(frames) < 3:
        raise VfxSkillBridgeError("A real filmstrip requires at least three captured frames")
    image_dims = {_image_check(project / filename) for filename in images}
    if not image_dims:
        raise VfxSkillBridgeError("Missing filmstrip image")
    frame_dims = {_image_check(project / filename) for filename in frames}
    if len(frame_dims) != 1:
        raise VfxSkillBridgeError("Captured frames have mismatched dimensions")
    expected = config.get("resolution")
    actual = list(next(iter(frame_dims)))
    if expected != actual:
        raise VfxSkillBridgeError("Frame dimensions do not match Godot capture metadata")
    frame_paths = []
    for name in frames:
        match = FRAME_PATTERN.search(name)
        if not match:
            raise VfxSkillBridgeError("Unexpected frame filename in capture evidence")
        frame_paths.append((int(match.group(1)), project / name))
    frame_paths.sort()
    if frame_paths[0][0] != 0:
        raise VfxSkillBridgeError("Godot capture lacks the baseline frame zero")
    if len({n for n, _ in frame_paths}) != len(frame_paths):
        raise VfxSkillBridgeError("Duplicate frame labels")
    # Pixel activity must be observable, not just reported as a boolean.
    # Comparing up to 12 representative frames bounds decoding and CPU cost.
    baseline = frame_paths[0][1]
    samples = frame_paths[1::max(1, (len(frame_paths) - 1) // 12)][:12]
    with Image.open(baseline) as first:
        base = first.convert("RGB")
        different = False
        for _, path in samples:
            with Image.open(path) as candidate:
                if ImageChops.difference(base, candidate.convert("RGB")).getbbox() is not None:
                    different = True
                    break
    if not different:
        raise VfxSkillBridgeError("No observable pixel changes in sampled Godot frames")
    return {
        "evidence_id": evidence_id,
        "effect_id": effect_id,
        "capture_sha256": _sha(work / "captures" / f"{evidence_id}.json"),
        "frame_count": len(frames), "resolution": actual,
        "images": images, "frames": frames,
        "observed_motion": True, "fps": 60,
    }


class RealGodotFilmstripDogfood:
    """Two-phase operator-controlled capture followed by promotion."""

    def __init__(self, *, checkout: str | Path, runner=None, git_runner=None,
                 timeout_seconds: int = 900) -> None:
        self.checkout = Path(checkout).expanduser().resolve()
        self.runner = runner or subprocess.run
        self.git_runner = git_runner or subprocess.run
        if not 120 <= timeout_seconds <= 1800:
            raise VfxSkillBridgeError("Dogfood timeout must be between 120 and 1800 seconds")
        self.timeout_seconds = timeout_seconds

    def _bridge(self) -> EffekseerVfxSkillReviewBridge:
        return EffekseerVfxSkillReviewBridge(
            checkout=self.checkout, runner=self.runner, git_runner=self.git_runner,
            timeout_seconds=min(600, self.timeout_seconds),
        )

    def _command(self, project: Path, *args: str) -> dict[str, Any]:
        entry = self.checkout / "skills/effekseer-vfx/scripts"
        if __import__("os").name == "nt":
            cmd = [str(entry / "vfx.cmd")]
            if not (entry / "vfx.cmd").is_file():
                raise VfxSkillBridgeError("Windows upstream vfx.cmd does not exist")
        else:
            cmd = ["sh", str(entry / "vfx")]
        argv = [*cmd, "--project", str(project), *args]
        try:
            proc = self.runner(argv, cwd=project, capture_output=True, text=True,
                               check=False, stdin=subprocess.DEVNULL, timeout=self.timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VfxSkillBridgeError(f"Upstream {args[0]} could not complete") from exc
        try:
            payload = json.loads(proc.stdout.strip())
        except (ValueError, json.JSONDecodeError) as exc:
            raise VfxSkillBridgeError(f"Upstream {args[0]} did not return valid JSON") from exc
        if proc.returncode or not isinstance(payload, dict) or payload.get("ok") is not True:
            raise VfxSkillBridgeError(f"Upstream {args[0]} failed (exit={proc.returncode})")
        return payload

    def capture(self, *, project: str | Path, effect_id: str, output_dir: str | Path,
                execute: bool = False, allow_window: bool = False,
                note: str = "MAF filmstrip dogfood") -> dict[str, Any]:
        if not execute or not allow_window:
            raise VfxSkillBridgeError("Real capture requires --execute and --allow-window")
        if not isinstance(effect_id, str) or not VALID_ID.fullmatch(effect_id):
            raise VfxSkillBridgeError("Invalid effect ID")
        if not isinstance(note, str) or not 1 <= len(note.strip()) <= 200:
            raise VfxSkillBridgeError("Capture note must be 1-200 characters")
        bridge = self._bridge()
        provenance = bridge.check_source()
        root = _sane_project(project)
        target = _destination(output_dir, root, self.checkout)
        doctor = self._command(root, "doctor")
        if not doctor.get("modes", {}).get("render") or not doctor.get("modes", {}).get("build"):
            raise VfxSkillBridgeError("Upstream doctor did not confirm build and render capability")
        if doctor.get("workspace", {}).get("initialized") is not True:
            raise VfxSkillBridgeError("Upstream VFX workspace is not initialized")
        self._command(root, "brief-validate", effect_id)
        self._command(root, "lint", "--ids", effect_id)
        self._command(root, "build", "--ids", effect_id)
        result = self._command(root, "review", "--ids", effect_id, "--note", note.strip())
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise VfxSkillBridgeError("Upstream review did not emit evidence IDs")
        snapshot = _validate_capture(root, effect_id, evidence.get(effect_id))
        handoff = self._command(root, "review-handoff", effect_id)
        if handoff.get("evidence_id") != snapshot["evidence_id"] or handoff.get("effect_id") != effect_id:
            raise VfxSkillBridgeError("Reviewer handoff is not bound to the latest capture")
        # No reviewer report is fabricated here. A separate session must inspect
        # real frames and submit its own judgment before the promotion phase.
        manifest = {
            "schema": SCHEMA, "status": "awaiting_independent_review",
            "project": str(root), "effect_id": effect_id, "source": provenance,
            "capture": snapshot, "handoff": {
                "prompt_file": handoff.get("prompt_file"),
                "report_file": handoff.get("report_file"),
                "evidence_id": handoff["evidence_id"],
            },
            "godot_version_detected": doctor.get("toolchain", {}).get("godot"),
            "license_approved": False, "release_approved": False,
            "note": note.strip(),
        }
        target.mkdir(parents=True, exist_ok=False)
        write_json(target / "capture-dogfood.json", manifest)
        return {"status": manifest["status"], "manifest": str(target / "capture-dogfood.json"),
                "evidence_id": snapshot["evidence_id"], "frame_count": snapshot["frame_count"],
                "reviewer_handoff": manifest["handoff"]["prompt_file"]}

    def promote(self, *, capture_manifest: str | Path, output_dir: str | Path,
                execute: bool = False, license_reviewed: bool = False) -> dict[str, Any]:
        if not execute or not license_reviewed:
            raise VfxSkillBridgeError("Promotion requires --execute and --license-reviewed")
        receipt_path = Path(capture_manifest).expanduser().resolve(strict=True)
        receipt = _object(receipt_path)
        if receipt.get("schema") != SCHEMA or receipt.get("status") != "awaiting_independent_review":
            raise VfxSkillBridgeError("Not a valid pending dogfood capture")
        if receipt.get("source", {}).get("ref") != self._bridge().check_source()["ref"]:
            raise VfxSkillBridgeError("Pinned upstream provenance changed")
        root = _sane_project(receipt.get("project"))
        target = _destination(output_dir, root, self.checkout)
        snapshot = receipt.get("capture")
        if not isinstance(snapshot, dict):
            raise VfxSkillBridgeError("Missing immutable capture record")
        original_id = snapshot.get("evidence_id")
        effect_id = receipt.get("effect_id")
        if not isinstance(effect_id, str) or not VALID_ID.fullmatch(effect_id):
            raise VfxSkillBridgeError("Invalid effect ID in capture manifest")
        current = _validate_capture(root, effect_id, original_id)
        if snapshot != current:
            raise VfxSkillBridgeError("Captured filmstrip files or metadata changed since dogfood")
        target.mkdir(parents=True, exist_ok=False)
        # Reuse the M0.8.2j source, screenshot and reviewer verification.
        job = AssetSkillJob(
            capability="vfx_visual_review", input_path=str(root),
            output_dir=str(target / "upstream-visual-review"),
            options={"effect_id": effect_id, "execute": True},
        )
        result = self._bridge().run(job)
        visual_report = _object(Path(result.evidence_path))
        if (
            result.status != "success"
            or visual_report.get("verified_visual") is not True
            or visual_report.get("visual_evidence", {}).get("evidence_id") != original_id
        ):
            raise VfxSkillBridgeError("Independent review is absent, unapproved or bound to another capture")
        approved = visual_report["visual_evidence"]
        if approved.get("capture_sha256") not in (None, snapshot["capture_sha256"]):
            raise VfxSkillBridgeError("Capture digest changed")
        if approved["capture_images"] != snapshot["images"] or approved["capture_frames"] != snapshot["frames"]:
            raise VfxSkillBridgeError("Review-approved images do not match the dogfood capture")
        files = {**snapshot["images"], **approved["overview_images"]}
        available_frames = {}
        for name in snapshot["frames"]:
            m = FRAME_PATTERN.search(name)
            if m:
                available_frames[int(m.group(1))] = name
        for frame_id in approved["observed_frames"]:
            files[available_frames[frame_id]] = snapshot["frames"][available_frames[frame_id]]
        for rel, expected_sha in files.items():
            source = (root / rel).resolve()
            destination = target / "visual-proof" / rel
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
            if _sha(destination) != expected_sha:
                raise VfxSkillBridgeError("Archived filmstrip hash changed during copy")
        _validate_capture(root, effect_id, original_id)
        promoted = {
            "schema": PROMOTION_SCHEMA, "status": "visual_evidence_promoted",
            "source_capture_manifest_sha256": _sha(receipt_path),
            "source_review_report_sha256": _sha(Path(result.evidence_path)),
            "effect_id": effect_id, "evidence_id": original_id,
            "visual_proof_files": files, "review_scores": approved["scores"],
            "reviewer_independence": approved["reviewer_independence"],
            "artifacts": approved["artifacts"],
            "license_reviewed_operator_attestation": True,
            "game_runtime_verified": False, "device_performance_verified": False,
            "release_approved": False,
            "note": "QA evidence only; separate Godot runtime, performance and asset-rights gates still required.",
        }
        path = target / "visual-promotion.json"
        write_json(path, promoted)
        return {"status": promoted["status"], "evidence": str(path),
                "archived_images": len(files), "release_approved": False}
