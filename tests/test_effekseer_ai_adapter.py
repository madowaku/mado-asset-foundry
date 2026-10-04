import json
import subprocess
from pathlib import Path

import pytest

from mado_asset_foundry.skills.adapters.effekseer_ai import (
    EFFEKSEER_COMPATIBILITY_TARGET,
    EffekseerAILocalAdapter,
)
from mado_asset_foundry.skills.adapters.models import AssetSkillJob


def make_effekseer_bin(root: Path) -> Path:
    root.mkdir()
    (root / "EffekseerCore.dll").write_bytes(b"synthetic-core-dll")
    return root


def make_cli(path: Path) -> Path:
    path.write_bytes(b"synthetic-effekseer-ai")
    return path


def job(tmp_path: Path, *, name: str = "Spark") -> AssetSkillJob:
    return AssetSkillJob(
        capability="vfx_create",
        input_path=f"vfx-brief:{name}",
        output_dir=str(tmp_path / "probe"),
        options={"effect_name": name},
    )


def test_effekseer_ai_probe_runs_new_node_add_export(tmp_path: Path) -> None:
    bin_dir = make_effekseer_bin(tmp_path / "Tool" / "bin")
    cli = make_cli(tmp_path / "effekseer-ai.exe")
    calls: list[tuple[list[str], dict[str, str]]] = []

    def runner(
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append((command, env))
        operation = command[1]
        if operation == "new":
            Path(command[2]).write_bytes(b"source-v1")
            payload = {"path": command[2], "root_children": 0}
        elif operation == "node-add":
            with Path(command[2]).open("ab") as handle:
                handle.write(b"-node")
            payload = {"path": "node/root/0"}
        elif operation == "export":
            Path(command[3]).write_bytes(b"runtime-efk")
            payload = {"path": command[3]}
        else:
            raise AssertionError(operation)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps(payload),
            "",
        )

    adapter = EffekseerAILocalAdapter(
        cli_bin=str(cli),
        effekseer_bin_dir=bin_dir,
        runner=runner,
        platform_name="Windows",
    )
    result = adapter.run(job(tmp_path))

    assert result.status == "success"
    assert len(calls) == 3
    assert [call[0][1] for call in calls] == ["new", "node-add", "export"]
    assert all(
        call[1]["EFFEKSEER_AI_BIN_DIR"] == str(bin_dir.resolve())
        for call in calls
    )
    assert result.metadata["executed_steps"] == 3
    assert result.metadata["compatibility_target"] == EFFEKSEER_COMPATIBILITY_TARGET
    assert result.metadata["network_service_started"] is False

    output = tmp_path / "probe"
    assert (output / "effect.efkefc").read_bytes().endswith(b"-node")
    assert (output / "effect.efk").read_bytes() == b"runtime-efk"
    assert (output / "evidence" / "job.json").exists()
    assert (output / "evidence" / "steps" / "new.json").exists()
    assert (output / "evidence" / "steps" / "node-add.json").exists()
    assert (output / "evidence" / "steps" / "export.json").exists()
    assert (output / "evidence" / "result.json").exists()


def test_effekseer_ai_probe_stops_and_preserves_failure_evidence(tmp_path: Path) -> None:
    bin_dir = make_effekseer_bin(tmp_path / "Tool" / "bin")
    cli = make_cli(tmp_path / "effekseer-ai.exe")

    def runner(
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        operation = command[1]
        if operation == "new":
            Path(command[2]).write_bytes(b"source")
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps({"path": command[2], "root_children": 0}),
                "",
            )
        if operation == "node-add":
            return subprocess.CompletedProcess(command, 5, "", "core failure")
        raise AssertionError("export must not run after node-add failure")

    adapter = EffekseerAILocalAdapter(
        cli_bin=str(cli),
        effekseer_bin_dir=bin_dir,
        runner=runner,
        platform_name="Windows",
    )
    result = adapter.run(job(tmp_path))

    assert result.status == "failed"
    assert "code 5" in result.message
    evidence = tmp_path / "probe" / "evidence"
    assert (evidence / "steps" / "node-add.stderr.log").read_text(
        encoding="utf-8"
    ) == "core failure"
    assert not (tmp_path / "probe" / "effect.efk").exists()
    assert (evidence / "result.json").exists()


def test_effekseer_ai_probe_requires_core_dll_before_execution(tmp_path: Path) -> None:
    bin_dir = tmp_path / "Tool" / "bin"
    bin_dir.mkdir(parents=True)
    cli = make_cli(tmp_path / "effekseer-ai.exe")
    called = False

    def runner(
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess(command, 0, "{}", "")

    adapter = EffekseerAILocalAdapter(
        cli_bin=str(cli),
        effekseer_bin_dir=bin_dir,
        runner=runner,
        platform_name="Windows",
    )

    with pytest.raises(FileNotFoundError, match="EffekseerCore.dll"):
        adapter.run(job(tmp_path))
    assert called is False


def test_effekseer_ai_probe_blocks_non_windows_platform(tmp_path: Path) -> None:
    bin_dir = make_effekseer_bin(tmp_path / "Tool" / "bin")
    cli = make_cli(tmp_path / "effekseer-ai.exe")
    adapter = EffekseerAILocalAdapter(
        cli_bin=str(cli),
        effekseer_bin_dir=bin_dir,
        platform_name="Linux",
    )

    with pytest.raises(RuntimeError, match="only on Windows"):
        adapter.run(job(tmp_path))


def test_effekseer_ai_probe_rejects_multiline_effect_name(tmp_path: Path) -> None:
    bin_dir = make_effekseer_bin(tmp_path / "Tool" / "bin")
    cli = make_cli(tmp_path / "effekseer-ai.exe")
    adapter = EffekseerAILocalAdapter(
        cli_bin=str(cli),
        effekseer_bin_dir=bin_dir,
        platform_name="Windows",
    )

    with pytest.raises(ValueError, match="1-80 characters"):
        adapter.run(job(tmp_path, name="bad\nname"))
