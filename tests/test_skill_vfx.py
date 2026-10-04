from pathlib import Path

from mado_asset_foundry.skills.registry import build_registry, resolve_capability
from mado_asset_foundry.skills.scanner import scan_skill
from mado_asset_foundry.skills.vfx import probe_vfx_capabilities


def test_effekseer_family_scans_into_vfx_taxonomy(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"

    effekseer, _, _ = scan_skill(
        "fixtures/skills/effekseer-snapshot",
        manifest_dir=manifests,
        evidence_dir=evidence / "effekseer",
    )
    ai, _, _ = scan_skill(
        "fixtures/skills/effekseer-ai-snapshot",
        manifest_dir=manifests,
        evidence_dir=evidence / "ai",
    )
    godot, _, _ = scan_skill(
        "fixtures/skills/effekseer-godot4-snapshot",
        manifest_dir=manifests,
        evidence_dir=evidence / "godot",
    )

    assert effekseer.source.upstream_ref == "82b37081a302b9f9eff0bf14dc6c845fca8c3c54"
    assert effekseer.license.spdx == "MIT"
    assert {"vfx_create", "vfx_edit", "vfx_runtime_playback"} <= set(effekseer.capabilities)

    assert ai.source.upstream_ref == "208922ef192220322c2a79e1243ed51ff7d2b7af"
    assert ai.license.spdx == "MIT"
    assert ai.runtime == ["python", "dotnet"]
    assert {
        "vfx_create",
        "vfx_edit",
        "vfx_runtime_export",
        "vfx_resource_import",
        "vfx_mcp_authoring",
    } <= set(ai.capabilities)

    assert godot.source.upstream_ref == "8706d2917c2487efac3a4943c16a10dfcfc5b127"
    assert godot.license.spdx == "MIT"
    assert {"vfx_runtime_playback", "godot_vfx_playback"} <= set(godot.capabilities)
    assert "vfx_create" not in godot.capabilities


def test_effekseer_vfx_resolver_stays_candidate_only(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"
    for fixture in (
        "fixtures/skills/effekseer-snapshot",
        "fixtures/skills/effekseer-ai-snapshot",
        "fixtures/skills/effekseer-godot4-snapshot",
    ):
        scan_skill(
            fixture,
            manifest_dir=manifests,
            evidence_dir=evidence / Path(fixture).name,
        )

    registry, _ = build_registry(manifests, output_path=tmp_path / "registry.json")

    create = resolve_capability(registry, "vfx_create")
    assert create.status == "candidate_only"
    assert [candidate.skill_id for candidate in create.candidates] == [
        "effekseer-ai-snapshot",
        "effekseer-snapshot",
    ]

    mcp = resolve_capability(registry, "vfx_mcp_authoring")
    assert mcp.status == "candidate_only"
    assert [candidate.skill_id for candidate in mcp.candidates] == [
        "effekseer-ai-snapshot"
    ]

    godot = resolve_capability(registry, "godot_vfx_playback")
    assert godot.status == "candidate_only"
    assert [candidate.skill_id for candidate in godot.candidates] == [
        "effekseer-godot4-snapshot"
    ]


def test_vfx_probe_builds_combined_evidence_without_execution(tmp_path: Path) -> None:
    report, report_path = probe_vfx_capabilities(
        manifest_dir=tmp_path / "manifests",
        evidence_dir=tmp_path / "evidence",
    )

    assert report.external_code_executed is False
    assert [member.skill_id for member in report.members] == [
        "effekseer-ai-snapshot",
        "effekseer-godot4-snapshot",
        "effekseer-snapshot",
    ]
    assert report.capability_candidates["vfx_mcp_authoring"] == [
        "effekseer-ai-snapshot"
    ]
    assert report.capability_candidates["godot_vfx_playback"] == [
        "effekseer-godot4-snapshot"
    ]
    assert report_path.exists()
