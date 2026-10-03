import json
from pathlib import Path

from mado_asset_foundry.skills.scanner import scan_skill


FIXTURE = Path("fixtures/skills/sample-background-remover")


def test_scan_detects_capabilities_runtime_and_license(tmp_path: Path) -> None:
    manifest, manifest_path, report_path = scan_skill(
        FIXTURE,
        manifest_dir=tmp_path / "manifests",
        evidence_dir=tmp_path / "evidence",
    )

    assert manifest.capabilities == ["background_remove", "alpha_cleanup"]
    assert manifest.runtime == ["python", "onnx_runtime"]
    assert manifest.license.spdx == "MIT"
    assert manifest.license.status == "detected"
    assert manifest.inputs == ["image", "transparent_png"]
    assert manifest.outputs == ["transparent_png"]
    assert manifest.adapter_status == "intake_only"

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["external_code_executed"] is False
    assert report["capability_classification_performed"] is True
    assert report["documents_scanned"] == ["SKILL.md", "README.md"]
    caps = {item["capability"]: item for item in report["capability_evidence"]}
    assert "background removal" in caps["background_remove"]["matched_terms"]
    assert "alpha mask" in caps["alpha_cleanup"]["matched_terms"]
    runtimes = {item["runtime"] for item in report["runtime_evidence"]}
    assert runtimes == {"python", "onnx_runtime"}
    assert manifest_path.exists()


def test_scan_does_not_classify_from_script_contents(tmp_path: Path) -> None:
    source = tmp_path / "script-only"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("# Script Only\nNo declared asset capabilities.\n", encoding="utf-8")
    (source / "scripts" / "tool.py").write_text(
        "# sprite sheet background removal palette lock\n",
        encoding="utf-8",
    )

    manifest, _, _ = scan_skill(
        source,
        manifest_dir=tmp_path / "manifests",
        evidence_dir=tmp_path / "evidence",
    )

    assert manifest.capabilities == []
    assert manifest.runtime == ["python"]


def test_scan_unknown_license_stays_unknown(tmp_path: Path) -> None:
    source = tmp_path / "unknown-license"
    source.mkdir()
    (source / "SKILL.md").write_text("# Unknown\nbackground removal\n", encoding="utf-8")
    (source / "LICENSE").write_text("Custom terms for testing only.\n", encoding="utf-8")

    manifest, _, report_path = scan_skill(
        source,
        manifest_dir=tmp_path / "manifests",
        evidence_dir=tmp_path / "evidence",
    )

    assert manifest.license.status == "unknown"
    assert manifest.license.spdx is None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["license_evidence"]["matched_identifiers"] == []


def test_scan_requires_force_to_replace_outputs(tmp_path: Path) -> None:
    kwargs = {
        "manifest_dir": tmp_path / "manifests",
        "evidence_dir": tmp_path / "evidence",
    }
    scan_skill(FIXTURE, **kwargs)

    try:
        scan_skill(FIXTURE, **kwargs)
        raise AssertionError("expected FileExistsError")
    except FileExistsError:
        pass

    manifest, _, _ = scan_skill(FIXTURE, force=True, **kwargs)
    assert "background_remove" in manifest.capabilities
