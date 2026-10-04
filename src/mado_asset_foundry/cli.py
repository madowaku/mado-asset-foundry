from __future__ import annotations

import typer

from .generation import generate_run
from .io import load_recipe, load_run

app = typer.Typer(help="MADO Asset Foundry")
recipe_app = typer.Typer(help="Asset recipe commands")
run_app = typer.Typer(help="Foundry run commands")
production_app = typer.Typer(help="Real production run commands")
skill_app = typer.Typer(help="OSS asset Skill intake commands")
skill_registry_app = typer.Typer(help="Build and inspect the local Skill registry")

app.add_typer(recipe_app, name="recipe")
app.add_typer(run_app, name="run")
app.add_typer(production_app, name="production")
app.add_typer(skill_app, name="skill")
skill_app.add_typer(skill_registry_app, name="registry")



@skill_registry_app.command("build")
def skill_registry_build(
    manifest_dir: str = typer.Argument("skills/manifests"),
    output: str = typer.Option("skills/registry.json", help="Registry JSON output path."),
    force: bool = typer.Option(False, "--force", help="Replace an existing registry."),
) -> None:
    from .skills.registry import build_registry

    try:
        registry, output_path = build_registry(
            manifest_dir,
            output_path=output,
            force=force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        typer.echo(f"Skill registry build failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Skills: {len(registry.entries)}")
    typer.echo(f"Registry: {output_path}")


@skill_app.command("list")
def skill_list(
    registry_path: str = typer.Option("skills/registry.json", "--registry"),
) -> None:
    from .skills.registry import load_registry

    try:
        registry = load_registry(registry_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Skill registry load failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if not registry.entries:
        typer.echo("No Skills registered.")
        return
    for entry in registry.entries:
        capabilities = ",".join(entry.capabilities) if entry.capabilities else "-"
        typer.echo(
            f"{entry.skill_id} | {entry.adapter_status} | "
            f"capabilities={capabilities}"
        )


@skill_app.command("show")
def skill_show(
    skill_id: str,
    registry_path: str = typer.Option("skills/registry.json", "--registry"),
) -> None:
    from .skills.registry import get_registry_entry, load_registry

    try:
        registry = load_registry(registry_path)
        entry = get_registry_entry(registry, skill_id)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Skill registry load failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    except KeyError as exc:
        typer.echo(f"Skill not found: {skill_id}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Skill: {entry.skill_id}")
    typer.echo(f"Name: {entry.name}")
    typer.echo(f"Adapter: {entry.adapter_status}")
    typer.echo(f"License: {entry.license.spdx or entry.license.status}")
    typer.echo(f"Runtime: {', '.join(entry.runtime) if entry.runtime else 'none'}")
    typer.echo(
        f"Capabilities: {', '.join(entry.capabilities) if entry.capabilities else 'none'}"
    )
    typer.echo(f"Manifest: {entry.manifest_path}")


@skill_app.command("resolve")
def skill_resolve(
    capability: str,
    registry_path: str = typer.Option("skills/registry.json", "--registry"),
) -> None:
    from .skills.registry import load_registry, resolve_capability

    try:
        registry = load_registry(registry_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Skill registry load failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    resolution = resolve_capability(registry, capability)
    typer.echo(f"Capability: {capability}")
    typer.echo(f"Status: {resolution.status}")
    if resolution.selected_skill_id:
        typer.echo(f"Resolved: {resolution.selected_skill_id}")
    if resolution.candidates:
        typer.echo("Candidates:")
        for candidate in resolution.candidates:
            typer.echo(
                f"- {candidate.skill_id} | {candidate.adapter_status} | "
                f"license={candidate.license_spdx or candidate.license_name or candidate.license_status}"
            )
    else:
        typer.echo("Candidates: none")

@skill_app.command("intake")
def skill_intake(
    path: str,
    manifest_dir: str = typer.Option("skills/manifests", help="Directory receiving normalized Skill manifests."),
    evidence_dir: str = typer.Option("evidence/skill-intake", help="Directory receiving read-only intake evidence."),
    force: bool = typer.Option(False, "--force", help="Replace an existing manifest/evidence report."),
) -> None:
    from .skills.intake import intake_skill

    try:
        manifest, manifest_path, report_path = intake_skill(
            path,
            manifest_dir=manifest_dir,
            evidence_dir=evidence_dir,
            force=force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        typer.echo(f"Skill intake failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Skill: {manifest.skill_id}")
    typer.echo(f"Name: {manifest.name}")
    typer.echo(f"Adapter: {manifest.adapter_status}")
    typer.echo(f"SKILL.md: {manifest.entrypoints.skill_md or 'not found'}")
    typer.echo(f"README: {manifest.entrypoints.readme or 'not found'}")
    typer.echo(f"License: {manifest.license.status}")
    typer.echo("Capabilities: pending M0.8.2b scanner")
    typer.echo(f"Manifest: {manifest_path}")
    typer.echo(f"Evidence: {report_path}")
    typer.echo("External code executed: NO")


@skill_app.command("scan")
def skill_scan(
    path: str,
    manifest_dir: str = typer.Option("skills/manifests", help="Directory receiving classified Skill manifests."),
    evidence_dir: str = typer.Option("evidence/skill-scan", help="Directory receiving capability-scan evidence."),
    force: bool = typer.Option(False, "--force", help="Replace an existing classified manifest/evidence report."),
) -> None:
    from .skills.scanner import scan_skill

    try:
        manifest, manifest_path, report_path = scan_skill(
            path,
            manifest_dir=manifest_dir,
            evidence_dir=evidence_dir,
            force=force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        typer.echo(f"Skill scan failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Skill: {manifest.skill_id}")
    typer.echo(f"Adapter: {manifest.adapter_status}")
    typer.echo(f"Capabilities: {', '.join(manifest.capabilities) if manifest.capabilities else 'none detected'}")
    typer.echo(f"Runtime: {', '.join(manifest.runtime) if manifest.runtime else 'none detected'}")
    typer.echo(
        f"License: {manifest.license.spdx or manifest.license.status}"
    )
    typer.echo(f"Inputs: {', '.join(manifest.inputs) if manifest.inputs else 'none'}")
    typer.echo(f"Outputs: {', '.join(manifest.outputs) if manifest.outputs else 'none'}")
    typer.echo(f"Manifest: {manifest_path}")
    typer.echo(f"Evidence: {report_path}")
    typer.echo("External code executed: NO")


@skill_app.command("scan-pack")
def skill_scan_pack(
    path: str,
    manifest_dir: str = typer.Option("skills/manifests", help="Directory receiving classified member manifests."),
    evidence_dir: str = typer.Option("evidence/skill-pack-scan", help="Directory receiving pack and member evidence."),
    force: bool = typer.Option(False, "--force", help="Replace existing pack/member scan outputs."),
) -> None:
    from .skills.pack import scan_skill_pack

    try:
        report, report_path = scan_skill_pack(
            path,
            manifest_dir=manifest_dir,
            evidence_dir=evidence_dir,
            force=force,
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        typer.echo(f"Skill pack scan failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Pack: {report.pack_id}")
    typer.echo(f"Skills discovered: {len(report.discovered_skills)}")
    typer.echo(
        f"Adapter candidates: {', '.join(report.candidate_skills) if report.candidate_skills else 'none'}"
    )
    typer.echo(
        f"CLI: {', '.join(item.name for item in report.cli_entrypoints) if report.cli_entrypoints else 'none'}"
    )
    typer.echo(
        f"MCP: {', '.join(item.name for item in report.mcp_servers) if report.mcp_servers else 'none'}"
    )
    typer.echo(f"Safety constraints: {len(report.safety_constraints)}")
    typer.echo(f"Evidence: {report_path}")
    typer.echo("External code executed: NO")


@skill_app.command("validate")
def skill_validate(manifest_path: str) -> None:
    from .skills.intake import load_skill_manifest

    try:
        manifest = load_skill_manifest(manifest_path)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Skill manifest invalid: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo("✓ Skill manifest valid")
    typer.echo(f"Skill: {manifest.skill_id}")
    typer.echo(f"Adapter: {manifest.adapter_status}")
    typer.echo(f"Capabilities: {len(manifest.capabilities)}")


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


@app.command("codex-imagegen-check")
def codex_imagegen_check(
    codex_model: str = typer.Option("gpt-6-luna", help="Codex orchestration model."),
    codex_binary: str = typer.Option("codex", help="Codex executable or path."),
) -> None:
    from .providers.codex_imagegen import CodexImageGenProvider

    try:
        info = CodexImageGenProvider(
            codex_model=codex_model,
            codex_binary=codex_binary,
        ).check_installation()
    except (FileNotFoundError, RuntimeError) as exc:
        typer.echo(f"Codex ImageGen check failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Codex: {info['version']}")
    typer.echo(f"Binary: {info['binary']}")
    typer.echo(f"Orchestrator: {info['codex_model']}")
    typer.echo(f"Image model: {info['image_model']}")
    typer.echo("No image was generated.")


@production_app.command("plan")
def production_plan(
    recipe_path: str = "fixtures/forest-alchemy-production.yaml",
) -> None:
    from .production import plan_production

    plan = plan_production(recipe_path)
    typer.echo(f"Recipe: {plan['recipe_id']}")
    typer.echo(f"Provider: {plan['provider']}")
    typer.echo(f"Image model: {plan['model']}")
    if plan.get("codex_model"):
        typer.echo(f"Codex orchestrator: {plan['codex_model']}")
    typer.echo(f"Probe: {plan['probe_count']}")
    typer.echo(f"Pilot: {plan['pilot_count']}")
    typer.echo(f"Production: {plan['production_count']}")
    typer.echo(f"Max live: {plan['max_live_count']}")
    typer.echo("No image-generation request was made.")
    if plan["usage_scope"] == "codex_general_usage":
        typer.echo("Real generation uses built-in Codex ImageGen and counts toward general Codex usage limits.")
    else:
        typer.echo("Real generation uses separately billed OpenAI API usage.")


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
    except (ValueError, RuntimeError, FileExistsError, FileNotFoundError) as exc:
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
