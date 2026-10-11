"""MAF-M1.2.1 deterministic screenshot inspector negative/positive contracts."""
from __future__ import annotations

import hashlib
import io
import json

import pytest
from PIL import Image, ImageDraw

import e2e.visual_goldens as visual


def png(color=(25, 40, 52), *, modified=False, size=(100, 80)) -> bytes:
    image = Image.new("RGB", size, color)
    ImageDraw.Draw(image).rectangle((10, 10, 45, 45), fill=(160, 203, 170))
    if modified:
        ImageDraw.Draw(image).rectangle((10, 10, 85, 65), fill=(255, 40, 80))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def lock(tmp_path, monkeypatch):
    root = tmp_path / "goldens"
    root.mkdir()
    content = png()
    (root / "demo.png").write_bytes(content)
    data = {
        "schema_version": "1.0",
        "goldens": {"demo": {
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": [100, 80],
        }},
        "comparison": {
            "pixel_channel_tolerance": 16,
            "max_changed_fraction": 0.02,
            "max_mean_absolute_error": 3,
        },
    }
    (root / "manifest.json").write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(visual, "MANIFEST_PATH", root / "manifest.json")
    monkeypatch.setattr(visual, "GOLDEN_ROOT", root)
    return root


def test_exact_golden_passes_and_emits_before_after_diff(lock, tmp_path):
    out = tmp_path / "delta"
    result = visual.compare_golden("demo", png(), destination=out)
    assert result["status"] == "passed"
    assert result["changed_fraction"] == 0
    assert result["mean_absolute_error"] == 0
    assert (out / "demo-before-after-diff.png").is_file()
    assert (out / "demo-diff.png").is_file()
    assert (out / "demo-metrics.json").is_file()


def test_regression_generates_visual_evidence_before_failing(lock, tmp_path):
    out = tmp_path / "delta"
    with pytest.raises(AssertionError, match="Golden screenshot changed"):
        visual.compare_golden("demo", png(modified=True), destination=out)
    record = json.loads((out / "demo-metrics.json").read_text())
    assert record["status"] == "regression"
    assert record["changed_fraction"] > 0.02
    with Image.open(out / "demo-before-after-diff.png") as image:
        assert image.size == (300, 118)
    assert (out / "demo-diff.png").is_file()


def test_dimension_change_fails_with_visual_comparison(lock, tmp_path):
    with pytest.raises(AssertionError, match="Golden screenshot changed"):
        visual.compare_golden("demo", png(size=(105, 80)), destination=tmp_path / "delta")
    report = json.loads((tmp_path / "delta" / "demo-metrics.json").read_text())
    assert report["golden_size"] == [100, 80]
    assert report["actual_size"] == [105, 80]


def test_locked_golden_tampering_fails_closed(lock, tmp_path):
    (lock / "demo.png").write_bytes(png(color=(180, 25, 25)))
    with pytest.raises(ValueError, match="tampering"):
        visual.compare_golden("demo", png(), destination=tmp_path / "delta")


def test_missing_unknown_goldens_are_never_automatically_approved(lock, tmp_path):
    with pytest.raises(ValueError, match="not in approved"):
        visual.compare_golden("unapproved", png(), destination=tmp_path / "delta")
    (lock / "demo.png").unlink()
    with pytest.raises(FileNotFoundError, match="explicit golden bootstrap"):
        visual.compare_golden("demo", png(), destination=tmp_path / "delta")
    assert not (lock / "demo.png").exists()
