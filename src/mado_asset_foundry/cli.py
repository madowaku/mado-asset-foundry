from __future__ import annotations

import typer

from .generation import generate_run
from .io import load_recipe, load_run

app = typer.Typer(help="MADO Asset Foundry")
recipe_app = typer.Typer(help="Asset recipe commands")
run_app = typer.Typer(help="Foundry run commands")
production_app = typer.Typer(help="Real production run commands")

app.add_typer(recipe_app, name="recipe")
app.add_typer(run_app, name="run")
app.add_typer(production_app, name="production")


@recipe_app.command("validate")
def validate_recipe(path: str) -> None:
    recipe = load_recipe(path)
    typer.echo("✓ Recipe valid")
    typer.echo(f"Asset Type: {recipe.asset_type}")
    typer.echo(f"Output: {recipe.output.width}x{recipe.output.height} {recipe.output.format.upper()}")
    typer.echo(f"Provider: {recipe.generation.provider}")
    typer.echo(f"Model: {recipe.generation.model}")
    typer.echo(f"Render: {recipe.generation.render_size} / {recipe.generation.quality}")
    typer.echo(
        f"Refine: padding={recipe.refinement.padding}px "
        f"palette={recipe.refinement.palette_colors or 'full'} "
        f"resample={recipe.refinement.resample}"
    )
    if recipe.product:
        typer.echo(
            f"Product: {recipe.product.product_id}@{recipe.product.version} "
            f"license={recipe.product.license_id} ({recipe.product.license_status})"
        )
    if recipe.itch:
        typer.echo(
            f"itch.io: visibility={recipe.itch.visibility} "
            f"classification={recipe.itch.classification} "
            f"upload_type={recipe.itch.upload_type}"
        )
    typer.echo(f"Target Count: {recipe.curation.target_count}")
    typer.echo(f"Candidate Count: {recipe.generation.candidate_count}")
    typer.echo("Targets:")
    for target in recipe.targets:
        typer.echo(f"- {target}")


@production_app.command("plan")
def production_plan(
    recipe_path: str = "fixtures/forest-alchemy-production.yaml",
) -> None:
    from .production import plan_production

    plan = plan_production(recipe_path)
    typer.echo(f"Recipe: {plan['recipe_id']}")
    typer.echo(f"Model: {plan['model']}")
    typer.echo(f"Probe: {plan['probe_count']}")
    typer.echo(f"Pilot: {plan['pilot_count']}")
    typer.echo(f"Production: {plan['production_count']}")
    typer.echo(f"Max live: {plan['max_live_count']}")
    typer.echo("No API request was made.")


@production_app.command("start")
def production_start(
    recipe_path: str = "fixtures/forest-alchemy-production.yaml",
    stage: str = typer.Option("probe", help="probe, pilot, or production"),
    live: bool = typer.Option(False, "--live", help="Actually call the configured image provider."),
    workspace: str = typer.Option("runs", help="Directory receiving production evidence."),
    run_id: str | None = typer.Option(None, help="Optional deterministic run id."),
) -> None:
    from .production import start_production

    try:
        report, run_dir = start_production(
            recipe_path,
            stage=stage,
            live=live,
            workspace=workspace,
            run_id=run_id,
        )
    except (ValueError, RuntimeError) as exc:
        typer.echo(f"Production start failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Run: {report.run_id}")
    typer.echo(f"Stage: {report.stage}")
    typer.echo(f"Requested: {report.requested_count}")
    typer.echo(f"Live: {'YES' if report.live else 'NO'}")
    typer.echo(f"Status: {report.status}")
    typer.echo(f"Evidence: {run_dir}")
    typer.echo(f"Next: {report.next_action}")


