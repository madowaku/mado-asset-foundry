"""MAF-M0.9.4 one-command asset production flow CLI."""
from __future__ import annotations

import typer

from .asset_flow import inspect_asset_flow, review_asset_flow, run_asset_flow


flow_app = typer.Typer(help="End-to-end intake, Godot QA, visual preview, and human review")


@flow_app.command("run")
def run(
    recipe: str,
    godot_bin: str = typer.Option(..., "--godot-bin", help="Operator-supplied Godot 4.2+."),
    workspace: str = typer.Option("runs/asset-flows", "--workspace"),
    virtual_display: bool = typer.Option(False, "--virtual-display", help="Use Xvfb when no display exists."),
    timeout: int = typer.Option(120, "--timeout", min=1, max=600),
    force: bool = typer.Option(False, "--force"),
) -> None:
    try:
        summary, path = run_asset_flow(
            recipe, godot_bin=godot_bin, workspace=workspace,
            virtual_display=virtual_display, timeout=timeout, force=force,
        )
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        typer.echo(f"Asset flow failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Flow: {summary['flow_id']}")
    typer.echo(f"Assets: {summary['source_count']}")
    typer.echo(f"Status: {summary['status']}")
    typer.echo(f"Godot: {summary['godot_version']}")
    typer.echo(f"Gallery: {path / summary['output_paths']['screenshot']}")
    typer.echo(f"Credits: {path / summary['output_paths']['credits']}")
    typer.echo(f"Summary: {path / 'summary.json'}")
    typer.echo("Human review required. Publication approved: NO")


@flow_app.command("inspect")
def inspect(run_dir: str) -> None:
    try:
        status = inspect_asset_flow(run_dir)
    except (ValueError, FileNotFoundError, OSError) as exc:
        typer.echo(f"Asset flow inspection failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Flow: {status['flow_id']}")
    typer.echo(f"Status: {status['status']}")
    typer.echo(f"Review: {status['review_status']}")
    typer.echo(f"Gallery: {status['output_paths']['screenshot']}")
    typer.echo("Publication approved: NO")


@flow_app.command("review")
def review(
    run_dir: str,
    attestation: str = typer.Option(..., "--review", help="Human review JSON bound to output hashes."),
    force: bool = typer.Option(False, "--force"),
) -> None:
    try:
        gate, evidence = review_asset_flow(run_dir, review_path=attestation, force=force)
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as exc:
        typer.echo(f"Asset flow review failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Status: {gate['status']}")
    typer.echo(f"Reviewer: {gate['reviewer']}")
    typer.echo(f"Evidence: {evidence}")
    typer.echo("Publication approved: NO")
    for reason in gate["reasons"]:
        typer.echo(f"- {reason}")
    if gate["status"] != "human_release_review_passed":
        raise typer.Exit(code=2)
