"""Immutable, provenance-checked full-resolution screenshot golden comparisons.

Golden PNGs are imported exactly once from pinned known-good M1.2 CI
artifact by a separate bootstrapping workflow. Ordinary E2E tests
never create/approve/update goldens.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "goldens" / "manifest.json"
GOLDEN_ROOT = MANIFEST_PATH.parent
DIFF_ROOT = Path("runs/browser-e2e/visual-delta")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_manifest() -> dict:
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0":
        raise ValueError("Unsupported screenshot golden manifest")
    if not isinstance(data.get("goldens"), dict) or not data["goldens"]:
        raise ValueError("Missing locked screenshot golden definitions")
    return data


def _diff_rgb(expected: Image.Image, actual: Image.Image, tolerance: int) -> tuple[float, float, Image.Image]:
    difference = ImageChops.difference(expected, actual)
    stats = ImageStat.Stat(difference)
    mae = sum(stats.mean) / 3
    largest = ImageChops.lighter(
        ImageChops.lighter(difference.getchannel("R"), difference.getchannel("G")),
        difference.getchannel("B"),
    )
    mask = largest.point(lambda val: 255 if val > tolerance else 0)
    changed_fraction = ImageStat.Stat(mask).mean[0] / 255.0
    highlighted = Image.new("RGB", expected.size, (12, 21, 27))
    highlighted.paste(Image.new("RGB", expected.size, (250, 83, 68)), mask=mask)
    return changed_fraction, mae, highlighted


def compare_golden(name: str, actual_data: bytes, *, destination: Path | None = None) -> dict:
    """Read-only golden compare. Always save an inspector even if comparison fails.

    Fails closed on missing golden or altered golden SHA-256; does not
    accidentally treat the current screenshot as an approved reference.
    """
    manifest = read_manifest()
    if name not in manifest["goldens"]:
        raise ValueError(f"Checkpoint is not in approved golden manifest: {name}")
    entry = manifest["goldens"][name]
    path = GOLDEN_ROOT / f"{name}.png"
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f"Approved golden PNG missing: {path}; run the explicit golden bootstrap")
    stored_hash = sha256(path)
    if stored_hash != entry["sha256"]:
        raise ValueError(f"Golden screenshot tampering detected: {name}")
    output = destination or DIFF_ROOT
    output.mkdir(parents=True, exist_ok=True)

    with Image.open(path) as source, Image.open(io.BytesIO(actual_data)) as candidate:
        if source.format != "PNG" or candidate.format != "PNG":
            raise ValueError("Visual golden inputs must both be PNG")
        before = source.convert("RGB")
        after = candidate.convert("RGB")
    expected_size = tuple(entry["size"])
    if before.size != expected_size:
        raise ValueError(f"Golden dimension mismatch with pinned manifest: {name}")
    equal_dimensions = before.size == after.size
    tolerance = int(manifest["comparison"]["pixel_channel_tolerance"])
    changed_fraction, mae, diff = (1.0, 255.0, Image.new("RGB", expected_size, (250, 83, 68)))
    if equal_dimensions:
        changed_fraction, mae, diff = _diff_rgb(before, after, tolerance)

    comparison = Image.new("RGB", (before.width * 3, max(before.height, after.height) + 38), (11, 20, 27))
    comparison.paste(before, (0, 38))
    if after.size == before.size:
        comparison.paste(after, (before.width, 38))
    else:
        scaled = after.copy()
        scaled.thumbnail(before.size)
        comparison.paste(scaled, (before.width, 38))
    comparison.paste(diff, (before.width * 2, 38))
    legend = ImageDraw.Draw(comparison)
    for index, label in enumerate(("BEFORE: locked golden", "AFTER: current", "DIFF: changed pixels")):
        legend.text((index * before.width + 16, 11), label, fill=(193, 235, 216))

    comparison.save(output / f"{name}-before-after-diff.png", format="PNG", optimize=True)
    diff.save(output / f"{name}-diff.png", format="PNG", optimize=True)
    thresholds = manifest["comparison"]
    passed = bool(
        equal_dimensions
        and changed_fraction <= float(thresholds["max_changed_fraction"])
        and mae <= float(thresholds["max_mean_absolute_error"])
    )
    result = {
        "schema_version": "1.0",
        "checkpoint": name,
        "status": "passed" if passed else "regression",
        "golden_sha256": stored_hash,
        "actual_sha256": hashlib.sha256(actual_data).hexdigest(),
        "golden_size": list(before.size),
        "actual_size": list(after.size),
        "pixel_channel_tolerance": tolerance,
        "changed_fraction": round(changed_fraction, 7),
        "mean_absolute_error": round(mae, 5),
        "max_changed_fraction": thresholds["max_changed_fraction"],
        "max_mean_absolute_error": thresholds["max_mean_absolute_error"],
        "comparison": f"{name}-before-after-diff.png",
        "diff": f"{name}-diff.png",
    }
    (output / f"{name}-metrics.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if not passed:
        raise AssertionError(
            f"Golden screenshot changed: {name}: {changed_fraction:.2%} pixels, "
            f"mean absolute error {mae:.3f}. Inspect {output / result['comparison']}"
        )
    return result
