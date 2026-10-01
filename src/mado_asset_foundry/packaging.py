from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw

from .io import load_recipe, load_run, write_json
from .models import (
    AssetRecord,
    AssetState,
    ProductCompileReport,
    RefinementStatus,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "asset"


def _resolve_refined_path(run_dir: Path, asset: AssetRecord) -> Path | None:
    canonical = run_dir / "refined" / f"{asset.asset_id}.png"
    if canonical.exists():
        return canonical
    if asset.refined_path:
        recorded = Path(asset.refined_path)
        if recorded.is_absolute() and recorded.exists():
            return recorded
        if recorded.exists():
            return recorded
        relative = run_dir / recorded
        if relative.exists():
            return relative
    return None


def _metadata_path(run_dir: Path, asset: AssetRecord) -> Path:
    canonical = run_dir / "metadata" / f"{asset.asset_id}.json"
    if canonical.exists() or asset.metadata_path is None:
        return canonical
    recorded = Path(asset.metadata_path)
    if recorded.is_absolute() and recorded.exists():
        return recorded
    if recorded.exists():
        return recorded
    return canonical


def _checkerboard(size: tuple[int, int], cell: int = 8) -> Image.Image:
    image = Image.new("RGB", size, (42, 45, 49))
    draw = ImageDraw.Draw(image)
    alternate = (58, 62, 67)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if ((x // cell) + (y // cell)) % 2:
                draw.rectangle(
                    (x, y, min(x + cell - 1, size[0] - 1), min(y + cell - 1, size[1] - 1)),
                    fill=alternate,
                )
    return image


def _build_sprite_sheet(
    asset_paths: list[Path],
    *,
    asset_size: tuple[int, int],
    columns: int,
    output: Path,
) -> tuple[int, int]:
    actual_columns = min(columns, len(asset_paths))
    rows = math.ceil(len(asset_paths) / actual_columns)
    sheet = Image.new("RGBA", (actual_columns * asset_size[0], rows * asset_size[1]), (0, 0, 0, 0))

    for index, path in enumerate(asset_paths):
        with Image.open(path) as opened:
            image = opened.convert("RGBA")
        col = index % actual_columns
        row = index // actual_columns
        sheet.alpha_composite(image, dest=(col * asset_size[0], row * asset_size[1]))

    sheet.save(output, format="PNG", compress_level=9)
    return actual_columns, rows


def _build_contact_sheet(
    asset_paths: list[Path],
    *,
    asset_size: tuple[int, int],
    columns: int,
    scale: int,
    output: Path,
) -> tuple[int, int]:
    actual_columns = min(columns, len(asset_paths))
    rows = math.ceil(len(asset_paths) / actual_columns)
    preview_size = (asset_size[0] * scale, asset_size[1] * scale)
    sheet = Image.new("RGB", (actual_columns * preview_size[0], rows * preview_size[1]), (30, 33, 37))

    for index, path in enumerate(asset_paths):
        background = _checkerboard(preview_size, cell=max(4, scale * 2))
        with Image.open(path) as opened:
            image = opened.convert("RGBA").resize(preview_size, Image.Resampling.NEAREST)
        background.paste(image.convert("RGB"), mask=image.getchannel("A"))
        col = index % actual_columns
        row = index // actual_columns
        sheet.paste(background, (col * preview_size[0], row * preview_size[1]))

    sheet.save(output, format="PNG", compress_level=9)
    return actual_columns, rows


def _write_readme(
    path: Path,
    *,
    title: str,
    description: str,
    author: str,
    count: int,
    asset_size: tuple[int, int],
    targets: list[str],
    license_id: str,
    ai_disclosure: str,
) -> None:
    target_lines = "\n".join(f"- {target}" for target in targets)
    path.write_text(
        f"""# {title}

{description}

## Contents

- {count} individual PNG assets
- {asset_size[0]}x{asset_size[1]} pixels each
- transparent background
- sprite sheet
- preview contact sheet
- machine-readable manifest

## Targets

{target_lines}

## AI assistance

{ai_disclosure}

## License

{license_id}. See LICENSE.txt for the complete terms.

## Author

{author}
""",
        encoding="utf-8",
    )


def _deterministic_zip(source_dir: Path, zip_path: Path, *, root_name: str) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(item for item in source_dir.rglob("*") if item.is_file()):
            relative = path.relative_to(source_dir).as_posix()
            info = zipfile.ZipInfo(f"{root_name}/{relative}", date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def compile_product(
    run_dir: str | Path,
    *,
    force: bool = False,
) -> ProductCompileReport:
    directory = Path(run_dir)
    run_path = directory / "run.json"
    recipe = load_recipe(directory / "recipe.yaml")
    run = load_run(run_path)

    if recipe.product is None:
        raise ValueError("recipe.product is required before packaging")

    product = recipe.product
    eligible = sorted(
        (asset for asset in run.assets if asset.refinement_status == RefinementStatus.NORMALIZED),
        key=lambda asset: asset.asset_id,
    )
    if not eligible:
        raise ValueError("no normalized assets are available for packaging")

    bundle_name = f"{product.product_id}-{product.version}"
    product_parent = directory / "product"
    dist_dir = directory / "dist"
    package_dir = product_parent / bundle_name
    zip_path = dist_dir / f"{bundle_name}.zip"
    temp_package = product_parent / f".{bundle_name}.tmp"
    temp_zip = dist_dir / f".{bundle_name}.tmp.zip"

    product_parent.mkdir(parents=True, exist_ok=True)
    dist_dir.mkdir(parents=True, exist_ok=True)

    if (package_dir.exists() or zip_path.exists()) and not force:
        raise FileExistsError("product output already exists; use --force to replace it")

    if force:
        if package_dir.exists():
            shutil.rmtree(package_dir)
        if zip_path.exists():
            zip_path.unlink()

    if temp_package.exists():
        shutil.rmtree(temp_package)
    if temp_zip.exists():
        temp_zip.unlink()

    assets_dir = temp_package / "assets"
    preview_dir = temp_package / "preview"
    assets_dir.mkdir(parents=True)
    preview_dir.mkdir(parents=True)

    asset_entries: list[dict[str, object]] = []
    packaged_paths: list[Path] = []
    asset_size = (recipe.output.width, recipe.output.height)

    try:
        for asset in eligible:
            source = _resolve_refined_path(directory, asset)
            if source is None:
                raise FileNotFoundError(f"refined output missing for {asset.asset_id}")

            with Image.open(source) as opened:
                if opened.format != "PNG":
                    raise ValueError(f"{asset.asset_id} refined output is not PNG")
                if opened.size != asset_size:
                    raise ValueError(
                        f"{asset.asset_id} refined output size {opened.size} does not match {asset_size}"
                    )

            subject_slug = _slug(asset.subject or asset.asset_id)
            filename = f"{subject_slug}-{asset.asset_id}.png"
            destination = assets_dir / filename
            shutil.copyfile(source, destination)
            digest = _sha256(destination)
            packaged_paths.append(destination)
            asset_entries.append(
                {
                    "asset_id": asset.asset_id,
                    "subject": asset.subject,
                    "filename": f"assets/{filename}",
                    "sha256": digest,
                    "qa_status": asset.qa_status.value if asset.qa_status else None,
                    "source_refined_sha256": asset.refined_sha256,
                }
            )

        sprite_sheet = temp_package / "sprite_sheet.png"
        sheet_columns, sheet_rows = _build_sprite_sheet(
            packaged_paths,
            asset_size=asset_size,
            columns=product.sheet_columns,
            output=sprite_sheet,
        )

        contact_sheet = preview_dir / "contact_sheet.png"
        preview_columns, preview_rows = _build_contact_sheet(
            packaged_paths,
            asset_size=asset_size,
            columns=product.sheet_columns,
            scale=product.preview_scale,
            output=contact_sheet,
        )

        manifest = {
            "schema_version": "0.1",
            "product_id": product.product_id,
            "version": product.version,
            "title": product.title,
            "asset_type": recipe.asset_type,
            "asset_count": len(asset_entries),
            "asset_dimensions": {"width": asset_size[0], "height": asset_size[1]},
            "format": recipe.output.format,
            "transparent": recipe.output.transparent,
            "targets": recipe.targets,
            "source_recipe": recipe.id,
            "source_run": run.run_id,
            "license_id": product.license_id,
            "ai_assisted": product.ai_assisted,
            "sprite_sheet": {
                "path": "sprite_sheet.png",
                "columns": sheet_columns,
                "rows": sheet_rows,
                "sha256": _sha256(sprite_sheet),
            },
            "contact_sheet": {
                "path": "preview/contact_sheet.png",
                "columns": preview_columns,
                "rows": preview_rows,
                "scale": product.preview_scale,
                "sha256": _sha256(contact_sheet),
            },
            "assets": asset_entries,
        }
        write_json(temp_package / "MANIFEST.json", manifest)

        product_json = {
            "product_id": product.product_id,
            "version": product.version,
            "title": product.title,
            "author": product.author,
            "short_description": product.short_description,
            "license_id": product.license_id,
            "ai_assisted": product.ai_assisted,
            "ai_disclosure": product.ai_disclosure,
            "targets": recipe.targets,
        }
        write_json(temp_package / "PRODUCT.json", product_json)
        (temp_package / "LICENSE.txt").write_text(product.license_text.rstrip() + "\n", encoding="utf-8")
        _write_readme(
            temp_package / "README.md",
            title=product.title,
            description=product.short_description,
            author=product.author,
            count=len(asset_entries),
            asset_size=asset_size,
            targets=recipe.targets,
            license_id=product.license_id,
            ai_disclosure=product.ai_disclosure or "",
        )

        _deterministic_zip(temp_package, temp_zip, root_name=bundle_name)
        temp_package.rename(package_dir)
        temp_zip.rename(zip_path)
    except Exception:
        if temp_package.exists():
            shutil.rmtree(temp_package)
        if temp_zip.exists():
            temp_zip.unlink()
        raise

    product_ref = f"{product.product_id}@{product.version}"
    for asset in eligible:
        asset.state = AssetState.PACKAGED
        if product_ref not in asset.packaged_products:
            asset.packaged_products.append(product_ref)
        metadata_path = _metadata_path(directory, asset)
        metadata: dict[str, object] = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        packaged_products = list(metadata.get("packaged_products", []))
        if product_ref not in packaged_products:
            packaged_products.append(product_ref)
        metadata["packaged_products"] = packaged_products
        write_json(metadata_path, metadata)
        asset.metadata_path = str(metadata_path)

    write_json(run_path, run.model_dump(mode="json"))

    report = ProductCompileReport(
        run_id=run.run_id,
        recipe_id=recipe.id,
        product_id=product.product_id,
        version=product.version,
        asset_count=len(asset_entries),
        product_dir=str(package_dir),
        zip_path=str(zip_path),
        zip_sha256=_sha256(zip_path),
        manifest_path=str(package_dir / "MANIFEST.json"),
        sprite_sheet_path=str(package_dir / "sprite_sheet.png"),
        contact_sheet_path=str(package_dir / "preview" / "contact_sheet.png"),
    )
    write_json(directory / "packaging" / "report.json", report.model_dump(mode="json"))
    return report
