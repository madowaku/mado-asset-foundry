# MAF-M0.3 Image QA

## Goal

Automatically inspect human-selected (`KEEP`) image candidates before refinement and packaging.

## Boundary

M0.3 validates the **generated source image**, not the final 32x32 game asset.

The current recipe deliberately generates 1024x1024 source art. Final crop, resize, palette control, pixel cleanup, and 32x32 normalization belong to the next refinement stage.

## Command

```bash
maf qa runs/<run-id>
```

A hard QA failure returns a non-zero CLI exit code.

## Checks

For every `KEEP` candidate:

- source file exists
- image decodes successfully
- source dimensions match `generation.render_size`
- alpha-channel requirement
- transparent pixels are actually present
- visible pixels do not significantly touch the image border
- exact duplicate detection across selected candidates
- perceptual near-duplicate detection using dHash

## Severity

### FAIL

A candidate cannot safely continue without repair:

- missing/corrupt source
- wrong generated dimensions
- transparency requested but absent

### WARN

The file is technically usable but should be reviewed:

- object appears to touch/clamp against the border
- exact duplicate
- perceptual near duplicate

### PASS

No hard failures or warnings.

Warnings are recorded as `qa_passed` at the lifecycle level because the file can continue after human review. The detailed QA report retains `warn` status.

## Evidence

```text
runs/<run-id>/
  qa/
    report.json
    asset_0001.json
    asset_0002.json
```

QA also writes:

- `qa_status` into each selected `AssetRecord` in `run.json`
- `qa_status` and `qa_report_path` into `metadata/<asset_id>.json`

Raw generated files remain immutable.

## Duplicate policy

Exact duplicate matching uses SHA-256.

Near duplicate matching uses 64-bit dHash with a default maximum Hamming distance of 4:

```bash
maf qa runs/<run-id> --near-duplicate-distance 4
```

No candidate is automatically deleted. Duplicate detection is advisory and remains human-authoritative.

## Acceptance criteria

- only `KEEP` candidates are inspected
- raw files are never modified
- corrupt/missing files hard-fail
- expected render dimensions are validated
- required transparency is validated
- likely edge clipping is surfaced
- exact and perceptual duplicates are surfaced
- per-asset and run-level evidence is written
- `run.json` and asset metadata receive QA status
- CLI exits non-zero only for hard failures
