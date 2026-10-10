# MAF-M1.1 Cockpit Live Progress / Visual Review UX

## Outcome

A real local UI for observing M0.9.4 stages as they run, comparing
visual decisions per asset, and safely completing a human gate. Built
on top of M1.0 FastAPI + local HTML/JS/CSS without adding npm, a
database, paid API, upload, or any publishing capability.

## Stage progress: actual state, not guessed percentage

The existing flow runner accepts an optional in-process
\`progress(stage, status)\` callback. Five monotonic named stages:
\`intake\`, \`attribution\`, \`runtime\`, \`gallery\`, \`evidence\`.
Each stage emits \`running\` and \`completed\` events; a failing stage
emits \`failed\`. Callback exceptions do not affect the underlying
asset/license QA gate.

Cockpit jobs retain the stage snapshot in memory and serve it through
\`GET /api/jobs/{job_id}\`. Existing job shape and semantics are
preserved. UI polls this endpoint and shows precise stage labels and
completion count. Status is not persisted across server restart; the
final run evidence and gallery remain on disk.

The GUI never reports a completed stage until the corresponding
Python operation finishes successfully. The human approval stage is
not auto-completed.

## Visual decision desk

For each asset in a completed flow, the reviewer:

1. Opens/inspects the source thumbnail in context of the real Godot
   screenshot (the M0.9.3 screenshot remains available above).
2. Records Pass, Rework, or Reject and a reviewer name.
3. Records notes, required for Rework/Reject.
4. Filters the gallery by pending/pass/rework/reject. Counts show
   differences and outstanding work for each asset.
5. When **every** asset has a Pass, they can use the existing three-
   checkbox human final gate. The final gate still verifies source
   integrity, license evidence, gallery image, credits, and hashes.

The \`POST /api/flows/{flow_id}/assets/{asset_id}/visual\` API has
strict typed values. The sheet lives in
\`runs/asset-flows/<id>/review/visual-decisions.json\`, with a
screenshot/CREDITS/manifest SHA-256 binding and each asset's SHA-256.
Writes are atomic and reject symlinked review paths. Edited sources,
reports, credits or screenshots remain blocked by the M1.0 integrity
checks. A completed final human review locks further visual edits.

The final human attestation now records a SHA-256 of the completed
per-asset sheet. Its integrity is checked on subsequent detail views.
Existing v1.0 completed reviews without a visual sheet remain readable
as historical evidence; they do not gain retroactive M1.1 per-asset
review claims.

## Security and review semantics

No new route performs publication or asset-pack redistribution.
\`publication_approved\` remains false. Visual Pass is a human visual
observation, not a legal determination of commercial rights.
Human review still asks for separate attribution and game embedding
rights approval. Browser mutations inherit M1.0 local Trusted Host,
same-origin/custom header, and no arbitrary path rules.

One process, one local operator, one active run. Active job stage
information is in memory and not a durable queue.

## Use

    maf cockpit serve --recipes recipes/asset-flows \
      --workspace runs/asset-flows --godot-bin godot

Then open http://127.0.0.1:4174 and select an existing or new flow.
The production run displays stage-by-stage state. Use the visual
review desk to mark every asset before pressing final review.

## Verification

    python -m pip install -e ".[dev]"
    pytest -q tests/test_asset_flow.py tests/test_cockpit_api.py
    node --check src/mado_asset_foundry/ui/cockpit/cockpit.js

GitHub Actions also checks the Windows full suite, Linux M1.1
contracts, and the existing real Godot resource import and screenshot
smokes. Visual-browser screenshot comparison is not in M1.1 acceptance.

## Deferred

Durable job event streaming/history, authenticated remote Cockpit,
per-image before/after renders, multiuser review assignment, and
automated production publish remain intentionally out of scope.
