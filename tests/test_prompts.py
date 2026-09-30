from mado_asset_foundry.io import load_recipe
from mado_asset_foundry.prompts import plan_generation


def test_plan_chunks_to_provider_batch_size() -> None:
    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    plan = plan_generation(recipe, count=10)
    assert [batch.count for batch in plan] == [4, 4, 2]
    assert "red healing potion" in plan[0].prompt
    assert "blue mana potion" in plan[1].prompt


def test_plan_rejects_count_over_recipe_limit() -> None:
    recipe = load_recipe("fixtures/forest-alchemy.yaml")
    try:
        plan_generation(recipe, count=97)
    except ValueError as exc:
        assert "candidate_count" in str(exc)
    else:
        raise AssertionError("expected ValueError")
