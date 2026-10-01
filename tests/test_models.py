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
        "subjects": ["potion"],
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
            "batch_size": 4,
            "render_size": "1024x1024",
            "quality": "low",
            "background": "transparent",
            "output_format": "png",
        },
        "targets": ["generic"],
        "curation": {
            "target_count": 32,
            "criteria": ["readability"],
        },
        "refinement": {
            "alpha_threshold": 8,
            "padding": 2,
            "palette_colors": 16,
            "resample": "lanczos",
            "dither": False,
        },
    }


def test_recipe_accepts_valid_counts() -> None:
    recipe = AssetRecipe.model_validate(valid_recipe())
    assert recipe.curation.target_count == 32
    assert recipe.refinement.palette_colors == 16


def test_recipe_rejects_target_over_candidate_count() -> None:
    data = valid_recipe()
    data["curation"]["target_count"] = 97
    with pytest.raises(ValidationError):
        AssetRecipe.model_validate(data)


def test_recipe_rejects_transparent_jpeg() -> None:
    data = valid_recipe()
    data["generation"]["output_format"] = "jpeg"
    with pytest.raises(ValidationError):
        AssetRecipe.model_validate(data)


def test_recipe_rejects_padding_that_consumes_output() -> None:
    data = valid_recipe()
    data["refinement"]["padding"] = 16
    with pytest.raises(ValidationError):
        AssetRecipe.model_validate(data)
