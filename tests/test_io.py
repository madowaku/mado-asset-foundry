from mado_asset_foundry.io import load_recipe, load_run


def test_load_recipe_fixture() -> None:
    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    assert recipe.id == "forest-alchemy-icons-v1"
    assert recipe.generation.candidate_count == 96


def test_load_run_fixture() -> None:
    run = load_run("fixtures/run-001.json")
    assert run.run_id == "run_001"
    assert len(run.assets) == 1
