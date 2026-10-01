# MADO Asset Foundry

Game-asset manufacturing pipeline for turning ideas into curated, QA-checked, game-ready, sellable asset packs.

## M0 vertical slice

`2D Icon Factory -> Curate -> QA -> Package -> itch.io-ready ZIP`

## Status

**MAF-M0.2 Candidate Curator UI**

Implemented:

- Asset Recipe + generation planning
- OpenAI image-provider boundary
- raw candidate + provenance evidence
- human curation states
- local Candidate Curator web UI
- keyboard-first KEEP / MAYBE / REJECT / FAVORITE workflow

## Setup

```bash
python -m pip install -e ".[dev]"
pytest -q
```

## Generate safely

Preview without an API request:

```bash
maf generate fixtures/forest-alchemy.yaml --count 4 --dry-run --run-id preview-001
```

Generate one live candidate:

```bash
maf generate fixtures/forest-alchemy.yaml --count 1
```

The live default remains one candidate intentionally.

## Curate

```bash
maf curate
```

Open:

```text
http://127.0.0.1:4173
```

Keyboard:

- Left / Right: navigate
- 1: Reject
- 2: Maybe
- 3: Keep
- 4: Favorite

Curation updates both `run.json` and per-asset `metadata/*.json`, so M0.3 QA can consume the selected candidates directly.

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
```

Generated runs and distribution artifacts are intentionally ignored by git.
