"""Read-only SRPG material coverage and provenance planning commands."""
from __future__ import annotations

import typer

from .srpg_planner import plan_srpg_assets

srpg_app = typer.Typer(help="Offline SRPG asset coverage and license-review planning")


@srpg_app.command("plan")
def plan(
    brief: str,
    registry: str | None = typer.Option(None, "--registry"),
    output: str = typer.Option("evidence/srpg-intelligence/plan.json", "--output"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    try:
        report, saved = plan_srpg_assets(
            brief, registry_path=registry, output_path=output, force=force
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        typer.echo(f"SRPG planning failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    typer.echo(f"Project: {report['project']}")
    typer.echo(f"Needed: {report['required_quantity']}")
    typer.echo("Ready: 0 (all candidates need provenance or production review)")
    for need in report["needs"]:
        typer.echo(f"- {need['need_id']}: {need['next_action']}")
    typer.echo(f"Evidence: {saved}")
    typer.echo("Assets copied: NO; publishing approved: NO")
