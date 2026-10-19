import json

import pytest
from PIL import Image

from mado_asset_foundry.moss_bakeoff import MODELS, compile_layout, inspect_images


def test_layout_centered_coordinates_and_japanese():
    layout = compile_layout({"width": 1024, "height": 1024, "caption": "縦書きの漫画",
        "items": [{"label": "text", "caption": "title", "text": "冒険", "bbox_xyxy": [96, 128, 224, 512]}]})
    assert layout["items"][0]["bbox"] == [-384, -416, 0, -288]
    assert json.loads(json.dumps(layout, ensure_ascii=False)) == layout


@pytest.mark.parametrize("bbox", [[0, 0, 1025, 12], [2, 2, 1, 4], [0, 0, 1.5, 4]])
def test_layout_rejects_bad_boxes(bbox):
    with pytest.raises(ValueError):
        compile_layout({"width": 1024, "height": 1024, "caption": "x",
            "items": [{"label": "object", "caption": "x", "bbox_xyxy": bbox}]})


def test_evidence_uses_real_png_and_hash(tmp_path):
    samples = []
    for model in MODELS:
        name = model + ".png"
        Image.new("RGB", (64, 64), "white").save(tmp_path / name)
        samples.append({"model": model, "path": name})
    result = inspect_images({"cases": [{"id": "ja-text", "seed": 42,
        "width": 64, "height": 64, "samples": samples}]}, tmp_path)
    assert result["cases"][0]["paired_complete"]
    assert all(len(x["sha256"]) == 64 for x in result["cases"][0]["samples"])
    assert not result["quality_approved"]


def test_evidence_rejects_traversal(tmp_path):
    with pytest.raises(ValueError):
        inspect_images({"cases": [{"id": "x", "seed": 1, "width": 64,
            "height": 64, "samples": [{"model": "moss-base", "path": "../oops.png"}]}]}, tmp_path)


def test_evidence_rejects_mismatched_dimensions(tmp_path):
    Image.new("RGB", (32, 32)).save(tmp_path / "wrong.png")
    with pytest.raises(ValueError):
        inspect_images({"cases": [{"id": "x", "seed": 1, "width": 64,
            "height": 64, "samples": [{"model": "moss-base", "path": "wrong.png"}]}]}, tmp_path)
