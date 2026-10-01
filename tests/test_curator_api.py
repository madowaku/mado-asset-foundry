from pathlib import Path

from fastapi.testclient import TestClient

from mado_asset_foundry.curator import create_app
from mado_asset_foundry.io import write_json
from mado_asset_foundry.models import AssetRecord, FoundryRun


def make_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "runs"
    run_dir = workspace / "run_001"
    (run_dir / "raw").mkdir(parents=True)
    (run_dir / "metadata").mkdir()
    (run_dir / "raw" / "asset_0001.png").write_bytes(b"fake-png")
    run = FoundryRun(
        run_id="run_001",
        recipe_id="recipe",
        provider="fixture",
        model="fixture",
        requested_count=1,
        assets=[AssetRecord(asset_id="asset_0001", recipe_id="recipe", provider="fixture", model="fixture", subject="potion")],
    )
    write_json(run_dir / "run.json", run.model_dump(mode="json"))
    return workspace


def test_curator_lists_runs_and_updates_asset(tmp_path: Path) -> None:
    client = TestClient(create_app(make_workspace(tmp_path)))
    runs = client.get("/api/runs")
    assert runs.status_code == 200
    assert runs.json()["runs"][0]["run_id"] == "run_001"

    changed = client.patch("/api/runs/run_001/assets/asset_0001", json={"decision": "keep", "favorite": True})
    assert changed.status_code == 200
    assert changed.json()["asset"]["curation_decision"] == "keep"
    assert changed.json()["asset"]["favorite"] is True


def test_curator_serves_asset_image_and_ui(tmp_path: Path) -> None:
    client = TestClient(create_app(make_workspace(tmp_path)))
    assert client.get("/").status_code == 200
    image = client.get("/api/runs/run_001/assets/asset_0001/image")
    assert image.status_code == 200
    assert image.content == b"fake-png"
