import json
from pathlib import Path

import pytest

from mado_asset_foundry.skills.intake import inspect_skill, intake_skill, load_skill_manifest


FIXTURE = Path("fixtures/skills/sample-background-remover")


def test_inspect_skill_is_structural_and_read_only() -> None:
    manifest, discovered = inspect_skill(FIXTURE)

    assert manifest.skill_id == "sample-background-remover"
    assert manifest.name == "Sample Background Remover"
    assert manifest.adapter_status == "intake_only"
    assert manifest.capabilities == []
    assert manifest.runtime == []
    assert manifest.entrypoints.skill_md == "SKILL.md"
    assert manifest.entrypoints.readme == "README.md"
    assert "scripts/remove.py" in manifest.entrypoints.scripts
    assert manifest.license.status == "detected"
    assert "LICENSE" in discovered


def test_intake_skill_writes_manifest_and_evidence(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"

    manifest, manifest_path, report_path = intake_skill(
        FIXTURE,
        manifest_dir=manifests,
        evidence_dir=evidence,
    )

    assert manifest_path.exists()
    assert report_path.exists()
    loaded = load_skill_manifest(manifest_path)
    assert loaded == manifest

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["external_code_executed"] is False
    assert report["capability_classification_performed"] is False
    assert report["status"] == "success"


def test_intake_does_not_overwrite_without_force(tmp_path: Path) -> None:
    kwargs = {
        "manifest_dir": tmp_path / "manifests",
        "evidence_dir": tmp_path / "evidence",
    }
    intake_skill(FIXTURE, **kwargs)

    with pytest.raises(FileExistsError):
        intake_skill(FIXTURE, **kwargs)

    manifest, _, _ = intake_skill(FIXTURE, force=True, **kwargs)
    assert manifest.skill_id == "sample-background-remover"


def test_inspect_missing_source_fails() -> None:
    with pytest.raises(FileNotFoundError):
        inspect_skill("fixtures/skills/does-not-exist")
