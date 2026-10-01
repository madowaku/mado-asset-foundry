# MAF-M0.2 Candidate Curator UI

## Goal

Turn a Foundry run full of raw generated candidates into a human-curated set without breaking provenance.

## Operator loop

```text
raw candidates
    ↓
Candidate Curator
    ↓
REJECT / MAYBE / KEEP
    + FAVORITE
    ↓
run.json + metadata/*.json
    ↓
M0.3 Image QA
```

## Launch

```bash
python -m pip install -e ".[dev]"
maf curate
```

Default URL: `http://127.0.0.1:4173`.

## Keyboard contract

- Left / Right: move selection
- 1: reject
- 2: maybe
- 3: keep
- 4: toggle favorite

## Persistence contract

A decision updates both:

- the asset record in `run.json`
- the corresponding `metadata/<asset_id>.json`

Decision → asset state mapping:

- unreviewed → generated
- reject → rejected
- maybe → review_pending
- keep → selected

Favorite is independent from decision.

## API

- `GET /api/runs`
- `GET /api/runs/{run_id}`
- `GET /api/runs/{run_id}/assets/{asset_id}/image`
- `PATCH /api/runs/{run_id}/assets/{asset_id}`

Patch body examples:

```json
{"decision":"keep"}
```

```json
{"favorite":true}
```

## Acceptance criteria

- candidate grid loads directly from Foundry run evidence
- run switcher works across multiple run directories
- selected candidate is keyboard navigable
- reject/maybe/keep/favorite can be applied without page reload
- filters exist for every decision and favorite state
- progress/counts update after every decision
- curation persists to run and per-asset metadata
- raw files remain immutable
- no frontend build step is required
- server binds to localhost by default
