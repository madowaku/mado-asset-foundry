# MAF M1.3 / MGSF Pixel Art Atlas Intelligence M0.1

## Purpose

Create a research-only, human-led reference library for 16×16 sprites in MADO Asset Foundry. Source: https://huggingface.co/datasets/Angais/pixel-art-atlas-1.4m . It provides 1,409,404 AI-generated sprites and fields image, caption, subject and row_id. **This is not an asset-pack distributor or model trainer.**

## Guardrails

- No network calls unless operator explicitly passes --fetch. No default full-dataset download, model training, paid APIs or asset export.
- Local research runs are created only into fresh output directories. Raw external sprites and indexes must remain outside Git.
- Captions are approximate and have not been systematically verified. The upstream train/validation split does not guarantee unseen subjects.
- Publisher CC0-1.0 applies only to rights it may waive; Krea and third-party rights still require review. M0.1 does **not** approve commercial game inclusion, training or redistribution.
- No bypass around MAF-M0.9 source/license evidence, curation, Godot QA and human release gates.
- Palette count, visible-fraction, alpha flags, border contact and pixel hashes describe geometry, **not aesthetic quality**. Do not turn those values into a Human Touch quality score.

## Setup (from MADO Asset Foundry repository)

    python -m pip install -e ".[dev,atlas]"
    pytest -q tests/test_pixel_atlas.py

The optional atlas dependency installs Hugging Face datasets. Normal MAF installation does not need it.

## Commands

Small explicit network probe:

    maf atlas sample --fetch --count 256 --output runs/pixel-atlas-probe-001

Larger deliberate sample (hard cap is 5,000):

    maf atlas sample --fetch --count 5000 --output runs/pixel-atlas-pilot-001

Create a focused comparison grid from previously sampled sprites:

    maf atlas sheet runs/pixel-atlas-pilot-001 --subject slime --output runs/slime-comparison.png

For reproducibility specify --revision with an upstream Hugging Face commit SHA. Default revision main is mutable. Sampling takes the **first N streaming rows**; it is not statistically representative. You can also pass --split validation, but this is not an unseen-subject evaluation.

Each bundle contains:
- sprites/<row_id>.png : normalized native 16×16 RGBA PNG, for local research only
- index.jsonl : original caption, subject, row ID, split, PNG and pixel hashes, descriptive metrics
- summary.json : provenance, counts, exact duplicates, flagged issues, explicit rights hold
- contact-sheet.png : nearest-neighbor image overview (max 128 items)

## MGSF handoffs

| Consumer | M0.1 handoff | Boundary |
|---|---|---|
| Organic Pixel Art Director | Color/alpha descriptors, visual reference grids | No automatic style copying |
| Pixel Art Quality Gate | Hash-based exact duplicates, inspect flags | No AI quality score |
| Human Touch Lab | Small visual batches for subjective review | Human ratings are M0.2 |
| Creative Taste Learning | Stable PNG hashes and subject keys | No training without curated labels and rights clearance |
| Godot / Game Test Player | Future owned-asset comparison fixture | No direct export to a game |

## Acceptance

- Offline synthetic pytest suite passes without network or third-party media.
- No network access by default; explicit --fetch and at most 5,000 rows.
- Bad dimensions and duplicate row IDs fail closed; outputs are staged then atomically moved, never silently overwritten.
- Data provenance and rights holds are included in summary.json.
- No Atlas sprites are committed into the repository.

## M0.2 proposal

Add opt-in human ratings for legibility, distinctiveness, delightful irregularity and fit with a particular game's art direction. Bind each review to image SHA-256. Then compare against *owned* RAPIPPO assets in Organic Pixel Art Director, without treating aesthetic heuristics as human taste or approving dataset re-use automatically.
