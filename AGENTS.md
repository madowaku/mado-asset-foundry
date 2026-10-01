# MADO Asset Foundry agent notes

## Mission

Build a game-asset manufacturing pipeline: generate, curate, refine, QA, dogfood, package, and prepare assets for distribution.

## Current milestone

MAF-M0.6 itch.io Ready Pack.

## Engineering constraints

- Python 3.11+.
- Keep the core filesystem-first. Do not introduce a database without a milestone that requires it.
- Tests must never make live image-generation API calls.
- Live generation must remain explicit; the CLI default is one candidate.
- Preserve provider independence behind the ImageProvider boundary.
- Curation is human-authoritative.
- QA and refinement must never mutate raw generated assets.
- Packaging may consume only normalized assets.
- Product/license metadata must come from the recipe; never infer legal terms.
- itch.io preparation must remain Draft-first and must never auto-publish.
- Generative AI usage must be represented explicitly in release metadata.
- Do not set executable OS platform flags for graphical asset ZIPs.
- A draft/non-public license must block public release readiness.
- Existing refined, product, or release outputs must not be silently overwritten.
- Do not commit secrets, API keys, generated runs, refined outputs, product bundles, or release kits.

## Verification

Run:

```bash
pytest -q
```

Core smoke loop:

```bash
maf generate fixtures/forest-alchemy.yaml --count 4 --dry-run --run-id preview-001
maf curate
maf qa runs/<live-run-id>
maf refine runs/<live-run-id>
maf package runs/<live-run-id>
maf itch-ready runs/<live-run-id>
```
