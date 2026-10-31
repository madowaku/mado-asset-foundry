# MAF-M1.6 SRPG Asset Intelligence (planning slice)

## Purpose

Convert a small SRPG art brief and a handful of manually curated references
into a deterministic production/review backlog. This **adds no new use
permissions** and reuses MAF-M0.9 for per-asset rights intake.

```bash
maf srpg plan fixtures/srpg-asset-brief.yaml --output evidence/srpg-intelligence/plan.json
pytest -q tests/test_srpg_planner.py tests/test_asset_sources.py
```

The planner emits a machine-readable report with each need's quantity,
priority, candidates, and next action. `ready_quantity` is intentionally
zero until a separate, fully verified production path exists; merely listing
a repository or an asset's claimed SPDX value is not proof of usage rights.

## Candidate routing

| Route | Plan status | Required next step |
| --- | --- | --- |
| `reference` | `study_only` | Study composition/style, not copy or redistribute |
| `external` | `intake_required` | Locate original creator and asset-specific terms, then use `maf asset-source intake` |
| `original` | `not_created` | Create original art, run QA and human rights review |

External candidates must use registered M0.9 sources with matching HTTPS
hosts; arbitrary names, HTTP, credentials, and spoofed subdomains are rejected.
References must be HTTPS. Original candidates may not carry external URLs or
source IDs. Duplicate and dangling IDs fail closed.

`pixel-srpg-forge` is added to the M0.9 source registry with
`redistribution_policy: blocked`. Its README says the material was collected
from multiple sources, including purchased and downloaded material with
uncertain rights. The collection's MIT badge is **not** an asset-level license.
A direct asset submission attributed only to this aggregator stays
`needs_review` for game embedding and is `blocked` for pack redistribution,
even if its manifest claims CC0. Seek the actual original creator's permission.

`pixelfx` is represented only as a research reference. No npm package,
upstream repository code, font, or generated effect is bundled or executed.
Future integration needs a separate pinned-source dependency/license and
Godot sprite-sheet quality review.

## Safety properties and limits

- Deterministic, offline and metadata-only; no downloads, scraping, plugins,
  generation calls, writes to game projects, or automatic publishing.
- No candidate is promoted to `eligible` by planning.
- Existing license intake, asset-flow, Godot runtime and human final review
  remain authoritative and unchanged.
- Outputs default to `evidence/srpg-intelligence/plan.json`; reruns require
  an explicit `--force` to overwrite evidence.
- The evidence contains the SHA-256 of the exact input brief.
- This milestone does **not** rank actual image beauty, inspect a compressed
  collection, establish original authorship, or prove a Godot import.
  Those are separate measured follow-ups.

## Next milestones

1. **M1.6a:** Manual per-asset source-of-truth link + usage evidence collection;
   feed existing M0.9 and block unknown/aggregated-only provenance.
2. **M1.6b:** Produce original 16 px terrain, character and VFX probes;
   pass through MAF QA and Godot runtime/gallery evidence.
3. **M1.6c:** Compare handmade vs PixelFX-accelerated *original* animations
   on readability, frame continuity, CPU cost, and actionable QA regressions.
4. Expose reports read-only in Cockpit only after Python planner gates stabilize.

No merge or deployment is authorized by this document.
