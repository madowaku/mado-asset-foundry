"""M1.5.2 deterministic synthetic media + malicious archive QA."""
from __future__ import annotations

import json
import subprocess
import zipfile
from pathlib import Path

import pytest

from mado_asset_foundry.colab_artifact_bridge import (
    export_h3_bundle, inspect_h3_bundle, import_h3_bundle,
)


@pytest.fixture
def artifacts(tmp_path):
    src = tmp_path / "video.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=160x90:r=12:d=1", "-c:v", "mpeg4",
                    "-y", str(src)], check=True)
    settings = tmp_path / "settings.json"
    settings.write_text('{"seed": 17, "prompt": "demo"}', encoding="utf-8")
    dest = tmp_path / "mounted_drive"
    dest.mkdir()
    return src, settings, dest


def _produce(artifacts, run="h3-test-01"):
    src, settings, dest = artifacts
    receipt = export_h3_bundle(src, dest, run, settings=settings)
    return dest / f"{run}.h3.zip", receipt


def test_export_inspect_import_end_to_end(artifacts, tmp_path):
    archive, receipt = _produce(artifacts)
    assert receipt["status"] == "destination_readback_verified"
    assert receipt["remote_sync_verified"] is False
    manifest = inspect_h3_bundle(archive)["manifest"]
    assert manifest["profile"] == "int8"
    assert set(manifest["files"]) == {"video.mp4", "settings.json", "hardware.json"}
    imported = import_h3_bundle(archive, tmp_path / "runs")
    result = Path(imported["destination"])
    assert imported["status"] == "local_import_verified"
    assert imported["release_ready"] is False
    assert imported["gpu_generation_verified"] is False
    assert result.joinpath("video.mp4").read_bytes() == artifacts[0].read_bytes()
    assert json.loads(result.joinpath("import_receipt.json").read_text())["media_probe"]["format"]["duration"]
    with pytest.raises(FileExistsError):
        import_h3_bundle(archive, tmp_path / "runs")
    with pytest.raises(FileExistsError):
        _produce(artifacts)


def test_invalid_runids_and_settings(artifacts):
    src, settings, dest = artifacts
    for run_id in ("../escape", "evil/path", "", "a" * 65):
        with pytest.raises(ValueError):
            export_h3_bundle(src, dest, run_id)
    settings.write_text("[1, 2]")
    with pytest.raises(ValueError):
        export_h3_bundle(src, dest, "valid", settings=settings)
    assert not list(dest.iterdir())


def test_corrupt_video_blocks_import(artifacts, tmp_path):
    src, settings, dest = artifacts
    src.write_bytes(b"not-mp4")
    archive, _ = _produce(artifacts)
    with pytest.raises((RuntimeError, ValueError)):
        import_h3_bundle(archive, tmp_path / "runs")
    assert not list((tmp_path / "runs").iterdir())


def test_tampered_hash_is_blocked(artifacts, tmp_path):
    original, _ = _produce(artifacts)
    broken = tmp_path / "modified.zip"
    with zipfile.ZipFile(original) as zin, zipfile.ZipFile(broken, "w", compression=zipfile.ZIP_STORED) as zout:
        for member in zin.infolist():
            payload = zin.read(member)
            if member.filename == "video.mp4":
                payload = b"altered" + payload
            zout.writestr(member.filename, payload)
    with pytest.raises(ValueError, match="File size mismatch"):
        inspect_h3_bundle(broken)


def test_zip_slip_and_symlink_member_blocked(artifacts, tmp_path):
    original, _ = _produce(artifacts)
    malicious = tmp_path / "malicious.zip"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(malicious, "w") as out:
        for info in source.infolist():
            out.writestr(info.filename, source.read(info))
        out.writestr("../escape.py", "nope")
    with pytest.raises(ValueError, match="unsafe"):
        inspect_h3_bundle(malicious)
    sym = tmp_path / "link.zip"
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(sym, "w") as out:
        for info in source.infolist():
            if info.filename == "hardware.json":
                cloned = zipfile.ZipInfo(info.filename)
                cloned.create_system = 3
                cloned.external_attr = (0o120777 << 16)
                out.writestr(cloned, "token")
            else:
                out.writestr(info.filename, source.read(info))
    with pytest.raises(ValueError, match="Non-regular"):
        inspect_h3_bundle(sym)


def test_mounted_destination_symlink_and_existing_target(artifacts, tmp_path):
    src, _, _ = artifacts
    link = tmp_path / "linked_dest"
    link.symlink_to(artifacts[2], target_is_directory=True)
    with pytest.raises(ValueError):
        export_h3_bundle(src, link, "run123")
    with pytest.raises(ValueError):
        export_h3_bundle(src, tmp_path / "absent", "run123")


def test_missing_ffprobe_is_not_approved(artifacts, tmp_path):
    archive, _ = _produce(artifacts)
    with pytest.raises((RuntimeError, FileNotFoundError)):
        import_h3_bundle(archive, tmp_path / "runs", ffprobe="no_such_ffprobe_xyz")
    assert not list((tmp_path / "runs").iterdir())


def test_hardware_report_cannot_self_certify_gpu(artifacts):
    video, _, dest = artifacts
    bad_report = {"schema": "maf.h3.compatibility.v1", "profile": "int8",
                  "gpu_generation_verified": True}
    with pytest.raises(ValueError, match="Hardware evidence"):
        export_h3_bundle(video, dest, "h3-forged", hardware=bad_report)
    assert not list(dest.iterdir())


def test_copy_interruption_cleans_partial(artifacts, monkeypatch):
    from mado_asset_foundry import colab_artifact_bridge as bridge
    video, _, dest = artifacts
    original_copy = bridge.shutil.copyfileobj

    def boom(*args, **kwargs):
        original_copy(*args, **kwargs)
        raise OSError("simulated interrupted mounted-drive write")

    monkeypatch.setattr(bridge.shutil, "copyfileobj", boom)
    with pytest.raises(OSError):
        export_h3_bundle(video, dest, "h3-interrupted")
    assert list(dest.iterdir()) == []


def test_cli_inspect_succeeds(artifacts):
    from typer.testing import CliRunner
    from mado_asset_foundry.colab_artifact_cli import colab_app
    archive, _ = _produce(artifacts)
    result = CliRunner().invoke(colab_app, ["inspect", str(archive)])
    assert result.exit_code == 0, result.output
    assert '"integrity": "verified"' in result.output
