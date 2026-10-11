"""Offline ThreeJS Assets Studio bridge commands."""
from __future__ import annotations

import typer

from .threejs_studio import compile_worldplan, verify_studio_export

studio_app = typer.Typer(help="ThreeJS Assets Studio WorldPlan and export evidence (offline)")


@studio_app.command("compile")
def compile_cmd(
    plan: str,
    catalog: str | None = typer.Option(None, "--catalog", help="Operator-supplied catalog snapshot."),
    output_root: str = typer.Option("runs/threejs-studio", "--output-root"),
) -> None:
    try:
        result, folder = compile_worldplan(plan, catalog_path=catalog, output_root=output_root)
    except (OSError, ValueError) as exc:
        typer.echo(f"Studio WorldPlan compile failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"WorldPlan: {folder / 'worldplan.json'}")
    typer.echo(f"Candidates: {result['candidate_count']}/{result['placement_count']}")
    typer.echo("Studio seed: UNVERIFIED; release: BLOCKED")


@studio_app.command("verify-export")
def verify_export_cmd(
    run_dir: str,
    map_data: str = typer.Option(..., "--map-data"),
    glb: str = typer.Option(..., "--glb"),
    license_ledger: str | None = typer.Option(None, "--license-ledger"),
) -> None:
    try:
        result, output = verify_studio_export(
            run_dir, map_data=map_data, glb=glb, license_ledger=license_ledger
        )
    except (OSError, ValueError) as exc:
        typer.echo(f"Studio export verification failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Evidence: {output}")
    typer.echo(f"Status: {result['status']}")
    typer.echo("Godot runtime: UNVERIFIED; publication: BLOCKED")
    if result["status"] != "awaiting_godot_runtime_and_visual_qa":
        raise typer.Exit(code=2)
