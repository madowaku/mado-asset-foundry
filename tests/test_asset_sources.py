from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from mado_asset_foundry.asset_sources import (
    AssetSubmission,
    evaluate_submission,
    get_source,
    intake_asset,
    load_source_registry,
)
from mado_asset_foundry.cli import app


runner = CliRunner()


def _submission(tmp_path: Path, **changes: object) -> Path:
    (tmp_path / "asset.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>", encoding="utf-8")
    (tmp_path / "LICENSE.txt").write_text("Local test fixture rights: CC0-1.0", encoding="utf-8")
    details: dict[str, object] = {
        "asset_id": "test-icon",
        "source_id": "local",
        "title": "Test icon",
        "creator": "Test Author",
        "local_file": "asset.svg",
        "license_spdx": "CC0-1.0",
        "license_evidence_file": "LICENSE.txt",
        "reviewed_by_human": True,
        "use_case": "game_embedding",
        "commercial": True,
    }
    details.update(changes)
    manifest = tmp_path / "submission.yaml"
    manifest.write_text(yaml.safe_dump(details), encoding="utf-8")
    return manifest


def test_registry_has_sources_and_does_not_claim_licenses() -> None:
    registry = load_source_registry()
    assert len(registry.sources) >= 9
    assert get_source(registry, "kenney").discovery_mode == "manual"
    assert get_source(registry, "mixamo").redistribution_policy == "blocked"
    assert get_source(registry, "freesound").terms_url is not None


def test_local_fixture_eligible_but_never_publication_approved(tmp_path: Path) -> None:
    report, path = intake_asset(_submission(tmp_path), output_root=tmp_path / "results")
    assert report["status"] == "eligible"
    assert report["publication_approved"] is False
    assert report["network_accessed"] is False
    assert report["external_code_executed"] is False
    assert report["asset_copied"] is False
    assert report["sha256"] and report["license_evidence_sha256"]
    assert json.loads(path.read_text(encoding="utf-8")) == report


def test_no_human_review_and_unknown_license_need_review(tmp_path: Path) -> None:
    report, _ = intake_asset(
        _submission(tmp_path, reviewed_by_human=False, license_spdx="Custom"),
        output_root=tmp_path / "results",
    )
    assert report["status"] == "needs_review"
    assert len(report["reasons"]) >= 2


def test_commercial_noncommercial_license_is_blocked(tmp_path: Path) -> None:
    report, _ = intake_asset(
        _submission(tmp_path, license_spdx="CC-BY-NC-4.0"),
        output_root=tmp_path / "results",
    )
    assert report["status"] == "blocked"


def test_cc_by_requires_credits_and_redistribution_review(tmp_path: Path) -> None:
    manifest = AssetSubmission(
        asset_id="some-icon", source_id="local", title="Icon", creator="Artist",
        local_file="asset.svg", license_spdx="CC-BY-4.0",
        use_case="game_embedding", reviewed_by_human=True,
    )
    source = get_source(load_source_registry(), "local")
    state, why, _ = evaluate_submission(manifest, source, has_evidence=True)
    assert state == "needs_review"
    assert any("attribution" in item for item in why)
    state, _, _ = evaluate_submission(
        manifest.model_copy(update={"attribution": "Artist, CC BY 4.0"}), source,
        has_evidence=True,
    )
    assert state == "eligible"
    state, _, _ = evaluate_submission(
        manifest.model_copy(update={"attribution": "Artist, CC BY 4.0", "use_case": "asset_pack_redistribution"}),
        source, has_evidence=True,
    )
    assert state == "needs_review"


def test_mixamo_redistribution_block_cannot_be_bypassed() -> None:
    submission = AssetSubmission(
        asset_id="dance", source_id="mixamo", title="Dance", creator="Adobe",
        local_file="asset.fbx", asset_url="https://www.mixamo.com/",
        license_spdx="CC0-1.0", license_evidence_url="https://www.mixamo.com/",
        use_case="asset_pack_redistribution", reviewed_by_human=True,
    )
    status, reasons, _ = evaluate_submission(
        submission, get_source(load_source_registry(), "mixamo"), has_evidence=True,
    )
    assert status == "blocked"
    assert any("redistribution" in item for item in reasons)


def test_remote_source_url_spoofing_is_rejected(tmp_path: Path) -> None:
    manifest = _submission(
        tmp_path, source_id="kenney",
        asset_url="https://kenney.nl.evil.example/asset",
        license_evidence_url="https://kenney.nl/assets/pack",
    )
    with pytest.raises(ValueError, match="registered hosts"):
        intake_asset(manifest, output_root=tmp_path / "results")
    assert not (tmp_path / "results").exists()


def test_external_source_can_be_intaken_with_per_asset_evidence(tmp_path: Path) -> None:
    manifest = _submission(
        tmp_path, source_id="kenney", asset_url="https://kenney.nl/assets/example",
        license_evidence_url="https://kenney.nl/assets/example",
    )
    report, _ = intake_asset(manifest, output_root=tmp_path / "results")
    assert report["status"] == "eligible"
    assert report["source_discovery_mode"] == "manual"


def test_local_path_escape_and_symlink_blocked(tmp_path: Path) -> None:
    manifest = _submission(tmp_path, local_file="../outside.svg")
    with pytest.raises(ValueError, match="escapes submission directory"):
        intake_asset(manifest, output_root=tmp_path / "results")
    (tmp_path / "pointer.svg").symlink_to(tmp_path / "asset.svg")
    manifest = _submission(tmp_path, local_file="pointer.svg")
    with pytest.raises(ValueError, match="Symlink"):
        intake_asset(manifest, output_root=tmp_path / "results")


def test_no_silent_overwrite_and_explicit_force(tmp_path: Path) -> None:
    submission = _submission(tmp_path)
    kwargs = {"output_root": tmp_path / "results"}
    intake_asset(submission, **kwargs)
    with pytest.raises(FileExistsError):
        intake_asset(submission, **kwargs)
    report, _ = intake_asset(submission, force=True, **kwargs)
    assert report["status"] == "eligible"


def test_registry_duplicate_ids_rejected(tmp_path: Path) -> None:
    source = load_source_registry().sources[0].model_dump()
    path = tmp_path / "dup.json"
    path.write_text(json.dumps({"sources": [source, source]}), encoding="utf-8")
    with pytest.raises(ValueError, match="Duplicate"):
        load_source_registry(path)


def test_cli_list_and_show() -> None:
    listed = runner.invoke(app, ["asset-source", "list"])
    assert listed.exit_code == 0, listed.output
    assert "kenney" in listed.output
    shown = runner.invoke(app, ["asset-source", "show", "mixamo"])
    assert shown.exit_code == 0, shown.output
    assert "Redistribution: blocked" in shown.output


def test_cli_intake_and_review_exit_codes(tmp_path: Path) -> None:
    manifest = _submission(tmp_path)
    result = runner.invoke(
        app, ["asset-source", "intake", str(manifest),
              "--output-root", str(tmp_path / "results")],
    )
    assert result.exit_code == 0, result.output
    assert "Status: eligible" in result.output
    assert "publishing approved: NO" in result.output

    _submission(tmp_path, reviewed_by_human=False)
    result = runner.invoke(
        app, ["asset-source", "intake", str(manifest),
              "--output-root", str(tmp_path / "results"), "--force"],
    )
    assert result.exit_code == 2, result.output
    assert "Status: needs_review" in result.output
