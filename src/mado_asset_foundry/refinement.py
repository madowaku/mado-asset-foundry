from __future__ import annotations

import hashlib
import json
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from .io import load_recipe, load_run, write_json
from .models import (
    AssetRecord,
    AssetRefinementReport,
    AssetState,
    CurationDecision,
    QAStatus,
    RefinementRunReport,
    RefinementStatus,
)


_RESAMPLE = {
    "nearest": Image.Resampling.NEAREST,
    "bilinear": Image.Resampling.BILINEAR,
    "bicubic": Image.Resampling.BICUBIC,
    "lanczos": Image.Resampling.LANCZOS,
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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


def _clean_alpha(image: Image.Image, threshold: int) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A").point(lambda value: 0 if value <= threshold else value)
    rgba.putalpha(alpha)
    return rgba


def _quantize_rgba(image: Image.Image, colors: int, *, dither: bool) -> Image.Image:
    alpha = image.getchannel("A")
    rgb = Image.new("RGB", image.size, (0, 0, 0))
    rgb.paste(image.convert("RGB"), mask=alpha)
    quantized = rgb.quantize(
        colors=colors,
        method=Image.Quantize.MEDIANCUT,
        dither=Image.Dither.FLOYDSTEINBERG if dither else Image.Dither.NONE,
    ).convert("RGB")
    result = quantized.convert("RGBA")
    result.putalpha(alpha)
    return result


def _normalize_image(
    source: Path,
    *,
    target_size: tuple[int, int],
    alpha_threshold: int,
    padding: int,
    palette_colors: int | None,
    resample: str,
    dither: bool,
) -> tuple[Image.Image, tuple[int, int, int, int], tuple[int, int]]:
    with Image.open(source) as opened:
        opened.load()
        source_size = opened.size
        image = _clean_alpha(opened, alpha_threshold)

    alpha = image.getchannel("A")
    crop_box = alpha.getbbox()
    if crop_box is None:
        raise ValueError("source has no visible pixels after alpha cleanup")

    cropped = image.crop(crop_box)
    available_width = target_size[0] - padding * 2
    available_height = target_size[1] - padding * 2
    if available_width <= 0 or available_height <= 0:
        raise ValueError("padding leaves no drawable output area")

    scale = min(available_width / cropped.width, available_height / cropped.height)
    resized_size = (
        max(1, min(available_width, round(cropped.width * scale))),
        max(1, min(available_height, round(cropped.height * scale))),
    )
    resized = cropped.resize(resized_size, resample=_RESAMPLE[resample])
    resized = _clean_alpha(resized, alpha_threshold)

    if palette_colors is not None:
        resized = _quantize_rgba(resized, palette_colors, dither=dither)

    canvas = Image.new("RGBA", target_size, (0, 0, 0, 0))
    offset = (
        (target_size[0] - resized.width) // 2,
        (target_size[1] - resized.height) // 2,
    )
    canvas.alpha_composite(resized, dest=offset)
    return canvas, crop_box, source_size


def refine_run(
    run_dir: str | Path,
    *,
    force: bool = False,
) -> RefinementRunReport:
    directory = Path(run_dir)
    run_path = directory / "run.json"
    recipe = load_recipe(directory / "recipe.yaml")
    run = load_run(run_path)

    selected = [asset for asset in run.assets if asset.curation_decision == CurationDecision.KEEP]
    eligible_statuses = {QAStatus.PASS, QAStatus.WARN}
    eligible = [asset for asset in selected if asset.qa_status in eligible_statuses]

    output_dir = directory / "refined"
    evidence_dir = directory / "refinement"
    output_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    reports: list[AssetRefinementReport] = []
    target_size = (recipe.output.width, recipe.output.height)

    for asset in selected:
        if asset.qa_status not in eligible_statuses:
            report = AssetRefinementReport(
                asset_id=asset.asset_id,
                status=RefinementStatus.SKIPPED,
                message="Asset is not QA-pass/warn eligible for refinement.",
                source_path=asset.source_path,
                details={"qa_status": asset.qa_status.value if asset.qa_status else None},
            )
            reports.append(report)
            write_json(evidence_dir / f"{asset.asset_id}.json", report.model_dump(mode="json"))
            continue

        source = _resolve_source_path(directory, asset)
        output = output_dir / f"{asset.asset_id}.png"

        if output.exists() and not force:
            report = AssetRefinementReport(
                asset_id=asset.asset_id,
                status=RefinementStatus.SKIPPED,
                message="Normalized output already exists; use --force to replace it.",
                source_path=str(source) if source else asset.source_path,
                output_path=str(output),
                output_sha256=_sha256(output),
                output_size=target_size,
                details={"reason": "output_exists"},
            )
            reports.append(report)
            write_json(evidence_dir / f"{asset.asset_id}.json", report.model_dump(mode="json"))
            continue

        if source is None:
            asset.refinement_status = RefinementStatus.FAILED
            asset.state = AssetState.REFINE_FAILED
            report = AssetRefinementReport(
                asset_id=asset.asset_id,
                status=RefinementStatus.FAILED,
                message="Source image is missing.",
                source_path=asset.source_path,
            )
            reports.append(report)
            write_json(evidence_dir / f"{asset.asset_id}.json", report.model_dump(mode="json"))
            continue

        source_digest = _sha256(source)
        try:
            normalized, crop_box, source_size = _normalize_image(
                source,
                target_size=target_size,
                alpha_threshold=recipe.refinement.alpha_threshold,
                padding=recipe.refinement.padding,
                palette_colors=recipe.refinement.palette_colors,
                resample=recipe.refinement.resample,
                dither=recipe.refinement.dither,
            )
            normalized.save(output, format="PNG", compress_level=9)
            output_digest = _sha256(output)

            if _sha256(source) != source_digest:
                raise RuntimeError("raw source changed during refinement")

            asset.refinement_status = RefinementStatus.NORMALIZED
            asset.refined_path = str(output)
            asset.refined_sha256 = output_digest
            asset.state = AssetState.NORMALIZED

            report = AssetRefinementReport(
                asset_id=asset.asset_id,
                status=RefinementStatus.NORMALIZED,
                message="Asset normalized successfully.",
                source_path=str(source),
                output_path=str(output),
                source_sha256=source_digest,
                output_sha256=output_digest,
                source_size=source_size,
                output_size=normalized.size,
                crop_box=crop_box,
                details={
                    "alpha_threshold": recipe.refinement.alpha_threshold,
                    "padding": recipe.refinement.padding,
                    "palette_colors": recipe.refinement.palette_colors,
                    "resample": recipe.refinement.resample,
                    "dither": recipe.refinement.dither,
                },
            )
        except (OSError, UnidentifiedImageError, ValueError, RuntimeError) as exc:
            if output.exists():
                output.unlink()
            asset.refinement_status = RefinementStatus.FAILED
            asset.state = AssetState.REFINE_FAILED
            report = AssetRefinementReport(
                asset_id=asset.asset_id,
                status=RefinementStatus.FAILED,
                message="Asset normalization failed.",
                source_path=str(source),
                source_sha256=source_digest,
                details={"error": str(exc)},
            )

        reports.append(report)
        write_json(evidence_dir / f"{asset.asset_id}.json", report.model_dump(mode="json"))

        metadata_path = _metadata_path(directory, asset)
        metadata: dict[str, object] = {}
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata["refinement_status"] = report.status.value
        metadata["refinement_report_path"] = str(evidence_dir / f"{asset.asset_id}.json")
        if report.output_path:
            metadata["refined_path"] = report.output_path
        if report.output_sha256:
            metadata["refined_sha256"] = report.output_sha256
        write_json(metadata_path, metadata)
        asset.metadata_path = str(metadata_path)

    run_report = RefinementRunReport(
        run_id=run.run_id,
        recipe_id=run.recipe_id,
        selected_count=len(selected),
        eligible_count=len(eligible),
        normalized_count=sum(report.status == RefinementStatus.NORMALIZED for report in reports),
        failed_count=sum(report.status == RefinementStatus.FAILED for report in reports),
        skipped_count=sum(report.status == RefinementStatus.SKIPPED for report in reports),
        reports=reports,
    )
    write_json(evidence_dir / "report.json", run_report.model_dump(mode="json"))
    write_json(run_path, run.model_dump(mode="json"))
    return run_report
