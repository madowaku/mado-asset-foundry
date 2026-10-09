# MAF-M0.9 Asset Source Registry / License-Aware Intake

## Scope

M0.9 adds a **manual, offline** asset-source catalog and a per-asset license/provenance
intake gate. It does not crawl asset sites, call APIs, download third-party files,
install plug-ins, convert assets, or approve marketplace publication.

The bundled registry includes local assets, Kenney, OpenGameArt, Game-icons.net,
Lospec, Freesound, itch.io, Mixamo, Godot Asset Library, and Godot Asset Store.
Site-level license hints are **not** asset-level permissions.

## CLI

Run from the repository root after installing dependencies:

```bash
maf asset-source list
maf asset-source show kenney
maf asset-source intake fixtures/m0-9-demo/asset.yaml
```

This creates `evidence/asset-intake/m0-9-demo-triangle/report.json`.
The report stores a SHA-256 of the local file, any local license evidence file
hash, the stated asset origin, creator, requested use case, and gate status.

For an external asset, supply **an already-downloaded file**, its original asset
page URL on the registered domain, and that same site's per-asset license evidence
URL, plus an explicit human verification statement. URLs are recorded only,
never fetched. For a local asset, a local license evidence file is accepted.

`--output-root` selects the evidence directory; `--force` is required to
overwrite existing evidence. `--registry` points to an alternate JSON catalog.

## Decision logic

- `eligible`: human-reviewed per-asset evidence and recognized CC0-1.0, or
  CC BY 3.0/4.0 with supplied attribution for game embedding, except source
  restrictions. **Not release authorization.**
- `needs_review`: unverified or missing license evidence, unknown/custom
  license, share-alike/copyleft complexity, missing credit, or source policy review.
- `blocked`: commercially requested use with NC license, or standalone
  asset redistribution from a source explicitly blocked in the registry.

CC BY standalone redistribution requires extra review. Site-specific and
API-specific service terms still govern acquisition. Freesound API commercial
rights are separate from downloaded sound content license rights. Mixamo
standalone redistribution is denied by default.

Return code: 0 eligible, 2 needs_review or blocked, 1 invalid input/error.
All three statuses preserve `publication_approved: false`.

## Trust boundaries

- Registry is fixed, versioned JSON and duplicate IDs are rejected.
- Remote asset/evidence URLs must be HTTPS, without embedded credentials,
  and hosted on the declared source domain or subdomain.
- Submitted local files are confined to the submission directory; symlinks
  and traversal are rejected.
- No unapproved network operation or third-party code execution.
- No local asset copy, modification, normalization, Godot import, or upload.
- Evidence is preserved and never silently overwritten.
- The operator remains responsible for checking rights and license scope.
- Existing generated-asset recipe/product licensing flow is unchanged.

Next milestones can add lawful provider adapters, attribution export, and a
Godot-ready copy stage that consumes **eligible** reports with freshness checks.
