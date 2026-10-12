"""Pinned KanaWorks Effekseer VFX Skill -> MAF visual evidence bridge.

Only the upstream effect-verify command may execute, with explicit opt-in.
No setup, download, build, review authoring or Godot window is launched here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from ...io import write_json
from .models import AdapterDefinition, AssetSkillJob, AssetSkillResult

UPSTREAM_REF = "d2f28031ac62014f00e04b416dfe1a7f3818593d"
UPSTREAM_URL = "https://github.com/kanaworksai-hue/effekseer-vfx-skill"
SKILL_ID = "effekseer-vfx-skill-snapshot"
ADAPTER_ID = "effekseer-vfx-skill-review-bridge"
RUBRIC = frozenset(("read", "timing", "layering", "shape_change", "motion", "placement", "tail", "identity"))
ID_RE = re.compile(r"VFX_[A-Za-z0-9_]+\Z")
EVIDENCE_RE = re.compile(r"[a-f0-9]{32}\Z")
SHA_RE = re.compile(r"[a-f0-9]{64}\Z")
SKILL_PATHS = (
    "skills/effekseer-vfx/SKILL.md", "skills/vfx-review/SKILL.md",
    "skills/effekseer-vfx/scripts/vfx", "skills/effekseer-vfx/assets/review_rubric.json",
    "LICENSE", "THIRD_PARTY_NOTICES.md",
)

DEFINITION = AdapterDefinition(
    adapter_id=ADAPTER_ID, skill_id=SKILL_ID,
    capabilities=["vfx_visual_review"], execution_implemented=True, timeout_seconds=180,
    required_executables=["git"], required_env=["EFFEKSEER_VFX_SKILL_HOME"],
    source_env="EFFEKSEER_VFX_SKILL_HOME",
    required_source_files=list(SKILL_PATHS),
    notes=[
        "Pinned external Skill is MIT; bundled dependencies carry separate notices.",
        "Only effect-verify is executed; no setup or Godot rendering is performed by MAF.",
        "The upstream Godot plugin 1.80.5.1 differs from the existing MAF 1.80.7.",
        "Reviewer independence is host-attested, not cryptographically authenticated.",
    ],
)


class VfxSkillBridgeError(ValueError):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _object(path: Path) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > 4_000_000:
        raise VfxSkillBridgeError(f"Missing or oversized evidence: {path}")
    result = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise VfxSkillBridgeError("Evidence must be a JSON object")
    return result


def _snapshot(files: Any, root: Path, label: str) -> dict[str, str]:
    """Review only project-relative images. Reject symlinks leaving the project."""
    if not isinstance(files, dict) or not 1 <= len(files) <= 1000:
        raise VfxSkillBridgeError(f"{label}: empty or invalid snapshot")
    result = {}
    for relative, expected in sorted(files.items()):
        if not isinstance(relative, str) or not isinstance(expected, str) or not SHA_RE.fullmatch(expected):
            raise VfxSkillBridgeError(f"{label}: invalid hash entry")
        p = Path(relative)
        if not relative or p.is_absolute() or ":" in relative or "\\" in relative or ".." in p.parts:
            raise VfxSkillBridgeError(f"{label}: unsafe path")
        target = (root / p).resolve()
        if not target.is_relative_to(root) or not target.is_file() or _sha(target) != expected:
            raise VfxSkillBridgeError(f"{label}: missing or changed file {relative}")
        result[relative] = expected
    return result


def _visual_receipts(project: Path, checkout: Path, effect_id: str, evidence_id: Any) -> dict[str, Any]:
    if not isinstance(evidence_id, str) or not EVIDENCE_RE.fullmatch(evidence_id):
        raise VfxSkillBridgeError("Invalid upstream evidence ID")
    work = project / "vfx" / "work"
    capture_path = work / "captures" / f"{evidence_id}.json"
    review_path = work / "reviews" / f"{evidence_id}.json"
    overview_path = work / "overview.json"
    capture = _object(capture_path)
    review = _object(review_path)
    overview = _object(overview_path)
    pointer = _object(work / "latest" / f"{effect_id}_standard_default.json")
    if not (capture.get("schema_version") == 1
            and capture.get("evidence_id") == evidence_id
            and capture.get("effect_id") == effect_id
            and review.get("evidence_id") == evidence_id
            and pointer.get("evidence_id") == evidence_id
            and isinstance(overview.get("evidence"), dict)
            and overview["evidence"].get(effect_id) == evidence_id):
        raise VfxSkillBridgeError("Capture, independent review and overview refer to different versions")
    if capture.get("capture", {}).get("status") != "complete":
        raise VfxSkillBridgeError("Real Godot capture is incomplete")
    config = capture.get("configuration", {})
    if config.get("view") != "standard" or config.get("profile") != "default":
        raise VfxSkillBridgeError("Only standard Godot captures qualify")
    images = _snapshot(capture.get("images"), project, "filmstrip")
    frames = _snapshot(capture.get("frames"), project, "frames")
    overview_images = _snapshot(overview.get("images"), project, "overview")
    if review.get("image_hashes") != images:
        raise VfxSkillBridgeError("Review image hashes disagree with capture")
    rubric = checkout / "skills/effekseer-vfx/assets/review_rubric.json"
    if review.get("rubric_sha256") != _sha(rubric):
        raise VfxSkillBridgeError("Changed visual review rubric")
    reviewer = review.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip() or reviewer.strip().lower() in {"self", "author"}:
        raise VfxSkillBridgeError("Independent reviewer identifier is missing")
    if review.get("independence") != "host_attested":
        raise VfxSkillBridgeError("Host independent-review attestation is missing")
    report = review.get("report")
    if not isinstance(report, dict) or report.get("id") != effect_id:
        raise VfxSkillBridgeError("Review report effect ID mismatch")
    scores = report.get("scores")
    if not isinstance(scores, dict) or scores.keys() != RUBRIC or any(type(s) is not int or not 2 <= s <= 3 for s in scores.values()):
        raise VfxSkillBridgeError("Eight visual quality scores must pass")
    if report.get("verdict") != "ship" or report.get("worst") not in RUBRIC or scores[report["worst"]] != min(scores.values()):
        raise VfxSkillBridgeError("Review verdict and worst score do not agree")
    if not isinstance(report.get("fix"), str) or not report["fix"].strip():
        raise VfxSkillBridgeError("Review needs an actionable fix")
    observed = review.get("observed_frames")
    frames_available = {int(m.group(1)) for name in frames if (m := re.search(r"_f(\d+)\.png\Z", name))}
    if (not isinstance(observed, list) or not observed or
            any(type(n) is not int or n not in frames_available for n in observed)):
        raise VfxSkillBridgeError("Review cites frames absent from capture")
    if "observed_frames" in report and report["observed_frames"] != observed:
        raise VfxSkillBridgeError("Review and report frame lists differ")
    artifacts = {}
    for kind, relative in (
        ("source", f"vfx/effects/{effect_id}.efkefc"),
        ("runtime", f"vfx/exports/{effect_id}.efk"),
    ):
        target = (project / relative).resolve()
        if not target.is_relative_to(project) or not target.is_file() or not target.stat().st_size:
            raise VfxSkillBridgeError(f"Compiled effect artifact absent: {relative}")
        artifacts[kind] = {"path": relative, "sha256": _sha(target), "size_bytes": target.stat().st_size}
    return {
        "evidence_id": evidence_id, "reviewer": reviewer,
        "reviewer_independence": "host_attested_not_authentication",
        "scores": scores, "observed_frames": observed, "verdict": "ship",
        "capture_images": images, "capture_frames": frames, "overview_images": overview_images,
        "capture_receipt_sha256": _sha(capture_path),
        "review_receipt_sha256": _sha(review_path),
        "overview_receipt_sha256": _sha(overview_path),
        "artifacts": artifacts,
    }


class EffekseerVfxSkillReviewBridge:
    definition = DEFINITION

    def __init__(self, *, checkout: str | Path, runner=None, git_runner=None,
                 timeout_seconds: int = 180) -> None:
        self.checkout = Path(checkout).expanduser().resolve()
        self.runner = runner or subprocess.run
        self.git_runner = git_runner or subprocess.run
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(cls) -> "EffekseerVfxSkillReviewBridge":
        home = os.environ.get("EFFEKSEER_VFX_SKILL_HOME")
        if not home:
            raise VfxSkillBridgeError("Set EFFEKSEER_VFX_SKILL_HOME to pinned checkout")
        return cls(checkout=home)

    def check_source(self) -> dict[str, str]:
        for rel in SKILL_PATHS:
            if not (self.checkout / rel).is_file():
                raise VfxSkillBridgeError(f"Missing Skill file: {rel}")
        try:
            revision = self.git_runner(
                ["git", "-C", str(self.checkout), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=False, timeout=15)
            dirty = self.git_runner(
                ["git", "-C", str(self.checkout), "status", "--porcelain", "--",
                 "skills/effekseer-vfx", "skills/vfx-review", "LICENSE", "THIRD_PARTY_NOTICES.md"],
                capture_output=True, text=True, check=False, timeout=15)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VfxSkillBridgeError("Unable to check pinned Git revision") from exc
        if revision.returncode != 0 or revision.stdout.strip().lower() != UPSTREAM_REF:
            raise VfxSkillBridgeError("Upstream Git HEAD does not match pinned source revision")
        if dirty.returncode != 0 or dirty.stdout.strip():
            raise VfxSkillBridgeError("Upstream checkout is dirty or contains untracked code")
        return {"url": UPSTREAM_URL, "ref": UPSTREAM_REF, "license": "MIT"}

    def run(self, job: AssetSkillJob) -> AssetSkillResult:
        if job.capability != "vfx_visual_review":
            raise VfxSkillBridgeError("Only vfx_visual_review is supported")
        effect_id = job.options.get("effect_id")
        if not isinstance(effect_id, str) or not ID_RE.fullmatch(effect_id):
            raise VfxSkillBridgeError("Invalid effect ID")
        if job.options.get("execute") is not True:
            raise VfxSkillBridgeError("Explicit --execute is required")
        origin = self.check_source()
        project = Path(job.input_path).expanduser().resolve(strict=True)
        if not project.is_dir() or not (project / "vfx/src").is_dir() or not (project / "vfx/vfx_manifest.json").is_file():
            raise VfxSkillBridgeError("An initialized local VFX workspace is required")
        output = Path(job.output_dir).expanduser().resolve()
        if output.exists() or output.is_relative_to(project / "vfx"):
            raise VfxSkillBridgeError("Use a fresh evidence directory outside the VFX workspace")
        if not 30 <= self.timeout_seconds <= 600:
            raise VfxSkillBridgeError("Unsupported timeout")
        scripts = self.checkout / "skills/effekseer-vfx/scripts"
        if os.name == "nt":
            entry = scripts / "vfx.cmd"
            if not entry.is_file():
                raise VfxSkillBridgeError("Windows vfx.cmd not found")
            command = [str(entry)]
        else:
            command = ["sh", str(scripts / "vfx")]
        command += ["--project", str(project), "effect-verify", effect_id]
        try:
            completed = self.runner(
                command, cwd=project, capture_output=True, text=True,
                stdin=subprocess.DEVNULL, check=False, timeout=self.timeout_seconds)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise VfxSkillBridgeError("Local upstream effect-verify failed to run") from exc
        try:
            upstream = json.loads(completed.stdout.strip())
        except (ValueError, json.JSONDecodeError) as exc:
            raise VfxSkillBridgeError("Upstream command did not return JSON") from exc
        if not isinstance(upstream, dict) or upstream.get("ok") is not True or upstream.get("effect_id") != effect_id:
            raise VfxSkillBridgeError("Malformed upstream verification result")
        passed = (
            completed.returncode == 0 and upstream.get("verified") is True and
            upstream.get("issues") == [] and upstream.get("partial") is not True
        )
        if completed.returncode not in (0, 1) or (upstream.get("verified") is True and not passed):
            raise VfxSkillBridgeError("Upstream status contradicts exit code or issues")
        visual = _visual_receipts(project, self.checkout, effect_id, upstream.get("evidence_id")) if passed else None
        output.mkdir(parents=True, exist_ok=False)
        evidence = {
            "schema": "maf.effekseer-vfx-skill-review.v1",
            "skill": origin, "adapter_id": ADAPTER_ID, "effect_id": effect_id,
            "verified_visual": passed, "status": "verified_visual" if passed else "hold_not_verified",
            "upstream_exit_code": completed.returncode, "upstream_verification": upstream,
            "visual_evidence": visual, "game_runtime_verified": False, "release_approved": False,
            "scope": "Visual authoring only; runtime and device QA are separate.",
        }
        report_path = output / "review-bridge-report.json"
        write_json(report_path, evidence)
        return AssetSkillResult(
            skill_id=SKILL_ID, adapter_id=ADAPTER_ID, capability=job.capability,
            status="success" if passed else "skipped", input_path=str(project),
            output_paths=[str(report_path)], evidence_path=str(report_path),
            message=evidence["status"], metadata={
                "upstream_ref": UPSTREAM_REF, "verified_visual": passed,
                "game_runtime_verified": False, "release_approved": False,
            })
