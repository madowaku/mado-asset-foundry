"""Synthetic-only tests: never call Hugging Face or use redistributed sprites."""
import json
from pathlib import Path

import pytest
from PIL import Image
from typer.testing import CliRunner

from mado_asset_foundry.pixel_atlas import analyze_sprite, build_sample, make_subject_sheet
from mado_asset_foundry.pixel_atlas_cli import atlas_app

runner = CliRunner()


def _sprite(color=(255, 0, 0, 255)):
    image = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    for y in range(4, 12):
        for x in range(4, 12):
            image.putpixel((x, y), color)
    return image


def _rows():
    return [
        {"row_id": 7, "caption": "red slime", "subject": "slime", "image": _sprite()},
        {"row_id": 8, "caption": "scarlet slime", "subject": "slime", "image": _sprite()},
        {"row_id": 9, "caption": "blue berry", "subject": "berry", "image": _sprite((0, 0, 255, 255))},
    ]


def test_research_bundle_has_provenance_flags_metrics_and_sheet(tmp_path: Path):
    out = tmp_path / "atlas"
    report = build_sample(_rows(), out, count=3, source="fixture://synthetic")
    assert report["sample_count"] == 3
    assert report["subjects_count"] == 2
    assert report["exact_duplicate_extra_rows"] == 1
    assert report["rights_review_required"] is True
    assert report["game_embedding_approved"] is False
    assert report["training_approved"] is False
    assert report["caption_verified"] is False
    entries = [json.loads(line) for line in (out / "index.jsonl").read_text().splitlines()]
    assert [x["row_id"] for x in entries] == [7, 8, 9]
    assert entries[0]["visible_palette_colors"] == 1
    assert entries[0]["visible_fraction"] == 0.25
    assert (out / "sprites/7.png").is_file()
    assert (out / "contact-sheet.png").is_file()
    with Image.open(out / "contact-sheet.png") as sheet:
        assert sheet.size == (832, 112)
    assert json.loads((out / "summary.json").read_text()) == report


def test_invalid_image_causes_no_partial_output(tmp_path: Path):
    rows = [{"row_id": 1, "caption": "bad", "subject": "bad", "image": Image.new("RGBA", (32, 32))}]
    with pytest.raises(ValueError, match="16x16"):
        build_sample(rows, tmp_path / "atlas", count=1)
    assert not (tmp_path / "atlas").exists()


def test_refuses_duplicate_ids_and_existing_output(tmp_path: Path):
    rows = _rows()[:1] * 2
    with pytest.raises(ValueError, match="duplicate row_id"):
        build_sample(rows, tmp_path / "atlas", count=2)
    build_sample(_rows(), tmp_path / "atlas", count=2)
    with pytest.raises(FileExistsError):
        build_sample(_rows(), tmp_path / "atlas", count=2)


def test_transparent_rgb_canonicalized_and_flags_are_not_scores():
    a = _sprite()
    b = _sprite()
    b.putpixel((0, 0), (255, 255, 255, 0))
    assert analyze_sprite(a)["pixel_sha256"] == analyze_sprite(b)["pixel_sha256"]
    assert analyze_sprite(a)["visible_palette_colors"] == 1
    assert "quality_score" not in analyze_sprite(a)
    assert "empty_sprite" in analyze_sprite(Image.new("RGBA", (16, 16), (0, 0, 0, 0)))["flags"]


def test_subject_sheet_filtered_and_not_overwritten(tmp_path: Path):
    bundle = tmp_path / "atlas"
    build_sample(_rows(), bundle, count=3)
    out = tmp_path / "slimes.png"
    assert make_subject_sheet(bundle, subject="SLIME", output_path=out) == 2
    assert out.exists()
    with pytest.raises(FileExistsError):
        make_subject_sheet(bundle, subject="slime", output_path=out)
    with pytest.raises(ValueError, match="No sprites matched"):
        make_subject_sheet(bundle, subject="robots", output_path=tmp_path / "none.png")


def test_cli_network_is_opt_in_and_no_import_needed(tmp_path: Path):
    result = runner.invoke(atlas_app, ["sample", "--output", str(tmp_path / "atlas")])
    assert result.exit_code == 2
    assert "No network request made" in result.output
    assert not (tmp_path / "atlas").exists()
