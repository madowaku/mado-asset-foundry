"""Pixel Art Atlas M0.1 CLI: manual opt-in to network sampling."""
from __future__ import annotations

from pathlib import Path

import typer

from .pixel_atlas import make_subject_sheet, sample_from_huggingface

atlas_app = typer.Typer(help="Research-only 16x16 sprite atlas; never promotes assets to production")


@atlas_app.command("sample")
def sample(
    output: Path = typer.Option(Path("runs/pixel-atlas-m0-1"), "--output", help="Fresh output directory."),
    count: int = typer.Option(256, "--count", min=1, max=5000),
    split: str = typer.Option("train", "--split", help="train or validation"),
    revision: str = typer.Option("main", "--revision", help="Pin a HF commit SHA for reproducibility."),
    sheet_limit: int = typer.Option(64, "--sheet-limit", min=1, max=128),
    fetch: bool = typer.Option(False, "--fetch", help="Explicitly authorize streaming external dataset rows."),
) -> None:
    if not fetch:
        typer.echo("No network request made. Add --fetch to stream a bounded research sample.", err=True)
        raise typer.Exit(code=2)
    try:
        result = sample_from_huggingface(output, count=count, split=split, revision=revision, sheet_limit=sheet_limit)
    except (FileExistsError, FileNotFoundError, ValueError, RuntimeError, OSError) as exc:
        typer.echo(f"Atlas sampling failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Sampled: {result['sample_count']} sprites (requested: {count})")
    typer.echo(f"Subjects: {result['subjects_count']}; exact duplicate extras: {result['exact_duplicate_extra_rows']}")
    typer.echo(f"Bundle: {output}")
    typer.echo("Status: research only; rights review required; game export NOT approved")


@atlas_app.command("sheet")
def sheet(
    bundle_dir: Path = typer.Argument(..., help="Previously sampled Atlas directory."),
    subject: str = typer.Option(..., "--subject", help="Case-insensitive subject substring."),
    output: Path = typer.Option(..., "--output", help="New PNG path, never overwritten."),
    limit: int = typer.Option(64, "--limit", min=1, max=128),
) -> None:
    try:
        total = make_subject_sheet(bundle_dir, subject=subject, output_path=output, limit=limit)
    except (FileNotFoundError, FileExistsError, ValueError, OSError, KeyError) as exc:
        typer.echo(f"Atlas sheet failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(f"Subject matches: {total}")
    typer.echo(f"Sheet: {output}")
    typer.echo("Status: visual research only; not a release approval")
