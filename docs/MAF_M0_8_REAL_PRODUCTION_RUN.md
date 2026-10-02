# MAF-M0.8 Real Forest Alchemy Production Run

## Goal

Run the complete MADO Asset Foundry pipeline with real generated imagery while keeping live API usage deliberately small and human-authoritative.

## Production recipe

`fixtures/forest-alchemy-production.yaml`

The production pack uses six subjects and a 12-candidate ceiling:

- probe: 1 image
- pilot: 6 images
- production: 12 images
- final human KEEP target: 6 icons
- model: `gpt-image-2.5-flare`
- quality: `low`
- source: 1024x1024 transparent PNG
- final: 32x32 transparent PNG

As of 2026-10-02, OpenAI's image generation guide estimates 196 output tokens for GPT Image 2.5 at low quality / 1024x1024, or about $0.00588 of image-output cost per image at the current $30/M output-token rate. Text/input token charges are additional and actual usage should be read from API response usage.

Official references:

- https://developers.openai.com/api/docs/models/gpt-image-2.5-flare
- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/api/docs/pricing

## Safety ladder

No live call:

```bash
maf production plan
maf production start --stage probe
```

One-image real probe:

```bash
maf production start --stage probe --live
```

Six-image pilot:

```bash
maf production start --stage pilot --live
```

Twelve-image production:

```bash
maf production start --stage production --live
```

`--live` is mandatory for API calls. Every stage is capped by `production.max_live_count`.

## Evidence

Generation now writes:

```text
runs/<run-id>/
  recipe.yaml
  plan.json
  requests.json
  run.json
  production.json
  raw/
  metadata/
```

`requests.json` records one row per provider request, including request ID and usage when returned by the provider.

## Human gate

A production-stage run cannot advance until:

- every generated candidate has a human curation decision
- KEEP count exactly equals `curation.target_count`

For the Forest Alchemy production recipe, 12 candidates must be fully reviewed and exactly 6 must be KEEP.

## Downstream advance

After curation:

```bash
maf production status runs/<run-id>
maf production advance runs/<run-id>
```

With real Godot verification:

```bash
maf production advance runs/<run-id> --godot-bin godot
```

Advance performs:

1. Image QA
2. Refinement / normalization
3. Product Compiler
4. itch.io Ready Pack
5. Godot Dogfood Fixture

The draft product license remains a release blocker, intentionally. Marketplace publishing remains manual.

## Acceptance criteria

- live API calls require explicit `--live`
- probe/pilot/production counts are bounded and validated
- production recipe generates only 12 candidates, not 96
- request IDs and API usage are retained when provided
- production cannot advance before full human curation
- KEEP count must equal the six-icon product target
- deterministic downstream stages can run from one command
- itch.io release blockers remain visible
- optional real Godot verification remains part of the final evidence
