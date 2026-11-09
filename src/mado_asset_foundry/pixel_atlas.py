"""MAF Pixel Art Atlas M0.1: bounded, research-only sprite sampling.

This module does not promote third-party images to the asset production pipeline.
No external data is loaded unless sample_from_huggingface is called explicitly.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from itertools import islice
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Iterable, Mapping

from PIL import Image, ImageDraw

DATASET_ID = "Angais/pixel-art-atlas-1.4m"
SCHEMA = "mgsf.pixel-atlas.sample.v0.1"


def _pixels(image: Image.Image) -> list:
    # Pillow 12 renamed getdata; retain Pillow 11 compatibility.
    if hasattr(image, "get_flattened_data"):
        return list(image.get_flattened_data())
    return list(image.getdata())


def _normalized_image(source: Image.Image) -> Image.Image:
    if not isinstance(source, Image.Image):
        raise ValueError("image must be a decoded Pillow image")
    if source.size != (16, 16):
        raise ValueError(f"expected native 16x16 image, got {source.size}")
    rgba = source.convert("RGBA")
    # Invisible RGB values can differ between visually identical sprite files.
    canonical = [((0, 0, 0, 0) if a == 0 else (r, g, b, a)) for r, g, b, a in _pixels(rgba)]
    rgba.putdata(canonical)
    return rgba


def _dhash(image: Image.Image) -> int:
    canvas = Image.new("RGBA", (16, 16), (24, 24, 24, 255))
    canvas.alpha_composite(image)
    gray = canvas.convert("L").resize((9, 8), Image.Resampling.NEAREST)
    pixels = _pixels(gray)
    result = 0
    for y in range(8):
        for x in range(8):
            result = (result << 1) | int(pixels[y * 9 + x] > pixels[y * 9 + x + 1])
    return result


def analyze_sprite(image: Image.Image) -> dict[str, object]:
    """Measure descriptive properties, never aesthetic quality."""
    rgba = _normalized_image(image)
    pixels = _pixels(rgba)
    alpha = [p[3] for p in pixels]
    visible = [p for p in pixels if p[3] > 0]
    visible_count = len(visible)
    border = {(x, 0) for x in range(16)} | {(x, 15) for x in range(16)}
    border |= {(0, y) for y in range(16)} | {(15, y) for y in range(16)}
    border_hits = sum(rgba.getpixel(xy)[3] > 0 for xy in border)
    coverage = visible_count / 256
    palette = len({p[:3] for p in visible})
    flags = []
    if not visible_count:
        flags.append("empty_sprite")
    if visible_count == 256:
        flags.append("no_transparent_pixels")
    if palette > 24:
        flags.append("large_palette_review")
    if border_hits / len(border) > 0.15:
        flags.append("border_contact_review")
    if any(0 < a < 255 for a in alpha):
        flags.append("partial_alpha_review")
    return {
        "pixel_sha256": sha256(rgba.tobytes()).hexdigest(),
        "dhash64": f"{_dhash(rgba):016x}",
        "visible_fraction": round(coverage, 4),
        "visible_palette_colors": palette,
        "border_contact_fraction": round(border_hits / len(border), 4),
        "flags": flags,
    }


def _render_sheet(records: list[dict[str, object]], sprite_dir: Path, out: Path, *, columns: int = 8) -> None:
    if not records:
        raise ValueError("No matching sprites for sheet")
    width, height = 104, 112
    rows = (len(records) + columns - 1) // columns
    sheet = Image.new("RGBA", (columns * width, rows * height), "#e8e8e8")
    draw = ImageDraw.Draw(sheet)
    for i, entry in enumerate(records):
        x, y = (i % columns) * width, (i // columns) * height
        draw.rounded_rectangle((x + 2, y + 2, x + width - 3, y + height - 3), radius=5, fill="#fafafa")
        # Transparent checker only under image, with nearest-neighbor scaling.
        for yy in range(0, 64, 8):
            for xx in range(0, 64, 8):
                fill = "#dedede" if (xx + yy) // 8 % 2 else "#ffffff"
                draw.rectangle((x + 20 + xx, y + 7 + yy, x + 27 + xx, y + 14 + yy), fill=fill)
        with Image.open(sprite_dir / f"{entry['row_id']}.png") as sprite:
            scaled = sprite.convert("RGBA").resize((64, 64), Image.Resampling.NEAREST)
            sheet.alpha_composite(scaled, (x + 20, y + 7))
        label = f"#{entry['row_id']} {entry['subject']}"[:19]
        draw.text((x + 6, y + 76), label, fill="#333333")
        draw.text((x + 6, y + 91), f"{entry['visible_palette_colors']} colors", fill="#666666")
    sheet.convert("RGB").save(out)


def build_sample(
    rows: Iterable[Mapping[str, object]],
    output_dir: str | Path,
    *,
    count: int = 256,
    source: str = DATASET_ID,
    split: str = "train",
    revision: str = "main",
    sheet_limit: int = 64,
) -> dict[str, object]:
    """Store at most count images and their provenance. Never overwrite a run."""
    if count < 1 or count > 5000:
        raise ValueError("count must be from 1 to 5000")
    if sheet_limit < 1 or sheet_limit > 128:
        raise ValueError("sheet_limit must be from 1 to 128")
    dest = Path(output_dir)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"Atlas output already exists: {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{dest.name}-", dir=dest.parent))
    try:
        sprite_dir = temp / "sprites"
        sprite_dir.mkdir()
        seen_ids: set[int] = set()
        records: list[dict[str, object]] = []
        for item in islice(rows, count):
            row_id = item.get("row_id")
            if isinstance(row_id, bool) or not isinstance(row_id, int) or row_id < 0:
                raise ValueError(f"invalid row_id: {row_id!r}")
            if row_id in seen_ids:
                raise ValueError(f"duplicate row_id: {row_id}")
            seen_ids.add(row_id)
            image = item.get("image")
            if not isinstance(image, Image.Image):
                raise ValueError("image must be a decoded Pillow image")
            caption = item.get("caption")
            subject = item.get("subject")
            if not isinstance(caption, str) or not isinstance(subject, str):
                raise ValueError(f"caption and subject must be strings for row_id {row_id}")
            canonical = _normalized_image(image)
            metrics = analyze_sprite(canonical)
            image_path = sprite_dir / f"{row_id}.png"
            canonical.save(image_path, format="PNG", optimize=False)
            records.append({
                "row_id": row_id,
                "caption": caption,
                "subject": subject,
                "split": split,
                "png_sha256": sha256(image_path.read_bytes()).hexdigest(),
                **metrics,
            })
        if not records:
            raise ValueError("No samples received")

        with (temp / "index.jsonl").open("w", encoding="utf-8") as handle:
            for row in records:
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
        hashes: dict[str, list[int]] = defaultdict(list)
        flags: Counter[str] = Counter()
        subjects: Counter[str] = Counter()
        for row in records:
            hashes[str(row["pixel_sha256"])].append(int(row["row_id"]))
            subjects[str(row["subject"])] += 1
            flags.update(row["flags"])
        duplicate_groups = [ids for ids in hashes.values() if len(ids) > 1]
        report: dict[str, object] = {
            "schema_version": SCHEMA,
            "source": source,
            "requested_revision": revision,
            "split": split,
            "requested_count": count,
            "sample_count": len(records),
            "sampling_complete": len(records) == count,
            "method": "stream_order_first_n; not representative of entire dataset",
            "subjects_count": len(subjects),
            "subjects_top_20": [[subject, amount] for subject, amount in subjects.most_common(20)],
            "flags_count": dict(sorted(flags.items())),
            "exact_duplicate_extra_rows": sum(len(ids) - 1 for ids in duplicate_groups),
            "exact_duplicate_groups_first_20": duplicate_groups[:20],
            "evaluation": "descriptive_heuristics_only_not_aesthetic_quality",
            "caption_verified": False,
            "license_claim": "CC0-1.0 to the extent publisher can waive; upstream terms remain relevant",
            "rights_review_required": True,
            "game_embedding_approved": False,
            "training_approved": False,
            "asset_pack_redistribution_approved": False,
            "external_code_executed": False,
        }
        (temp / "summary.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _render_sheet(records[:sheet_limit], sprite_dir, temp / "contact-sheet.png")
        if dest.exists() or dest.is_symlink():
            raise FileExistsError(f"Atlas output already exists: {dest}")
        os.rename(temp, dest)
        return report
    finally:
        if temp.exists():
            shutil.rmtree(temp)


def sample_from_huggingface(
    output_dir: str | Path,
    *,
    count: int = 256,
    split: str = "train",
    revision: str = "main",
    sheet_limit: int = 64,
) -> dict[str, object]:
    """Explicit opt-in network path; requires optional datasets installation."""
    if split not in ("train", "validation"):
        raise ValueError("split must be train or validation")
    if not revision.strip():
        raise ValueError("revision must be provided")
    if Path(output_dir).exists() or Path(output_dir).is_symlink():
        raise FileExistsError(f"Atlas output already exists: {output_dir}")
    if count < 1 or count > 5000:
        raise ValueError("count must be from 1 to 5000")
    try:
        from datasets import load_dataset
    except ImportError as exc:
        raise RuntimeError('Install optional dependency: pip install -e ".[atlas]"') from exc
    stream = load_dataset(DATASET_ID, split=split, revision=revision, streaming=True)
    return build_sample(
        stream,
        output_dir,
        count=count,
        split=split,
        revision=revision,
        sheet_limit=sheet_limit,
    )


def make_subject_sheet(
    bundle_dir: str | Path,
    *,
    subject: str,
    output_path: str | Path,
    limit: int = 64,
) -> int:
    if not 1 <= limit <= 128:
        raise ValueError("limit must be between 1 and 128")
    bundle = Path(bundle_dir)
    dest = Path(output_path)
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"Refusing to overwrite: {dest}")
    index = bundle / "index.jsonl"
    records = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line]
    chosen = [entry for entry in records if subject.casefold() in str(entry["subject"]).casefold()][:limit]
    if not chosen:
        raise ValueError(f"No sprites matched subject: {subject}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    _render_sheet(chosen, bundle / "sprites", dest)
    return len(chosen)
