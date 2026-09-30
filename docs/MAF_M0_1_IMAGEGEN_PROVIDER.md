# MAF-M0.1 ImageGen Provider

## Goal

Turn an `AssetRecipe` into a reproducible image-generation run whose raw outputs and provenance are saved before curation or QA.

## Contract

Input:

- validated recipe
- explicit live candidate count
- output workspace

Output:

- recipe snapshot
- generation plan
- raw image candidates
- per-candidate provenance JSON
- Foundry run manifest

## Safety and cost boundary

`maf generate` defaults to one live candidate. A recipe may request 96 production candidates, but the CLI does not silently spend that budget. Use `--dry-run` to inspect the exact generation plan without making API calls.

## Provider boundary

The initial provider is `openai-image` using `gpt-image-2.5-flare`, but all generation goes through the `ImageProvider` protocol. The recipe and run format therefore do not depend on the OpenAI SDK.

## Source-image strategy

The provider generates a high-resolution source image (initially 1024x1024). The final 32x32 asset is intentionally not produced by the model. Crop, resize, pixel cleanup, palette control, alpha cleanup, and final normalization belong to later Foundry stages where they can be deterministic and testable.

## Evidence layout

```text
runs/<run-id>/
  recipe.yaml
  plan.json
  run.json
  raw/
  metadata/
```

Each asset metadata record includes prompt, subject, model/provider, render settings, SHA-256, and provider request metadata when available.

## Acceptance criteria

- recipe can select an image provider and model
- prompt plan can be previewed without an API call
- live count is explicit and capped by the recipe candidate count
- provider response is decoded and stored as a raw asset
- every generated asset has provenance metadata and SHA-256
- run manifest references generated assets
- provider is replaceable in tests
- no API key is stored in recipes or run evidence
