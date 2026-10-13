"""Read-only MiniMax H3 compatibility and media evidence gate (MAF-M1.5.1)."""
from __future__ import annotations
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Values are notebook-declared requirements, not empirically certified minima.
PROFILES = {
    "int8": {"vram_gib": 38, "ram_gib": 60, "disk_gib": 58},
    "full": {"vram_gib": 75, "ram_gib": 120, "disk_gib": 120},
}

def assess_h3_hardware(profile, *, gpu=None, vram_gib=None, ram_gib=None, disk_gib=None):
    if profile not in PROFILES:
        raise ValueError("Unknown profile")
    observed = dict(gpu=gpu, vram_gib=vram_gib, ram_gib=ram_gib, disk_gib=disk_gib)
    issues = [] if isinstance(gpu, str) and gpu.strip() else ["GPU identity unavailable"]
    for key, minimum in PROFILES[profile].items():
        actual = observed[key]
        if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not (0 <= actual < float("inf")):
            issues.append(f"{key}: missing/invalid telemetry")
        elif actual < minimum:
            issues.append(f"{key}: {actual} < {minimum} GiB")
    return dict(schema="maf.h3.compatibility.v1", profile=profile,
                requirements=PROFILES[profile], observed=observed,
                status="blocked" if issues else "compatible_on_reported_capacity",
                issues=issues, gpu_generation_verified=False, license_review="required",
                colab_cost="unknown")

def probe_local_hardware(profile="int8"):
    gpu, vram = None, None
    if shutil.which("nvidia-smi"):
        try:
            p = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total",
                                "--format=csv,noheader,nounits"], capture_output=True,
                               text=True, check=True, timeout=5)
            gpu, mib = p.stdout.strip().splitlines()[0].rsplit(",", 1)
            gpu, vram = gpu.strip(), int(mib.strip()) / 1024
        except (OSError, ValueError, IndexError, subprocess.SubprocessError):
            pass
    try:
        ram = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1024**3
    except (OSError, ValueError, AttributeError):
        ram = None
    return assess_h3_hardware(profile, gpu=gpu, vram_gib=vram, ram_gib=ram,
                               disk_gib=shutil.disk_usage(Path.cwd()).free / 1024**3)

def _sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def intake_h3_result(video, output_dir, *, metadata=None, ffprobe="ffprobe", license_reviewed=False):
    video, output_dir = Path(video), Path(output_dir)
    if not video.is_file() or video.is_symlink() or video.suffix.lower() != ".mp4" or not video.stat().st_size:
        raise ValueError("Expected regular, non-empty MP4")
    if output_dir.exists():
        raise FileExistsError(str(output_dir))
    if metadata is not None:
        metadata = Path(metadata)
        if not metadata.is_file() or metadata.is_symlink() or not isinstance(json.loads(metadata.read_text(encoding="utf-8")), dict):
            raise ValueError("Invalid metadata JSON")
    if not shutil.which(ffprobe) and not Path(ffprobe).is_file():
        raise RuntimeError("ffprobe unavailable")
    p = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                        "format=duration:stream=codec_type,codec_name,width,height",
                        "-of", "json", str(video)], capture_output=True, text=True, timeout=60)
    if p.returncode:
        raise RuntimeError("ffprobe failed: " + p.stderr[:500])
    probe = json.loads(p.stdout)
    if not any(s.get("codec_type") == "video" for s in probe.get("streams", [])):
        raise ValueError("No video stream")
    if float(probe.get("format", {}).get("duration", 0)) <= 0:
        raise ValueError("Invalid duration")
    output_dir.mkdir(parents=True, exist_ok=False)
    record = dict(schema="maf.h3.intake.v1", source_model="MiniMax-H3",
                  created_at=datetime.now(timezone.utc).isoformat(),
                  video_path=str(video.resolve()), video_sha256=_sha(video),
                  video_bytes=video.stat().st_size, probe=probe,
                  metadata_path=str(metadata.resolve()) if metadata else None,
                  metadata_sha256=_sha(metadata) if metadata else None,
                  license_reviewed=license_reviewed, release_ready=False,
                  human_visual_review="pending", gpu_generation_verified=False)
    (output_dir / "h3_intake_evidence.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record
