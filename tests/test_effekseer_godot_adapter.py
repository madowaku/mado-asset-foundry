import hashlib
import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from mado_asset_foundry.io import write_json
from mado_asset_foundry.skills.adapters.effekseer_godot import (
    EFFEKSEER_GODOT_VERSION,
    EffekseerGodotLocalAdapter,
)
from mado_asset_foundry.skills.adapters.models import AssetSkillJob


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_effect_run(tmp_path: Path) -> Path:
    run = tmp_path / "effect-run"
    evidence = run / "evidence"
    evidence.mkdir(parents=True)
    source = run / "effect.efkefc"
    runtime = run / "effect.efk"
    source.write_bytes(b"efkefc-source")
    runtime.write_bytes(b"efk-runtime")
    write_json(
        evidence / "result.json",
        {
            "skill_id": "effekseer-ai-snapshot",
            "adapter_id": "effekseer-ai-local",
            "capability": "vfx_create",
            "status": "success",
            "input_path": "vfx-brief:Spark",
            "output_paths": [str(source), str(runtime)],
            "evidence_path": str(evidence),
            "message": "fixture",
            "metadata": {
                "source_sha256": sha256(source),
                "runtime_sha256": sha256(runtime),
                "compatibility_target": "1.80.6",
            },
        },
    )
    return run


def make_plugin_archive(tmp_path: Path, *, unsafe: bool = False) -> Path:
    archive = tmp_path / "EffekseerForGodot4-180_7.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        root = "release/addons/effekseer/"
        bundle.writestr(root + "plugin.cfg", '[plugin]\nversion="1.80.7"\n')
        bundle.writestr(
            root + "effekseer.gdextension",
            '[configuration]\ncompatibility_minimum = 4.2\n',
        )
        bundle.writestr(root + "plugin.gd", "@tool\nextends EditorPlugin\n")
        bundle.writestr(
            root + "bin/windows/libeffekseer.x86_64.dll",
            b"synthetic-gdextension",
        )
        if unsafe:
            bundle.writestr("../escape.txt", "nope")
    return archive


def make_godot(path: Path) -> Path:
    path.write_bytes(b"synthetic-godot")
    return path


def make_job(tmp_path: Path, effect_run: Path) -> AssetSkillJob:
    return AssetSkillJob(
        capability="godot_vfx_playback",
        input_path=str(effect_run),
        output_dir=str(tmp_path / "godot-run"),
    )


def test_effekseer_godot_runs_import_and_playback_evidence(tmp_path: Path) -> None:
    effect_run = make_effect_run(tmp_path)
    archive = make_plugin_archive(tmp_path)
    godot = make_godot(tmp_path / "godot.exe")
    calls: list[list[str]] = []

    def runner(
        command: list[str],
        cwd: Path,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "4.6.stable.official\n", "")
        if "--import" in command:
            return subprocess.CompletedProcess(command, 0, "imported\n", "")
        report = {
            "status": "passed",
            "effect_path": "res://effects/effect.efkefc",
            "effect_loaded": True,
            "effect_class": "EffekseerEffect",
            "emitter_class_exists": True,
            "play_called": True,
            "is_playing": True,
            "errors": [],
        }
        write_json(cwd / "evidence" / "runtime-report.json", report)
        return subprocess.CompletedProcess(command, 0, json.dumps(report), "")

    adapter = EffekseerGodotLocalAdapter(
        plugin_archive=archive,
        godot_bin=str(godot),
        runner=runner,
        platform_name="Windows",
        expected_archive_sha256=sha256(archive),
    )
    result = adapter.run(make_job(tmp_path, effect_run))

    assert result.status == "success"
    assert result.metadata["playback_verified"] is True
    assert result.metadata["plugin_version"] == EFFEKSEER_GODOT_VERSION
    assert result.metadata["visual_quality_approved"] is False
    assert len(calls) == 3
    assert "--version" in calls[0]
    assert "--import" in calls[1]
    assert "--headless" in calls[2]

    fixture = tmp_path / "godot-run"
    assert (fixture / "addons" / "effekseer" / "plugin.cfg").exists()
    assert (
        fixture
        / "addons"
        / "effekseer"
        / "bin"
        / "windows"
        / "libeffekseer.x86_64.dll"
    ).exists()
    assert (fixture / "effects" / "effect.efkefc").read_bytes() == b"efkefc-source"
    assert (fixture / "effects" / "effect.efk").read_bytes() == b"efk-runtime"
    playback = (fixture / "playback.gd").read_text(encoding="utf-8")
    assert 'load(EFFECT_PATH)' in playback
    assert 'emitter.call("play")' in playback
    assert 'emitter.call("is_playing")' in playback

    job = json.loads((fixture / "evidence" / "job.json").read_text(encoding="utf-8"))
    assert job["version_delta"]["effect_authoring"] == "1.80.6"
    assert job["version_delta"]["godot_plugin"] == "1.80.7"


