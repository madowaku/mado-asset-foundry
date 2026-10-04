from pathlib import Path

from PIL import Image
from typer.testing import CliRunner

from mado_asset_foundry.cli import app


runner = CliRunner()


def test_triposr_probe_cli_rejects_missing_local_source(tmp_path: Path) -> None:
    input_path = tmp_path / "input.png"
    Image.new("RGBA", (32, 32), (0, 0, 0, 0)).save(input_path)
    model = tmp_path / "model"
    model.mkdir()
    (model / "config.yaml").write_text("x: y\n", encoding="utf-8")
    (model / "model.ckpt").write_bytes(b"x")

    result = runner.invoke(
        app,
        [
            "skill",
            "probe",
            "triposr-snapshot",
            "--input",
            str(input_path),
            "--source-root",
            str(tmp_path / "missing"),
            "--model-path",
            str(model),
            "--run-id",
            "probe-test",
            "--workspace",
            str(tmp_path / "runs"),
        ],
    )
    assert result.exit_code == 1
    assert "source directory not found" in result.output
