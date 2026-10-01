from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .io import load_recipe, load_run, write_json
from .pillow_compat import flattened_data
from .models import (
    AssetQAReport,
    AssetRecord,
    AssetState,
    CurationDecision,
    QACheckResult,
    QARunReport,
    QAStatus,
)


def _status_from_checks(checks: list[QACheckResult]) -> QAStatus:
    if any(check.status == QAStatus.FAIL for check in checks):
        return QAStatus.FAIL
    if any(check.status == QAStatus.WARN for check in checks):
        return QAStatus.WARN
    if checks and all(check.status == QAStatus.SKIP for check in checks):
        return QAStatus.SKIP
    return QAStatus.PASS


def _parse_render_size(value: str) -> tuple[int, int] | None:
    try:
        width, height = value.lower().split("x", 1)
        parsed = (int(width), int(height))
    except (AttributeError, TypeError, ValueError):
        return None
    if parsed[0] <= 0 or parsed[1] <= 0:
        return None
    return parsed


def _resolve_source_path(run_dir: Path, asset: AssetRecord) -> Path | None:
    raw_dir = run_dir / "raw"
    matches = sorted(path for path in raw_dir.glob(f"{asset.asset_id}.*") if path.is_file())
    if matches:
        return matches[0]

    if asset.source_path:
        recorded = Path(asset.source_path)
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _dhash(image: Image.Image, hash_size: int = 8) -> int:
    grayscale = image.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
    pixels = list(flattened_data(grayscale))
    value = 0
    for row in range(hash_size):
        offset = row * (hash_size + 1)
        for col in range(hash_size):
            value <<= 1
            value |= pixels[offset + col] > pixels[offset + col + 1]
    return value


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _border_alpha_ratio(image: Image.Image) -> float:
    alpha = image.getchannel("A")
    width, height = alpha.size
    if width == 1 and height == 1:
        return 1.0 if alpha.getpixel((0, 0)) > 0 else 0.0

    values: list[int] = []
    values.extend(flattened_data(alpha.crop((0, 0, width, 1))))
    if height > 1:
        values.extend(flattened_data(alpha.crop((0, height - 1, width, height))))
    if height > 2:
        values.extend(flattened_data(alpha.crop((0, 1, 1, height - 1))))
        if width > 1:
            values.extend(flattened_data(alpha.crop((width - 1, 1, width, height - 1))))
    if not values:
        return 0.0
    return sum(1 for value in values if value > 8) / len(values)


