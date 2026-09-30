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
