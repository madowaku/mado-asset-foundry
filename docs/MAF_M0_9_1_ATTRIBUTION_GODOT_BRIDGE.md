# MAF-M0.9.1 Attribution Compiler / Godot Import Bridge

M0.9.1 compiles a Godot 4 project directory from M0.9 **eligible**
game-embedding intake reports. It re-hashes source PNGs and local
license-evidence files and compares report metadata against the current
submission, so edited inputs and forged eligibility are rejected.

There is no web retrieval, source-license scraping, runtime execution,
pack selling, or publishing. An eligible input is **not** a public-release
license. Existing generated-product and itch.io gates remain independent.

## Commands

Run M0.9 intake for each PNG first, then create a plan JSON:

```json
{
  "schema_version": "0.1",
  "project_id": "my-godot-assets",
  "assets": [
    {"submission": "submissions/icon.yaml", "report": "reports/icon.json"}
  ]
}
```

All plan references are relative to the plan's directory, and each
submission's \`local_file\` and \`license_evidence_file\` are relative to the
submission's directory.

```bash
maf asset-godot compile plan.json
maf asset-godot compile plan.json --output-root runs/asset-godot --force
```

Generated files:

```text
runs/asset-godot/my-godot-assets/
  project.godot
  CREDITS.md
  asset_manifest.json
  assets/<asset-id>.png
  evidence/bridge-report.json
```

Explicit limit: only PNG, and no Godot engine launch in this milestone.
The bridge makes a Godot-importable project layout; a later runtime
harness can add engine-level verification. \`--force\` uses a staged build
with a backup and restoration on rename failure.

The per-asset SPDX and license evidence are retained in the manifest.
Credits are inert text with escaped markup. Source policy and intended
use are rechecked before every compile. Redistributable asset packs are
**not** supported.
