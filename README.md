# MADO Asset Foundry

Game-asset manufacturing pipeline for turning ideas into curated, QA-checked, game-ready, sellable asset packs.

## M0 vertical slice

`2D Icon Factory -> Curate -> QA -> Refine -> Package -> itch.io-ready release kit`

## Status

**MAF-M0.7 Godot Dogfood Fixture**

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
