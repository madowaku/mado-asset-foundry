# MADO Asset Foundry agent notes

## Mission

Build a game-asset manufacturing pipeline: generate, curate, refine, QA, dogfood, package, and prepare assets for distribution.

## Current milestone

MAF-M0.8.2a Skill Intake Skeleton.

## Engineering constraints

- Python 3.11+.
- Keep the core filesystem-first. Do not introduce a database without a milestone that requires it.
- Tests must never make live image-generation API calls.
- Live generation must remain explicit; the generic CLI default is one candidate.
- Production runs must require explicit --live and obey production.max_live_count.
- Scale real generation through probe -> pilot -> production rather than jumping straight to a large candidate batch.
- Preserve provider independence behind the ImageProvider boundary.
- Curation is human-authoritative.
- QA and refinement must never mutate raw generated assets.
- Packaging may consume only normalized assets.
- Product/license metadata must come from the recipe; never infer legal terms.
- itch.io preparation must remain Draft-first and must never auto-publish.
- Godot dogfood must consume compiled product assets, never bypass packaging through internal refined assets.
- Godot runtime verification must load assets through the engine resource loader and preserve evidence.
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
maf godot-fixture runs/<live-run-id>
```

- M0.8 production advance may automate deterministic downstream stages only after every candidate has a human curation decision and KEEP count equals the recipe target.
- Persist provider request usage evidence when the provider returns it.

- Codex ImageGen recipes must keep image model and orchestrator model separate: generation.model=gpt-image-2 and generation.codex_model=<Codex model>.
- Default Codex ImageGen orchestration to Luna for focused icon generation; do not claim Sol/Astra change the underlying image renderer.
- Codex gpt-image-2 transparency is preview. The bridge must inspect the PNG alpha channel and fail opaque results when transparency is required.
- For explicit GPT Image 2.5 rendering, use the openai-image provider and API billing path.
- Never bypass Codex sandbox or approval safety with danger-full-access shortcuts.

- Skill intake is read-only. Never execute third-party code while scanning.
- M0.8.2a manifests must remain intake_only and must not infer capabilities; classification belongs to M0.8.2b.
- Do not clone external repositories automatically during intake.
- Generated skill manifests/evidence are local artifacts and should not be committed by default.
