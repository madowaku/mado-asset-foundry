from pathlib import Path

from typer.testing import CliRunner

from mado_asset_foundry.cli import app
from mado_asset_foundry.skills.registry import build_registry
from mado_asset_foundry.skills.scanner import scan_skill


runner = CliRunner()


def test_preflight_cli_for_registered_contract(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "scan-evidence"
    registry_path = tmp_path / "registry.json"

    scan_skill(
        "fixtures/skills/triposr-snapshot",
        manifest_dir=manifests,
        evidence_dir=evidence,
    )
    build_registry(manifests, output_path=registry_path)

    result = runner.invoke(
        app,
        [
            "skill",
            "preflight",
            "triposr-snapshot",
            "--registry",
            str(registry_path),
            "--evidence-dir",
            str(tmp_path / "preflight"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Adapter: triposr-local" in result.output
    assert "Promotion eligible: NO" in result.output
    assert "External Skill code executed: NO" in result.output
