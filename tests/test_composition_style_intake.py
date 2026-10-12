"""Synthetic, offline acceptance cases for MAF-M1.7.1."""
from io import BytesIO
import json

import pytest
from PIL import Image

import mado_asset_foundry.composition_style_intake as intake
from mado_asset_foundry.composition_style import build_run, digest


@pytest.fixture
def queued_run(tmp_path):
    source = tmp_path / "composition.png"
    Image.new("RGBA", (64, 48), (50, 100, 150, 255)).save(source)
    workflow = tmp_path / "api.json"
    workflow.write_text(json.dumps({
        "1": {"class_type": "LoadImage", "inputs": {"image": "before.png"}},
        "2": {"class_type": "KSampler", "inputs": {"seed": 0, "denoise": 0.5}},
        "3": {"class_type": "SaveImage", "inputs": {"images": ["2", 0]}},
        "4": {"class_type": "PreviewImage", "inputs": {"images": ["2", 0]}},
    }))
    output = tmp_path / "run"
    build_run(source, workflow, output, image_node="1", sampler_node="2",
              seeds=(14, 15), model_id="Anima test", model_license_review="manual review")
    evidence_path = output / "evidence.json"
    evidence = json.loads(evidence_path.read_text())
    evidence["runtime"] = "comfyui"
    for job in evidence["jobs"]:
        job["prompt_id"] = "prompt-" + str(job["seed"])
        job["status"] = "queued"
    evidence_path.write_text(json.dumps(evidence))
    return output


@pytest.fixture
def mocked_comfy(queued_run, monkeypatch):
    def history(base, pid):
        seed = int(pid.split("-")[-1])
        graph = json.loads((queued_run / f"workflows/seed-{seed}.json").read_text())
        return {pid: {
            "prompt": [0, pid, graph, {}],
            "status": {"completed": True, "status_str": "success"},
            "outputs": {
                "3": {"images": [{"filename": "ComfyUI_0001_.png", "subfolder": "", "type": "output"}]},
                "4": {"images": [{"filename": "temp.png", "subfolder": "", "type": "temp"}]},
            },
        }}
    def download(base, descriptor):
        data = BytesIO()
        Image.new("RGBA", (64, 48), (40, 120, 140, 255)).save(data, format="PNG")
        return data.getvalue()
    monkeypatch.setattr(intake, "_history", history)
    monkeypatch.setattr(intake, "_download", download)


def test_collect_both_seeds_and_integrity(queued_run, mocked_comfy):
    evidence = intake.collect_run(queued_run)
    assert evidence["intake_stage"] == "complete"
    assert evidence["publication_approved"] is False
    assert [job["status"] for job in evidence["jobs"]] == ["rendered", "rendered"]
    for job in evidence["jobs"]:
        assert job["history_graph_verified"] is True
        candidate = job["outputs"][0]
        assert candidate["qa"]["decision"] == "needs_human_review"
        assert candidate["qa"]["same_dimensions"] is True
        assert (queued_run / candidate["path"]).is_file()
        assert (queued_run / candidate["comparison"]).is_file()
        assert "\\" not in candidate["path"]
        assert candidate["path"].startswith("outputs/")
        assert digest(queued_run / candidate["path"]) == candidate["sha256"]
    assert intake.collect_run(queued_run)["intake_stage"] == "complete"
    gallery = (queued_run / "gallery.html").read_text(encoding="utf-8")
    assert "Composition proxy" in gallery
    assert "Publication approved: NO" in gallery


def test_offline_run_cannot_collect(tmp_path):
    root = tmp_path / "run"
    root.mkdir()
    (root / "evidence.json").write_text(json.dumps({"schema": "maf.composition_style.v1", "runtime": "offline"}))
    with pytest.raises(ValueError, match="Only live"):
        intake.collect_run(root)


def test_pending_history_does_not_invent_output(queued_run, monkeypatch):
    monkeypatch.setattr(intake, "_history", lambda *a: {})
    result = intake.collect_run(queued_run)
    assert result["intake_stage"] == "incomplete"
    assert all(j["intake_state"] == "pending" for j in result["jobs"])
    assert list((queued_run / "outputs").iterdir()) == []


def test_failed_execution_never_rendered(queued_run, monkeypatch):
    monkeypatch.setattr(intake, "_history",
                        lambda base, pid: {pid: {"status": {"completed": True, "status_str": "error"}}})
    result = intake.collect_run(queued_run)
    assert all(j["status"] == "error" for j in result["jobs"])
    assert result["intake_stage"] == "incomplete"


def test_refuses_history_graph_mismatch(queued_run, mocked_comfy, monkeypatch):
    real = intake._history
    def wrong(base, pid):
        payload = real(base, pid)
        payload[pid]["prompt"][2]["2"]["inputs"]["seed"] = 666
        return payload
    monkeypatch.setattr(intake, "_history", wrong)
    with pytest.raises(ValueError, match="differs"):
        intake.collect_run(queued_run)
    assert list((queued_run / "outputs").iterdir()) == []


def test_tampered_input_blocks_collect(queued_run):
    (queued_run / "source.png").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="evidence mismatch"):
        intake.collect_run(queued_run)


def test_tampered_completed_output_blocks_replay(queued_run, mocked_comfy):
    evidence = intake.collect_run(queued_run)
    (queued_run / evidence["jobs"][0]["outputs"][0]["path"]).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Previously collected output changed"):
        intake.collect_run(queued_run)


@pytest.mark.parametrize("item", [
    {"filename": "../escaped.png", "subfolder": "", "type": "output"},
    {"filename": "/tmp/foo.png", "subfolder": "", "type": "output"},
    {"filename": "test.png", "subfolder": "../x", "type": "output"},
    {"filename": "test.png", "subfolder": "a\\b", "type": "output"},
    {"filename": "test.png", "subfolder": "", "type": "temp"},
    {"filename": "test.jpg", "subfolder": "", "type": "output"},
])
def test_unsafe_descriptors_blocked(item):
    with pytest.raises(ValueError):
        intake._safe_descriptor(item)


@pytest.mark.parametrize("server", ["http://malicious.invalid:8188", "https://localhost:8188",
                                    "http://127.0.0.1:8188/other"])
def test_external_servers_blocked(server, queued_run):
    with pytest.raises(ValueError):
        intake.collect_run(queued_run, server=server)


def test_png_required():
    with pytest.raises(ValueError):
        intake._png(b"not png")


def test_review_is_hash_bound_and_no_release(queued_run, mocked_comfy):
    evidence = intake.collect_run(queued_run)
    candidate = evidence["jobs"][0]["outputs"][0]["path"]
    file = intake.record_review(queued_run, candidate=candidate,
                                decision="keep", reviewer="local operator", note="composition manually checked")
    review = json.loads(file.read_text())
    assert review["release_gate_satisfied"] is False
    assert review["publication_approved"] is False
    with pytest.raises(FileExistsError):
        intake.record_review(queued_run, candidate=candidate,
                             decision="reject", reviewer="other", note="reject")
    with pytest.raises(ValueError):
        intake.record_review(queued_run, candidate=candidate,
                             decision="keep", reviewer="operator", note="")


def test_no_real_network_used(queued_run, mocked_comfy, monkeypatch):
    monkeypatch.setattr(intake, "_read_local", lambda *a, **k: pytest.fail("unexpected network"))
    assert intake.collect_run(queued_run)["intake_stage"] == "complete"
