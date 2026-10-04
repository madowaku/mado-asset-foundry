# MADO Asset Foundry agent notes

## Mission

Build a game-asset manufacturing pipeline: generate, curate, refine, QA, dogfood, package, and prepare assets for distribution.

## Current milestone

MAF-M0.8.2g Effekseer Intake / VFX Capability Probe.

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

- Capability scanning must be deterministic and evidence-backed. Do not use an LLM for M0.8.2b classification.
- Infer capabilities only from explicit terms in SKILL.md/README, not from executable script contents.
- Runtime detection may read metadata and filenames but must never import or run third-party code.
- License detection is conservative metadata classification, not legal permission; unknown/ambiguous must remain visible.

- Registry builds must be deterministic and recurse through nested manifest directories.
- Duplicate skill_id values must fail registry construction rather than overwrite each other.
- Resolver must never promote intake_only Skills to executable.
- If multiple executable Skills satisfy one capability, return ambiguous rather than silently picking one.
- 3D capability taxonomy should remain provider-independent; TripoSR/SF3D are candidate implementations, not capability names.

- Preflight must never execute third-party Skill code, import third-party modules, or install dependencies.
- Python dependency checks use module discovery only; executable checks use PATH discovery only.
- An adapter is promotion-eligible only when its contract checks pass and run() is implemented.
- Adapter definitions must declare capabilities explicitly and those capabilities must be a subset of the scanned Skill manifest.
- Unknown or ambiguous licenses block promotion eligibility.
- Preflight evidence must record external_code_executed=false.

- Declaring execution_implemented=true is not sufficient; a concrete runner factory must also be registered before preflight can become ready.
- Module discovery must not import the third-party module; top-level PathFinder discovery is acceptable.

- TripoSR live probes must process exactly one input asset per run.
- Do not clone TripoSR, install its dependencies, or download model weights automatically.
- The TripoSR adapter must pass a local --pretrained-model-name-or-path so upstream hf_hub_download fallback is never used.
- Default TripoSR probes require pinned upstream commit 107cefdc244c39106fa830359024f6a2f1c78871; unpinned source requires an explicit override.
- Preserve stdout, stderr, input hash, source evidence, exact command, and output hash for every real TripoSR probe.
- A zero exit code without a valid non-empty mesh is failure.

- TripoSR M0.8.2f probes require real alpha transparency; opaque input is blocked to avoid implicit rembg model acquisition.
- MAF prepares the TripoSR conditioning image locally and passes --no-remove-bg so rembg.new_session is never invoked during the probe.

- M0.8.2g Effekseer fixtures are metadata-only and must never vendor official binaries, DLLs, samples, or generated effects.
- Keep Effekseer authoring, effekseer-ai CLI/MCP bridging, and Godot runtime playback as separate Skills/capabilities.
- The Effekseer master snapshot is development evidence only; do not treat it as a production runtime recommendation.
- effekseer-ai compatibility evidence is pinned to its documented Effekseer 1.80.6 Windows configuration.
- VFX capability probing must remain read-only and external_code_executed=false.
