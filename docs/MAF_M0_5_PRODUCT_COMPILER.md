# MAF-M0.5 Product Compiler

## Goal

Compile normalized game assets into a reproducible product bundle without publishing it.

## Boundary

Input:

- recipe product metadata
- assets with `refinement_status: normalized`
- normalized PNG files

Output:

- individual asset files with stable descriptive names
- game-use sprite sheet
- preview contact sheet
- README
- LICENSE
- MANIFEST
- PRODUCT metadata
- deterministic ZIP
- packaging evidence

M0.5 does **not** publish to a marketplace.

## Product recipe

```yaml
product:
  product_id: forest-alchemy-icons
  version: 0.1.0
  title: Forest Alchemy Icons
  author: madowaku
  short_description: A compact pack of transparent 32x32 forest alchemy icons.
  license_id: YOUR-LICENSE-ID
  license_status: public
  license_text: |
    Replace this with the actual distribution license.
  ai_assisted: true
  ai_disclosure: AI-assisted source images are human-curated, QA-checked, normalized, and packaged.
  sheet_columns: 8
  preview_scale: 4
```

The compiler refuses to package a recipe with no product block. When AI assistance is declared, disclosure text is required. Packaging records license status, while M0.6 blocks public-release readiness until the license is explicitly marked `public`.

## Command

```bash
maf package runs/<run-id>
```

Compiled products are protected from silent overwrite. Explicit rebuild:

```bash
maf package runs/<run-id> --force
```

## Output

```text
runs/<run-id>/
  product/
    forest-alchemy-icons-0.1.0/
      assets/
        red-potion-asset_0001.png
        ...
      preview/
        contact_sheet.png
      sprite_sheet.png
      README.md
      LICENSE.txt
      MANIFEST.json
      PRODUCT.json
  dist/
    forest-alchemy-icons-0.1.0.zip
  packaging/
    report.json
```

## Reproducibility

The ZIP writer:

- sorts files by path
- uses a fixed ZIP timestamp
- uses fixed file permissions
- uses fixed compression settings
- contains deterministic product text and manifests

For identical normalized assets and recipe metadata, the ZIP SHA-256 should remain stable.

## Manifest

`MANIFEST.json` records:

- product id/version/title
- asset count and dimensions
- target engines
- source recipe/run
- license id
- AI-assisted flag
- sprite/contact sheet dimensions and SHA-256
- each asset's stable filename and SHA-256
- each asset's original Foundry asset id and subject

## License boundary

MADO Asset Foundry does not guess a distribution license.

The fixture intentionally uses `MADO-DOGFOOD-DRAFT`. Replace the draft license before public publishing or selling. Marketplace-specific license/disclosure checks belong to M0.6.

## Acceptance criteria

- only normalized assets enter the product
- individual files have stable descriptive names
- sprite sheet is generated at native game resolution
- contact sheet is generated for visual review
- README/LICENSE/MANIFEST/PRODUCT files are present
- deterministic ZIP is emitted
- product outputs are protected from silent overwrite
- packaging updates run and per-asset evidence
- identical inputs reproduce the same ZIP SHA-256
- no marketplace publishing occurs
