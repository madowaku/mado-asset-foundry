# MAF-M1.0 Asset Foundry Cockpit UI

## Purpose

The M1.0 Cockpit is a local-only browser interface to the merged M0.9
through M0.9.4 pipeline. It provides recipe selection, a complete
asset manufacturing run, gallery, source/license evidence, credits and
an explicit human review interface. Existing flow and review Python
functions remain authoritative. It never publishes assets.

## Launch

Install dependencies:

    python -m pip install -e ".[dev]"

Create a flow YAML in the configured recipe directory. Follow the
M0.9.4 integration guide for relative submission paths and per-asset
license evidence. Human-reviewed flags must reflect actual prior rights
verification.

    maf cockpit serve --recipes recipes/asset-flows --workspace runs/asset-flows --godot-bin godot

Visit http://127.0.0.1:4174

On Windows, pass the absolute path to the installed Godot executable,
for example:

    maf cockpit serve --godot-bin "C:\Tools\Godot_v4.6.1-stable_win64.exe"

Linux virtual display environments can use --virtual-display after
installing xvfb-run. Without --godot-bin, the UI is read-only and can
still show previously completed runs.

## Workflow

Choose a recipe from the operator-approved recipe directory, then
press Run full pipeline. The browser receives a job ID and polls
progress/status. The single process permits one running job at a time.

Once complete, inspect the real Godot gallery PNG, individual PNG
thumbnails, credits, source/license metadata, and SHA-256 evidence.
A separate form asks the human reviewer to confirm visual quality,
attribution completeness, and game embedding rights explicitly.
It also requires a reviewer name and notes. The review calls the
existing M0.9.4 evidence gate, recording the human review as an
attestation and binding it to screenshot, credits and manifest hashes.

A successful review does not approve publication or standalone
redistribution. The interface contains no marketplace upload or
publish capability.

## Local security model

- The serve command binds ONLY to loopback, 127.0.0.1 or ::1.
  There is no authentication, so never reverse-proxy it publicly.
- Trusted Host checks and secure browser headers are enabled, with
  strict same-origin mutations, an X-MAF-Action custom header, and no
  CORS allowance. No CDN, external scripts or assets are loaded.
- Browser controls cannot supply filesystem paths, executable names,
  upload external code, or override the configured Godot runtime.
  Only simple filenames in the explicitly allowed recipe directory
  can be launched.
- Gallery, thumbnails, credits, and reports are served from validated
  local run IDs; traversal and symlink files are refused.
- User-controlled metadata is inserted with textContent rather than
  untrusted HTML injection.
- Human review is not automatically checked or silently overwritten.
  Notes and approval flags are kept beside the existing review gate.
- Job state is currently in-memory and vanishes when the server
  restarts; completed evidence remains durable under runs/.
- One local operator is the supported model. No multiuser authentication,
  network daemon, persistent job broker, or third-party assets are
  provided by M1.0.

## Tests

    pytest -q tests/test_cockpit_api.py
    node --check src/mado_asset_foundry/ui/cockpit/cockpit.js

CI runs these contracts along with the full Windows suite and the
existing real Godot + Xvfb pipeline tests. Visual-browser screenshot
comparison is not included in M1.0 acceptance.

## Potential follow-up

Stage-level progress events, durable job queue, per-asset visual
decisions, pagination, and Cockpit integration with mado-cockpit are
future scope.
