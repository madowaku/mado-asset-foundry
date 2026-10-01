# MAF-M0.4 Image Refiner / Normalizer

## Goal

Convert QA-approved generated source art into deterministic game-ready PNG assets while keeping raw generation evidence immutable.

## Boundary

Input:

- human decision: `KEEP`
- QA status: `pass` or `warn`
- raw generated source
- recipe refinement settings

Output:

- exact recipe output size
- transparent PNG
- centered and padded subject
- cleaned low alpha
- optional palette reduction
- per-asset refinement evidence
- updated run/asset metadata

The raw source is never edited.

## Recipe

```yaml
refinement:
  alpha_threshold: 8
  padding: 2
  palette_colors: 16
  resample: lanczos
  dither: false
```

For the initial Forest Alchemy fixture, the final target is `32x32 PNG`.

## Pipeline

```text
QA PASS/WARN raw
      ↓
RGBA normalize
      ↓
alpha cleanup
      ↓
visible-bounds crop
      ↓
aspect-fit into target minus padding
      ↓
resample
      ↓
alpha cleanup
      ↓
optional palette reduction
      ↓
center on transparent canvas
      ↓
32x32 PNG
```

## Command

```bash
maf refine runs/<run-id>
```

Existing outputs are preserved by default. Explicit replacement:

```bash
maf refine runs/<run-id> --force
```

## Eligibility

Only assets satisfying both conditions are normalized:

- curation decision is `KEEP`
- QA status is `pass` or `warn`

QA failures and assets that have not completed QA are skipped.

## Evidence

```text
runs/<run-id>/
  raw/
    asset_0001.png
  refined/
    asset_0001.png
  refinement/
    report.json
    asset_0001.json
```

Per-asset evidence records:

- source/output paths
- source/output SHA-256
- source/output sizes
- source crop box
- alpha threshold
- final padding
- palette limit
- resize method
- dithering choice

## State transition

Successful normalization:

```text
qa_passed
  ↓
normalized
```

A processing error becomes `refine_failed`. Skipped assets retain their previous lifecycle state.

## Acceptance criteria

- only KEEP + QA pass/warn assets are processed
- raw source SHA-256 is unchanged
- output is exact recipe width/height
- output is transparent PNG
- visible subject is aspect-fit and centered
- requested final padding is preserved
- palette limit is honored when configured
- outputs are not overwritten without `--force`
- per-asset and run-level evidence is emitted
- run.json and metadata receive refinement output/status
- one failed asset does not destroy successful outputs from the same run
