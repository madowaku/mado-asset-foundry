# MADO Asset Foundry

Game-asset manufacturing pipeline for turning ideas into curated, QA-checked, game-ready, sellable asset packs.

## M0 vertical slice

`2D Icon Factory -> Curate -> QA -> Refine -> Package -> itch.io-ready ZIP`

## Status

**MAF-M0.5 Product Compiler**

Implemented:

- Asset Recipe + generation planning
- OpenAI image-provider boundary
- raw candidate + provenance evidence
- human Candidate Curator
- selected-candidate image QA
- deterministic image refinement / normalization
- normalized 32x32 game-ready PNG output
- product metadata and explicit license boundary
- native-resolution sprite sheet
- visual contact sheet
- README / LICENSE / MANIFEST / PRODUCT metadata
- deterministic product ZIP
- packaging evidence

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
```

## Package

```bash
maf package runs/<run-id>
```

The compiler packages only normalized assets.

The fixture carries a **dogfood-only draft license**. Replace it before public distribution or sale.

Existing package output is protected. Explicit deterministic rebuild:

```bash
maf package runs/<run-id> --force
```

## Product output

```text
runs/<run-id>/
  raw/
  metadata/
  qa/
  refined/
  refinement/
  product/
    forest-alchemy-icons-0.1.0/
      assets/
      preview/contact_sheet.png
      sprite_sheet.png
      README.md
      LICENSE.txt
      MANIFEST.json
      PRODUCT.json
  dist/
    forest-alchemy-icons-0.1.0.zip
  packaging/
    report.json
```

Generated runs, refined outputs, product bundles, and distribution artifacts are intentionally ignored by git.
