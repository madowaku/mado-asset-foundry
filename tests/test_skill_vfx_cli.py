from pathlib import Path

from typer.testing import CliRunner

from mado_asset_foundry.cli import app


runner = CliRunner()


def test_vfx_probe_cli(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "skill",
            "vfx-probe",
            "--manifest-dir",
            str(tmp_path / "manifests"),
            "--evidence-dir",
            str(tmp_path / "evidence"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Probe: effekseer-vfx" in result.output
    assert "Skills: 3" in result.output
    assert "effekseer-ai-snapshot" in result.output
    assert "godot_vfx_playback" in result.output
    assert "External code executed: NO" in result.output
