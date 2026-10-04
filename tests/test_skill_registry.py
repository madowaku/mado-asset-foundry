import json
from pathlib import Path

import pytest

from mado_asset_foundry.skills.models import SkillManifest
from mado_asset_foundry.skills.registry import (
    build_registry,
    load_registry,
    resolve_capability,
)
from mado_asset_foundry.skills.scanner import scan_skill


def _scan(source: str, manifest_dir: Path, evidence_dir: Path) -> None:
    scan_skill(
        source,
        manifest_dir=manifest_dir,
        evidence_dir=evidence_dir,
    )


def test_registry_builds_deterministically_from_nested_manifests(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"
    _scan("fixtures/skills/sample-background-remover", manifests, evidence)
    _scan("fixtures/skills/sample-pixel-art-studio", manifests / "nested", evidence / "nested")

    registry, registry_path = build_registry(
        manifests,
        output_path=tmp_path / "registry.json",
    )

    assert [entry.skill_id for entry in registry.entries] == [
        "sample-background-remover",
        "sample-pixel-art-studio",
    ]
    loaded = load_registry(registry_path)
    assert loaded == registry


def test_registry_rejects_duplicate_skill_ids(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"
    _scan("fixtures/skills/sample-background-remover", manifests, evidence)

    original = manifests / "sample-background-remover.json"
    duplicate_dir = manifests / "copy"
    duplicate_dir.mkdir()
    (duplicate_dir / original.name).write_text(original.read_text(encoding="utf-8"), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate skill_id"):
        build_registry(manifests, output_path=tmp_path / "registry.json")


def test_resolver_keeps_intake_only_as_candidate_only(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"
    _scan("fixtures/skills/sample-background-remover", manifests, evidence)

    registry, _ = build_registry(manifests, output_path=tmp_path / "registry.json")
    resolution = resolve_capability(registry, "background_remove")

    assert resolution.status == "candidate_only"
    assert resolution.selected_skill_id is None
    assert [candidate.skill_id for candidate in resolution.candidates] == [
        "sample-background-remover"
    ]


def test_resolver_selects_exactly_one_executable(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"
    _scan("fixtures/skills/sample-background-remover", manifests, evidence)

    path = manifests / "sample-background-remover.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["adapter_status"] = "executable"
    path.write_text(json.dumps(data), encoding="utf-8")

    registry, _ = build_registry(manifests, output_path=tmp_path / "registry.json")
    resolution = resolve_capability(registry, "background_remove")

    assert resolution.status == "resolved"
    assert resolution.selected_skill_id == "sample-background-remover"


def test_resolver_returns_ambiguous_for_multiple_executables(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    manifests.mkdir()

    for skill_id in ("a-skill", "b-skill"):
        manifest = SkillManifest(
            skill_id=skill_id,
            name=skill_id,
            source={"type": "local_directory", "path": skill_id},
            capabilities=["background_remove"],
            adapter_status="executable",
        )
        (manifests / f"{skill_id}.json").write_text(
            manifest.model_dump_json(),
            encoding="utf-8",
        )

    registry, _ = build_registry(manifests, output_path=tmp_path / "registry.json")
    resolution = resolve_capability(registry, "background_remove")

    assert resolution.status == "ambiguous"
    assert resolution.selected_skill_id is None
    assert [candidate.skill_id for candidate in resolution.candidates] == [
        "a-skill",
        "b-skill",
    ]


def test_resolver_unresolved_when_capability_is_missing(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"
    _scan("fixtures/skills/sample-background-remover", manifests, evidence)

    registry, _ = build_registry(manifests, output_path=tmp_path / "registry.json")
    resolution = resolve_capability(registry, "does_not_exist")

    assert resolution.status == "unresolved"
    assert resolution.candidates == []


def test_scanner_classifies_image_to_3d_capabilities(tmp_path: Path) -> None:
    manifest, _, _ = scan_skill(
        "fixtures/skills/sample-image-to-3d",
        manifest_dir=tmp_path / "manifests",
        evidence_dir=tmp_path / "evidence",
    )

    assert {
        "model3d_generate",
        "image_to_mesh",
        "mesh_texture_bake",
        "uv_unwrap",
        "material_predict",
        "image_delight",
        "mesh_decimate",
        "mesh_repair",
        "mesh_qa",
        "glb_export",
    } <= set(manifest.capabilities)
    assert manifest.runtime == ["python"]
    assert "model_3d" in manifest.outputs
    assert "glb" in manifest.outputs