def _image_checks(
    path: Path,
    *,
    expected_size: tuple[int, int] | None,
    expected_format: str,
    expects_transparency: bool,
) -> tuple[list[QACheckResult], int | None]:
    checks: list[QACheckResult] = []

    try:
        with Image.open(path) as probe:
            probe.verify()
        checks.append(QACheckResult(check="image_integrity", status=QAStatus.PASS, message="Image decodes successfully."))
    except (OSError, UnidentifiedImageError, ValueError) as exc:
        checks.append(
            QACheckResult(
                check="image_integrity",
                status=QAStatus.FAIL,
                message="Image could not be decoded.",
                details={"error": str(exc)},
            )
        )
        return checks, None

    with Image.open(path) as opened:
        image = opened.convert("RGBA") if opened.mode != "RGBA" else opened.copy()
        original_mode = opened.mode
        actual_size = opened.size
        actual_format = (opened.format or "").lower()
        has_transparency_info = "transparency" in opened.info

    normalized_expected_format = expected_format.lower()
    if actual_format == normalized_expected_format:
        checks.append(
            QACheckResult(
                check="file_format",
                status=QAStatus.PASS,
                message="Source format matches recipe output_format.",
                details={"actual": actual_format, "expected": normalized_expected_format},
            )
        )
    else:
        checks.append(
            QACheckResult(
                check="file_format",
                status=QAStatus.FAIL,
                message="Source format does not match recipe output_format.",
                details={"actual": actual_format, "expected": normalized_expected_format},
            )
        )

    if expected_size is None:
        checks.append(
            QACheckResult(
                check="dimensions",
                status=QAStatus.SKIP,
                message="Recipe render_size could not be parsed.",
            )
        )
    elif actual_size == expected_size:
        checks.append(
            QACheckResult(
                check="dimensions",
                status=QAStatus.PASS,
                message="Source dimensions match recipe render_size.",
                details={"actual": list(actual_size), "expected": list(expected_size)},
            )
        )
    else:
        checks.append(
            QACheckResult(
                check="dimensions",
                status=QAStatus.FAIL,
                message="Source dimensions do not match recipe render_size.",
                details={"actual": list(actual_size), "expected": list(expected_size)},
            )
        )

    source_has_alpha = (
        original_mode in {"RGBA", "LA", "PA"}
        or "A" in original_mode
        or has_transparency_info
    )
    alpha = image.getchannel("A")
    extrema = alpha.getextrema()
    transparent_pixels = sum(1 for value in flattened_data(alpha) if value < 255)
    transparent_ratio = transparent_pixels / (image.width * image.height)

    if expects_transparency and not source_has_alpha:
        checks.append(
            QACheckResult(
                check="alpha_channel",
                status=QAStatus.FAIL,
                message="Transparent output was requested but source has no alpha channel.",
                details={"mode": original_mode},
            )
        )
    else:
        checks.append(
            QACheckResult(
                check="alpha_channel",
                status=QAStatus.PASS,
                message="Alpha channel requirement is satisfied.",
                details={"mode": original_mode},
            )
        )

    if expects_transparency and extrema[0] == 255:
        checks.append(
            QACheckResult(
                check="transparency",
                status=QAStatus.FAIL,
                message="Transparent output was requested but every pixel is opaque.",
                details={"transparent_ratio": transparent_ratio},
            )
        )
    elif expects_transparency:
        checks.append(
            QACheckResult(
                check="transparency",
                status=QAStatus.PASS,
                message="Transparent pixels are present.",
                details={"transparent_ratio": round(transparent_ratio, 6)},
            )
        )
    else:
        checks.append(
            QACheckResult(
                check="transparency",
                status=QAStatus.SKIP,
                message="Recipe does not require transparent output.",
            )
        )

    if expects_transparency:
        border_ratio = _border_alpha_ratio(image)
        checks.append(
            QACheckResult(
                check="edge_clipping",
                status=QAStatus.WARN if border_ratio > 0.02 else QAStatus.PASS,
                message=(
                    "Visible pixels touch more than 2% of the image border; subject may be clipped."
                    if border_ratio > 0.02
                    else "Transparent border is clear enough for later normalization."
                ),
                details={"opaque_border_ratio": round(border_ratio, 6), "warning_threshold": 0.02},
            )
        )
    else:
        checks.append(
            QACheckResult(
                check="edge_clipping",
                status=QAStatus.SKIP,
                message="Edge clipping check currently requires alpha transparency.",
            )
        )

    return checks, _dhash(image)


