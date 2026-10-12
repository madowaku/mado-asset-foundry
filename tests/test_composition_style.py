import json
from pathlib import Path

import pytest
from PIL import Image

from mado_asset_foundry.composition_style import build_run, compile_workflow, _url


@pytest.fixture
def project(tmp_path):
    image = tmp_path / "composition.png"
    Image.new("RGB", (32, 48), (100, 10, 30)).save(image)
    workflow = tmp_path / "api.json"
    workflow.write_text(json.dumps({
        "1": {"class_type": "LoadImage", "inputs": {"image": "old.png"}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 1, "denoise": .7}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}}
    }), encoding="utf-8")
    return image, workflow, tmp_path / "run"


def test_offline_evidence_and_no_mutation(project):
    image, workflow, run = project
    original = workflow.read_bytes()
    build_run(image, workflow, run, image_node="1", sampler_node="2",
              seeds=(7, 8), model_id="Anima local", model_license_review="review needed")
    evidence = json.loads((run / "evidence.json").read_text())
    assert evidence["stage"] == "prepared"
    assert evidence["publication_approved"] is False
    assert len(evidence["jobs"]) == 2
    compiled = json.loads((run / "workflows/seed-7.json").read_text())
    assert compiled["2"]["inputs"] == {"seed": 7, "denoise": .35}
    assert compiled["1"]["inputs"]["image"] == "maf-input.png"
    assert workflow.read_bytes() == original
    with pytest.raises(FileExistsError):
        build_run(image, workflow, run, image_node="1", sampler_node="2",
                  model_id="Anima", model_license_review="review")


@pytest.mark.parametrize("denoise", [-.1, 1.01])
def test_denoise_guard(project, denoise):
    image, workflow, run = project
    with pytest.raises(ValueError):
        build_run(image, workflow, run, image_node="1", sampler_node="2",
                  denoise=denoise, model_id="Anima", model_license_review="review")
    assert not run.exists()


def test_invalid_node_and_missing_save_image():
    with pytest.raises(ValueError):
        compile_workflow({"1": {"inputs": {"image": "foo"}}},
                         image_node="1", sampler_node="2",
                         input_name="x", denoise=.3, seed=1)


@pytest.mark.parametrize("server", [
    "http://example.com:8188", "https://127.0.0.1:8188",
    "http://127.0.0.1:8188/evil", "http://localhost:8188@evil.com",
])
def test_loopback_only(server):
    with pytest.raises(ValueError):
        _url(server, "/prompt")


def test_no_network_in_offline_mode(project, monkeypatch):
    import mado_asset_foundry.composition_style as bridge
    image, workflow, run = project
    monkeypatch.setattr(bridge, "_upload", lambda *a, **k: pytest.fail("network"))
    build_run(image, workflow, run, image_node="1", sampler_node="2",
              model_id="Anima", model_license_review="review")
