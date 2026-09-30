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
    provider: str
    model: str = "configurable"
    candidate_count: int = Field(gt=0)


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
    output: OutputSpec
    generation: GenerationSpec
    targets: list[str] = Field(default_factory=lambda: ["generic"])
    curation: CurationSpec

    @model_validator(mode="after")
    def target_must_fit_candidates(self) -> "AssetRecipe":
        if self.curation.target_count > self.generation.candidate_count:
            raise ValueError("curation.target_count cannot exceed generation.candidate_count")
        return self


class AssetRecord(BaseModel):
    asset_id: str
    recipe_id: str
    provider: str
    model: str
    seed: int | None = None
    state: AssetState = AssetState.GENERATED
    source_path: str | None = None


class FoundryRun(BaseModel):
    run_id: str
    recipe_id: str
    assets: list[AssetRecord] = Field(default_factory=list)
