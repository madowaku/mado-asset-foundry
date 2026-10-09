"""Typer interface for MAF-M0.9 offline asset source intake."""
from __future__ import annotations

import typer

from .asset_sources import get_source, intake_asset, load_source_registry

asset_source_app = typer.Typer(help="Offline asset source registry and license-aware intake")


@asset_source_app.command("list")
def list_sources(
    registry: str | None = typer.Option(None, "--registry", help="Optional source registry JSON."),
) -> None:
    try:
        sources = load_source_registry(registry)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Asset source registry failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    for source in sorted(sources.sources, key=lambda item: item.source_id):
        typer.echo(f"{source.source_id} | {source.discovery_mode} | {source.name} | {source.homepage}")


@asset_source_app.command("show")
def show_source(
    source_id: str,
    registry: str | None = typer.Option(None, "--registry"),
) -> None:
    try:
        source = get_source(load_source_registry(registry), source_id)
    except (FileNotFoundError, ValueError) as exc:
        typer.echo(f"Asset source lookup failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Source: {source.source_id}")
    typer.echo(f"Homepage: {source.homepage}")
    typer.echo(f"Discovery: {source.discovery_mode}")
    typer.echo(f"License hint (not permission): {source.license_hint}")
    typer.echo(f"Redistribution: {source.redistribution_policy}")
    typer.echo(f"Notes: {source.notes}")


@asset_source_app.command("intake")
def intake(
    submission: str,
    registry: str | None = typer.Option(None, "--registry"),
    output_root: str = typer.Option("evidence/asset-intake", "--output-root"),
    force: bool = typer.Option(False, "--force"),
) -> None:
    try:
        report, report_path = intake_asset(
            submission, registry_path=registry, output_root=output_root, force=force
        )
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        typer.echo(f"Asset intake failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Asset: {report['asset_id']}")
    typer.echo(f"Source: {report['source_id']}")
    typer.echo(f"Status: {report['status']}")
    typer.echo(f"SHA-256: {report['sha256']}")
    typer.echo(f"Evidence: {report_path}")
    typer.echo("Network accessed: NO; publishing approved: NO")
    for reason in report["reasons"]:
        typer.echo(f"- {reason}")
    if report["status"] != "eligible":
        raise typer.Exit(code=2)
