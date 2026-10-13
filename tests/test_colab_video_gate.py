import json
import subprocess

import pytest

from mado_asset_foundry.colab_video_gate import assess_h3_hardware, intake_h3_result


def test_capacity_fail_closed():
    assert assess_h3_hardware("int8")["status"] == "blocked"
    good = assess_h3_hardware("int8", gpu="A100", vram_gib=39, ram_gib=64, disk_gib=60)
    assert good["status"] == "compatible_on_reported_capacity"
    assert good["gpu_generation_verified"] is False
    assert assess_h3_hardware("full", gpu="A100", vram_gib=80, ram_gib=64, disk_gib=120)["status"] == "blocked"
    assert assess_h3_hardware("int8", gpu="A100", vram_gib=float("nan"), ram_gib=64, disk_gib=60)["status"] == "blocked"
    with pytest.raises(ValueError):
        assess_h3_hardware("invalid")


def test_bad_video_does_not_create_evidence(tmp_path):
    src = tmp_path / "bad.mp4"
    src.write_bytes(b"not a movie")
    with pytest.raises((RuntimeError, ValueError)):
        intake_h3_result(src, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_intake_with_stubbed_ffprobe(tmp_path, monkeypatch):
    src = tmp_path / "movie.mp4"
    src.write_bytes(b"synthetic")
    meta = tmp_path / "settings.json"
    meta.write_text('{"seed":42}')
    monkeypatch.setattr("mado_asset_foundry.colab_video_gate.shutil.which", lambda _: "/usr/bin/ffprobe")
    probe = {"streams": [{"codec_type": "video", "codec_name": "h264"}],
             "format": {"duration": "2.0"}}
    monkeypatch.setattr("mado_asset_foundry.colab_video_gate.subprocess.run",
                        lambda *a, **kw: subprocess.CompletedProcess(a, 0, json.dumps(probe), ""))
    out = tmp_path / "evidence"
    report = intake_h3_result(src, out, metadata=meta)
    assert not report["release_ready"]
    assert report["metadata_sha256"]
    assert json.loads((out / "h3_intake_evidence.json").read_text())["video_sha256"] == report["video_sha256"]
    with pytest.raises(FileExistsError):
        intake_h3_result(src, out)
