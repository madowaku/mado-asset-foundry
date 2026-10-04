from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from ..io import write_json
from .models import SkillManifest
from .scanner import scan_skill


class VfxProbeMember(BaseModel):
    skill_id: str
    role: str
    upstream_url: str | None = None
    upstream_ref: str | None = None
    license: str
    runtime: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    manifest_path: str


class VfxCapabilityProbeReport(BaseModel):
    schema_version: str = "0.1"
    probe_id: str = "effekseer-vfx"
    members: list[VfxProbeMember] = Field(default_factory=list)
    capability_candidates: dict[str, list[str]] = Field(default_factory=dict)
    external_code_executed: bool = False


VFX_FIXTURES: tuple[tuple[str, str], ...] = (
    ("fixtures/skills/effekseer-snapshot", "authoring_runtime"),
    ("fixtures/skills/effekseer-ai-snapshot", "cli_mcp_bridge"),
    ("fixtures/skills/effekseer-godot4-snapshot", "godot_runtime"),
)


def _license_label(manifest: SkillManifest) -> str:
    return manifest.license.spdx or manifest.license.name or manifest.license.status


def probe_vfx_capabilities(
    *,
    manifest_dir: str | Path = "skills/manifests/vfx",
    evidence_dir: str | Path = "evidence/vfx-capability-probe",
    force: bool = False,
) -> tuple[VfxCapabilityProbeReport, Path]:
    manifests: list[tuple[SkillManifest, Path, str]] = []
    for source, role in VFX_FIXTURES:
        manifest, manifest_path, _ = scan_skill(
            source,
            manifest_dir=manifest_dir,
            evidence_dir=Path(evidence_dir) / "members",
            force=force,
        )
        manifests.append((manifest, manifest_path, role))

    members = [
        VfxProbeMember(
            skill_id=manifest.skill_id,
            role=role,
            upstream_url=manifest.source.upstream_url,
            upstream_ref=manifest.source.upstream_ref,
            license=_license_label(manifest),
            runtime=list(manifest.runtime),
            capabilities=list(manifest.capabilities),
            manifest_path=str(manifest_path),
        )
        for manifest, manifest_path, role in manifests
    ]
    members.sort(key=lambda member: member.skill_id)

    capability_candidates: dict[str, list[str]] = {}
    for member in members:
        for capability in member.capabilities:
            capability_candidates.setdefault(capability, []).append(member.skill_id)
    capability_candidates = {
        capability: sorted(skill_ids)
        for capability, skill_ids in sorted(capability_candidates.items())
    }

    report = VfxCapabilityProbeReport(
        members=members,
        capability_candidates=capability_candidates,
    )
    report_path = Path(evidence_dir) / "report.json"
    if report_path.exists() and not force:
        raise FileExistsError(
            f"VFX capability probe evidence already exists: {report_path}; use --force to replace it"
        )
    write_json(report_path, report.model_dump(mode="json"))
    return report, report_path
