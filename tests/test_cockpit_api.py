from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

import mado_asset_foundry.asset_flow as flow
import mado_asset_foundry.cockpit as cockpit
from mado_asset_foundry.asset_sources import _sha256
from mado_asset_foundry.attribution_bridge import BridgePlan, _read_object
from mado_asset_foundry.io import write_json
from mado_asset_foundry.visual_gallery import _evidence_entries

HEADERS = {"X-MAF-Action": "cockpit"}
REVIEW = {
    "reviewer": "MADO human reviewer",
    "notes": "I personally verified the screenshot, credits and per-asset game embedding rights.",
    "visual_approved": True,
    "attribution_approved": True,
    "rights_approved_for_game_embedding": True,
}


def sample(tmp_path: Path) -> tuple[Path, Path]:
    recipes = tmp_path / "recipes"
    source = recipes / "inputs" / "icon"
    source.mkdir(parents=True)
    Image.new("RGBA", (32, 32), (180, 135, 90, 255)).save(source / "source.png")
    (source / "LICENSE.txt").write_text("Synthetic CC0-1.0 artwork.", encoding="utf-8")
    (source / "submission.yaml").write_text(yaml.safe_dump({
        "asset_id": "icon", "source_id": "local", "title": "<Unsafe> & an icon",
        "creator": "MADO test", "local_file": "source.png", "license_spdx": "CC0-1.0",
        "license_evidence_file": "LICENSE.txt", "reviewed_by_human": True,
        "use_case": "game_embedding",
    }), encoding="utf-8")
    (recipes / "demo.yaml").write_text(yaml.safe_dump({
        "flow_id": "demo-flow", "submissions": ["inputs/icon/submission.yaml"]
    }), encoding="utf-8")
    return recipes, tmp_path / "runs"


