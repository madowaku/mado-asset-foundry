from pathlib import Path

from typer.testing import CliRunner

from mado_asset_foundry.cli import app


runner = CliRunner()


def test_vfx_godot_dogfood_cli_rejects_missing_plugin_archive(tmp_path: Path) -> None:
    godot = tmp_path / "godot.exe"
    godot.write_bytes(b"synthetic")

    result = runner.invoke(
        app,
        [
            "skill",
            "vfx-godot-dogfood",
            str(tmp_path / "missing-effect-run"),
            "--plugin-archive",
            str(tmp_path / "missing.zip"),
            "--godot-bin",
            str(godot),
        ],
    )

    assert result.exit_code == 1
    assert "effect probe artifact missing" in result.output or "missing" in result.output.lower()