@production_app.command("status")
def production_status(run_dir: str) -> None:
    from .production import refresh_production_status

    report = refresh_production_status(run_dir)
    typer.echo(f"Run: {report.run_id}")
    typer.echo(f"Stage: {report.stage}")
    typer.echo(f"Status: {report.status}")
    typer.echo(f"Reviewed: {report.reviewed_count}/{report.requested_count}")
    typer.echo(f"KEEP: {report.keep_count}")
    if report.usage:
        typer.echo(f"Usage: {report.usage}")
    if report.blockers:
        typer.echo("Blockers:")
        for blocker in report.blockers:
            typer.echo(f"- {blocker}")
    typer.echo(f"Next: {report.next_action}")


@production_app.command("advance")
def production_advance(
    run_dir: str,
    force: bool = typer.Option(False, "--force", help="Rebuild downstream outputs when needed."),
    godot_bin: str | None = typer.Option(None, "--godot-bin", help="Optional Godot executable for real verification."),
) -> None:
    from .production import advance_production

    try:
        report = advance_production(run_dir, force=force, godot_bin=godot_bin)
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        typer.echo(f"Production advance failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Run: {report.run_id}")
    typer.echo(f"Status: {report.status}")
    typer.echo(f"KEEP: {report.keep_count}")
    typer.echo(f"QA FAIL: {report.qa_fail_count}")
    typer.echo(f"Normalized: {report.normalized_count}")
    typer.echo(f"Godot: {report.godot_verification}")
    if report.release_blockers:
        typer.echo("Release blockers:")
        for blocker in report.release_blockers:
            typer.echo(f"- {blocker}")
    if report.blockers:
        typer.echo("Blockers:")
        for blocker in report.blockers:
            typer.echo(f"- {blocker}")
    typer.echo(f"Next: {report.next_action}")
    if report.status == "blocked":
        raise typer.Exit(code=2)


