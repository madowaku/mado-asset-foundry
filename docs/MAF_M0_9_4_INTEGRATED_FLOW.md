# MAF-M0.9.4 Integrated Asset Dogfood Flow

## Purpose

This is the single operator entrypoint connecting MAF-M0.9, M0.9.1,
M0.9.2, and M0.9.3. The goal is to assemble a **real Godot game-embedding
asset preview** from reviewed inputs and leave inspectable evidence for a
human to decide whether the preview, credits and game-use rights are acceptable.

**This does not publish, sell, auto-license, or authorize redistributing
standalone assets.** It does not fetch marketplace assets, use a paid API,
install Godot or Xvfb, or execute a project's third-party code.

## Prepare your assets

Download or create the PNGs yourself under their actual licenses.
For each asset, prepare an M0.9-compatible \`submission.yaml\` in a
directory with that asset and, preferably, a local license evidence file.
The \`reviewed_by_human: true\` flag must reflect a real prior rights review.
Do not mark materials as reviewed just to make the gate pass.

Example \`my-icons/submission.yaml\`:

\`\`\`yaml
schema_version: "0.1"
asset_id: demo-icon
source_id: local
title: Original Demo Icon
creator: Your studio
local_file: demo.png
license_spdx: CC0-1.0
license_evidence_file: LICENSE.txt
reviewed_by_human: true
use_case: game_embedding
commercial: true
\`\`\`

Then create \`flow.yaml\` alongside the input subdirectories:

\`\`\`yaml
schema_version: "0.1"
flow_id: my-first-asset-flow
submissions:
  - my-icons/submission.yaml
\`\`\`

Submission paths must stay beneath the flow recipe directory.
The first milestone supports **1 to 8 PNG images**. More can be split into
several runs. Non-PNG files, unverified rights, unsupported licensing,
duplicate asset IDs, and source path escapes fail closed before Godot launch.

## Run

\`\`\`bash
python -m pip install -e ".[dev]"

maf asset-godot flow run flow.yaml --godot-bin godot
maf asset-godot flow inspect runs/asset-flows/my-first-asset-flow
\`\`\`

For Linux without a local display, run with \`--virtual-display\` and
an operator-installed \`xvfb-run\`. \`--timeout 120\` limits each Godot
process. \`--workspace\` chooses the output directory; \`--force\`
rebuilds the flow using an atomic swap with recovery of the previous run.
No existing outputs are silently overwritten.

One command carries out:
1. Snapshot each submitted PNG and local license evidence with SHA-256.
2. Execute M0.9 \`intake_asset\` for every copied input.
3. Compile M0.9.1 CREDITS and canonical Godot project.
4. Execute M0.9.2 real engine import and Texture2D load checks.
5. Execute M0.9.3 capture with Godot's actual renderer.
6. Emit an \`awaiting_human_review\` summary and preview.

The gallery stage independently repeats runtime verification to
maintain freshness rather than trusting an old report. No model or
external service calls are needed. CI runs a real two-PNG synthetic
fixture through Godot 4.6.1 + Xvfb and uploads the screenshot as a
synthetic-only workflow artifact.

## Run folder

\`\`\`text
runs/asset-flows/<flow-id>/
  summary.json
  plan.json
  inputs/<asset-id>/asset.png
  inputs/<asset-id>/LICENSE.txt
  inputs/<asset-id>/submission.yaml
  reports/<asset-id>/report.json
  godot/<flow-id>/
    project.godot
    CREDITS.md
    asset_manifest.json
    assets/
  runtime/<flow-id>/report.json
  gallery/<flow-id>/
    gallery.png
    CREDITS.md
    report.json
  review/release-check.json   # created only after explicit review
\`\`\`

The path under \`runs/\` is ignored by Git. Never commit downloaded
marketplace assets or commercial source material.

## Human review is the finish line

Open \`gallery/<flow-id>/gallery.png\` and \`CREDITS.md\`, then verify
the actual image, license attribution, and game-embedding rights.
Use hashes from the gallery \`report.json\` to create the human
review JSON as documented in M0.9.3. The review must explicitly
affirm visual, attribution, and game-embedding rights approvals.

\`\`\`bash
maf asset-godot flow review runs/asset-flows/my-first-asset-flow \
  --review human-review.json
maf asset-godot flow inspect runs/asset-flows/my-first-asset-flow
\`\`\`

\`human_release_review_passed\` is **not** \`publication_approved\`.
MAF's product and itch.io public-release checks remain separate.
The review command verifies the plan, runtime report, gallery report,
capture, CREDITS, manifest and saved license evidence. Negative or
incomplete reviews remain blocked. If any source changes, create a new
run rather than silently weakening provenance.

## Verification

Run \`pytest -q tests/test_asset_flow.py\` for deterministic contracts.
The graphical CI job runs
\`pytest -q tests/test_visual_gallery_real_godot.py tests/test_asset_flow_real_godot.py\`
using Godot 4.6.1, Xvfb and synthetic original CC0 PNGs. CI artifacts
include an actual gallery screenshot, CREDITS and summary, not third-party assets.
