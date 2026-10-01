from __future__ import annotations

import json
from pathlib import Path

import yaml

from .models import AssetRecipe, FoundryRun


def load_recipe(path: str | Path) -> AssetRecipe:
    source = Path(path)
    data = yaml.safe_load(source.read_text(encoding="utf-8"))
    return AssetRecipe.model_validate(data)


def load_run(path: str | Path) -> FoundryRun:
    source = Path(path)
    data = json.loads(source.read_text(encoding="utf-8"))
    return FoundryRun.model_validate(data)


def write_json(path: str | Path, data: object) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def write_recipe_snapshot(path: str | Path, recipe: AssetRecipe) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        yaml.safe_dump(recipe.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
