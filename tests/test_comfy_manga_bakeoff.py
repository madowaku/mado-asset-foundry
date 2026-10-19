import io
import json
from pathlib import Path

import pytest
from PIL import Image

from mado_asset_foundry.comfy_manga_bakeoff import (
    ComfyClient, build_gallery, fetch_single_output, load_plan, patch_workflow,
    run_plan, create_scorecard, validate_scorecard,
)
from mado_asset_foundry.moss_bakeoff import MODELS


def workflow(model):
    nodes = {
        "1": {"class_type": "MOSSImageHFLoader" if model != "anima" else "CheckpointLoaderSimple",
              "inputs": {"model_path": "local", "ckpt_name": "dummy"}},
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "placeholder", "clip": ["1", 1]}},
        "6": {"class_type": "EmptyFlux2LatentImage", "inputs": {"width": 512, "height": 512}},
        "16": {"class_type": "KSampler", "inputs": {"seed": 12, "model": ["1", 0]}},
        "18": {"class_type": "SaveImage", "inputs": {"images": ["16", 0], "filename_prefix": "test"}},
    }
    if model == "moss-sft-lora":
        nodes["11"] = {"class_type": "LoraLoader", "inputs": {"lora_name": "operator.safetensors",
                     "model": ["1", 0]}}
        nodes["16"]["inputs"]["model"] = ["11", 0]
    return nodes


def make_plan(tmp_path, *, layout=False):
    arms = {}
    for model in MODELS:
        (tmp_path / (model + ".json")).write_text(json.dumps(workflow(model)), encoding="utf-8")
        arms[model] = {
            "workflow": model + ".json",
            "bindings": {"positive": ["4", "text"], "seed": ["16", "seed"],
                         "width": ["6", "width"], "height": ["6", "height"]},
            "save_node": "18", "overrides": {"1": {"model_path": model}},
        }
    case = {"id": "manga", "prompt": "漫画の表紙", "seed": 42, "width": 64, "height": 64}
    if layout:
        case["moss_layout"] = {"width": 64, "height": 64, "caption": "漫画の表紙",
            "items": [{"label": "text", "caption": "top title", "text": "星",
                       "bbox_xyxy": [1, 1, 32, 48]}]}
    plan = {"arms": arms, "cases": [case]}
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    return path


class FakeComfy:
    def __init__(self):
        img = Image.new("RGB", (64, 64), "blue")
        stream = io.BytesIO()
        img.save(stream, format="PNG")
        self.png = stream.getvalue()
        self.prompts = {}
        self.num = 0

    def json(self, method, route, payload=None):
        if route == "/system_stats":
            return {"devices": [{"name": "mock GPU"}]}
        if route == "/object_info":
            return {name: {} for model in MODELS for name in [x["class_type"] for x in workflow(model).values()]}
        if route == "/prompt":
            self.num += 1
            pid = "id" + str(self.num)
            self.prompts[pid] = payload["prompt"]
            return {"prompt_id": pid}
        if route.startswith("/history/"):
            pid = route.split("/")[-1]
            return {pid: {"status": {"status_str": "success", "completed": True},
                   "outputs": {"18": {"images": [{"type": "output", "filename": "mock.png", "subfolder": ""}]}}}}
        raise AssertionError(route)

    def request(self, method, route, payload=None, limit=None):
        assert method == "GET" and route.startswith("/view?")
        return self.png


def test_localhost_only():
    for url in ("http://evil.example:8188", "https://127.0.0.1:8188", 
                "http://127.0.0.1:8188@evil.example:8188", "http://localhost:8188"):
        with pytest.raises(ValueError):
            ComfyClient(url)
    assert ComfyClient("http://127.0.0.1:8188").url.endswith("8188")


def test_real_pipeline_with_fake_comfy_and_gallery(tmp_path):
    path = make_plan(tmp_path, layout=True)
    plan, workflows, _ = load_plan(path)
    patched = patch_workflow(workflows["moss-base"], plan["arms"]["moss-base"],
                             plan["cases"][0], "moss-base")
    assert "bbox_format" in patched["4"]["inputs"]["text"]
    fake = FakeComfy()
    output = tmp_path / "run"
    result = run_plan(path, output, fake, poll_seconds=0)
    assert result["status"] == "awaiting_human_review"
    assert not result["quality_approved"] and not result["rights_approved"]
    assert fake.num == 4
    assert len(list((output / "images").glob("*.png"))) == 4
    gallery = output / "gallery.html"
    build_gallery(output / "report.json", gallery)
    assert "moss-sft-lora" in gallery.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        run_plan(path, output, fake, poll_seconds=0)
    first = output / "images" / "manga__moss-base.png"
    first.write_bytes(b"tamper")
    with pytest.raises(ValueError, match="hash mismatch"):
        build_gallery(output / "report.json", output / "other.html")


def test_rejects_absent_lora_node(tmp_path):
    path = make_plan(tmp_path)
    location = tmp_path / "moss-sft-lora.json"
    payload = workflow("moss-sft")
    location.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="LoRA"):
        load_plan(path)


def test_rejects_foreign_file_and_ui_workflow(tmp_path):
    path = make_plan(tmp_path)
    plan = json.loads(path.read_text(encoding="utf-8"))
    plan["arms"]["anima"]["workflow"] = "../other.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(ValueError, match="relative"):
        load_plan(path)


def test_missing_or_preview_image_rejected():
    fake = FakeComfy()
    history = {"outputs": {"18": {"images": [{"type": "temp", "filename": "x.png"}]}}}
    with pytest.raises(ValueError, match="output"):
        fetch_single_output(fake, history, "18", 64, 64)


def test_scorecard_manual_verification_and_hash_binding(tmp_path):
    path = make_plan(tmp_path)
    run = tmp_path / "run"
    run_plan(path, run, FakeComfy(), poll_seconds=0)
    scorecard_path = run / "scorecard.json"
    create_scorecard(run / "report.json", scorecard_path)
    card = json.loads(scorecard_path.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="reviewer"):
        validate_scorecard(run / "report.json", scorecard_path)
    card["reviewer"] = "Human tester"
    for sample in card["samples"]:
        sample["scores"] = {k: 3 for k in sample["scores"]}
    scorecard_path.write_text(json.dumps(card), encoding="utf-8")
    result = validate_scorecard(run / "report.json", scorecard_path)
    assert result["visual_review_recorded"] and not result["rights_approved"]
    with pytest.raises(FileExistsError):
        create_scorecard(run / "report.json", scorecard_path)
    card["samples"][0]["scores"]["text_fidelity"] = "N/A"
    scorecard_path.write_text(json.dumps(card), encoding="utf-8")
    with pytest.raises(ValueError, match="N/A"):
        validate_scorecard(run / "report.json", scorecard_path)


def test_lora_node_must_connect_to_sampler(tmp_path):
    path = make_plan(tmp_path)
    f = tmp_path / "moss-sft-lora.json"
    wf = workflow("moss-sft-lora")
    wf["16"]["inputs"]["model"] = ["1", 0]  # orphaned LoRA
    f.write_text(json.dumps(wf))
    with pytest.raises(ValueError, match="connected"):
        load_plan(path)
