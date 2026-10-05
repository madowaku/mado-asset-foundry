import json
import subprocess
from pathlib import Path

import pytest

from mado_asset_foundry.skills.adapters.crafting_apps import (
    CRAFTING_APP_SPECS,
    CraftingAppMcpAdapter,
    get_crafting_app_spec,
    write_crafting_apps_intake,
)


def test_crafting_apps_intake_is_read_only_and_pinned(tmp_path: Path) -> None:
    report, path = write_crafting_apps_intake(
        output_path=tmp_path / "intake" / "report.json"
    )

    assert path.exists()
    assert report.external_code_executed is False
    assert report.mcp_servers_started is False
    assert [app.app_id for app in report.apps] == [
        "effectcraft",
        "photocraft",
        "vectorcraft",
    ]
    assert all(len(app.upstream_ref) == 40 for app in report.apps)
    assert all(app.mcp_args == ["mcp"] for app in report.apps)
    assert all(app.mcp_transport == "stdio" for app in report.apps)
    assert CRAFTING_APP_SPECS["vectorcraft"].maf_capabilities == ["vector_edit"]

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["external_code_executed"] is False
    assert payload["mcp_servers_started"] is False


def test_crafting_app_probe_hashes_cli_and_materializes_descriptor(
    tmp_path: Path,
) -> None:
    cli = tmp_path / "photocraft-cli.exe"
    cli.write_bytes(b"synthetic-photocraft-cli")
    calls: list[list[str]] = []

    def runner(
        command: list[str],
        cwd: Path,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            "PhotoCraft CLI help\n",
            "",
        )

    adapter = CraftingAppMcpAdapter(
        "photocraft",
        cli_bin=str(cli),
        runner=runner,
    )
    result = adapter.probe(tmp_path / "run")

    assert result.status == "success"
    assert calls == [[str(cli.resolve()), "--help"]]
    assert result.mcp_server_started is False
    assert result.network_service_started is False
    assert result.mcp_descriptor_path is not None

    descriptor = json.loads(
        Path(result.mcp_descriptor_path).read_text(encoding="utf-8")
    )
    assert descriptor["transport"] == "stdio"
    assert descriptor["command"] == str(cli.resolve())
    assert descriptor["args"] == ["mcp"]
    assert descriptor["server_started"] is False
    assert descriptor["upstream_ref"] == CRAFTING_APP_SPECS["photocraft"].upstream_ref

    evidence = tmp_path / "run" / "evidence"
    assert (evidence / "job.json").exists()
    assert (evidence / "probe.stdout.log").read_text(
        encoding="utf-8"
    ) == "PhotoCraft CLI help\n"
    assert (evidence / "result.json").exists()


def test_crafting_app_probe_failure_preserves_evidence_without_descriptor(
    tmp_path: Path,
) -> None:
    cli = tmp_path / "vectorcraft-cli"
    cli.write_bytes(b"synthetic-vectorcraft-cli")

    def runner(
        command: list[str],
        cwd: Path,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            2,
            "",
            "bad cli invocation",
        )

    adapter = CraftingAppMcpAdapter(
        "vectorcraft",
        cli_bin=str(cli),
        runner=runner,
    )
    result = adapter.probe(tmp_path / "run")

    assert result.status == "failed"
    assert result.returncode == 2
    assert result.mcp_descriptor_path is None
    assert result.mcp_server_started is False
    evidence = tmp_path / "run" / "evidence"
    assert (evidence / "probe.stderr.log").read_text(
        encoding="utf-8"
    ) == "bad cli invocation"
    assert not (evidence / "mcp-server.json").exists()
    assert (evidence / "result.json").exists()


def test_crafting_app_probe_rejects_nonempty_output(tmp_path: Path) -> None:
    cli = tmp_path / "effectcraft-cli"
    cli.write_bytes(b"synthetic-effectcraft-cli")
    output = tmp_path / "run"
    output.mkdir()
    (output / "keep.txt").write_text("keep", encoding="utf-8")

    adapter = CraftingAppMcpAdapter(
        "effectcraft",
        cli_bin=str(cli),
    )

    with pytest.raises(FileExistsError, match="not empty"):
        adapter.probe(output)


def test_unknown_crafting_app_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown Crafting App"):
        get_crafting_app_spec("designcraft")