@app.command("generate")
def generate(
    recipe_path: str,
    count: int = typer.Option(1, min=1, help="Number of candidates to generate; defaults to a safe live fixture of 1."),
    workspace: str = typer.Option("runs", help="Directory that receives Foundry run evidence."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Write the plan and run manifest without calling an image provider."),
    run_id: str | None = typer.Option(None, help="Optional deterministic run id for fixtures/tests."),
) -> None:
    recipe = load_recipe(recipe_path)
    run, run_dir = generate_run(recipe, workspace=workspace, count=count, dry_run=dry_run, run_id=run_id)
    typer.echo(f"Run: {run.run_id}")
    typer.echo(f"Provider: {run.provider}")
    typer.echo(f"Model: {run.model}")
    typer.echo(f"Requested: {run.requested_count}")
    typer.echo(f"Generated: {len(run.assets)}")
    typer.echo(f"Evidence: {run_dir}")
    if dry_run:
        typer.echo("Dry run: no API request was made.")


@app.command("curate")
def curate(
    workspace: str = typer.Option("runs", help="Workspace containing Foundry run directories."),
    host: str = typer.Option("127.0.0.1", help="Bind address. Use 0.0.0.0 only when network access is intentional."),
    port: int = typer.Option(4173, min=1, max=65535, help="Local Curator port."),
) -> None:
    from .curator import serve_curator

    typer.echo(f"Candidate Curator: http://{host}:{port}")
    typer.echo(f"Workspace: {workspace}")
    serve_curator(workspace, host=host, port=port)


@app.command("qa")
def qa(
    run_dir: str,
    near_duplicate_distance: int = typer.Option(
        4,
        min=0,
        max=64,
        help="Maximum dHash Hamming distance treated as a near duplicate.",
    ),
) -> None:
    from .qa import run_image_qa

    report = run_image_qa(run_dir, near_duplicate_distance=near_duplicate_distance)
    typer.echo(f"Run: {report.run_id}")
    typer.echo(f"Selected: {report.selected_count}")
    typer.echo(f"PASS: {report.pass_count}")
    typer.echo(f"WARN: {report.warn_count}")
    typer.echo(f"FAIL: {report.fail_count}")
    typer.echo(f"Evidence: {run_dir}/qa/report.json")
    if report.fail_count:
        raise typer.Exit(code=1)


@app.command("refine")
def refine(
    run_dir: str,
    force: bool = typer.Option(False, "--force", help="Replace existing normalized outputs."),
) -> None:
    from .refinement import refine_run

    report = refine_run(run_dir, force=force)
    typer.echo(f"Run: {report.run_id}")
    typer.echo(f"Selected: {report.selected_count}")
    typer.echo(f"Eligible: {report.eligible_count}")
    typer.echo(f"NORMALIZED: {report.normalized_count}")
    typer.echo(f"FAILED: {report.failed_count}")
    typer.echo(f"SKIPPED: {report.skipped_count}")
    typer.echo(f"Evidence: {run_dir}/refinement/report.json")
    if report.failed_count:
        raise typer.Exit(code=1)


@app.command("package")
def package(
    run_dir: str,
    force: bool = typer.Option(False, "--force", help="Replace an existing compiled product."),
) -> None:
    from .packaging import compile_product

    try:
        report = compile_product(run_dir, force=force)
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        typer.echo(f"Package failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Product: {report.product_id}@{report.version}")
    typer.echo(f"Assets: {report.asset_count}")
    typer.echo(f"Product dir: {report.product_dir}")
    typer.echo(f"ZIP: {report.zip_path}")
    typer.echo(f"ZIP SHA-256: {report.zip_sha256}")
    typer.echo(f"Evidence: {run_dir}/packaging/report.json")


@app.command("godot-fixture")
def godot_fixture(
    run_dir: str,
    force: bool = typer.Option(False, "--force", help="Replace an existing Godot dogfood fixture."),
    godot_bin: str | None = typer.Option(
        None,
        "--godot-bin",
        help="Optional Godot executable/path. When supplied, run headless import + verifier.",
    ),
) -> None:
    from .godot_fixture import build_godot_fixture

    try:
        report = build_godot_fixture(run_dir, force=force, godot_bin=godot_bin)
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        typer.echo(f"Godot fixture failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Product: {report.product_id}@{report.version}")
    typer.echo(f"Assets: {report.asset_count}")
    typer.echo(f"Fixture: {report.fixture_dir}")
    typer.echo(f"Verification: {report.verification_status}")
    if report.godot_version:
        typer.echo(f"Godot: {report.godot_version}")
    if report.import_report_path:
        typer.echo(f"Evidence: {report.import_report_path}")
    if godot_bin and report.verification_status != "passed":
        raise typer.Exit(code=1)


@app.command("itch-ready")
def itch_ready(
    run_dir: str,
    force: bool = typer.Option(False, "--force", help="Replace an existing itch.io ready pack."),
) -> None:
    from .itch_ready import compile_itch_ready_pack

    try:
        report = compile_itch_ready_pack(run_dir, force=force)
    except (ValueError, FileExistsError, FileNotFoundError) as exc:
        typer.echo(f"itch.io ready pack failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Product: {report.product_id}@{report.version}")
    typer.echo(f"Ready: {'YES' if report.ready else 'NO'}")
    typer.echo(f"Release dir: {report.release_dir}")
    typer.echo(f"Upload ZIP: {report.upload_zip}")
    if report.blockers:
        typer.echo("Blockers:")
        for blocker in report.blockers:
            typer.echo(f"- {blocker}")
    if report.warnings:
        typer.echo("Warnings:")
        for warning in report.warnings:
            typer.echo(f"- {warning}")
    if not report.ready:
        raise typer.Exit(code=2)


@run_app.command("inspect")
def inspect_run(path: str) -> None:
    run = load_run(path)
    typer.echo(f"Run: {run.run_id}")
    typer.echo(f"Recipe: {run.recipe_id}")
    typer.echo(f"Provider: {run.provider}")
    typer.echo(f"Model: {run.model}")
    typer.echo(f"Requested: {run.requested_count}")
    typer.echo(f"Assets: {len(run.assets)}")


if __name__ == "__main__":
    app()