def fake_godot(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_runtime(plan_path, project_dir, *, godot_bin, output_root, timeout):
        out = Path(output_root) / "demo-flow"
        out.mkdir(parents=True)
        report = {"status": "passed", "godot_version": "4.6.1.stable"}
        write_json(out / "report.json", report)
        return report, out

    def fake_gallery(plan_path, project_dir, *, godot_bin, output_root, timeout, virtual_display):
        plan_path = Path(plan_path)
        project_dir = Path(project_dir)
        folder = Path(output_root) / "demo-flow"
        folder.mkdir(parents=True)
        image = Image.new("RGB", (960, 540), (18, 30, 42))
        ImageDraw.Draw(image).rectangle((50, 50, 200, 280), fill=(225, 99, 70))
        image.save(folder / "gallery.png")
        (folder / "CREDITS.md").write_bytes((project_dir / "CREDITS.md").read_bytes())
        plan = BridgePlan.model_validate(_read_object(plan_path))
        manifest = _read_object(project_dir / "asset_manifest.json")
        report = {
            "status": "captured", "project_id": "demo-flow",
            "screenshot_sha256": _sha256(folder / "gallery.png"),
            "credits_sha256": _sha256(folder / "CREDITS.md"),
            "manifest_sha256": _sha256(project_dir / "asset_manifest.json"),
            "assets": _evidence_entries(plan, plan_path, manifest),
        }
        write_json(folder / "report.json", report)
        return report, folder

    monkeypatch.setattr(flow, "verify_godot_import", fake_runtime)
    monkeypatch.setattr(flow, "render_gallery", fake_gallery)


def completed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipes, workspace = sample(tmp_path)
    fake_godot(monkeypatch)
    flow.run_asset_flow(recipes / "demo.yaml", workspace=workspace, godot_bin="godot")
    client = TestClient(cockpit.create_app(workspace, recipes=recipes, godot_bin="godot"))
    return client, workspace, recipes


def test_cockpit_serves_self_hosted_app_and_safe_headers(tmp_path: Path):
    client = TestClient(cockpit.create_app(tmp_path / "runs", recipes=tmp_path / "recipes"))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Asset Foundry Cockpit" in resp.text
    assert "script-src 'self'" in resp.headers["content-security-policy"]
    assert resp.headers["x-frame-options"] == "DENY"
    assert client.get("/static/cockpit.js").status_code == 200
    assert client.get("/static/cockpit.css").status_code == 200
    assert client.get("/api/status").json()["can_start"] is False
    assert client.get("/api/flows").json() == {"flows": []}
    assert client.get("/api/recipes").json() == {"recipes": []}


def test_flow_history_asset_images_and_credits(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, workspace, recipes = completed(tmp_path, monkeypatch)
    assert client.get("/api/recipes").json()["recipes"] == [{"name": "demo.yaml"}]
    items = client.get("/api/flows").json()["flows"]
    assert len(items) == 1
    assert items[0]["review_status"] == "not_submitted"
    detail = client.get("/api/flows/demo-flow").json()
    assert detail["asset_count"] == 1
    assert detail["assets"][0]["license"] == "CC0-1.0"
    assert detail["assets"][0]["title"] == "<Unsafe> & an icon"
    assert detail["assets"][0]["license_status"] == "eligible"
    assert detail["screenshot_sha256"]
    assert detail["publication_approved"] is False
    assert client.get("/api/flows/demo-flow/gallery").headers["content-type"] == "image/png"
    assert client.get("/api/flows/demo-flow/assets/icon/image").status_code == 200
    assert "MADO test" in client.get("/api/flows/demo-flow/credits").text
    assert client.get("/api/flows/../gallery").status_code in (404, 400)
    assert client.get("/api/flows/demo-flow/assets/%2E%2E/image").status_code in (400, 404)


def test_review_requires_explicit_csrf_and_three_checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, workspace, _ = completed(tmp_path, monkeypatch)
    url = "/api/flows/demo-flow/review"
    assert client.post(url, json=REVIEW).status_code == 403
    assert client.post(url, json=REVIEW, headers={**HEADERS,"Origin":"https://evil.example"}).status_code == 403
    assert client.post(url, json={**REVIEW, "rights_approved_for_game_embedding": False}, headers=HEADERS).status_code == 422
    assert not (workspace / "demo-flow" / "review" / "release-check.json").exists()
    blocked = client.post(url, json=REVIEW, headers=HEADERS)
    assert blocked.status_code == 409
    assert "every asset" in blocked.json()["detail"]
    assessment = client.post("/api/flows/demo-flow/assets/icon/visual", headers=HEADERS, json={
        "decision": "pass", "reviewer": "MADO human reviewer", "note": "Checked image on gallery"
    })
    assert assessment.status_code == 200, assessment.text
    response = client.post(url, json=REVIEW, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "human_release_review_passed"
    assert response.json()["publication_approved"] is False
    recorded = _read_object(workspace / "demo-flow" / "review" / "human-attestation.json")
    assert recorded["reviewer"] == REVIEW["reviewer"]
    assert recorded["notes"] == REVIEW["notes"]
    assert recorded["rights_approved_for_game_embedding"] is True
    assert client.get("/api/flows/demo-flow").json()["review_status"] == "human_release_review_passed"
    assert client.post(url, json=REVIEW, headers=HEADERS).status_code == 409


def test_review_rechecks_changed_rights(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, workspace, _ = completed(tmp_path, monkeypatch)
    (workspace / "demo-flow" / "inputs" / "icon" / "LICENSE.txt").write_text("changed", encoding="utf-8")
    res = client.post("/api/flows/demo-flow/review", json=REVIEW, headers=HEADERS)
    assert res.status_code == 409
    assert not (workspace / "demo-flow" / "review" / "release-check.json").exists()


def test_review_rejects_bogus_origin_and_types(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, _, _ = completed(tmp_path, monkeypatch)
    url = "/api/flows/demo-flow/review"
    assert client.post(url, json={**REVIEW,"visual_approved":"true"}, headers=HEADERS).status_code == 422
    assert client.post(url, json={**REVIEW,"reviewer":"   "}, headers=HEADERS).status_code == 422


def test_start_job_from_allowlisted_recipe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipes, workspace = sample(tmp_path)
    fake_godot(monkeypatch)
    client = TestClient(cockpit.create_app(workspace, recipes=recipes, godot_bin="godot"))
    assert client.post("/api/actions/run", json={"recipe":"demo.yaml"}).status_code == 403
    assert client.post("/api/actions/run", json={"recipe":"../secret.yaml"}, headers=HEADERS).status_code == 400
    assert client.post("/api/actions/run", json={"recipe":"missing.yaml"}, headers=HEADERS).status_code == 404
    assert client.post("/api/actions/run", json={"recipe":"demo.yaml"},headers={**HEADERS,"Origin":"https://evil.example"}).status_code == 403
    started = client.post("/api/actions/run", json={"recipe":"demo.yaml"}, headers=HEADERS)
    assert started.status_code == 202, started.text
    job_id = started.json()["job_id"]
    record = None
    for _ in range(200):
        record = client.get("/api/jobs/" + job_id).json()
        if record["status"] != "running": break
        time.sleep(0.01)
    assert record["status"] == "completed", record
    assert record["flow_id"] == "demo-flow"
    assert client.get("/api/flows/demo-flow").status_code == 200
    assert client.get("/api/jobs/notfound").status_code == 404


def test_read_only_mode_and_no_external_executable(tmp_path: Path):
    recipes, workspace = sample(tmp_path)
    client = TestClient(cockpit.create_app(workspace, recipes=recipes))
    assert client.post("/api/actions/run", json={"recipe":"demo.yaml"}, headers=HEADERS).status_code == 503
    assert client.post("/api/actions/run", json={"recipe":"demo.yaml","godot_bin":"bad"},headers=HEADERS).status_code == 422
    with pytest.raises(ValueError, match="loopback"):
        cockpit.serve_cockpit(workspace, recipes=recipes, host="0.0.0.0")


def test_file_symlink_is_not_served(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, workspace, _ = completed(tmp_path, monkeypatch)
    gallery = workspace / "demo-flow" / "gallery" / "demo-flow" / "gallery.png"
    original = workspace / "saved.png"
    gallery.rename(original)
    try:
        gallery.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is unavailable")
    assert client.get("/api/flows/demo-flow/gallery").status_code == 400


def test_no_recipe_symlinks_allowed(tmp_path: Path):
    recipes, workspace = sample(tmp_path)
    target = recipes / "demo.yaml"
    alias = recipes / "alias.yaml"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks is unavailable")
    client = TestClient(cockpit.create_app(workspace, recipes=recipes, godot_bin="godot"))
    assert [item["name"] for item in client.get("/api/recipes").json()["recipes"]] == ["demo.yaml"]
    assert client.post("/api/actions/run",json={"recipe":"alias.yaml"},headers=HEADERS).status_code == 404


@pytest.mark.parametrize("tamper", [
    ("gallery", "demo-flow", "gallery.png"),
    ("gallery", "demo-flow", "CREDITS.md"),
    ("runtime", "demo-flow", "report.json"),
    ("inputs", "icon", "LICENSE.txt"),
])
def test_detail_refuses_stale_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tamper: tuple[str, ...]
):
    client, workspace, _ = completed(tmp_path, monkeypatch)
    file = workspace / "demo-flow"
    for part in tamper:
        file = file / part
    with file.open("ab") as out:
        out.write(b"tampered")
    assert client.get("/api/flows/demo-flow").status_code == 409


def test_symlinked_flow_summary_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, workspace, _ = completed(tmp_path, monkeypatch)
    summary = workspace / "demo-flow" / "summary.json"
    original = workspace / "original-summary.json"
    summary.rename(original)
    try:
        summary.symlink_to(original)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable")
    assert client.get("/api/flows/demo-flow").status_code == 400



def test_visual_review_defaults_and_comparison(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, workspace, _ = completed(tmp_path, monkeypatch)
    result = client.get("/api/flows/demo-flow")
    assert result.status_code == 200
    status = result.json()["visual_review"]
    assert status["total"] == 1
    assert status["pending"] == 1
    assert status["reviewed"] == 0
    assert status["ready_for_final_review"] is False
    url = "/api/flows/demo-flow/assets/icon/visual"
    assert client.post(url, json={"decision":"pass","reviewer":"Human","note":""}).status_code == 403
    assert client.post(url, headers={**HEADERS, "Origin":"https://evil.example"},
        json={"decision":"pass","reviewer":"Human","note":""}).status_code == 403
    assert client.post(url, headers=HEADERS,
        json={"decision":"pass","reviewer":"  ","note":""}).status_code == 422
    assert client.post(url, headers=HEADERS,
        json={"decision":"rework","reviewer":"Human","note":""}).status_code == 422
    assert client.post("/api/flows/demo-flow/assets/unknown/visual", headers=HEADERS,
        json={"decision":"pass","reviewer":"Human","note":""}).status_code == 404
    r = client.post(url, headers=HEADERS,
        json={"decision":"rework","reviewer":"Human","note":"Outline needs cleanup"})
    assert r.status_code == 200, r.text
    assert r.json()["visual_review"]["rework"] == 1
    assert r.json()["visual_review"]["ready_for_final_review"] is False
    assert client.post("/api/flows/demo-flow/review", headers=HEADERS, json=REVIEW).status_code == 409
    r = client.post(url, headers=HEADERS,
        json={"decision":"pass","reviewer":"Human","note":"Fixed outline"})
    assert r.status_code == 200
    assert r.json()["visual_review"]["passed"] == 1
    assert r.json()["visual_review"]["ready_for_final_review"] is True
    saved = _read_object(workspace / "demo-flow" / "review" / "visual-decisions.json")
    assert saved["decisions"]["icon"]["decision"] == "pass"
    assert saved["screenshot_sha256"] == result.json()["screenshot_sha256"]
    assert r.json()["publication_approved"] is False


def test_visual_decisions_stale_and_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    client, workspace, _ = completed(tmp_path, monkeypatch)
    url = "/api/flows/demo-flow/assets/icon/visual"
    assert client.post(url, headers=HEADERS, json={
        "decision":"pass","reviewer":"QA operator","note":"Observed PNG"
    }).status_code == 200
    sheet = workspace / "demo-flow" / "review" / "visual-decisions.json"
    record = _read_object(sheet)
    record["screenshot_sha256"] = "0" * 64
    write_json(sheet, record)
    assert client.get("/api/flows/demo-flow").status_code == 409
    assert client.post(url, headers=HEADERS, json={
        "decision":"pass","reviewer":"QA operator","note":"Same observation"
    }).status_code == 409


def test_pipeline_progress_events_real_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipes, workspace = sample(tmp_path)
    fake_godot(monkeypatch)
    seen: list[tuple[str, str]] = []
    summary, _ = flow.run_asset_flow(
        recipes / "demo.yaml", godot_bin="godot", workspace=workspace,
        progress=lambda stage,status: seen.append((stage,status))
    )
    stages = ("intake","attribution","runtime","gallery","evidence")
    assert seen == [item for stage in stages for item in ((stage,"running"),(stage,"completed"))]
    assert summary["status"] == "awaiting_human_review"


def test_pipeline_progress_failure_marks_real_failed_stage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipes, workspace = sample(tmp_path)
    fake_godot(monkeypatch)
    def failing_runtime(*args, **kwargs):
        raise ValueError("test engine failed")
    monkeypatch.setattr(flow, "verify_godot_import", failing_runtime)
    seen: list[tuple[str,str]] = []
    with pytest.raises(ValueError, match="test engine failed"):
        flow.run_asset_flow(recipes / "demo.yaml", godot_bin="godot", workspace=workspace,
                            progress=lambda a,b:seen.append((a,b)))
    assert seen[-1] == ("runtime","failed")
    assert ("gallery","running") not in seen


def test_completed_job_exposes_stage_states(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    recipes, workspace = sample(tmp_path)
    fake_godot(monkeypatch)
    client = TestClient(cockpit.create_app(workspace, recipes=recipes, godot_bin="godot"))
    started = client.post("/api/actions/run", json={"recipe":"demo.yaml"}, headers=HEADERS)
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    for _ in range(200):
        job = client.get("/api/jobs/" + job_id).json()
        if job["status"] == "completed": break
        time.sleep(0.01)
    assert job["status"] == "completed"
    assert [item["stage"] for item in job["stages"]] == [
        "intake","attribution","runtime","gallery","evidence"
    ]
    assert all(item["status"] == "completed" for item in job["stages"])
    assert job["current_stage"] == "evidence"
