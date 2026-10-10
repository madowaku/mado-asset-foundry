"""Fail-closed, local-first Cloud Asset Vault materializer.

The vault manifest is an operator-authored inventory, not a license grant.
Cloud runtime only materializes files already present in a Git/LFS checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path, PurePosixPath

SCHEMA = "maf.cloud-vault.v1"
MAX_ASSETS = 1000
MAX_BYTES = 1024 * 1024 * 1024  # 1 GiB per asset, configurable in later milestones


class VaultError(ValueError):
    """The vault has failed a security or integrity check."""


def _relative(raw: object) -> Path:
    if not isinstance(raw, str) or not raw or "\\" in raw or "\x00" in raw:
        raise VaultError("Invalid relative asset path")
    posix = PurePosixPath(raw)
    if posix.is_absolute() or any(part in ("", ".", "..") for part in raw.split("/")):
        raise VaultError("Path must be a normalized relative POSIX path")
    if ":" in raw.split("/")[0]:
        raise VaultError("Drive/URL paths are forbidden")
    return Path(*posix.parts)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_file(root: Path, relative: Path) -> Path:
    """Refuse symlinks anywhere in the path, including the manifest root."""
    if root.is_symlink():
        raise VaultError("Vault root may not be a symlink")
    candidate = root
    for part in relative.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise VaultError(f"Symlinks forbidden: {relative}")
    if not candidate.is_file() or not candidate.resolve().is_relative_to(root.resolve()):
        raise VaultError(f"Missing or escaping vault file: {relative}")
    return candidate


def _checked_file(root: Path, spec: dict, field: str, sha_field: str) -> tuple[Path, Path]:
    relative = _relative(spec.get(field))
    checksum = spec.get(sha_field)
    if not isinstance(checksum, str) or len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise VaultError(f"Missing lowercase SHA-256 for {field}")
    file_path = _regular_file(root, relative)
    if file_path.stat().st_size > MAX_BYTES:
        raise VaultError("Oversized asset")
    if _sha256(file_path) != checksum:
        raise VaultError(f"SHA-256 mismatch: {relative}")
    return file_path, relative


def materialize(manifest: str | Path, destination: str | Path, *, asset_ids: list[str] | None = None) -> dict:
    """Verify rights evidence and hashes, then atomically create a new output folder.

    No downloads, network requests, third-party code, or overwrites.
    """
    manifest_path = Path(manifest)
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise VaultError("Manifest missing or symlinked")
    root = manifest_path.parent
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("schema_version") != SCHEMA:
        raise VaultError("Unsupported vault schema")
    assets = data.get("assets")
    if not isinstance(assets, list) or not 0 < len(assets) <= MAX_ASSETS:
        raise VaultError("Manifest must contain 1-1000 assets")
    requested = set(asset_ids) if asset_ids is not None else None
    if requested is not None and (not requested or len(requested) != len(asset_ids)):
        raise VaultError("Empty or duplicated selection")
    seen = set()
    chosen = []
    paths = set()
    for entry in assets:
        if not isinstance(entry, dict):
            raise VaultError("Invalid asset entry")
        asset_id = entry.get("asset_id")
        if not isinstance(asset_id, str) or not asset_id or not all(c.isalnum() or c in "-_" for c in asset_id):
            raise VaultError("Invalid asset_id")
        if asset_id in seen:
            raise VaultError("Duplicate asset_id")
        seen.add(asset_id)
        if requested is not None and asset_id not in requested:
            continue
        if entry.get("reviewed_by_human") is not True or entry.get("use_case") != "game_embedding":
            raise VaultError(f"Human rights review/game embedding missing for {asset_id}")
        if not isinstance(entry.get("license_spdx"), str) or not entry["license_spdx"].strip() or entry["license_spdx"].lower() in ("unknown", "none", "proprietary"):
            raise VaultError(f"License metadata missing for {asset_id}")
        source, rel = _checked_file(root, entry, "path", "sha256")
        evidence, evidence_rel = _checked_file(root, entry, "license_evidence", "license_evidence_sha256")
        if rel == evidence_rel:
            raise VaultError("Asset and license evidence must differ")
        if rel in paths or evidence_rel in paths:
            raise VaultError("Duplicate source/evidence path")
        paths.update((rel, evidence_rel))
        chosen.append((entry, source, rel, evidence, evidence_rel))
    if requested is not None and requested != {entry["asset_id"] for entry, *_ in chosen}:
        raise VaultError("Requested asset not found")
    if not chosen:
        raise VaultError("No eligible assets")
    target = Path(destination)
    if target.exists() or target.is_symlink():
        raise FileExistsError(f"Destination exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.parent.is_symlink():
        raise VaultError("Destination parent may not be a symlink")
    staging = Path(tempfile.mkdtemp(prefix=".maf-vault-", dir=target.parent))
    try:
        export = []
        for entry, src, rel, evidence, evidence_rel in chosen:
            # Stable materialization folder, no user-controlled destination path.
            folder = staging / "assets" / entry["asset_id"]
            folder.mkdir(parents=True)
            shutil.copyfile(src, folder / rel.name)
            shutil.copyfile(evidence, folder / evidence_rel.name)
            if _sha256(folder / rel.name) != entry["sha256"] or _sha256(folder / evidence_rel.name) != entry["license_evidence_sha256"]:
                raise VaultError("Copied file checksum mismatch")
            export.append({"asset_id": entry["asset_id"], "path": f"assets/{entry['asset_id']}/{rel.name}",
                           "sha256": entry["sha256"], "license_spdx": entry["license_spdx"],
                           "license_evidence": f"assets/{entry['asset_id']}/{evidence_rel.name}",
                           "license_evidence_sha256": entry["license_evidence_sha256"],
                           "reviewed_by_human": True, "use_case": "game_embedding",
                           "release_approved": False})
        report = {"schema_version": SCHEMA, "status": "materialized_not_release_approved", "assets": export}
        (staging / "vault-materialization.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.rename(staging, target)
        return report
    finally:
        if staging.exists():
            shutil.rmtree(staging)
