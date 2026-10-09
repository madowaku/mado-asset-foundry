"""MAF-M0.9.1 Godot import compiler CLI."""
from __future__ import annotations

import typer

from .attribution_bridge import compile_godot_import

bridge_app = typer.Typer(help="Compile attribution and a Godot project from eligible asset evidence")


@bridge_app.command("compile")
def compile_bridge(
    plan: str,
    output_root: str = typer.Option("runs/asset-godot", "--output-root"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    try:
        report, project = compile_godot_import(plan, output_root=output_root, force=force)
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        typer.echo(f"Godot asset bridge failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Project: {project}")
    typer.echo(f"Assets: {report['asset_count']}")
    typer.echo(f"Credits: {project / 'CREDITS.md'}")
    typer.echo("Godot executed: NO; published: NO")


@bridge_app.command("qa")
def runtime_qa(
    plan: str,
    project: str,
    godot_bin: str = typer.Option(..., "--godot-bin", help="Godot 4.2+ executable, explicitly supplied."),
    output_root: str = typer.Option("evidence/asset-godot-runtime", "--output-root"),
    force: bool = typer.Option(False, "--force"),
    timeout: int = typer.Option(120, "--timeout", min=1, max=600),
) -> None:
    from .runtime_import_qa import verify_godot_import

    try:
        report, evidence = verify_godot_import(
            plan, project, godot_bin=godot_bin, output_root=output_root,
            force=force, timeout=timeout,
        )
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        typer.echo(f"Godot import QA blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Project: {report['project_id']}")
    typer.echo(f"Status: {report['status']}")
    typer.echo(f"License evidence gate: {report['license_evidence_gate']}")
    typer.echo(f"Input integrity gate: {report['input_integrity_gate']}")
    typer.echo(f"Godot version: {report['godot_version']}")
    typer.echo(f"Textures: {report['loaded_count']}/{report['asset_count']}")
    typer.echo(f"Evidence: {evidence / 'report.json'}")
    typer.echo("Release approved: NO")
    if report["failure_reason"]:
        typer.echo(f"Failure: {report['failure_reason']}")
    if report["status"] != "passed":
        raise typer.Exit(code=2)


@bridge_app.command("gallery")
def visual_gallery(
    plan: str,
    project: str,
    godot_bin: str = typer.Option(..., "--godot-bin"),
    output_root: str = typer.Option("evidence/asset-gallery", "--output-root"),
    virtual_display: bool = typer.Option(False, "--virtual-display", help="Use xvfb-run for Linux CI/servers."),
    force: bool = typer.Option(False, "--force"),
    timeout: int = typer.Option(120, "--timeout", min=1, max=600),
) -> None:
    from .visual_gallery import render_gallery

    try:
        report, evidence = render_gallery(
            plan, project, godot_bin=godot_bin, output_root=output_root,
            virtual_display=virtual_display, force=force, timeout=timeout,
        )
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        typer.echo(f"Visual gallery blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Gallery: {evidence}")
    typer.echo(f"Status: {report['status']}")
    typer.echo(f"Screenshot: {evidence / 'gallery.png' if report['status'] == 'captured' else 'none'}")
    typer.echo("Visual and attribution review required; publication approved: NO")
    if report["failure_reason"]:
        typer.echo(f"Failure: {report['failure_reason']}")
    if report["status"] != "captured":
        raise typer.Exit(code=2)


@bridge_app.command("release-check")
def release_check(
    plan: str,
    project: str,
    gallery: str,
    review: str | None = typer.Option(None, "--review", help="Human-signed review JSON."),
    output: str | None = typer.Option(None, "--output", help="Optional review-gate JSON report."),
    force: bool = typer.Option(False, "--force"),
) -> None:
    from .visual_gallery import review_release

    try:
        report, path = review_release(
            plan, project, gallery, review_path=review, output_path=output, force=force,
        )
    except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
        typer.echo(f"Attribution release gate blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Status: {report['status']}")
    typer.echo(f"Release review: {report['reviewer'] or 'not submitted'}")
    typer.echo(f"Publication approved: NO")
    for reason in report["reasons"]:
        typer.echo(f"- {reason}")
    if path:
        typer.echo(f"Evidence: {path}")
    if report["status"] != "human_release_review_passed":
        raise typer.Exit(code=2)
