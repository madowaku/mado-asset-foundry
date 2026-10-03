import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from mado_asset_foundry.cli import app
from mado_asset_foundry.skills.pack import discover_skill_directories, scan_skill_pack


FIXTURE = Path("fixtures/skills/universal-modder-snapshot")
EXPECTED_SKILLS = [
    "asset-pipeline",
    "fal-assets",
    "game-automation",
    "game-recon",
    "mashup-mods",
    "mod-any-game",
    "publish-mod",
    "reverse-engineering",
    "share-field-notes",
    "showcase-video",
]


def test_discover_universal_modder_skill_pack() -> None:
    discovered = discover_skill_directories(FIXTURE)
    assert [path.name for path in discovered] == EXPECTED_SKILLS


def test_scan_universal_modder_pack_is_evidence_only(tmp_path: Path) -> None:
    report, report_path = scan_skill_pack(
        FIXTURE,
        manifest_dir=tmp_path / "manifests",
        evidence_dir=tmp_path / "evidence",
    )

    assert report.pack_id == "universal-modder"
    assert report.upstream_ref == "15d6f9d5fbd32de9b1884f29ddec3be9133bd912"
    assert report.discovered_skills == EXPECTED_SKILLS
    assert report.candidate_skills == [
        "asset-pipeline",
        "fal-assets",
        "showcase-video",
    ]
    assert report.license.spdx == "MIT"
    assert report.external_code_executed is False

    assert [(item.name, item.target) for item in report.cli_entrypoints] == [
        ("um", "um.cli:main"),
    ]
    assert [(item.name, item.url) for item in report.mcp_servers] == [
        ("fal", "https://mcp.fal.ai/mcp"),
    ]

    dependencies = {(item.kind, item.dependency) for item in report.dependencies}
    assert {
        ("python_package", "pillow"),
        ("python_package", "numpy"),
        ("python_package", "pyyaml"),
        ("tool", "blender"),
        ("tool", "ffmpeg"),
        ("service", "fal"),
    } <= dependencies

    constraints = {item.constraint for item in report.safety_constraints}
    assert constraints == {
        "ownership_required",
        "offline_or_controlled_server_only",
        "no_anticheat_or_drm_bypass",
        "no_game_file_redistribution",
        "backup_before_mutation",
        "human_confirmation_for_machine_changes",
    }

    members = {item.skill_id: item for item in report.members}
    assert {
        "sprite_cutout",
        "sprite_fit",
        "sprite_sheet_pack",
        "render3d_to_sprite",
        "palette_lock",
        "pixelate",
    } <= set(members["asset-pipeline"].capabilities)
    assert {
        "image_generate",
        "image_edit",
        "background_remove",
        "pixelate",
        "image_upscale",
        "texture_generate",
        "pbr_generate",
        "model3d_generate",
        "rig_generate",
        "sfx_generate",
        "music_generate",
        "voice_generate",
        "video_generate",
    } <= set(members["fal-assets"].capabilities)
    assert "video_edit" in members["showcase-video"].capabilities
    assert members["game-recon"].decision == "out_of_scope"
    assert members["fal-assets"].decision == "adapter_required"

    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["external_code_executed"] is False
    for member in report.members:
        assert Path(member.manifest_path).exists()
        assert Path(member.report_path).exists()


def test_pack_scan_requires_force_to_replace_outputs(tmp_path: Path) -> None:
    kwargs = {
        "manifest_dir": tmp_path / "manifests",
        "evidence_dir": tmp_path / "evidence",
    }
    scan_skill_pack(FIXTURE, **kwargs)
    with pytest.raises(FileExistsError):
        scan_skill_pack(FIXTURE, **kwargs)
    report, _ = scan_skill_pack(FIXTURE, force=True, **kwargs)
    assert report.pack_id == "universal-modder"


def test_scan_pack_cli(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "skill",
            "scan-pack",
            str(FIXTURE),
            "--manifest-dir",
            str(tmp_path / "manifests"),
            "--evidence-dir",
            str(tmp_path / "evidence"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Pack: universal-modder" in result.output
    assert "Skills discovered: 10" in result.output
    assert "fal-assets" in result.output
    assert "MCP: fal" in result.output
    assert "Safety constraints: 6" in result.output
    assert "External code executed: NO" in result.output
