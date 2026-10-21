from __future__ import annotations

import hashlib
import json

import pytest

from mado_asset_foundry.cloud_vault import VaultError, materialize, SCHEMA


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def fixture(tmp_path):
    root = tmp_path / "vault"
    root.mkdir()
    (root / "triangle.png").write_bytes(b"original synthetic asset")
    (root / "LICENSE.txt").write_bytes(b"Original synthetic fixture for tests")
    entry = {
        "asset_id": "triangle", "path": "triangle.png",
        "sha256": _hash(b"original synthetic asset"),
        "license_evidence": "LICENSE.txt",
        "license_evidence_sha256": _hash(b"Original synthetic fixture for tests"),
        "license_spdx": "CC0-1.0",
        "reviewed_by_human": True, "use_case": "game_embedding",
    }
    manifest = root / "vault.json"
    manifest.write_text(json.dumps({"schema_version": SCHEMA, "assets": [entry]}))
    return root, manifest, entry


def test_verified_materialization(tmp_path):
    root, manifest, entry = fixture(tmp_path)
    out = tmp_path / "out"
    report = materialize(manifest, out)
    assert report["status"] == "materialized_not_release_approved"
    assert (out / "assets/triangle/triangle.png").read_bytes() == b"original synthetic asset"
    assert report["assets"][0]["release_approved"] is False
    with pytest.raises(FileExistsError):
        materialize(manifest, out)


def test_hash_tampering_fails_without_outputs(tmp_path):
    root, manifest, entry = fixture(tmp_path)
    (root / "triangle.png").write_bytes(b"tampered")
    with pytest.raises(VaultError, match="SHA-256"):
        materialize(manifest, tmp_path / "out")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("field,value", [
    ("reviewed_by_human", False),
    ("use_case", "standalone_asset_pack"),
    ("license_spdx", "unknown"),
    ("path", "../secret.png"),
    ("path", "/tmp/secret.png"),
])
def test_rights_and_paths_block(tmp_path, field, value):
    root, manifest, entry = fixture(tmp_path)
    entry[field] = value
    manifest.write_text(json.dumps({"schema_version": SCHEMA, "assets": [entry]}))
    with pytest.raises(VaultError):
        materialize(manifest, tmp_path / "out")


def test_symlink_and_selection(tmp_path):
    root, manifest, entry = fixture(tmp_path)
    (root / "triangle.png").unlink()
    (root / "triangle.png").symlink_to(root / "LICENSE.txt")
    with pytest.raises(VaultError, match="Symlinks"):
        materialize(manifest, tmp_path / "out")
    (root / "triangle.png").unlink()
    (root / "triangle.png").write_bytes(b"original synthetic asset")
    with pytest.raises(VaultError, match="Requested asset not found"):
        materialize(manifest, tmp_path / "out", asset_ids=["missing"])
