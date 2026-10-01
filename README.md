# MADO Asset Foundry

Game-asset manufacturing pipeline for turning ideas into curated, QA-checked, game-ready, sellable asset packs.

## M0 vertical slice

`2D Icon Factory -> Curate -> QA -> Refine -> Package -> itch.io-ready ZIP`

## Status

**MAF-M0.3 Image QA**

Implemented:

- Asset Recipe + generation planning
- OpenAI image-provider boundary
- raw candidate + provenance evidence
- human Candidate Curator
- KEEP / MAYBE / REJECT / FAVORITE workflow
- selected-candidate image QA
- alpha/transparency and dimension validation
- edge-clipping warning
- exact + perceptual duplicate detection
- per-asset and run-level QA evidence

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

Keyboard:

- Left / Right: navigate
- 1: Reject
- 2: Maybe
- 3: Keep
- 4: Favorite

## QA selected candidates

```bash
maf qa runs/<run-id>
```

QA checks only candidates marked `KEEP`.

The generated source is checked against `generation.render_size` (currently 1024x1024), not the final intended 32x32 output. Final normalization belongs to the refinement stage.

Hard failures make the CLI exit non-zero. Warnings such as likely clipping or duplicates remain reviewable.

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
```

Generated runs and distribution artifacts are intentionally ignored by git.
