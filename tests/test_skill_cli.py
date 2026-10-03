from pathlib import Path

from typer.testing import CliRunner

from mado_asset_foundry.cli import app


runner = CliRunner()


def test_skill_intake_cli(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "skill",
            "intake",
            "fixtures/skills/sample-background-remover",
            "--manifest-dir",
            str(tmp_path / "manifests"),
            "--evidence-dir",
            str(tmp_path / "evidence"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Adapter: intake_only" in result.output
    assert "Capabilities: pending M0.8.2b scanner" in result.output
    assert "External code executed: NO" in result.output
