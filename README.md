# MADO Asset Foundry

Game-asset manufacturing pipeline for turning ideas into curated, QA-checked, game-ready, sellable asset packs.

## M0 vertical slice

`2D Icon Factory -> Curate -> QA -> Refine -> Package -> itch.io-ready release kit`

## Status

**MAF-M1.2 Cockpit Browser E2E / Visual Regression Harness**

Implemented:

- Asset Recipe + generation planning
- OpenAI image-provider boundary
- human Candidate Curator
- selected-candidate image QA
- deterministic image normalization
- Product Compiler with deterministic ZIP
- itch.io listing metadata compiler
- 630x500 cover generation
- three truthful product screenshots
- Generative AI disclosure metadata
- license/public-release gate
- human release checklist
- no automatic marketplace publishing
- Godot dogfood fixture generated from packaged product assets
- optional headless Godot import + Texture2D verifier
- in-engine icon gallery with F12 evidence capture

## Setup

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## Core loop

```bash
maf generate fixtures/forest-alchemy.yaml --count 1
maf curate
maf qa runs/<run-id>
maf refine runs/<run-id>
maf package runs/<run-id>
maf itch-ready runs/<run-id>
maf godot-fixture runs/<run-id>
```

The fixture deliberately uses a dogfood-only draft license. Therefore `maf itch-ready` should generate the kit but report `Ready: NO` until a real public distribution license is supplied.

## itch.io release kit

```text
runs/<run-id>/itch/<product-version>/
  READY.json
  listing.json
  title.txt
  short-description.txt
  description.md
  tags.json
  ai-disclosure.md
  policy-notes.md
  release-checklist.md
  cover.png
  screenshots/
  upload/
```

Public publishing remains a human action.


## Godot dogfood

Build the Godot project from the packaged product:

```bash
maf godot-fixture runs/<run-id>
```

Run real Godot import + resource verification when a Godot executable is available:

```bash
maf godot-fixture runs/<run-id> --force --godot-bin godot
```

The visual gallery uses nearest-neighbor texture filtering. Press F12 in the running scene to save `evidence/gallery.png`.


## Real Forest Alchemy production run

Plan without spending API credits:

```bash
maf production plan
maf production start --stage probe
```

Make the first real one-image probe explicit:

```bash
maf production start --stage probe --live
```

Then scale deliberately:

```bash
maf production start --stage pilot --live
maf production start --stage production --live
```

The production recipe is `fixtures/forest-alchemy-production.yaml`: 12 generated candidates, 6 human-selected final icons.

After the production-stage run is fully curated:

```bash
maf production advance runs/<production-run-id> --godot-bin godot
```

This runs QA, normalization, product compilation, itch.io-ready preparation, and Godot dogfood verification. Public marketplace publishing is still manual.


## Codex subscription ImageGen bridge

Check the Codex CLI without generating an image:

```bash
maf codex-imagegen-check
```

Plan the Codex-backed Forest Alchemy run:

```bash
maf production plan fixtures/forest-alchemy-codex.yaml
```

Generate one real probe through Codex built-in ImageGen:

```bash
maf production start fixtures/forest-alchemy-codex.yaml --stage probe --live
```

The orchestration model defaults to `gpt-6-luna`. Codex built-in image generation currently renders with `gpt-image-2`, whose transparent-background support is preview. MAF validates the returned alpha channel and rejects opaque PNGs when transparency is required.

For a production path that explicitly uses GPT Image 2.5 transparency, keep using the `openai-image` provider with `gpt-image-2.5-flare` or `gpt-image-2.5-sunburst`.


## OSS Asset Skill intake

M0.8.2a adds a read-only intake boundary for local OSS Skills and repositories.

```bash
maf skill intake fixtures/skills/sample-background-remover
maf skill validate skills/manifests/sample-background-remover.json
```

Intake discovers structural files such as `SKILL.md`, README, LICENSE, and `scripts/`, then writes a normalized `intake_only` manifest plus evidence. It does **not** execute third-party code and does not infer capabilities yet; capability classification arrives in M0.8.2b.


## Capability Scanner

Classify a local Skill without executing it:

```bash
maf skill scan fixtures/skills/sample-background-remover
```

M0.8.2b maps only explicit phrases from `SKILL.md` and README into the MAF capability taxonomy, then records source-file and matched-term evidence. It also detects Python/Node/ffmpeg/ONNX Runtime requirements and performs conservative SPDX-style license detection.

The structural `maf skill intake` command remains unchanged and intentionally produces no capabilities.


## Universal Modder intake fixture

