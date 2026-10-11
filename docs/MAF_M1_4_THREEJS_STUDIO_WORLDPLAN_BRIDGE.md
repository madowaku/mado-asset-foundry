# MAF-M1.4 ThreeJS Assets Studio Intake / WorldPlan Bridge

## Architecture and compatibility

- Additive offline Python 3.11+ subsystem. M0.9 2D PNG attribution, M0.9.4 flow, Godot Texture2D tests and M1.x Cockpit remain unchanged.
- No automatic downloads, catalog/API calls, account access, Studio commands, Godot launch, third-party code execution, or publishing.
- Studio Map's `map.seedFromWorldPlan` is a browser command, not a hosted REST endpoint; local developer MCP requires a connected browser tab for most tools.
- Studio's documented WorldPlan v1 requires `schemaVersion: 1`, coordinates `x,z` in metres, `rotation` in radians, and per-placement semantic `assetHint` / `kind`. An unmatched asset hint is skipped.
- MAF only does deterministic exact-slug candidate matching using an operator-supplied catalog snapshot. It does not claim to replicate Studio's fuzzy resolution or verify live entitlements.
- The public catalog API omits entitlements; authenticated `/api/v1/assets` requires a scoped `tja_live_` key. Do not put credentials, real licensed models or per-user entitlements in Git.

## Offline usage

```bash
python -m pip install -e '.[dev]'
maf asset-source show threejsassets
maf threejs-studio compile fixtures/threejs-worldplan.yaml --catalog fixtures/threejs-catalog-example.json
```

The `--catalog` option accepts either a curated `schema_version: 0.1` / `assets` snapshot or one **complete** saved authenticated `/api/v1/assets` response with `data` and `pagination`. Multi-page responses must be curated into a complete snapshot; `has_more: true` is rejected. Source API URLs are not copied to output and saved `entitled` claims remain advisory. Do not commit raw authenticated responses.

The example slugs and names are **synthetic placeholders**. They do not assert any real assets exist or are owned. Output `runs/threejs-studio/studio-smoke/` contains `worldplan.json` plus `report.json` with source SHA-256, candidacy and explicit unverified flags. Re-running the same plan refuses overwrite.

## Studio and export verification (human-operated)

1. Log in at https://studio.threejsassets.com/ and open Map. Check actual owned/free asset availability.
2. Load generated `worldplan.json` via **New from WorldPlan...** or run the Map seed command using the live Studio browser API. Record actual seeded/skipped counts.
3. Export **Map data JSON** as `*.mapproj.json` and **GLB** to an untracked local folder.
4. Create an operator-reviewed license ledger beside genuine license evidence files. Example:

```json
{
  "schema_version": "0.1",
  "assets": [{
    "slug": "real-asset-slug",
    "asset_url": "https://threejsassets.com/assets/real-asset-slug",
    "license_label": "threejsassets-free-commercial",
    "evidence_file": "LICENSE-real-asset.txt",
    "reviewed_by_human": true,
    "game_embedding_allowed": true,
    "standalone_redistribution_allowed": false
  }]
}
```

```bash
maf threejs-studio verify-export runs/threejs-studio/studio-smoke \
  --map-data /path/to/exported.mapproj.json \
  --glb /path/to/exported.glb \
  --license-ledger /path/to/ledger.json
```

Evidence `studio-export-evidence.json` stores GLB, map, WorldPlan, ledger and per-asset license-evidence hashes. Map placements must preserve source IDs and transform coordinates. Site asset slugs require matching human rights declarations; local editor-project assets remain blocked pending their own rights review.

## Evidence meanings and remaining verification

- `awaiting_studio_seed`: only offline plan serialization has been tested.
- `blocked_for_review`: missing rights evidence, missing placements, changed transforms or unhandled local models.
- `awaiting_godot_runtime_and_visual_qa`: offline export structure and human declarations were checked, **not** real Godot runtime loading or aesthetic acceptance.
- M1.4 checks GLB v2 magic/header/length/JSON-chunk header, not full glTF semantics.
- Export verification is not legal advice or publishing permission. M0.9 license and M1.x final human release gates are never bypassed. Standalone asset redistribution is always blocked.
- Live Studio browser automation, actual Godot 3D resource loading/rendered QA and opt-in credentialed API usage are future milestones.

## Official references

- https://docs.threejsassets.com/studio/studio-formats-reference
- https://docs.threejsassets.com/studio/studio-map-worldplan-seeding
- https://docs.threejsassets.com/studio/studio-scripting-and-automation
- https://docs.threejsassets.com/api/api-endpoints
- https://docs.threejsassets.com/licensing/license-terms
