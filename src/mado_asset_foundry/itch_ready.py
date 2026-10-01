from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from .io import load_recipe, write_json
from .models import ItchReadyReport, ProductCompileReport


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _checkerboard(size: tuple[int, int], cell: int = 16) -> Image.Image:
    image = Image.new("RGB", size, (33, 36, 41))
    draw = ImageDraw.Draw(image)
    alternate = (48, 52, 58)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if ((x // cell) + (y // cell)) % 2:
                draw.rectangle(
                    (x, y, min(x + cell - 1, size[0] - 1), min(y + cell - 1, size[1] - 1)),
                    fill=alternate,
                )
    return image


def _fit_image(source: Image.Image, canvas_size: tuple[int, int], *, margin: int = 28) -> Image.Image:
    canvas = _checkerboard(canvas_size)
    rgba = source.convert("RGBA")
    max_width = max(1, canvas_size[0] - margin * 2)
    max_height = max(1, canvas_size[1] - margin * 2)
    scale = min(max_width / rgba.width, max_height / rgba.height)
    resized = rgba.resize(
        (max(1, round(rgba.width * scale)), max(1, round(rgba.height * scale))),
        Image.Resampling.NEAREST,
    )
    offset = ((canvas_size[0] - resized.width) // 2, (canvas_size[1] - resized.height) // 2)
    canvas.paste(resized.convert("RGB"), offset, resized.getchannel("A"))
    return canvas


def _sample_showcase(asset_paths: list[Path], size: tuple[int, int] = (960, 540)) -> Image.Image:
    canvas = _checkerboard(size, cell=24)
    chosen = asset_paths[: min(8, len(asset_paths))]
    columns = 4 if len(chosen) > 4 else max(1, len(chosen))
    rows = max(1, math.ceil(len(chosen) / columns))
    cell_width = size[0] // columns
    cell_height = size[1] // rows

    for index, path in enumerate(chosen):
        with Image.open(path) as opened:
            icon = opened.convert("RGBA")
        scale = min((cell_width * 0.6) / icon.width, (cell_height * 0.6) / icon.height)
        scaled = icon.resize(
            (max(1, round(icon.width * scale)), max(1, round(icon.height * scale))),
            Image.Resampling.NEAREST,
        )
        col = index % columns
        row = index // columns
        x = col * cell_width + (cell_width - scaled.width) // 2
        y = row * cell_height + (cell_height - scaled.height) // 2
        canvas.paste(scaled.convert("RGB"), (x, y), scaled.getchannel("A"))
    return canvas


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content.rstrip() + "\n")


def _load_packaging_report(run_dir: Path) -> ProductCompileReport:
    report_path = run_dir / "packaging" / "report.json"
    if not report_path.exists():
        raise FileNotFoundError("packaging/report.json is missing; run maf package first")
    return ProductCompileReport.model_validate(json.loads(report_path.read_text(encoding="utf-8")))


def _resolve_report_path(run_dir: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() and path.exists():
        return path
    if path.exists():
        return path
    candidate = run_dir / path
    if candidate.exists():
        return candidate
    return path


def compile_itch_ready_pack(run_dir: str | Path, *, force: bool = False) -> ItchReadyReport:
    directory = Path(run_dir)
    recipe = load_recipe(directory / "recipe.yaml")
    if recipe.product is None:
        raise ValueError("recipe.product is required")
    if recipe.itch is None:
        raise ValueError("recipe.itch is required")

    product = recipe.product
    itch = recipe.itch
    package_report = _load_packaging_report(directory)
    if package_report.product_id != product.product_id or package_report.version != product.version:
        raise ValueError("packaging report product does not match recipe product")

    package_dir = _resolve_report_path(directory, package_report.product_dir)
    zip_path = _resolve_report_path(directory, package_report.zip_path)
    if not package_dir.exists():
        raise FileNotFoundError("compiled product directory is missing")
    if not zip_path.exists():
        raise FileNotFoundError("compiled product ZIP is missing")
    if _sha256(zip_path) != package_report.zip_sha256:
        raise ValueError("compiled product ZIP SHA-256 does not match packaging evidence")

    bundle_name = f"{product.product_id}-{product.version}"
    release_parent = directory / "itch"
    release_dir = release_parent / bundle_name
    temp_dir = release_parent / f".{bundle_name}.tmp"
    if release_dir.exists() and not force:
        raise FileExistsError("itch ready pack already exists; use --force to replace it")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        upload_dir = temp_dir / "upload"
        screenshots_dir = temp_dir / "screenshots"
        upload_dir.mkdir()
        screenshots_dir.mkdir()

        blockers: list[str] = []
        warnings: list[str] = []
        if product.license_status != "public":
            blockers.append("license_not_public")
        if product.ai_assisted and "graphics" not in itch.ai_content_types:
            blockers.append("ai_graphics_disclosure_missing")
        if "draft" in product.license_id.lower():
            blockers.append("draft_license_identifier")
        if itch.pricing_mode == "manual_review":
            warnings.append("pricing_requires_manual_review")

        copied_zip = upload_dir / zip_path.name
        shutil.copyfile(zip_path, copied_zip)

        contact_sheet = package_dir / "preview" / "contact_sheet.png"
        sprite_sheet = package_dir / "sprite_sheet.png"
        asset_paths = sorted((package_dir / "assets").glob("*.png"))
        if not contact_sheet.exists() or not sprite_sheet.exists() or not asset_paths:
            raise FileNotFoundError("compiled product visual assets are incomplete")

        with Image.open(contact_sheet) as opened:
            contact = opened.copy()
        cover = _fit_image(contact, (630, 500), margin=36)
        screenshot_1 = _fit_image(contact, (960, 540), margin=32)
        cover.save(temp_dir / "cover.png", format="PNG", compress_level=9)
        screenshot_1.save(screenshots_dir / "01-contact-sheet.png", format="PNG", compress_level=9)

        with Image.open(sprite_sheet) as opened:
            sprite = opened.copy()
        screenshot_2 = _fit_image(sprite, (960, 540), margin=48)
        screenshot_2.save(screenshots_dir / "02-sprite-sheet.png", format="PNG", compress_level=9)

        screenshot_3 = _sample_showcase(asset_paths)
        screenshot_3.save(screenshots_dir / "03-samples.png", format="PNG", compress_level=9)

        pricing: dict[str, object] = {"mode": itch.pricing_mode}
        if itch.minimum_price_usd is not None:
            pricing["minimum_price_usd"] = itch.minimum_price_usd

        listing = {
            "title": product.title,
            "short_description": product.short_description,
            "classification": "Assets",
            "project_kind": "Downloadable",
            "upload_type": "Graphical Assets",
            "visibility_during_setup": "Draft",
            "tags": itch.tags,
            "pricing": pricing,
            "platform_flags": [],
            "generative_ai_disclosure": {
                "contains_generative_ai": product.ai_assisted,
                "content_types": itch.ai_content_types if product.ai_assisted else [],
            },
            "upload_file": f"upload/{copied_zip.name}",
            "cover_image": "cover.png",
            "screenshots": [
                "screenshots/01-contact-sheet.png",
                "screenshots/02-sprite-sheet.png",
                "screenshots/03-samples.png",
            ],
        }
        write_json(temp_dir / "listing.json", listing)
        write_json(temp_dir / "tags.json", {"tags": itch.tags})

        process_summary = (
            "The source imagery is AI-assisted, then human-curated, automatically QA-checked, "
            "normalized to game-ready dimensions, and packaged through MADO Asset Foundry."
            if product.ai_assisted
            else "The assets are human-curated, automatically QA-checked, normalized to game-ready "
            "dimensions, and packaged through MADO Asset Foundry."
        )

        description = f"""# {product.title}

{product.short_description}

## What is included

- {len(asset_paths)} individual {recipe.output.width}x{recipe.output.height} transparent PNG assets
- Native-resolution sprite sheet
- Preview contact sheet
- README, license, manifest, and product metadata
- Targets: {", ".join(recipe.targets)}

## Production process

{process_summary}

## AI disclosure

{product.ai_disclosure or "No generative AI disclosure required."}

## License

{product.license_id}. See the included LICENSE.txt for the complete terms.
"""
        _write_text(temp_dir / "description.md", description)
        _write_text(temp_dir / "title.txt", product.title)
        _write_text(temp_dir / "short-description.txt", product.short_description)
        _write_text(temp_dir / "ai-disclosure.md", product.ai_disclosure or "No generative AI content declared.")

        checklist = """# itch.io Release Checklist

- [ ] Create or open the itch.io project in Draft visibility.
- [ ] Set classification to Assets and upload kind to Graphical Assets.
- [ ] Upload the ZIP from upload/.
- [ ] Upload cover.png (630x500, 315:250 aspect ratio).
- [ ] Upload the three files in screenshots/.
- [ ] Copy title, short description, and description from this ready pack.
- [ ] Review tags and keep only tags that accurately describe the pack.
- [ ] Complete Generative AI disclosure and mark Graphics when applicable.
- [ ] Do not set Windows/macOS/Linux platform flags for a graphical asset ZIP.
- [ ] Review pricing in the itch.io editor.
- [ ] Confirm LICENSE.txt is a real public distribution license, not a draft.
- [ ] Preview the page before switching visibility from Draft to Public.
- [ ] Publish manually only after all blockers in READY.json are cleared.
"""
        _write_text(temp_dir / "release-checklist.md", checklist)

        policy_notes = """# itch.io policy notes used by MAF-M0.6

- https://itch.io/docs/creators/quality-guidelines
- https://itch.io/t/4309690/generative-ai-disclosure-tagging
- https://itch.io/docs/creators/getting-started
- https://itch.io/docs/creators/access-control

These links are reference material only. Re-check itch.io policy before an actual public release because marketplace rules can change.
"""
        _write_text(temp_dir / "policy-notes.md", policy_notes)

        ready = not blockers
        write_json(
            temp_dir / "READY.json",
            {
                "ready": ready,
                "blockers": blockers,
                "warnings": warnings,
                "human_publish_required": True,
                "public_publish_automated": False,
            },
        )

        if force and release_dir.exists():
            shutil.rmtree(release_dir)
        temp_dir.rename(release_dir)
    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
        raise

    report = ItchReadyReport(
        run_id=package_report.run_id,
        recipe_id=package_report.recipe_id,
        product_id=product.product_id,
        version=product.version,
        ready=ready,
        blockers=blockers,
        warnings=warnings,
        release_dir=str(release_dir),
        upload_zip=str(release_dir / "upload" / copied_zip.name),
        upload_zip_sha256=_sha256(release_dir / "upload" / copied_zip.name),
        cover_path=str(release_dir / "cover.png"),
        screenshot_paths=[
            str(release_dir / "screenshots" / "01-contact-sheet.png"),
            str(release_dir / "screenshots" / "02-sprite-sheet.png"),
            str(release_dir / "screenshots" / "03-samples.png"),
        ],
        listing_path=str(release_dir / "listing.json"),
        checklist_path=str(release_dir / "release-checklist.md"),
    )
    write_json(directory / "itch" / "report.json", report.model_dump(mode="json"))
    return report
