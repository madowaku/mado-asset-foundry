# MADO Asset Foundry

Game-asset manufacturing pipeline for turning ideas into curated, QA-checked, game-ready, sellable asset packs.

## M0 vertical slice

`2D Icon Factory -> Curate -> QA -> Refine -> Package -> itch.io-ready ZIP`

## Status

**MAF-M0.4 Image Refiner / Normalizer**

Implemented:

- Asset Recipe + generation planning
- OpenAI image-provider boundary
- raw candidate + provenance evidence
- human Candidate Curator
- KEEP / MAYBE / REJECT / FAVORITE workflow
- selected-candidate image QA
- alpha/transparency, format, dimensions, edge and duplicate checks
- deterministic image refinement / normalization
- crop, padding, alpha cleanup, resize and palette reduction
- immutable raw sources + refinement evidence

## Setup

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## Generate safely

```bash
maf generate fixtures/forest-alchemy.yaml --count 4 --dry-run --run-id preview-001
maf generate fixtures/forest-alchemy.yaml --count 1
```

## Curate

```bash
maf curate
```

Open `http://127.0.0.1:4173`.

## QA selected candidates

```bash
maf qa runs/<run-id>
```

QA checks only candidates marked `KEEP`.

## Refine into game-ready PNG

```bash
maf refine runs/<run-id>
```

The initial recipe turns QA-approved 1024x1024 source art into centered, padded, palette-limited `32x32 PNG` files.

Existing normalized outputs are protected. Rebuild explicitly with:

```bash
maf refine runs/<run-id> --force
```

## Evidence layout

```text
runs/<run-id>/
  recipe.yaml
  plan.json
  run.json
  raw/
    asset_0001.png
  metadata/
    asset_0001.json
  qa/
    report.json
    asset_0001.json
  refined/
    asset_0001.png
  refinement/
    report.json
    asset_0001.json
```

Generated runs, refined outputs, and distribution artifacts are intentionally ignored by git.
