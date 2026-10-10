"""M1.0-CAV CLI, deliberately separate from existing license gates."""
from __future__ import annotations

import json
from pathlib import Path

import typer

from .cloud_vault import VaultError, materialize

vault_app = typer.Typer(help="Verified local/Git-LFS cloud asset vault")


@vault_app.command("materialize")
def materialize_command(
    manifest: Path = typer.Argument(..., help="Vault manifest JSON located beside checked-out assets."),
    destination: Path = typer.Option(..., "--dest", help="New, non-existing destination directory."),
    asset_id: list[str] | None = typer.Option(None, "--asset-id", help="Repeat to select only needed assets."),
) -> None:
    try:
        report = materialize(manifest, destination, asset_ids=asset_id or None)
    except (VaultError, FileNotFoundError, FileExistsError, OSError, ValueError) as exc:
        typer.echo(f"Vault blocked: {exc}", err=True)
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))