def run_image_qa(
    run_dir: str | Path,
    *,
    near_duplicate_distance: int = 4,
) -> QARunReport:
    directory = Path(run_dir)
    run_path = directory / "run.json"
    recipe_path = directory / "recipe.yaml"
    run = load_run(run_path)
    recipe = load_recipe(recipe_path)

    selected = [asset for asset in run.assets if asset.curation_decision == CurationDecision.KEEP]
    report_dir = directory / "qa"
    report_dir.mkdir(parents=True, exist_ok=True)

    source_paths: dict[str, Path | None] = {asset.asset_id: _resolve_source_path(directory, asset) for asset in selected}
    exact_hashes: dict[str, str] = {}
    dhashes: dict[str, int] = {}

    for asset in selected:
        path = source_paths[asset.asset_id]
        if path is None:
            continue
        exact_hashes[asset.asset_id] = _sha256(path)
        try:
            with Image.open(path) as image:
                image.load()
                dhashes[asset.asset_id] = _dhash(image)
        except (OSError, UnidentifiedImageError, ValueError):
            pass

    exact_groups: dict[str, list[str]] = defaultdict(list)
    for asset_id, digest in exact_hashes.items():
        exact_groups[digest].append(asset_id)
    exact_peers = {
        asset_id: [peer for peer in group if peer != asset_id]
        for group in exact_groups.values()
        if len(group) > 1
        for asset_id in group
    }

    near_peers: dict[str, list[dict[str, object]]] = defaultdict(list)
    ids = sorted(dhashes)
    for index, left_id in enumerate(ids):
        for right_id in ids[index + 1 :]:
            if right_id in exact_peers.get(left_id, []):
                continue
            distance = _hamming_distance(dhashes[left_id], dhashes[right_id])
            if distance <= near_duplicate_distance:
                near_peers[left_id].append({"asset_id": right_id, "distance": distance})
                near_peers[right_id].append({"asset_id": left_id, "distance": distance})

    expected_size = _parse_render_size(recipe.generation.render_size)
    reports: list[AssetQAReport] = []

    for asset in selected:
        path = source_paths[asset.asset_id]
        checks: list[QACheckResult] = []

        if path is None:
            checks.append(
                QACheckResult(
                    check="file_exists",
                    status=QAStatus.FAIL,
                    message="Source image is missing.",
                )
            )
        else:
            checks.append(
                QACheckResult(
                    check="file_exists",
                    status=QAStatus.PASS,
                    message="Source image exists.",
                    details={"path": str(path)},
                )
            )
            image_checks, _ = _image_checks(
                path,
                expected_size=expected_size,
                expected_format=recipe.generation.output_format,
                expects_transparency=recipe.generation.background == "transparent",
            )
            checks.extend(image_checks)

            peers = exact_peers.get(asset.asset_id, [])
            checks.append(
                QACheckResult(
                    check="exact_duplicate",
                    status=QAStatus.WARN if peers else QAStatus.PASS,
                    message=(
                        "Exact duplicate candidate detected."
                        if peers
                        else "No exact duplicate among selected candidates."
                    ),
                    details={"matches": peers},
                )
            )

            similar = near_peers.get(asset.asset_id, [])
            checks.append(
                QACheckResult(
                    check="near_duplicate",
                    status=QAStatus.WARN if similar else QAStatus.PASS,
                    message=(
                        "Visually similar selected candidate detected."
                        if similar
                        else "No near duplicate within configured perceptual threshold."
                    ),
                    details={"matches": similar, "max_hamming_distance": near_duplicate_distance},
                )
            )

        status = _status_from_checks(checks)
        asset.qa_status = status
        asset.state = AssetState.QA_FAILED if status == QAStatus.FAIL else AssetState.QA_PASSED

        asset_report = AssetQAReport(
            asset_id=asset.asset_id,
            status=status,
            checks=checks,
            source_path=str(path) if path else asset.source_path,
        )
        reports.append(asset_report)
        write_json(report_dir / f"{asset.asset_id}.json", asset_report.model_dump(mode="json"))

        metadata_path = _metadata_path(directory, asset)
        metadata: dict[str, object] = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["qa_status"] = status.value
        metadata["qa_report_path"] = str(report_dir / f"{asset.asset_id}.json")
        write_json(metadata_path, metadata)
        asset.metadata_path = str(metadata_path)

    qa_run = QARunReport(
        run_id=run.run_id,
        recipe_id=run.recipe_id,
        selected_count=len(selected),
        pass_count=sum(report.status == QAStatus.PASS for report in reports),
        warn_count=sum(report.status == QAStatus.WARN for report in reports),
        fail_count=sum(report.status == QAStatus.FAIL for report in reports),
        reports=reports,
    )
    write_json(report_dir / "report.json", qa_run.model_dump(mode="json"))
    write_json(run_path, run.model_dump(mode="json"))
    return qa_run
