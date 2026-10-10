# MAF-M1.0-CAV Cloud Asset Vault / Codex Cloud Bootstrap

This is an additive milestone. **MAF-M1.0 already means Asset Foundry Cockpit UI.**
M1.0-CAV does not rename, supersede, or bypass that interface.

## Scope

Git/LFS checkout + a small JSON catalog -> deterministic, selective materialization.
No external fetchers or R2 credentials are needed in this milestone.
The CLI will never download an unverified file, infer rights, auto-mark a human
review, run Godot, approve release, overwrite output, or publish third-party assets.

## Codex Cloud setup

1. Put a manifest and *only legitimately redistributable or authorized-to-store*
   binary assets in a **private** Git repository or Git LFS repository.
2. Connect the repository to Codex Cloud and configure its setup script to install
   the package (`python -m pip install -e ".[dev]"`) and, if LFS is required,
   `git lfs install --local && git lfs pull`.
3. Keep paid/private source assets out of public repos and public CI logs. Do not
   put secrets in git. Use a private repository and explicit scoped access.
4. Run `maf vault materialize path/to/vault.json --dest runs/cloud-vault/session-001 --asset-id triangle`.
5. Consume only the output inside `runs/cloud-vault/session-001/assets`, and
   pass these assets through the existing M0.9 intake/Godot/review flow
   before they are treated as release-ready.

The manifest directory must be inside the checked-out repository.
External hosting/R2 is deferred until authenticated, auditable remote retrieval
can enforce the same checksum and rights-evidence gate.

## Manifest example

```json
{
  "schema_version": "maf.cloud-vault.v1",
  "assets": [
    {
      "asset_id": "triangle",
      "path": "textures/triangle.png",
      "sha256": "<64 lowercase hex digest>",
      "license_evidence": "licenses/triangle-license.txt",
      "license_evidence_sha256": "<64 lowercase hex digest>",
      "license_spdx": "CC0-1.0",
      "reviewed_by_human": true,
      "use_case": "game_embedding"
    }
  ]
}
```

The reviewer field must be truthful. This catalog is **not** a substitute for
M0.9 source provenance or license reviews; no standalone redistribution
permission follows from successful materialization.

## Verification

```bash
pytest -q tests/test_cloud_vault.py
maf vault --help
```

Acceptance: deterministic SHA-256 materialization, selective asset IDs,
symlink/traversal denial, unknown rights denial, no overwrite, and synthetic tests.

## Next milestone

M1.0-CAV.1: authenticated object-store backend (R2), credential isolation,
remote integrity verification, retention and upload consent, and Codex task
bootstrap per-project quotas.
