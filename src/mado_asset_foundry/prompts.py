from __future__ import annotations

from dataclasses import dataclass

from .models import AssetRecipe


@dataclass(frozen=True)
class GenerationBatch:
    subject: str
    prompt: str
    count: int


def compile_icon_prompt(recipe: AssetRecipe, subject: str) -> str:
    transparency = (
        "Isolate the icon on a transparent background."
        if recipe.generation.background == "transparent"
        else "Keep the background visually simple and unobtrusive."
    )
    extra = f"\nAdditional art direction: {recipe.prompt_extra.strip()}" if recipe.prompt_extra else ""
    return (
        "Create a single game inventory icon source image for later normalization and downscaling.\n"
        f"Subject: {subject}.\n"
        f"Theme: {recipe.theme.replace('_', ' ')}.\n"
        f"Style: {recipe.style.replace('_', ' ')}.\n"
        f"The final game asset will be {recipe.output.width}x{recipe.output.height} pixels, so prioritize a bold readable silhouette, "
        "simple internal shapes, strong separation between parts, and generous padding around the subject.\n"
        f"{transparency}\n"
        "Center one object only. No text, letters, numbers, watermark, logo, UI frame, mockup, drop shadow outside the object, or extra props."
        f"{extra}"
    )


def plan_generation(recipe: AssetRecipe, count: int | None = None) -> list[GenerationBatch]:
    total = recipe.generation.candidate_count if count is None else count
    if total < 1 or total > recipe.generation.candidate_count:
        raise ValueError("count must be between 1 and generation.candidate_count")

    subjects = recipe.subjects or [recipe.name]
    batches: list[GenerationBatch] = []
    remaining = total
    subject_index = 0

    while remaining > 0:
        subject = subjects[subject_index % len(subjects)]
        batch_count = min(recipe.generation.batch_size, remaining)
        batches.append(
            GenerationBatch(
                subject=subject,
                prompt=compile_icon_prompt(recipe, subject),
                count=batch_count,
            )
        )
        remaining -= batch_count
        subject_index += 1

    return batches
