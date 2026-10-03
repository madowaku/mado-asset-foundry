# MADO Asset Foundry

Game-asset manufacturing pipeline for turning ideas into curated, QA-checked, game-ready, sellable asset packs.

## M0 vertical slice

`2D Icon Factory -> Curate -> QA -> Refine -> Package -> itch.io-ready release kit`

## Status

**MAF-M0.8.2c Universal Modder Intake Fixture**

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
