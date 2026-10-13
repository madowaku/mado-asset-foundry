"""MAF-M1.5.2: explicit, single-archive H3 export and verified MAF intake.

Standard-library file transport only. No GPU launch, cloud authentication, or publishing.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .colab_video_gate import intake_h3_result, probe_local_hardware

SUPPORTED_PROFILES = {"int8", "full"}
SCHEMA = "maf.h3.artifact-bundle.v1"
RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
ALLOWED = {"video.mp4", "settings.json", "hardware.json"}
MAX_VIDEO_BYTES = 16 * 1024**3
MAX_JSON_BYTES = 1024**2


def _sha_file(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _valid_input(path: str | Path, *, suffix: str, limit: int) -> Path:
    path = Path(path)
    if path.is_symlink() or not path.is_file() or path.suffix.lower() != suffix:
        raise ValueError(f"Expected regular {suffix} file: {path}")
    if not 0 < path.stat().st_size <= limit:
        raise ValueError(f"Empty/oversized input: {path}")
    return path


def _read_json_file(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON evidence must be an object")
    return payload


def _json_bytes(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")


def export_h3_bundle(
    video: str | Path, destination_dir: str | Path, run_id: str, *,
    settings: str | Path | None = None, profile: str = "int8",
    hardware: dict | None = None, staging_dir: str | Path | None = None,
) -> dict:
    """Create a ZIP locally, then transfer once to operator-chosen persistent location.

    Destination readback is checked, but remote Google Drive sync is NOT attested.
    """
    if not RUN_ID.fullmatch(run_id):
        raise ValueError("Invalid run ID")
    if profile not in SUPPORTED_PROFILES:
        raise ValueError("Unknown profile")
    video = _valid_input(video, suffix=".mp4", limit=MAX_VIDEO_BYTES)
    settings_file = None
    if settings is not None:
        settings_file = _valid_input(settings, suffix=".json", limit=MAX_JSON_BYTES)
        _read_json_file(settings_file)
    dest = Path(destination_dir)
    if dest.is_symlink() or not dest.is_dir():
        raise ValueError("Destination directory must already exist and be explicit")
    target = dest / f"{run_id}.h3.zip"
    lock = dest / f".{run_id}.lock"
    if target.exists() or target.is_symlink():
        raise FileExistsError(target)
    # Do not carry unrestricted environment variables or secrets into the export.
    hardware_record = hardware if hardware is not None else probe_local_hardware(profile)
    if (not isinstance(hardware_record, dict) or
        hardware_record.get("schema") != "maf.h3.compatibility.v1" or
        hardware_record.get("profile") != profile or
        hardware_record.get("gpu_generation_verified") is not False or
        set(hardware_record) - {"schema", "profile", "requirements", "observed", "status", "issues", "gpu_generation_verified", "license_review", "colab_cost"}):
        raise ValueError("Hardware evidence must match the read-only compatibility schema")
    hardware_document = {
        "schema": "maf.h3.hardware-evidence.v1", "profile": profile,
        "report": hardware_record, "gpu_generation_verified": False,
        "colab_runtime_identity_verified": False,
    }
    hardware_bytes = _json_bytes(hardware_document)
    if len(hardware_bytes) > MAX_JSON_BYTES:
        raise ValueError("Hardware report is too large")
    entries: dict[str, tuple[Path | None, bytes | None]] = {
        "video.mp4": (video, None), "hardware.json": (None, hardware_bytes),
    }
    if settings_file:
        entries["settings.json"] = (settings_file, None)
    files = {}
    for name, (source, content) in entries.items():
        files[name] = {
            "bytes": source.stat().st_size if source else len(content),
            "sha256": _sha_file(source) if source else hashlib.sha256(content).hexdigest(),
        }
    manifest = {
        "schema": SCHEMA, "run_id": run_id, "source_model": "MiniMax-H3",
        "source_notebook": "MiniMax_H3.ipynb", "profile": profile,
        "created_at": datetime.now(timezone.utc).isoformat(), "files": files,
        "gpu_generation_verified": False, "license_review": "required",
        "visual_review": "pending", "release_ready": False,
    }
    # Local staging avoids dozens of small writes to a mounted Drive.
    with tempfile.TemporaryDirectory(prefix="maf-h3-export-", dir=staging_dir) as tempdir:
        staged = Path(tempdir) / f"{run_id}.h3.zip"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for name in sorted(entries):
                source, content = entries[name]
                if source:
                    archive.write(source, arcname=name)
                else:
                    archive.writestr(name, content)
            archive.writestr("manifest.json", _json_bytes(manifest))
        # Reject source changes between initial hashing and ZIP composition.
        inspect_h3_bundle(staged)
        archive_hash = _sha_file(staged)
        lock.mkdir()
        part = dest / f".{run_id}.{uuid.uuid4().hex}.partial"
        try:
            if target.exists() or target.is_symlink():
                raise FileExistsError(target)
            with staged.open("rb") as src, part.open("xb") as dst:
                shutil.copyfileobj(src, dst, 1024 * 1024)
                dst.flush()
                os.fsync(dst.fileno())
            if _sha_file(part) != archive_hash:
                raise IOError("Destination readback hash differs")
            if target.exists() or target.is_symlink():
                raise FileExistsError(target)
            os.replace(part, target)
        finally:
            part.unlink(missing_ok=True)
            lock.rmdir()
    return {
        "status": "destination_readback_verified", "destination": str(target),
        "archive_sha256": archive_hash, "run_id": run_id,
        "remote_sync_verified": False, "gpu_generation_verified": False,
        "release_ready": False,
    }


def inspect_h3_bundle(archive_path: str | Path, *, max_video_bytes: int = MAX_VIDEO_BYTES) -> dict:
    """Untrusted ZIP validator with closed file names, exact hashes and size limits."""
    archive_path = _valid_input(archive_path, suffix=".zip", limit=max_video_bytes + 2 * MAX_JSON_BYTES + 65536)
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)) or not {"video.mp4", "hardware.json", "manifest.json"} <= set(names):
            raise ValueError("Missing or duplicate bundle member")
        if set(names) - (ALLOWED | {"manifest.json"}):
            raise ValueError("Unexpected or unsafe bundle member")
        for info in infos:
            if info.is_dir() or info.flag_bits & 1 or info.compress_type != zipfile.ZIP_STORED:
                raise ValueError("Unsupported ZIP member")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_IFMT(mode) not in (0, stat.S_IFREG):
                raise ValueError("Non-regular ZIP member")
            ceiling = max_video_bytes if info.filename == "video.mp4" else MAX_JSON_BYTES
            if not 0 < info.file_size <= ceiling:
                raise ValueError("Empty or oversized ZIP member")
        manifest = json.loads(archive.read("manifest.json"))
        if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
            raise ValueError("Unknown manifest schema")
        if not isinstance(manifest.get("run_id"), str) or not RUN_ID.fullmatch(manifest["run_id"]):
            raise ValueError("Invalid manifest run ID")
        if manifest.get("source_model") != "MiniMax-H3" or manifest.get("profile") not in SUPPORTED_PROFILES:
            raise ValueError("Unsupported source")
        if manifest.get("release_ready") is not False or manifest.get("gpu_generation_verified") is not False:
            raise ValueError("Source may not self-attest release or verified GPU generation")
        expected = manifest.get("files")
        if not isinstance(expected, dict) or set(expected) != (set(names) - {"manifest.json"}):
            raise ValueError("Manifest file list mismatch")
        for info in infos:
            if info.filename == "manifest.json":
                continue
            declared = expected[info.filename]
            if not isinstance(declared, dict) or set(declared) != {"bytes", "sha256"}:
                raise ValueError("Invalid file evidence fields")
            digest = declared["sha256"]
            if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
                raise ValueError("Invalid SHA-256")
            if type(declared["bytes"]) is not int or declared["bytes"] != info.file_size:
                raise ValueError("File size mismatch")
            sha = hashlib.sha256()
            with archive.open(info, "r") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    sha.update(chunk)
            if sha.hexdigest() != digest:
                raise ValueError(f"SHA-256 mismatch: {info.filename}")
        for name in ("settings.json", "hardware.json"):
            if name in names and not isinstance(json.loads(archive.read(name)), dict):
                raise ValueError("Non-object JSON evidence")
        hardware = json.loads(archive.read("hardware.json"))
        if hardware.get("schema") != "maf.h3.hardware-evidence.v1" or hardware.get("gpu_generation_verified") is not False:
            raise ValueError("Invalid hardware evidence")
        return {"manifest": manifest, "archive_sha256": _sha_file(archive_path), "integrity": "verified", "remote_sync_verified": False}


def import_h3_bundle(archive_path: str | Path, output_root: str | Path, *, ffprobe: str = "ffprobe") -> dict:
    """Validate, copy, re-hash and media-probe a bundle; no silent overwrite."""
    source = Path(archive_path)
    inspected = inspect_h3_bundle(source)
    manifest = inspected["manifest"]
    root = Path(output_root)
    if root.is_symlink():
        raise ValueError("Symlink output root is forbidden")
    root.mkdir(parents=True, exist_ok=True)
    dest = root / manifest["run_id"]
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(dest)
    stage = Path(tempfile.mkdtemp(prefix=".h3-import-", dir=root))
    try:
        with zipfile.ZipFile(source) as archive:
            for name, evidence in manifest["files"].items():
                output = stage / name
                with archive.open(name) as src, output.open("xb") as dst:
                    shutil.copyfileobj(src, dst, 1024 * 1024)
                if output.stat().st_size != evidence["bytes"] or _sha_file(output) != evidence["sha256"]:
                    raise ValueError(f"Copy integrity failure: {name}")
        (stage / "manifest.json").write_bytes(_json_bytes(manifest))
        metadata = stage / "settings.json" if "settings.json" in manifest["files"] else None
        # Reuse M1.5.1's ffprobe validation boundary; no media execution or generation.
        media = intake_h3_result(stage / "video.mp4", stage / "_media_check", metadata=metadata, ffprobe=ffprobe)
        shutil.rmtree(stage / "_media_check")
        receipt = {
            "schema": "maf.h3.import-receipt.v1", "run_id": manifest["run_id"],
            "source_archive_sha256": inspected["archive_sha256"],
            "files": manifest["files"], "media_probe": media["probe"],
            "status": "local_import_verified", "gpu_generation_verified": False,
            "remote_sync_verified": False, "visual_review": "pending",
            "license_review": "required", "release_ready": False,
        }
        (stage / "import_receipt.json").write_bytes(_json_bytes(receipt))
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(dest)
        os.rename(stage, dest)
        return {"destination": str(dest), **receipt}
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
