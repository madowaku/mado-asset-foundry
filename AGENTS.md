# MADO Asset Foundry agent notes

## Mission

Build a game-asset manufacturing pipeline: generate, curate, refine, QA, dogfood, package, and prepare assets for distribution.

## Current milestone

MAF-M0.2 Candidate Curator UI.

## Engineering constraints

- Python 3.11+.
- Keep the core filesystem-first. Do not introduce a database without a milestone that requires it.
- Tests must never make live image-generation API calls.
- Live generation must remain explicit; the CLI default is one candidate.
- Preserve provider independence behind the ImageProvider boundary.
- Curation is human-authoritative. Never auto-publish or silently convert generated candidates into sellable assets.
- Every curation change must be reflected in run evidence and per-asset metadata.
- Keep the Curator UI build-tool-free for M0.x unless a later milestone justifies a frontend toolchain.
- Default the Curator server to localhost.
- Do not commit secrets, API keys, generated runs, or distribution artifacts.

## Verification

Run:

```bash
pytest -q
```

For Curator smoke testing:

```bash
maf curate
```

Then open http://127.0.0.1:4173.
