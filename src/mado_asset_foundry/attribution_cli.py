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
