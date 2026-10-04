from pathlib import Path

from typer.testing import CliRunner

from mado_asset_foundry.cli import app


runner = CliRunner()


def test_vfx_effect_probe_cli_rejects_missing_effekseer_core(tmp_path: Path) -> None:
    source = tmp_path / "effekseer-ai-source"
    (source / "src" / "effekseer_ai").mkdir(parents=True)
    (source / ".git").mkdir()
    (source / ".git" / "HEAD").write_text(
        "208922ef192220322c2a79e1243ed51ff7d2b7af\n",
        encoding="utf-8",
    )
    (source / "pyproject.toml").write_text(
        "[project]\nname='effekseer-ai'\n",
        encoding="utf-8",
    )
    (source / "src" / "effekseer_ai" / "cli.py").write_text(
        "# fixture\n",
        encoding="utf-8",
    )

    bin_dir = tmp_path / "Tool" / "bin"
    bin_dir.mkdir(parents=True)
    cli = tmp_path / "effekseer-ai.exe"
    cli.write_bytes(b"synthetic")

    result = runner.invoke(
        app,
        [
            "skill",
            "vfx-effect-probe",
            "--effekseer-ai-bin",
            str(cli),
            "--source-root",
            str(source),
            "--effekseer-bin-dir",
            str(bin_dir),
            "--workspace",
            str(tmp_path / "runs"),
            "--run-id",
            "vfx-probe-test",
        ],
    )

    assert result.exit_code == 1
    assert "EffekseerCore.dll" in result.output
