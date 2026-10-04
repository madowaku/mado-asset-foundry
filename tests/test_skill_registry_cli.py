from pathlib import Path

from typer.testing import CliRunner

from mado_asset_foundry.cli import app
from mado_asset_foundry.skills.scanner import scan_skill


runner = CliRunner()


def test_registry_cli_build_list_show_and_resolve(tmp_path: Path) -> None:
    manifests = tmp_path / "manifests"
    evidence = tmp_path / "evidence"
    registry = tmp_path / "registry.json"

    scan_skill(
        "fixtures/skills/sample-background-remover",
        manifest_dir=manifests,
        evidence_dir=evidence,
    )

    build = runner.invoke(
        app,
        [
            "skill",
            "registry",
            "build",
            str(manifests),
            "--output",
            str(registry),
        ],
    )
    assert build.exit_code == 0, build.output
    assert "Skills: 1" in build.output

    listed = runner.invoke(app, ["skill", "list", "--registry", str(registry)])
    assert listed.exit_code == 0, listed.output
    assert "sample-background-remover" in listed.output

    shown = runner.invoke(
        app,
        ["skill", "show", "sample-background-remover", "--registry", str(registry)],
    )
    assert shown.exit_code == 0, shown.output
    assert "background_remove" in shown.output

    resolved = runner.invoke(
        app,
        ["skill", "resolve", "background_remove", "--registry", str(registry)],
    )
    assert resolved.exit_code == 0, resolved.output
    assert "Status: candidate_only" in resolved.output
    assert "sample-background-remover" in resolved.output
