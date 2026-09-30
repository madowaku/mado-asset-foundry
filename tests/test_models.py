import pytest
from pydantic import ValidationError

from mado_asset_foundry.models import AssetRecipe


def valid_recipe() -> dict:
    return {
        "schema_version": "0.1",
        "id": "icons-v1",
        "name": "Icons",
        "asset_type": "icon",
        "theme": "forest",
        "style": "pixel_art",
        "output": {
            "width": 32,
            "height": 32,
            "format": "png",
            "transparent": True,
        },
        "generation": {
            "provider": "fixture",
            "model": "fixture",
            "candidate_count": 96,
        },
        "targets": ["generic"],
        "curation": {
            "target_count": 32,
            "criteria": ["readability"],
        },
    }


def test_recipe_accepts_valid_counts() -> None:
    recipe = AssetRecipe.model_validate(valid_recipe())
    assert recipe.curation.target_count == 32


def test_recipe_rejects_target_over_candidate_count() -> None:
    data = valid_recipe()
    data["curation"]["target_count"] = 97

    with pytest.raises(ValidationError):
        AssetRecipe.model_validate(data)
