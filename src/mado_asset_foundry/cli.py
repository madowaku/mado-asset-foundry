from __future__ import annotations

import typer

from .io import load_recipe, load_run

app = typer.Typer(help="MADO Asset Foundry")
recipe_app = typer.Typer(help="Asset recipe commands")
run_app = typer.Typer(help="Foundry run commands")

app.add_typer(recipe_app, name="recipe")
app.add_typer(run_app, name="run")


@recipe_app.command("validate")
def validate_recipe(path: str) -> None:
    recipe = load_recipe(path)
    typer.echo("✓ Recipe valid")
    typer.echo(f"Asset Type: {recipe.asset_type}")
    typer.echo(f"Output: {recipe.output.width}x{recipe.output.height} {recipe.output.format.upper()}")
    typer.echo(f"Target Count: {recipe.curation.target_count}")
    typer.echo(f"Candidate Count: {recipe.generation.candidate_count}")
    typer.echo("Targets:")
    for target in recipe.targets:
        typer.echo(f"- {target}")


@run_app.command("inspect")
def inspect_run(path: str) -> None:
    run = load_run(path)
    typer.echo(f"Run: {run.run_id}")
    typer.echo(f"Recipe: {run.recipe_id}")
    typer.echo(f"Assets: {len(run.assets)}")


if __name__ == "__main__":
    app()
