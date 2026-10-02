from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from .generation import generate_run
from .godot_fixture import build_godot_fixture
from .io import load_recipe, load_run, write_json
from .itch_ready import compile_itch_ready_pack
from .models import (
    CurationDecision,
    ProductionRunReport,
)
from .packaging import compile_product
from .qa import run_image_qa
from .refinement import refine_run

ProductionStage = Literal["probe", "pilot", "production"]
_VALID_STAGES = {"probe", "pilot", "production"}


def _stage_count(recipe, stage: ProductionStage) -> int:
    if recipe.production is None:
        raise ValueError("recipe.production is required")
    return {
        "probe": recipe.production.probe_count,
        "pilot": recipe.production.pilot_count,
        "production": recipe.production.production_count,
    }[stage]


def _read_request_usage(run_dir: Path) -> dict[str, int]:
    path = run_dir / "requests.json"
    if not path.exists():
        return {}
    rows = json.loads(path.read_text(encoding="utf-8"))
    totals: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        provider_metadata = row.get("provider_metadata", {})
        if not isinstance(provider_metadata, dict):
            continue
        usage = provider_metadata.get("usage", {})
        if not isinstance(usage, dict):
            continue
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, int):
                totals[key] = totals.get(key, 0) + value
    return totals


def _load_report(run_dir: Path) -> ProductionRunReport:
    path = run_dir / "production.json"
    if not path.exists():
        raise FileNotFoundError("production.json is missing; start with maf production start")
    return ProductionRunReport.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _save_report(run_dir: Path, report: ProductionRunReport) -> ProductionRunReport:
    write_json(run_dir / "production.json", report.model_dump(mode="json"))
    return report


def plan_production(recipe_path: str | Path) -> dict[str, object]:
    recipe = load_recipe(recipe_path)
    if recipe.production is None:
        raise ValueError("recipe.production is required")
    return {
        "recipe_id": recipe.id,
        "model": recipe.generation.model,
        "quality": recipe.generation.quality,
        "render_size": recipe.generation.render_size,
        "probe_count": recipe.production.probe_count,
        "pilot_count": recipe.production.pilot_count,
        "production_count": recipe.production.production_count,
        "max_live_count": recipe.production.max_live_count,
        "target_count": recipe.curation.target_count,
    }


def start_production(
    recipe_path: str | Path,
    *,
    stage: str = "probe",
    live: bool = False,
    workspace: str | Path = "runs",
    run_id: str | None = None,
    provider=None,
) -> tuple[ProductionRunReport, Path]:
    if stage not in _VALID_STAGES:
        raise ValueError("stage must be probe, pilot, or production")

    recipe = load_recipe(recipe_path)
    if recipe.production is None:
        raise ValueError("recipe.production is required")

    typed_stage: ProductionStage = stage  # type: ignore[assignment]
    count = _stage_count(recipe, typed_stage)
    if typed_stage in {"probe", "pilot"}:
        # Early stages should sample breadth across subjects, not generate
        # multiple variants of only the first few subjects.
        recipe.generation.batch_size = 1
    if count > recipe.production.max_live_count:
        raise ValueError("requested production stage exceeds max_live_count")

    run, run_dir = generate_run(
        recipe,
        workspace=workspace,
        count=count,
        dry_run=not live,
        run_id=run_id,
        provider=provider,
    )
    report = ProductionRunReport(
        run_id=run.run_id,
        recipe_id=recipe.id,
        stage=typed_stage,
        requested_count=count,
        live=live,
        status="awaiting_curation" if live else "planned",
        usage=_read_request_usage(run_dir),
        next_action=(
            "Open the Candidate Curator and review every generated candidate."
            if live
            else "Re-run this stage with --live after reviewing the plan."
        ),
    )
    return _save_report(run_dir, report), run_dir


def refresh_production_status(run_dir: str | Path) -> ProductionRunReport:
    directory = Path(run_dir)
    report = _load_report(directory)
    run = load_run(directory / "run.json")

    reviewed = sum(asset.curation_decision != CurationDecision.UNREVIEWED for asset in run.assets)
    keep_count = sum(asset.curation_decision == CurationDecision.KEEP for asset in run.assets)
    report.reviewed_count = reviewed
    report.keep_count = keep_count
    report.usage = _read_request_usage(directory)
    report.blockers = []

    if not report.live:
        report.status = "planned"
        report.next_action = "Re-run this stage with --live after reviewing the plan."
    elif reviewed < len(run.assets):
        report.status = "awaiting_curation"
        report.next_action = "Finish reviewing every candidate in maf curate."
    else:
        report.next_action = "Curation is complete. Inspect KEEP count or run maf production advance."
    return _save_report(directory, report)


def advance_production(
    run_dir: str | Path,
    *,
    force: bool = False,
    godot_bin: str | None = None,
) -> ProductionRunReport:
    directory = Path(run_dir)
    report = refresh_production_status(directory)
    recipe = load_recipe(directory / "recipe.yaml")
    run = load_run(directory / "run.json")

    blockers: list[str] = []
    if report.stage != "production":
        blockers.append("only_production_stage_can_advance")
    if not report.live or run.dry_run:
        blockers.append("live_generation_not_completed")
    if report.reviewed_count != len(run.assets):
        blockers.append("curation_incomplete")
    if report.keep_count != recipe.curation.target_count:
        blockers.append(
            f"keep_count_must_equal_target:{report.keep_count}!={recipe.curation.target_count}"
        )

    if blockers:
        report.status = "blocked"
        report.blockers = blockers
        report.next_action = "Resolve production blockers before running advance again."
        return _save_report(directory, report)

    qa_report = run_image_qa(directory)
    report.qa_fail_count = qa_report.fail_count
    if qa_report.fail_count:
        report.status = "blocked"
        report.blockers = ["qa_failures_present"]
        report.next_action = "Repair or replace QA-failed candidates before continuing."
        return _save_report(directory, report)

    refinement_report = refine_run(directory, force=force)
    report.normalized_count = refinement_report.normalized_count
    if refinement_report.failed_count or refinement_report.normalized_count != report.keep_count:
        report.status = "blocked"
        report.blockers = ["refinement_incomplete"]
        report.next_action = "Resolve refinement failures before packaging."
        return _save_report(directory, report)

    compile_product(directory, force=force)
    itch_report = compile_itch_ready_pack(directory, force=force)
    godot_report = build_godot_fixture(directory, force=force, godot_bin=godot_bin)

    report.status = "completed"
    report.blockers = []
    report.release_blockers = list(itch_report.blockers)
    report.godot_verification = godot_report.verification_status
    if itch_report.blockers:
        report.next_action = "Production proof completed. Resolve release blockers before public publishing."
    elif godot_bin is None:
        report.next_action = "Production proof completed. Re-run Godot fixture with --godot-bin for engine verification."
    elif godot_report.verification_status != "passed":
        report.next_action = "Production proof completed with Godot verification failure; inspect Godot evidence."
    else:
        report.next_action = "Production proof completed and engine verification passed. Human release review remains."
    return _save_report(directory, report)
