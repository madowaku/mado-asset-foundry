# MAF-M1.2.1 Golden Screenshot / Visual Delta Inspector

## What is genuinely verified

The M1.2.1 Chromium E2E harness compares seven **actual full-resolution
screenshots** against seven **frozen PNG reference images**, promoted
from the previously successful M1.2 Chromium job. It does not
generate or approve a new baseline in a normal test run.

Golden provenance is pinned in \`e2e/goldens/manifest.json\`:
- Repository \`madowaku/mado-asset-foundry\`
- Known-good Actions workflow run \`38016104787\`
- Artifact ID \`11656501819\`
- Original commit \`4ad5db9e06425e4900744ba4dd0a209cb3c77ef9\`
- Exact image SHA-256 and dimensions for seven checkpoints

Each reference PNG is checked against its SHA-256 **before** comparison.
Missing or changed references fail rather than silently blessing current
screenshots. Source screenshots were produced from synthetic test assets.
This is a **proposed reviewable baseline** until its PR is reviewed.

## Checkpoints

Desktop 1440 × 900 viewport (full-page captures):
- empty Cockpit
- two-asset gallery before human review
- Rework pending
- both assets reviewed and final review recorded

Mobile 390 × 844:
- empty Cockpit
- gallery before review
- Reject recorded

The desktop empty checkpoint is captured again after reload and checked
against the **same locked reference** to detect unstable rendering.

## Gate and inspector

For each screenshot:
1. Decode expected and actual PNG without changing either.
2. Fail on mismatched dimensions.
3. Calculate per-channel absolute difference.
4. Mark changed pixels when maximum channel delta exceeds **16**.
5. Pass only when changed-pixel fraction is no greater than **2%**
   and mean absolute RGB error is no greater than **3/255**.
6. Emit \`<checkpoint>-metrics.json\`, \`<checkpoint>-diff.png\` (red
   = changed), and \`<checkpoint>-before-after-diff.png\` (left golden,
   center current, right diff), including for failed comparisons.

Artifacts are under
\`runs/browser-e2e/visual-delta/<checkpoint>/\`. They are retained by
GitHub Actions for seven days and available for local inspection.

The gate is tolerant of minor antialiasing but catches meaningful
visual shifts beyond explicit limits. It does not replace human UX
inspection, WCAG assessment or font/platform matrix tests.

## Running

    python -m pip install -e ".[dev,browser]"
    python -m playwright install --with-deps chromium
    pytest -q tests/test_visual_goldens.py
    pytest -q e2e/test_cockpit_browser.py

Normal MAF operation does not need Playwright or extra services.

## Baseline adoption and changes

The seven frozen references were imported from the known-good historical
CI run using the separately restricted one-time bootstrap workflow.
The importer checks **both expected content hashes and PNG dimensions**,
refuses to overwrite any existing golden, and records the pinned origin
in source control.

When a deliberate UI redesign changes screenshots, do **not** run a
"bless all current screenshots" command in CI. Review the full Before /
After / Diff evidence, obtain human approval, then submit a separate PR
that changes the PNGs and SHA-256 manifest together with an explanation.
No image is automatically approved based on a passing build.

This preserves the MAF-M1.1 license, review and publication fence:
Playwright E2E uses original synthetic assets, while real Godot import
and rendering still have independent CI jobs. Passing visual QA does
not grant publication, redistribution, or marketplace rights.