def test_effekseer_godot_rejects_tampered_plugin_archive_before_execution(
    tmp_path: Path,
) -> None:
    effect_run = make_effect_run(tmp_path)
    archive = make_plugin_archive(tmp_path)
    godot = make_godot(tmp_path / "godot.exe")
    called = False

    def runner(
        command: list[str],
        cwd: Path,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal called
        called = True
        return subprocess.CompletedProcess(command, 0, "", "")

    adapter = EffekseerGodotLocalAdapter(
        plugin_archive=archive,
        godot_bin=str(godot),
        runner=runner,
        platform_name="Windows",
        expected_archive_sha256="0" * 64,
    )

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        adapter.run(make_job(tmp_path, effect_run))
    assert called is False


def test_effekseer_godot_rejects_unsafe_archive_member(tmp_path: Path) -> None:
    effect_run = make_effect_run(tmp_path)
    archive = make_plugin_archive(tmp_path, unsafe=True)
    godot = make_godot(tmp_path / "godot.exe")

    adapter = EffekseerGodotLocalAdapter(
        plugin_archive=archive,
        godot_bin=str(godot),
        platform_name="Windows",
        expected_archive_sha256=sha256(archive),
    )

    with pytest.raises(ValueError, match="Unsafe plugin archive member"):
        adapter.run(make_job(tmp_path, effect_run))
    assert not (tmp_path / "escape.txt").exists()


def test_effekseer_godot_rejects_tampered_effect_run(tmp_path: Path) -> None:
    effect_run = make_effect_run(tmp_path)
    (effect_run / "effect.efk").write_bytes(b"tampered")
    archive = make_plugin_archive(tmp_path)
    godot = make_godot(tmp_path / "godot.exe")

    adapter = EffekseerGodotLocalAdapter(
        plugin_archive=archive,
        godot_bin=str(godot),
        platform_name="Windows",
        expected_archive_sha256=sha256(archive),
    )

    with pytest.raises(ValueError, match="runtime_sha256|SHA-256"):
        adapter.run(make_job(tmp_path, effect_run))


def test_effekseer_godot_blocks_godot_older_than_4_2(tmp_path: Path) -> None:
    effect_run = make_effect_run(tmp_path)
    archive = make_plugin_archive(tmp_path)
    godot = make_godot(tmp_path / "godot.exe")
    calls = 0

    def runner(
        command: list[str],
        cwd: Path,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(command, 0, "4.1.4.stable\n", "")

    adapter = EffekseerGodotLocalAdapter(
        plugin_archive=archive,
        godot_bin=str(godot),
        runner=runner,
        platform_name="Windows",
        expected_archive_sha256=sha256(archive),
    )
    result = adapter.run(make_job(tmp_path, effect_run))

    assert result.status == "failed"
    assert "requires Godot 4.2+" in result.message
    assert calls == 1
    assert result.metadata["external_code_executed"] is True


def test_effekseer_godot_fails_when_emitter_is_not_playing(tmp_path: Path) -> None:
    effect_run = make_effect_run(tmp_path)
    archive = make_plugin_archive(tmp_path)
    godot = make_godot(tmp_path / "godot.exe")

    def runner(
        command: list[str],
        cwd: Path,
        timeout: int,
    ) -> subprocess.CompletedProcess[str]:
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "4.6.stable\n", "")
        if "--import" in command:
            return subprocess.CompletedProcess(command, 0, "", "")
        write_json(
            cwd / "evidence" / "runtime-report.json",
            {
                "status": "failed",
                "effect_loaded": True,
                "effect_class": "EffekseerEffect",
                "emitter_class_exists": True,
                "play_called": True,
                "is_playing": False,
                "errors": ["emitter_not_playing"],
            },
        )
        return subprocess.CompletedProcess(command, 1, "", "not playing")

    adapter = EffekseerGodotLocalAdapter(
        plugin_archive=archive,
        godot_bin=str(godot),
        runner=runner,
        platform_name="Windows",
        expected_archive_sha256=sha256(archive),
    )
    result = adapter.run(make_job(tmp_path, effect_run))

    assert result.status == "failed"
    assert result.metadata["playback_exit_code"] == 1
    assert result.metadata["runtime_report"]["is_playing"] is False


def test_effekseer_godot_blocks_non_windows(tmp_path: Path) -> None:
    effect_run = make_effect_run(tmp_path)
    archive = make_plugin_archive(tmp_path)
    godot = make_godot(tmp_path / "godot.exe")
    adapter = EffekseerGodotLocalAdapter(
        plugin_archive=archive,
        godot_bin=str(godot),
        platform_name="Linux",
        expected_archive_sha256=sha256(archive),
    )

    with pytest.raises(RuntimeError, match="Windows x86_64"):
        adapter.run(make_job(tmp_path, effect_run))



def test_effekseer_godot_rejects_wrong_authoring_compatibility_target(
    tmp_path: Path,
) -> None:
    effect_run = make_effect_run(tmp_path)
    result_path = effect_run / "evidence" / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["metadata"]["compatibility_target"] = "1.80.7"
    write_json(result_path, result)
    archive = make_plugin_archive(tmp_path)
    godot = make_godot(tmp_path / "godot.exe")

    adapter = EffekseerGodotLocalAdapter(
        plugin_archive=archive,
        godot_bin=str(godot),
        platform_name="Windows",
        expected_archive_sha256=sha256(archive),
    )

    with pytest.raises(ValueError, match="compatibility target"):
        adapter.run(make_job(tmp_path, effect_run))
