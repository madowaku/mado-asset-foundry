"""Explicit operator-invoked Colab H3 archive commands."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from .colab_artifact_bridge import export_h3_bundle, import_h3_bundle, inspect_h3_bundle
from .colab_video_gate import probe_local_hardware

colab_app = typer.Typer(help="H3 Colab artifact export and verified local intake")


@colab_app.command("preflight")
def preflight(profile: str = typer.Option("int8", "--profile")) -> None:
    """Only observe local capacity. Never launch a GPU job."""
    try:
        report = probe_local_hardware(profile)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
    if report["status"] != "compatible_on_reported_capacity":
        raise typer.Exit(2)


@colab_app.command("export")
def export(
    video: Path = typer.Argument(..., help="Finished H3 video.mp4"),
    destination_dir: Path = typer.Option(..., "--dest", help="Existing explicit destination directory, e.g. a mounted Drive folder"),
    run_id: str = typer.Option(..., "--run-id", help="Immutable run identifier"),
    settings: Path | None = typer.Option(None, "--settings", help="Notebook settings.json"),
    profile: str = typer.Option("int8", "--profile"),
    staging_dir: Path | None = typer.Option(None, "--staging-dir", help="Local disk workspace for ZIP staging"),
) -> None:
    """Create one readback-verified ZIP; remote synchronization is not proven."""
    try:
        receipt = export_h3_bundle(video, destination_dir, run_id, settings=settings,
                                   profile=profile, staging_dir=staging_dir)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(f"H3 export blocked: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(receipt, indent=2, ensure_ascii=False))


@colab_app.command("inspect")
def inspect(archive: Path) -> None:
    """Verify archive members and all SHA-256 hashes."""
    try:
        report = inspect_h3_bundle(archive)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        typer.echo(f"H3 ZIP invalid: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


@colab_app.command("import")
def import_archive(
    archive: Path = typer.Argument(..., help="Exported *.h3.zip"),
    output_root: Path = typer.Option(Path("runs/h3-imports"), "--output-root"),
    ffprobe: str = typer.Option("ffprobe", "--ffprobe"),
) -> None:
    """Verify bytes and MP4 before creating a new MAF run directory."""
    try:
        report = import_h3_bundle(archive, output_root, ffprobe=ffprobe)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
        typer.echo(f"H3 import blocked: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
