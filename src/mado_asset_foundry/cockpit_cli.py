"""Local-only Asset Foundry Cockpit server CLI."""
from __future__ import annotations

import typer

cockpit_app = typer.Typer(help="Local browser cockpit for licensed Godot asset flows")


@cockpit_app.command("serve")
def serve(
    workspace: str = typer.Option("runs/asset-flows", "--workspace"),
    recipes: str = typer.Option("recipes/asset-flows", "--recipes"),
    godot_bin: str | None = typer.Option(None, "--godot-bin"),
    virtual_display: bool = typer.Option(False, "--virtual-display"),
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(4174, "--port", min=1, max=65535),
) -> None:
    from .cockpit import serve_cockpit

    try:
        serve_cockpit(workspace, recipes=recipes, godot_bin=godot_bin,
                      virtual_display=virtual_display, host=host, port=port)
    except ValueError as exc:
        typer.echo(f"Cockpit refused to start: {exc}", err=True)
        raise typer.Exit(code=1) from exc