M0.8.2c adds a deterministic multi-Skill pack scan using a curated, non-executable snapshot of
[rehan-remade/universal-modder](https://github.com/rehan-remade/universal-modder) pinned to commit
`15d6f9d5fbd32de9b1884f29ddec3be9133bd912`.

```bash
maf skill scan-pack fixtures/skills/universal-modder-snapshot
```

The pack scan discovers every `skills/*/SKILL.md`, runs the existing M0.8.2b classifier per Skill, then
aggregates repository-level evidence for the `um` CLI, MCP servers, Python/tool/service dependencies,
root license, and explicit safety constraints. It writes member manifests plus
`evidence/skill-pack-scan/universal-modder/pack-report.json`.

The fixture contains only text metadata and selected Skill excerpts. It vendors no Universal Modder
executables, Python modules, game files, credentials, or generated assets, and the scan never imports,
installs, or executes third-party code.


## Skill Registry / Resolver

Build one deterministic registry from scanned manifests, including nested pack manifests:

```bash
maf skill registry build skills/manifests
maf skill list
maf skill show sample-background-remover
maf skill resolve background_remove
```

Resolution is deliberately conservative:

- exactly one `executable` candidate → `resolved`
- multiple executable candidates → `ambiguous`
- only `intake_only` candidates → `candidate_only`
- no usable candidates → `unresolved`

An intake-only Skill is never silently treated as executable.

M0.8.2d also extends the taxonomy for future TripoSR / Stable Fast 3D intake with `image_to_mesh`, `mesh_texture_bake`, `uv_unwrap`, `material_predict`, `image_delight`, `mesh_decimate`, `mesh_repair`, `mesh_qa`, and `glb_export`.


### Pinned 3D candidate fixtures

Two metadata-only fixtures are included for resolver dogfood:

```text
fixtures/skills/triposr-snapshot/
  upstream: VAST-AI-Research/TripoSR
  ref: 107cefdc244c39106fa830359024f6a2f1c78871
  license: MIT

fixtures/skills/stable-fast-3d-snapshot/
  upstream: Stability-AI/stable-fast-3d
  ref: ff21fc491b4dc5314bf6734c7c0dabd86b5f5bb2
  license: Stability AI Community License
```

These fixtures contain only curated metadata used for deterministic scanning tests. They do not vendor model weights or executable upstream code.

After scanning both, `maf skill resolve image_to_mesh` reports both as `intake_only` candidates. Neither is automatically executed.


## Adapter Contract / Preflight

M0.8.2e adds the execution boundary between discovered Skills and future runnable adapters.

```bash
maf skill preflight triposr-snapshot
maf skill preflight stable-fast-3d-snapshot
```

Preflight never executes third-party Skill code. It checks only:

- explicit MAF adapter registration
- capability-contract agreement
- detected license metadata
- source directory presence
- required executable discovery
- required Python module discovery
- required environment-variable presence
- required source-file presence
- whether adapter execution is actually implemented

Statuses:

```text
unregistered   no explicit MAF adapter definition
blocked        one or more required checks failed
contract_only  contract/dependencies pass, but run() is not implemented
ready          every check passes and execution is implemented
```

Only `ready` is promotion-eligible. M0.8.2e does not automatically edit manifests or promote Skills. TripoSR gained a real local runner in M0.8.2f; Stable Fast 3D remains contract-only.


## TripoSR Local 1-Asset Probe

M0.8.2f registers the first real external Skill runner. It requires a local TripoSR checkout pinned to `107cefdc244c39106fa830359024f6a2f1c78871`, a local model directory containing `config.yaml` and `model.ckpt`, and exactly one input image.

MAF does not clone TripoSR, install dependencies, download weights, or authenticate.

```powershell
maf skill probe triposr-snapshot \
  --input .\asset.png \
  --source-root C:\Tools\TripoSR \
  --model-path C:\Models\TripoSR \
  --python-bin C:\Tools\TripoSR\.venv\Scripts\python.exe \
  --format glb
```

The adapter always passes the local model directory through `--pretrained-model-name-or-path`, preventing the upstream Hugging Face fallback. It records the input hash, source pin, model-config hash, exact command, stdout/stderr, and mesh hash under `runs/skill-probes/<run-id>/evidence/`.

To keep the probe fully local, MAF currently requires a genuinely transparent RGBA input. It prepares a gray-background RGB conditioning image itself and calls upstream TripoSR with `--no-remove-bg`, so `rembg.new_session()` is never invoked and cannot trigger a hidden background-model download. Opaque inputs are rejected in this milestone.


## Effekseer Intake / VFX Capability Probe

M0.8.2g adds a metadata-only VFX capability probe for three pinned OSS components:

```text
Effekseer
  upstream ref: 82b37081a302b9f9eff0bf14dc6c845fca8c3c54
  role: authoring + runtime
  license: MIT

effekseer-ai
  upstream ref: 208922ef192220322c2a79e1243ed51ff7d2b7af
  role: Python CLI + MCP authoring bridge
  verified upstream compatibility: Effekseer 1.80.6 on Windows
  license: MIT

EffekseerForGodot4
  upstream ref: 8706d2917c2487efac3a4943c16a10dfcfc5b127
  role: Godot Engine 4.x runtime playback
  license: MIT
```

Run the combined read-only probe:

```powershell
maf skill vfx-probe
```

It scans the fixtures into MAF capabilities such as `vfx_create`, `vfx_edit`, `vfx_runtime_export`, `vfx_mcp_authoring`, and `godot_vfx_playback`, then writes `evidence/vfx-capability-probe/report.json`.

No Effekseer executable, DLL, MCP server, Godot plugin, or external code is launched in this milestone.


## Effekseer AI Local 1-Effect Probe

M0.8.2h registers `effekseer-ai-snapshot` as the first executable VFX adapter.

The live slice is intentionally tiny:

```text
effekseer-ai new
  -> effect.efkefc
effekseer-ai node-add --name "MAF Spark Probe"
  -> one child node
effekseer-ai export
  -> effect.efk
```

Requirements are explicit and local:

- Windows
- a local `effekseer-ai` checkout pinned to `208922ef192220322c2a79e1243ed51ff7d2b7af`
- an installed `effekseer-ai` CLI
- .NET runtime available to the bridge
- the official Effekseer **1.80.6 compatibility target**
- `Tool/bin/EffekseerCore.dll`

MAF never searches the machine for an Effekseer installation and does not install or download any dependency.

Because the `maf` console script may not be on PATH, the reliable Windows invocation is:

```powershell
python -m mado_asset_foundry.cli skill vfx-effect-probe `
  --effekseer-ai-bin C:\Tools\effekseer-ai\.venv\Scripts\effekseer-ai.exe `
  --source-root C:\Tools\effekseer-ai `
  --effekseer-bin-dir C:\Tools\Effekseer1806\Tool\bin `
  --name "MAF Spark Probe"
```

Evidence is written under `runs/vfx-effect-probes/<run-id>/evidence/` and includes:

- pinned effekseer-ai source ref and source-file hashes
- effekseer-ai executable hash
- EffekseerCore.dll hash and size
- the upstream effekseer-ai pin used by the adapter contract
- exact `new`, `node-add`, and `export` commands
- JSON stdout and stderr for every step
- source/runtime file hashes and sizes
- the compatibility target `1.80.6`

This milestone proves structural authoring/export only. A successful `.efk` export is **not** treated as visual-quality approval; Godot playback and visual QA belong to the next dogfood stage.


## Effekseer Godot Runtime Dogfood / Playback Evidence

M0.8.2i takes a successful M0.8.2h effect run and proves that the official Godot 4 plugin can import the `.efkefc` source and start it through `EffekseerEmitter3D`.

The official Godot release sequence has no 1.80.6 plugin release: 1.80.5.1 is followed by 1.80.7. This milestone therefore records the compatibility delta explicitly:

```text
Effekseer authoring / effekseer-ai target: 1.80.6
EffekseerForGodot4 runtime plugin:       1.80.7
```

The required plugin artifact is the official `EffekseerForGodot4-180_7.zip` release asset. MAF accepts it only when its SHA-256 is:

```text
581e02b4ad773df39674c6c5d57bc6c132adf6fe38ae60a75bf230f251d56fef
```

MAF does not download or install Godot or the plugin. It verifies the archive, safely extracts `addons/effekseer` into a generated dogfood project, runs Godot import, then runs a headless playback scene.

The official importer recognizes `.efkefc`, not the sibling runtime `.efk`. The `.efk` remains part of the source evidence while Godot imports the `.efkefc` into an `EffekseerEffect` resource.

```powershell
python -m mado_asset_foundry.cli skill vfx-godot-dogfood `
  .\runs\vfx-effect-probes\<effect-run> `
  --plugin-archive C:\Tools\EffekseerForGodot4-180_7.zip `
  --godot-bin C:\path\to\godot.exe
```

Acceptance requires all of the following:

- official plugin archive hash matches
- plugin reports version 1.80.7 and contains the Windows x86_64 GDExtension binary
- Godot is version 4.2 or newer
- the `.efkefc` loads as `EffekseerEffect`
- `EffekseerEmitter3D` exists
- `play()` is called
- `is_playing()` returns true
- import/playback stdout, stderr, commands, hashes, and runtime JSON are preserved

This is **runtime playback evidence, not visual-quality approval**. The current one-node structural probe may be visually trivial. A later VFX recipe/visual QA milestone should create a deliberately visible effect and capture rendered frames.


## M0.9: Asset source registry and offline license-aware intake

Manual discovery and explicit per-asset evidence keep external material separate from
MAF's generated-product licensing. No scraping, auto-download, asset copying, or publishing.

```bash
maf asset-source list
maf asset-source show kenney
maf asset-source intake fixtures/m0-9-demo/asset.yaml
```

Evidence is written to `evidence/asset-intake/<asset-id>/report.json`.
`eligible` means an intake gate passed, **not** permission for release or resale.
Read [M0.9 design and limitations](docs/MAF_M0_9_ASSET_SOURCE_LICENSE_INTAKE.md).

## M0.9.1: Godot asset import with attribution

`maf asset-godot compile plan.json` compiles eligible game-embedding PNGs, CREDITS.md, and source hashes into a Godot project without running Godot. See [design](docs/MAF_M0_9_1_ATTRIBUTION_GODOT_BRIDGE.md).

## M0.9.2: Godot Runtime Import QA / License Evidence Gate

After `maf asset-godot compile plan.json`, run `maf asset-godot qa plan.json <project-folder> --godot-bin godot` to re-verify provenance and input hashes and perform real Godot headless PNG import. The tool runs a sanitized temporary project, records logs, and never authorizes publishing. See [the M0.9.2 spec](docs/MAF_M0_9_2_RUNTIME_IMPORT_QA.md).

## M0.9.3: Godot rendered gallery and manual attribution release review

Generate an actual renderer screenshot: `maf asset-godot gallery plan.json <godot-project> --godot-bin godot` (Linux CI: add `--virtual-display`). Inspect the screenshot and CREDITS manually, then run `maf asset-godot release-check plan.json <godot-project> <gallery-evidence-dir> --review review.json`. The review gate binds checks to image, credits and manifest SHA-256, revalidates asset-level rights and never publishes. See [M0.9.3 spec](docs/MAF_M0_9_3_VISUAL_GALLERY_ATTRIBUTION_RELEASE_GATE.md).


## M0.9.4: One-command game asset dogfood flow

M0.9-M0.9.3 are merged on main. M0.9.4 orchestrates their public Python
boundaries from one flow recipe. Source PNGs and human-reviewed
license evidence are snapshotted into the run; no external URLs are fetched.

```bash
maf asset-godot flow run flow.yaml --godot-bin godot
maf asset-godot flow inspect runs/asset-flows/my-first-asset-flow
maf asset-godot flow review runs/asset-flows/my-first-asset-flow --review human-review.json
```

For Linux CI or servers, pass `--virtual-display` and install Xvfb explicitly.
The flow creates a Godot-importable project, real Godot QA evidence, a
rendered gallery PNG, CREDITS and a summary. It **always stops before
publication**, requiring an explicit human visual/attribution/rights
attestation. The final review never approves standalone asset resale or
automatic distribution.

[Start here: full flow recipe and workflow](docs/MAF_M0_9_4_INTEGRATED_FLOW.md).


## M1.0: Local browser Cockpit

Run `maf cockpit serve --recipes recipes/asset-flows --workspace runs/asset-flows --godot-bin godot` and open **http://127.0.0.1:4174**. No `--godot-bin` means read-only mode. Choose an allowlisted recipe, inspect the Godot preview and per-asset license/attribution evidence, and explicitly sign the three-part human review. The Cockpit never publishes or resells anything. See [M1.0 Cockpit guide](docs/MAF_M1_0_COCKPIT_UI.md).


## M1.1: Stage progress and individual visual assessments

The local Cockpit now displays the **actual five-stage pipeline state**
(intake → attribution → Godot runtime → gallery → evidence). Per-asset
Pass / Rework / Reject with human reviewer notes are persisted with
SHA-256 bindings to the captured image, credits, manifest and asset
source. Compare decisions with review-status filters and counts.
Every asset must be Pass before the existing human final review gate
can record its approval. No auto publication or redistribution.

[MAF-M1.1 Workflow Guide](docs/MAF_M1_1_COCKPIT_LIVE_PROGRESS_VISUAL_REVIEW.md).


## M1.2: Real browser E2E and responsive visual regression

The Cockpit now has a real Chromium browser acceptance harness covering
desktop/mobile layout, recipe execution, true stage progress, per-asset
Pass/Rework/Reject, rejection of incomplete final review, and the
hash-bound human attestation. Screenshots and geometry evidence are
uploaded as GitHub Actions artifacts on every pull request.

Use `python -m pip install -e '.[dev,browser]'`, followed by
`python -m playwright install --with-deps chromium` and
`pytest -q e2e/test_cockpit_browser.py`.

Visual regression checks an explicit approved **responsive layout geometry**
reference and repeated pixel screenshot stability. It does not yet claim
pixel-perfect screenshot goldens. Existing real Godot engine smoke tests
remain separate. See
[MAF-M1.2 Browser Harness](docs/MAF_M1_2_BROWSER_E2E_VISUAL_REGRESSION.md).
