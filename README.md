# MADO Asset Foundry

Game-asset manufacturing pipeline for turning ideas into curated, QA-checked, game-ready, sellable asset packs.

## M0 vertical slice

`2D Icon Factory -> Curate -> QA -> Package -> itch.io-ready ZIP`

## Status

**MAF-M0.1 ImageGen Provider**

The first live line converts an Asset Recipe into an OpenAI image-generation plan, stores raw candidates, and records per-asset provenance.

## Setup

```bash
python -m pip install -e ".[dev]"
export OPENAI_API_KEY="..."
```

On PowerShell:

```powershell
$env:OPENAI_API_KEY="..."
```

## Safe first run

Validate the recipe:

```bash
maf recipe validate fixtures/forest-alchemy.yaml
```

Preview requests without spending anything:

```bash
maf generate fixtures/forest-alchemy.yaml --count 4 --dry-run --run-id preview-001
```

Generate one live candidate:

```bash
maf generate fixtures/forest-alchemy.yaml --count 1
```

`--count` defaults to **1** intentionally. The recipe may describe a 96-candidate production run, but live generation starts with a tiny fixture unless the operator explicitly raises the count.

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

Each metadata record stores the prompt, subject, provider/model, generation settings, SHA-256 digest, and provider request metadata when available.

## Initial recipe

`fixtures/forest-alchemy.yaml` uses:

- provider: `openai-image`
- model: `gpt-image-2.5-flare`
- render source: `1024x1024`
- quality: `low`
- background: `transparent`
- final intended game asset: `32x32 PNG`

The high-resolution source is deliberate. Downscaling, palette control, pixel cleanup, and final 32x32 normalization belong to the Foundry QA/refinement stages rather than the generation model.
