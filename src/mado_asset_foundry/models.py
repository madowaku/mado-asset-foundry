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
    REFINE_FAILED = "refine_failed"
    QA_FAILED = "qa_failed"
    QA_PASSED = "qa_passed"
    GAME_VERIFIED = "game_verified"
    PACKAGED = "packaged"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class CurationDecision(StrEnum):
    UNREVIEWED = "unreviewed"
    REJECT = "reject"
    MAYBE = "maybe"
    KEEP = "keep"


class QAStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class RefinementStatus(StrEnum):
    NORMALIZED = "normalized"
    FAILED = "failed"
    SKIPPED = "skipped"


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
    codex_model: str = "gpt-6-luna"
    codex_binary: str = "codex"
    codex_timeout_seconds: int = Field(default=420, ge=30, le=1800)

    @model_validator(mode="after")
    def validate_provider_settings(self) -> "GenerationSpec":
        if self.provider.strip().lower() == "codex-imagegen":
            if self.model != "gpt-image-2":
                raise ValueError("codex-imagegen uses built-in gpt-image-2; set generation.model to gpt-image-2")
            if self.output_format != "png":
                raise ValueError("codex-imagegen bridge currently requires PNG output")
        return self


class CurationSpec(BaseModel):
    target_count: int = Field(gt=0)
    criteria: list[str] = Field(default_factory=list)


class RefinementSpec(BaseModel):
    alpha_threshold: int = Field(default=8, ge=0, le=254)
    padding: int = Field(default=2, ge=0)
    palette_colors: int | None = Field(default=16, ge=2, le=256)
    resample: Literal["nearest", "bilinear", "bicubic", "lanczos"] = "lanczos"
    dither: bool = False


class ProductionSpec(BaseModel):
    probe_count: int = Field(default=1, ge=1)
    pilot_count: int = Field(default=6, ge=1)
    production_count: int = Field(default=12, ge=1)
    max_live_count: int = Field(default=12, ge=1)

    @model_validator(mode="after")
    def validate_counts(self) -> "ProductionSpec":
        if not (self.probe_count <= self.pilot_count <= self.production_count):
            raise ValueError("production counts must satisfy probe <= pilot <= production")
        if self.production_count > self.max_live_count:
            raise ValueError("production.production_count cannot exceed production.max_live_count")
        return self


class ProductSpec(BaseModel):
    product_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    short_description: str = Field(min_length=1)
    license_id: str = Field(min_length=1)
    license_status: Literal["draft", "public"] = "draft"
    license_text: str = Field(min_length=20)
    ai_assisted: bool = True
    ai_disclosure: str | None = None
    sheet_columns: int = Field(default=8, ge=1, le=32)
    preview_scale: int = Field(default=4, ge=1, le=16)

    @model_validator(mode="after")
    def validate_disclosure(self) -> "ProductSpec":
        if self.ai_assisted and not (self.ai_disclosure and self.ai_disclosure.strip()):
            raise ValueError("product.ai_disclosure is required when ai_assisted is true")
        return self


class ItchDistributionSpec(BaseModel):
    visibility: Literal["draft"] = "draft"
    classification: Literal["assets"] = "assets"
    upload_type: Literal["graphical_assets"] = "graphical_assets"
    tags: list[str] = Field(min_length=1, max_length=10)
    ai_content_types: list[Literal["graphics", "sound", "text_dialog", "code"]] = Field(default_factory=lambda: ["graphics"])
    pricing_mode: Literal["manual_review", "free_or_donate", "paid"] = "manual_review"
    minimum_price_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_itch_distribution(self) -> "ItchDistributionSpec":
        normalized = [tag.strip().lower() for tag in self.tags]
        if any(not tag for tag in normalized):
            raise ValueError("itch.tags must not contain blank values")
        if len(set(normalized)) != len(normalized):
            raise ValueError("itch.tags must not contain duplicates")
        if self.pricing_mode == "paid" and (self.minimum_price_usd is None or self.minimum_price_usd <= 0):
            raise ValueError("itch.minimum_price_usd must be greater than 0 for paid pricing")
        return self


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
    refinement: RefinementSpec = Field(default_factory=RefinementSpec)
    product: ProductSpec | None = None
    itch: ItchDistributionSpec | None = None
    production: ProductionSpec | None = None

    @model_validator(mode="after")
    def validate_recipe_constraints(self) -> "AssetRecipe":
        if self.curation.target_count > self.generation.candidate_count:
            raise ValueError("curation.target_count cannot exceed generation.candidate_count")
        if self.generation.background == "transparent" and self.generation.output_format == "jpeg":
            raise ValueError("transparent generation requires png or webp output")
        if self.refinement.padding * 2 >= min(self.output.width, self.output.height):
            raise ValueError("refinement.padding leaves no drawable output area")
        if self.production is not None:
            if self.production.production_count > self.generation.candidate_count:
                raise ValueError("production.production_count cannot exceed generation.candidate_count")
            if self.curation.target_count > self.production.production_count:
                raise ValueError("curation.target_count cannot exceed production.production_count")
        return self


