# MADO Asset Foundry agent notes

## Mission

Build a game-asset manufacturing pipeline: generate, curate, refine, QA, dogfood, package, and prepare assets for distribution.

## Current milestone

MAF-M0.5 Product Compiler.

## Engineering constraints

- Python 3.11+.
- Keep the core filesystem-first. Do not introduce a database without a milestone that requires it.
- Tests must never make live image-generation API calls.
- Live generation must remain explicit; the CLI default is one candidate.
- Preserve provider independence behind the ImageProvider boundary.
- Curation is human-authoritative. Never auto-publish or silently convert generated candidates into sellable assets.
- Every curation change must be reflected in run evidence and per-asset metadata.
- QA must inspect selected candidates without mutating raw generated assets.
- Refinement must never mutate raw generated assets and must be reproducible from raw + recipe.
- Packaging may consume only normalized assets and must never mutate raw or refined source files.
- Product/license metadata must come from the recipe; never infer legal terms.
- Product ZIPs should be reproducible for identical inputs.
- Existing refined or product outputs must not be silently overwritten.
- M0.x must not auto-publish to any marketplace.
- Keep the Curator UI build-tool-free for M0.x unless a later milestone justifies a frontend toolchain.
- Default the Curator server to localhost.
- Do not commit secrets, API keys, generated runs, refined outputs, product bundles, or distribution artifacts.

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
```
