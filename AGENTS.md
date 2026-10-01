# MADO Asset Foundry agent notes

## Mission

Build a game-asset manufacturing pipeline: generate, curate, refine, QA, dogfood, package, and prepare assets for distribution.

## Current milestone

MAF-M0.3 Image QA.

## Engineering constraints

- Python 3.11+.
- Keep the core filesystem-first. Do not introduce a database without a milestone that requires it.
- Tests must never make live image-generation API calls.
- Live generation must remain explicit; the CLI default is one candidate.
- Preserve provider independence behind the ImageProvider boundary.
- Curation is human-authoritative. Never auto-publish or silently convert generated candidates into sellable assets.
- Every curation change must be reflected in run evidence and per-asset metadata.
- QA must inspect selected candidates without mutating raw generated assets.
- Hard QA failures may stop downstream automation; warnings must remain reviewable and must not silently delete assets.
- Keep the Curator UI build-tool-free for M0.x unless a later milestone justifies a frontend toolchain.
- Default the Curator server to localhost.
- Do not commit secrets, API keys, generated runs, or distribution artifacts.

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
```