class QACheckResult(BaseModel):
    check: str
    status: QAStatus
    message: str
    details: dict[str, object] = Field(default_factory=dict)


class AssetQAReport(BaseModel):
    asset_id: str
    status: QAStatus
    checks: list[QACheckResult]
    source_path: str | None = None


class QARunReport(BaseModel):
    run_id: str
    recipe_id: str
    selected_count: int
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    reports: list[AssetQAReport] = Field(default_factory=list)


class AssetRefinementReport(BaseModel):
    asset_id: str
    status: RefinementStatus
    message: str
    source_path: str | None = None
    output_path: str | None = None
    source_sha256: str | None = None
    output_sha256: str | None = None
    source_size: tuple[int, int] | None = None
    output_size: tuple[int, int] | None = None
    crop_box: tuple[int, int, int, int] | None = None
    details: dict[str, object] = Field(default_factory=dict)


class RefinementRunReport(BaseModel):
    run_id: str
    recipe_id: str
    selected_count: int
    eligible_count: int
    normalized_count: int = 0
    failed_count: int = 0
    skipped_count: int = 0
    reports: list[AssetRefinementReport] = Field(default_factory=list)


class ProductCompileReport(BaseModel):
    run_id: str
    recipe_id: str
    product_id: str
    version: str
    asset_count: int
    product_dir: str
    zip_path: str
    zip_sha256: str
    manifest_path: str
    sprite_sheet_path: str
    contact_sheet_path: str


class ProductionRunReport(BaseModel):
    run_id: str
    recipe_id: str
    stage: Literal["probe", "pilot", "production"]
    requested_count: int
    live: bool
    status: Literal[
        "planned",
        "awaiting_curation",
        "ready_to_advance",
        "blocked",
        "completed",
    ]
    reviewed_count: int = 0
    keep_count: int = 0
    qa_fail_count: int = 0
    normalized_count: int = 0
    usage: dict[str, int] = Field(default_factory=dict)
    blockers: list[str] = Field(default_factory=list)
    release_blockers: list[str] = Field(default_factory=list)
    godot_verification: Literal["not_run", "passed", "failed"] = "not_run"
    next_action: str


class GodotFixtureReport(BaseModel):
    run_id: str
    recipe_id: str
    product_id: str
    version: str
    asset_count: int
    fixture_dir: str
    project_path: str
    manifest_path: str
    verification_status: Literal["not_run", "passed", "failed"] = "not_run"
    godot_binary: str | None = None
    godot_version: str | None = None
    import_report_path: str | None = None
    gallery_capture_path: str | None = None


class ItchReadyReport(BaseModel):
    run_id: str
    recipe_id: str
    product_id: str
    version: str
    ready: bool
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    release_dir: str
    upload_zip: str
    upload_zip_sha256: str
    cover_path: str
    screenshot_paths: list[str]
    listing_path: str
    checklist_path: str


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
    curation_decision: CurationDecision = CurationDecision.UNREVIEWED
    favorite: bool = False
    qa_status: QAStatus | None = None
    refinement_status: RefinementStatus | None = None
    refined_path: str | None = None
    refined_sha256: str | None = None
    packaged_products: list[str] = Field(default_factory=list)


class FoundryRun(BaseModel):
    run_id: str
    recipe_id: str
    provider: str
    model: str
    requested_count: int = Field(gt=0)
    dry_run: bool = False
    assets: list[AssetRecord] = Field(default_factory=list)
