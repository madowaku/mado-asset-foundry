import pytest
from pydantic import ValidationError

from mado_asset_foundry.skills.models import SkillManifest


def test_skill_manifest_defaults_to_intake_only() -> None:
    manifest = SkillManifest(
        skill_id="sample-skill",
        name="Sample Skill",
        source={"type": "local_directory", "path": "fixtures/skills/sample-skill"},
    )
    assert manifest.adapter_status == "intake_only"
    assert manifest.capabilities == []
    assert manifest.runtime == []


def test_skill_manifest_rejects_invalid_skill_id() -> None:
    with pytest.raises(ValidationError):
        SkillManifest(
            skill_id="Bad Skill ID",
            name="Bad",
            source={"type": "local_directory", "path": "x"},
        )
