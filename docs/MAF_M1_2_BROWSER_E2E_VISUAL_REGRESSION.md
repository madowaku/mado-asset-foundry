# MAF-M1.2 Cockpit Browser E2E / Visual Regression Harness

## Objective

Drive the real M1.1 Cockpit in a **Chromium browser** rather than relying
only on FastAPI TestClient and JavaScript syntax checks.

The browser tests use a real Uvicorn listener on **127.0.0.1**, with
a temporary local workspace, original synthetic CC0 fixture PNGs and
the exact M1.1 HTML/CSS/JavaScript UI. The Godot-dependent runtime and
gallery steps are stubbed **only in the browser test fixture**, with
realistic evidence files; the separate existing real Godot + Xvfb CI
jobs continue to prove engine import and capture behavior.

## Commands

    python -m pip install -e ".[dev,browser]"
    python -m playwright install --with-deps chromium
    pytest -q e2e/test_cockpit_browser.py

The browser dependency is **optional** and isolated from normal Python
development, Windows full-suite and the normal local server.
The pin is intentional so Chromium behavior changes are reviewed.

## Coverage

- **Desktop 1440x900**: open Cockpit, select a recipe, click Run, wait
  for genuine progress events and 5/5 completed stages, inspect a
  synthetic gallery and two per-asset thumbnails, mark the first
  Pass, second Rework, verify that the final review remains disabled,
  filter decisions, change Rework to Pass, complete the three required
  human affirmations, accept the explicit confirmation dialog, and
  verify persisted per-asset evidence and human attestation.
- **Mobile 390x844**: responsive navigation and two-column KPI layout,
  no horizontal overflow, real Chromium gallery and asset cards,
  decision filters and rejected asset fence. The mobile path never
  bypasses the final review gate.
- **Visual regression**: explicitly versioned, immutable-by-default
  responsive **layout geometry baseline** in
  \`e2e/baselines/cockpit_layout.json\` validates viewport, sidebar,
  hero size, KPI and review columns, panel width and overflow. Each
  checkpoint emits an inspectable full-page screenshot; a repeated
  desktop screenshot is pixel-compared with animation disabled and a
  0.5% threshold to catch non-deterministic/blank captures.
- **Artifacts**: \`runs/browser-e2e/\` contains captured PNGs and
  geometry JSONs, retained in GitHub Actions for 7 days.

**Transparency:** M1.2's automated visual gate is geometry-baseline
regression plus repeated pixel-capture stability and non-blank-image
assertions. It is **not** a pixel-perfect comparison against previously
approved full-page screenshot PNGs. Image snapshots are uploaded for
human visual inspection. Golden image approvals may be introduced
as a later revision once stable environment-specific captures are
approved; never auto-accept arbitrary fresh screenshots as goldens.

## CI

A separate \`browser-e2e-linux\` GitHub Actions job:

1. Installs the package with the optional \`browser\` dependency.
2. Installs Chromium and OS dependencies via Playwright.
3. Runs the real Chromium desktop and mobile interaction tests.
4. Uploads PNGs and measured geometry as artifacts whether the test
   passes or fails.

Existing Windows, Linux contract, Godot import and real graphical
smoke jobs remain unchanged. Running a local Cockpit does **not**
require Playwright.

## Security and governance

The browser cannot provide arbitrary asset paths or external
executables and the test fixture is synthetic. The M1.1 server's
loopback-only policy, mutation headers, per-asset visual Pass fence,
manual final attestation and absolute no-auto-publication guarantees
are preserved. A successful UI test does not itself approve the
release of any marketplace asset.
