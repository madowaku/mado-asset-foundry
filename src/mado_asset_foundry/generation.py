from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from .io import write_json, write_recipe_snapshot
from .models import AssetRecord, AssetRecipe, FoundryRun
from .prompts import GenerationBatch, plan_generation
from .providers import get_image_provider
from .providers.base import ImageGenerationRequest, ImageProvider


def _default_run_id(recipe: AssetRecipe) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{recipe.id}"


def _serialize_plan(plan: list[GenerationBatch]) -> list[dict[str, object]]:
    return [{"subject": batch.subject, "count": batch.count, "prompt": batch.prompt} for batch in plan]


def generate_run(
    recipe: AssetRecipe,
    workspace: str | Path = "runs",
    *,
    count: int = 1,
    dry_run: bool = False,
    run_id: str | None = None,
    provider: ImageProvider | None = None,
) -> tuple[FoundryRun, Path]:
    plan = plan_generation(recipe, count=count)
    actual_run_id = run_id or _default_run_id(recipe)
    run_dir = Path(workspace) / actual_run_id
    raw_dir = run_dir / "raw"
    metadata_dir = run_dir / "metadata"
    raw_dir.mkdir(parents=True, exist_ok=False)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    write_recipe_snapshot(run_dir / "recipe.yaml", recipe)
    write_json(run_dir / "plan.json", _serialize_plan(plan))

    run = FoundryRun(
        run_id=actual_run_id,
        recipe_id=recipe.id,
        provider=recipe.generation.provider,
        model=recipe.generation.model,
        requested_count=count,
        dry_run=dry_run,
    )

    request_evidence: list[dict[str, object]] = []

    if dry_run:
        write_json(run_dir / "requests.json", request_evidence)
        write_json(run_dir / "run.json", run.model_dump(mode="json"))
        return run, run_dir

    image_provider = provider or get_image_provider(
        recipe.generation.provider,
        codex_model=recipe.generation.codex_model,
        codex_binary=recipe.generation.codex_binary,
        codex_timeout_seconds=recipe.generation.codex_timeout_seconds,
    )
    extension = recipe.generation.output_format
    asset_number = 0
    write_json(run_dir / "run.json", run.model_dump(mode="json"))

    for batch in plan:
        request = ImageGenerationRequest(
            model=recipe.generation.model,
            prompt=batch.prompt,
            count=batch.count,
            size=recipe.generation.render_size,
            quality=recipe.generation.quality,
            background=recipe.generation.background,
            output_format=recipe.generation.output_format,
        )
        try:
            results = image_provider.generate(request)
        except Exception as exc:
            write_json(
                run_dir / "generation-error.json",
                {
                    "request_index": len(request_evidence) + 1,
                    "subject": batch.subject,
                    "count": batch.count,
                    "model": request.model,
                    "codex_model": recipe.generation.codex_model if recipe.generation.provider == "codex-imagegen" else None,
                    "size": request.size,
                    "quality": request.quality,
                    "background": request.background,
                    "output_format": request.output_format,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "generated_assets_before_error": len(run.assets),
                },
            )
            write_json(run_dir / "run.json", run.model_dump(mode="json"))
            raise

        provider_metadata = results[0].provider_metadata if results else {}
        request_evidence.append(
            {
                "request_index": len(request_evidence) + 1,
                "subject": batch.subject,
                "count": batch.count,
                "model": request.model,
                "codex_model": recipe.generation.codex_model if recipe.generation.provider == "codex-imagegen" else None,
                "size": request.size,
                "quality": request.quality,
                "background": request.background,
                "output_format": request.output_format,
                "provider_metadata": provider_metadata,
            }
        )
        write_json(run_dir / "requests.json", request_evidence)

        for result in results:
            asset_number += 1
            asset_id = f"asset_{asset_number:04d}"
            raw_path = raw_dir / f"{asset_id}.{extension}"
            raw_path.write_bytes(result.content)
            digest = hashlib.sha256(result.content).hexdigest()

            metadata_path = metadata_dir / f"{asset_id}.json"
            metadata = {
                "asset_id": asset_id,
                "recipe_id": recipe.id,
                "provider": recipe.generation.provider,
                "model": recipe.generation.model,
                "codex_model": recipe.generation.codex_model if recipe.generation.provider == "codex-imagegen" else None,
                "subject": batch.subject,
                "prompt": batch.prompt,
                "revised_prompt": result.revised_prompt,
                "generation_index": asset_number,
                "sha256": digest,
                "request": {
                    "size": recipe.generation.render_size,
                    "quality": recipe.generation.quality,
                    "background": recipe.generation.background,
                    "output_format": recipe.generation.output_format,
                },
                "provider_metadata": result.provider_metadata,
            }
            write_json(metadata_path, metadata)

            run.assets.append(
                AssetRecord(
                    asset_id=asset_id,
                    recipe_id=recipe.id,
                    provider=recipe.generation.provider,
                    model=recipe.generation.model,
                    source_path=str(raw_path),
                    metadata_path=str(metadata_path),
                    subject=batch.subject,
                    generation_index=asset_number,
                    sha256=digest,
                )
            )
            write_json(run_dir / "run.json", run.model_dump(mode="json"))

    write_json(run_dir / "run.json", run.model_dump(mode="json"))
    return run, run_dir
