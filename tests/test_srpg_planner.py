"""Synthetic-only SRPG needs planning and provenance regression tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mado_asset_foundry.asset_sources import (
    AssetSubmission, evaluate_submission, get_source, load_source_registry,
)
from mado_asset_foundry.cli import app
from mado_asset_foundry.srpg_planner import plan_srpg_assets

runner = CliRunner()


def _brief(tmp_path: Path, **updates: object) -> Path:
    data = {
        "project": "Tiny SRPG",
        "engine": "godot",
        "needs": [
            {"need_id": "terrain", "category": "terrain", "quantity": 4,
             "priority": "high", "description": "Grid floor tiles"},
            {"need_id": "slash", "category": "vfx", "quantity": 1,
             "priority": "high", "description": "Sword swing"},
            {"need_id": "ui", "category": "ui", "quantity": 2,
             "description": "Action buttons"},
        ],
        "candidates": [
            {"candidate_id": "reference", "need_id": "terrain", "route": "reference",
             "url": "https://github.com/Huu-Yuu/PixelSRPG-Forge"},
            {"candidate_id": "kenney", "need_id": "terrain", "route": "external",
             "source_id": "kenney", "url": "https://kenney.nl/assets/example"},
            {"candidate_id": "original-fx", "need_id": "slash", "route": "original"},
            {"candidate_id": "fx-reference", "need_id": "slash", "route": "reference",
             "url": "https://github.com/patch-gg/pixelfx"},
        ],
    }
    data.update(updates)
    p = tmp_path / "brief.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return p


def test_plans_research_intake_original_and_gaps_without_permissions(tmp_path: Path) -> None:
    path = _brief(tmp_path)
    output = tmp_path / "out/plan.json"
    report, saved = plan_srpg_assets(path, output_path=output)
    assert saved == output
    assert json.loads(saved.read_text(encoding="utf-8")) == report
    assert report["required_quantity"] == 7
    assert report["ready_quantity"] == 0
    assert report["rights_verified"] is False
    assert report["publication_approved"] is False
    assert report["asset_copied"] is False
    assert report["network_accessed"] is False
    assert report["external_code_executed"] is False
    rows = {item["need_id"]: item for item in report["needs"]}
    assert rows["terrain"]["next_action"] == "verify_license_via_existing_asset_intake"
    assert rows["slash"]["next_action"] == "produce_original"
    assert rows["ui"]["next_action"] == "find_licensed_source_or_create_original"
    statuses = {c["candidate_id"]: c["status"]
                for row in rows.values() for c in row["candidates"]}
    assert statuses == {
        "reference": "study_only",
        "kenney": "intake_required",
        "original-fx": "not_created",
        "fx-reference": "study_only",
    }
    assert report["brief_sha256"]


def test_determinism_and_no_overwrite(tmp_path: Path) -> None:
    brief = _brief(tmp_path)
    a, _ = plan_srpg_assets(brief, output_path=tmp_path / "one.json")
    b, _ = plan_srpg_assets(brief, output_path=tmp_path / "two.json")
    assert a == b
    with pytest.raises(FileExistsError):
        plan_srpg_assets(brief, output_path=tmp_path / "one.json")
    assert plan_srpg_assets(
        brief, output_path=tmp_path / "one.json", force=True
    )[0] == a


@pytest.mark.parametrize("url", [
    "http://kenney.nl/assets/example",
    "https://kenney.nl.evil.example/fake",
    "https://user:password@kenney.nl/assets/example",
])
def test_untrusted_external_urls_fail_before_writing(tmp_path: Path, url: str) -> None:
    brief = _brief(tmp_path, candidates=[{
        "candidate_id": "spoof", "need_id": "terrain", "route": "external",
        "source_id": "kenney", "url": url,
    }])
    with pytest.raises(ValueError):
        plan_srpg_assets(brief, output_path=tmp_path / "out/report.json")
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("candidates", [
    [{"candidate_id": "copy", "need_id": "terrain", "route": "original",
      "url": "https://github.com/Huu-Yuu/PixelSRPG-Forge"}],
    [{"candidate_id": "bad", "need_id": "unknown", "route": "reference",
      "url": "https://example.org"}],
    [{"candidate_id": "bad", "need_id": "terrain", "route": "external",
      "source_id": "unknown-source", "url": "https://example.org"}],
])
def test_laundering_and_dangling_candidates_rejected(
    tmp_path: Path, candidates: list[dict[str, str]]
) -> None:
    with pytest.raises(ValueError):
        plan_srpg_assets(
            _brief(tmp_path, candidates=candidates), output_path=tmp_path / "plan.json"
        )
    assert not (tmp_path / "plan.json").exists()


def test_duplicate_needs_rejected(tmp_path: Path) -> None:
    need = {"need_id": "tile", "category": "terrain", "description": "Tile",
            "quantity": 1}
    with pytest.raises(ValueError, match="Duplicate"):
        plan_srpg_assets(
            _brief(tmp_path, needs=[need, need]), output_path=tmp_path / "plan.json"
        )


def test_pixel_srpg_collection_cannot_be_license_laundered() -> None:
    registry = load_source_registry()
    source = get_source(registry, "pixel-srpg-forge")
    assert source.redistribution_policy == "blocked"
    sample = AssetSubmission(
        asset_id="uncleared", source_id="pixel-srpg-forge", title="Uncleared image",
        creator="unknown", local_file="unavailable.png",
        asset_url="https://github.com/Huu-Yuu/PixelSRPG-Forge",
        license_spdx="CC0-1.0",
        license_evidence_url="https://github.com/Huu-Yuu/PixelSRPG-Forge",
        reviewed_by_human=True, use_case="game_embedding",
    )
    status, _, _ = evaluate_submission(sample, source, has_evidence=True)
    assert status == "needs_review"
    status, _, _ = evaluate_submission(
        sample.model_copy(update={"use_case": "asset_pack_redistribution"}),
        source, has_evidence=True,
    )
    assert status == "blocked"


def test_cli_plan_report_and_fail_closed(tmp_path: Path) -> None:
    brief = _brief(tmp_path)
    output = tmp_path / "report.json"
    first = runner.invoke(app, ["srpg", "plan", str(brief), "--output", str(output)])
    assert first.exit_code == 0, first.output
    assert "Ready: 0" in first.output
    assert "publishing approved: NO" in first.output
    second = runner.invoke(app, ["srpg", "plan", str(brief), "--output", str(output)])
    assert second.exit_code == 1
    assert "already exists" in second.output
