from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AssetState(StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    NORMALIZED = "normalized"
    REVIEW_PENDING = "review_pending"
    SELECTED = "selected"
    REJECTED = "rejected"
    REFINED = "refined"
    QA_FAILED = "qa_failed"
    QA_PASSED = "qa_passed"
    GAME_VERIFIED = "game_verified"
    PACKAGED = "packaged"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class OutputSpec(BaseModel):
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: Literal["png"] = "png"
    transparent: bool = True


class GenerationSpec(BaseModel):
    provider: str = "openai-image"
    model: str = "gpt-image-2.5-flare"
    candidate_count: int = Field(gt=0)
    batch_size: int = Field(default=4, ge=1, le=10)
    render_size: str = "1024x1024"
    quality: Literal["low", "medium", "high", "auto"] = "low"
    background: Literal["transparent", "opaque", "auto"] = "transparent"
    output_format: Literal["png", "webp", "jpeg"] = "png"


class CurationSpec(BaseModel):
    target_count: int = Field(gt=0)
    criteria: list[str] = Field(default_factory=list)


class AssetRecipe(BaseModel):
    schema_version: Literal["0.1"] = "0.1"
    id: str
    name: str
    asset_type: Literal["icon"]
    theme: str
    style: str
    subjects: list[str] = Field(default_factory=list)
    prompt_extra: str | None = None
    output: OutputSpec
    generation: GenerationSpec
    targets: list[str] = Field(default_factory=lambda: ["generic"])
    curation: CurationSpec

    @model_validator(mode="after")
    def validate_recipe_constraints(self) -> "AssetRecipe":
        if self.curation.target_count > self.generation.candidate_count:
            raise ValueError("curation.target_count cannot exceed generation.candidate_count")
        if self.generation.background == "transparent" and self.generation.output_format == "jpeg":
            raise ValueError("transparent generation requires png or webp output")
        return self


class AssetRecord(BaseModel):
    asset_id: str
    recipe_id: str
    provider: str
    model: str
    state: AssetState = AssetState.GENERATED
    source_path: str | None = None
    metadata_path: str | None = None
    subject: str | None = None
    generation_index: int | None = None
    sha256: str | None = None


class FoundryRun(BaseModel):
    run_id: str
    recipe_id: str
    provider: str
    model: str
    requested_count: int = Field(gt=0)
    dry_run: bool = False
    assets: list[AssetRecord] = Field(default_factory=list)
