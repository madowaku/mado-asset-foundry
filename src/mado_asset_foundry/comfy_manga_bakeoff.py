"""Explicit opt-in localhost ComfyUI manga image bake-off.

Uses operator-supplied *API-format* ComfyUI workflows. Never installs plugins,
downloads weights, trains a LoRA, or treats generated output as quality approval.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import html
import io
import json
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from PIL import Image

from .moss_bakeoff import MODELS, compile_layout, inspect_images

MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_PNG_BYTES = 32 * 1024 * 1024
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
Image.MAX_IMAGE_PIXELS = 20_000_000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(value: Any) -> str:
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ValueError("ID must match [A-Za-z0-9][A-Za-z0-9_-]{0,63}")
    return value


def local_path(root: Path, value: str) -> Path:
    relative = Path(value)
    if not isinstance(value, str) or relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise ValueError("workflow paths must be relative to the config directory")
    path = root / relative
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("workflow missing, symlinked, or outside config directory")
    return path


def load_plan(config_path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str]]:
    config_path = config_path.resolve(strict=True)
    plan = json.loads(config_path.read_text(encoding="utf-8"))
    arms, cases = plan.get("arms"), plan.get("cases")
    if not isinstance(arms, dict) or set(arms) != set(MODELS):
        raise ValueError("plan requires all four named model arms")
    if not isinstance(cases, list) or not cases or len(cases) > 12:
        raise ValueError("plan requires 1..12 cases")
    seen = set()
    for case in cases:
        case_id = safe_name(case["id"])
        if case_id in seen:
            raise ValueError("duplicate case")
        seen.add(case_id)
        if not isinstance(case.get("prompt"), str) or not case["prompt"].strip():
            raise ValueError("each case requires a prompt")
        for key in ("width", "height"):
            value = case.get(key)
            if type(value) is not int or not 64 <= value <= 4096 or value % 16:
                raise ValueError("case dimensions must be multiples of 16 in 64..4096")
        if type(case.get("seed")) is not int or case["seed"] < 0:
            raise ValueError("seed must be nonnegative integer")
        if "moss_layout" in case:
            layout = case["moss_layout"]
            if (layout["width"], layout["height"]) != (case["width"], case["height"]):
                raise ValueError("MOSS layout dimensions differ from case")
            compile_layout(layout)
    workflows: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    for model in MODELS:
        arm = arms[model]
        path = local_path(config_path.parent, arm["workflow"])
        raw = path.read_bytes()
        workflow = json.loads(raw)
        if not isinstance(workflow, dict) or not workflow:
            raise ValueError("ComfyUI workflow must be API node mapping, not UI graph")
        for node in workflow.values():
            if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict) or not isinstance(node.get("class_type"), str):
                raise ValueError("invalid workflow: use Save(API Format)")
        bindings = arm.get("bindings")
        if not isinstance(bindings, dict) or set(bindings) != {"positive", "seed", "width", "height"}:
            raise ValueError("arm bindings must name positive, seed, width and height")
        used = set()
        for name, target in bindings.items():
            if not isinstance(target, list) or len(target) != 2 or any(not isinstance(x, str) for x in target):
                raise ValueError("binding must be [node_id, input_name]")
            node_id, input_name = target
            if node_id not in workflow or input_name not in workflow[node_id]["inputs"]:
                raise ValueError("binding not present in workflow")
            used.add((node_id, input_name))
        if len(used) != 4:
            raise ValueError("bindings must target distinct inputs")
        save_node = arm.get("save_node")
        if save_node not in workflow or workflow[save_node]["class_type"] != "SaveImage":
            raise ValueError("save_node must be an existing SaveImage node")
        for node_id, inputs in arm.get("overrides", {}).items():
            if node_id not in workflow or not isinstance(inputs, dict):
                raise ValueError("override node missing")
            for name, value in inputs.items():
                if name not in workflow[node_id]["inputs"] or isinstance(value, (dict, list)):
                    raise ValueError("override must target an existing scalar input")
        classes = {node["class_type"] for node in workflow.values()}
        if model.startswith("moss-") and "MOSSImageHFLoader" not in classes:
            raise ValueError("MOSS arm must use the official MOSSImageHFLoader")
        if model == "moss-sft-lora":
            def model_path_has_lora(node_id: str, seen: set[str] | None = None) -> bool:
                seen = set() if seen is None else seen
                if node_id in seen or node_id not in workflow:
                    return False
                seen.add(node_id)
                node = workflow[node_id]
                if "lora" in node["class_type"].lower():
                    return True
                upstream = node["inputs"].get("model")
                return (isinstance(upstream, list) and len(upstream) == 2
                        and isinstance(upstream[0], str)
                        and model_path_has_lora(upstream[0], seen))
            samplers = [node["inputs"].get("model") for node in workflow.values()
                        if node["class_type"] in ("KSampler", "KSamplerAdvanced")]
            if not any(isinstance(link, list) and len(link) == 2
                       and isinstance(link[0], str) and model_path_has_lora(link[0])
                       for link in samplers):
                raise ValueError("LoRA must be connected to a sampler MODEL input")
        workflows[model] = workflow
        hashes[model] = digest(raw)
    return plan, workflows, hashes


def render_prompt(case: dict[str, Any], model: str) -> str:
    if model.startswith("moss-") and "moss_layout" in case:
        return json.dumps(compile_layout(case["moss_layout"]), ensure_ascii=False, separators=(",", ":"))
    return case["prompt"]


def patch_workflow(workflow: dict[str, Any], arm: dict[str, Any],
                   case: dict[str, Any], model: str) -> dict[str, Any]:
    result = copy.deepcopy(workflow)
    for node_id, fields in arm.get("overrides", {}).items():
        result[node_id]["inputs"].update(fields)
    for name, value in (("positive", render_prompt(case, model)),
                        ("seed", case["seed"]), ("width", case["width"]), ("height", case["height"])):
        node_id, input_name = arm["bindings"][name]
        result[node_id]["inputs"][input_name] = value
    return result


class ComfyClient:
    """Localhost-only HTTP without redirects, credentials, or external destinations."""

    def __init__(self, url: str):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1") or parsed.username or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise ValueError("only http://127.0.0.1:PORT or http://[::1]:PORT is allowed")
        self.url = url.rstrip("/")
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise ValueError("redirects are disallowed")
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, method: str, route: str, payload: dict[str, Any] | None = None,
                limit: int = MAX_JSON_BYTES) -> bytes:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(self.url + route, data=data, method=method,
                                         headers={"Content-Type": "application/json"} if data is not None else {})
        with self.opener.open(request, timeout=20) as response:
            raw = response.read(limit + 1)
        if len(raw) > limit:
            raise ValueError("ComfyUI returned an oversized response")
        return raw

    def json(self, method: str, route: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        result = json.loads(self.request(method, route, payload))
        if not isinstance(result, dict):
            raise ValueError("expected ComfyUI JSON object")
        return result


def sample_vram_mib() -> int | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=5, check=True)
        return max(int(line.strip()) for line in result.stdout.splitlines() if line.strip())
    except (ValueError, subprocess.SubprocessError, OSError):
        return None


def checked_png(data: bytes, width: int, height: int) -> None:
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("ComfyUI /view did not return PNG")
    with Image.open(io.BytesIO(data)) as image:
        image.verify()
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "PNG" or image.size != (width, height):
            raise ValueError("ComfyUI returned wrong PNG dimensions")


def fetch_single_output(client: ComfyClient, history: dict[str, Any], save_node: str,
                        width: int, height: int) -> bytes:
    outputs = history.get("outputs", {})
    images = outputs.get(save_node, {}).get("images", []) if isinstance(outputs, dict) else []
    if not isinstance(images, list) or len(images) != 1:
        raise ValueError("expected exactly one SaveImage output per job")
    image = images[0]
    if image.get("type") != "output":
        raise ValueError("only persisted ComfyUI output images accepted")
    filename = image.get("filename")
    subfolder = image.get("subfolder", "")
    if not isinstance(filename, str) or not filename or not isinstance(subfolder, str):
        raise ValueError("invalid image output metadata")
    params = urllib.parse.urlencode({"filename": filename, "subfolder": subfolder, "type": "output"})
    raw = client.request("GET", "/view?" + params, limit=MAX_PNG_BYTES)
    checked_png(raw, width, height)
    return raw


def run_job(client: ComfyClient, workflow: dict[str, Any], save_node: str,
            case: dict[str, Any], timeout_seconds: int, poll_seconds: float) -> tuple[bytes, dict[str, Any]]:
    started = time.monotonic()
    first_vram = sample_vram_mib()
    peak_vram = first_vram
    response = client.json("POST", "/prompt", {"prompt": workflow})
    prompt_id = response.get("prompt_id")
    if not isinstance(prompt_id, str) or not prompt_id:
        raise ValueError("ComfyUI rejected workflow: " + str(response.get("error", response))[:500])
    while time.monotonic() - started < timeout_seconds:
        observed = sample_vram_mib()
        if observed is not None:
            peak_vram = max(peak_vram or 0, observed)
        payload = client.json("GET", "/history/" + urllib.parse.quote(prompt_id, safe=""))
        history = payload.get(prompt_id)
        if isinstance(history, dict):
            status = history.get("status", {})
            if not isinstance(status, dict):
                status = {}
            if status.get("status_str") == "error" or status.get("completed") is False and status.get("status_str") in ("failed", "error"):
                raise ValueError("ComfyUI execution failed: " + str(status.get("messages", []))[:500])
            if status.get("completed") is True and status.get("status_str") == "success":
                png = fetch_single_output(client, history, save_node, case["width"], case["height"])
                return png, {"prompt_id": prompt_id,
                             "elapsed_queue_and_execution_seconds": round(time.monotonic() - started, 3),
                             "gpu_memory_used_mib_observed_max": peak_vram,
                             "gpu_memory_used_mib_start": first_vram}
        time.sleep(poll_seconds)
    raise TimeoutError("ComfyUI prompt timed out; it may still be running: " + prompt_id)


def run_plan(config_path: Path, output_dir: Path, client: ComfyClient,
             timeout_seconds: int = 900, poll_seconds: float = 2) -> dict[str, Any]:
    if timeout_seconds < 1 or poll_seconds < 0:
        raise ValueError("invalid polling settings")
    plan, workflows, workflow_hashes = load_plan(config_path)
    if output_dir.exists():
        raise FileExistsError("output directory already exists; never overwrite generated evidence")
    output_dir.mkdir(parents=True)
    images_dir = output_dir / "images"
    images_dir.mkdir()
    config_hash = digest(config_path.read_bytes())
    report: dict[str, Any] = {"schema": "maf.moss-comfy-live.v1", "status": "running",
        "config_sha256": config_hash, "workflow_sha256": workflow_hashes,
        "generation_executed": False, "generation_attempted": False,
        "quality_approved": False, "rights_approved": False,
        "comfyui_system_stats": None, "cases": [], "jobs": [], "error": None}
    try:
        report["comfyui_system_stats"] = client.json("GET", "/system_stats")
        object_info = client.json("GET", "/object_info")
        for model in MODELS:
            missing = {node["class_type"] for node in workflows[model].values()} - set(object_info)
            if missing:
                raise ValueError("ComfyUI lacks required nodes for " + model + ": " + ", ".join(sorted(missing)))
        for case in plan["cases"]:
            entry: dict[str, Any] = {"id": case["id"], "seed": case["seed"],
                "width": case["width"], "height": case["height"], "samples": []}
            report["cases"].append(entry)
            for model in MODELS:
                arm = plan["arms"][model]
                patched = patch_workflow(workflows[model], arm, case, model)
                job: dict[str, Any] = {"case": case["id"], "model": model, "status": "submitted",
                                        "patched_workflow_sha256": digest(json.dumps(patched, sort_keys=True, ensure_ascii=False).encode())}
                report["jobs"].append(job)
                report["generation_attempted"] = True
                png, stats = run_job(client, patched, arm["save_node"], case, timeout_seconds, poll_seconds)
                report["generation_executed"] = True
                filename = case["id"] + "__" + model + ".png"
                path = images_dir / filename
                with path.open("xb") as image_stream:
                    image_stream.write(png)
                entry["samples"].append({"model": model, "path": "images/" + filename, "sha256": digest(png)})
                job.update(stats)
                job["status"] = "completed"
        proof = inspect_images({"cases": report["cases"]}, output_dir)
        if not all(case["paired_complete"] for case in proof["cases"]):
            raise ValueError("incomplete model comparison")
        report["status"] = "awaiting_human_review"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)[:1000]
        raise
    finally:
        (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def build_gallery(report_path: Path, html_path: Path) -> None:
    """Offline, immutable-image-hash-checked comparison; no release approval."""
    root = report_path.resolve(strict=True).parent
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("schema") != "maf.moss-comfy-live.v1":
        raise ValueError("not a ComfyUI live report")
    cards = []
    for case in report["cases"]:
        for sample in case["samples"]:
            path = local_path(root, sample["path"])
            if digest(path.read_bytes()) != sample["sha256"]:
                raise ValueError("image hash mismatch; refusing gallery")
            cards.append('<article><h3>' + html.escape(case["id"]) + ' / ' + html.escape(sample["model"]) +
                         '</h3><img alt="Generated sample" loading="lazy" src="' +
                         html.escape(path.relative_to(html_path.parent.resolve()).as_posix(), quote=True) +
                         '"><p>SHA-256: <code>' + html.escape(sample["sha256"]) + '</code></p></article>')
    if html_path.exists():
        raise FileExistsError("gallery already exists")
    content = ('<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
               '<title>MAF ComfyUI Manga Bake-off</title><style>'
               'body{font:16px system-ui;margin:2rem;background:#101622;color:#f2f5ff}'
               '.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem}'
               'article{background:#202a3a;padding:1rem;border-radius:12px;min-width:0}'
               'img{width:100%;height:auto;max-height:550px;object-fit:contain;background:#111}'
               'code{overflow-wrap:anywhere;font-size:.7rem}</style><body><h1>Manga Bake-off Visual Evidence</h1>'
               '<p>Unreviewed images, not quality or licensing approval. Score text fidelity, layout, identity and artifacts manually.</p>'
               '<div class="gallery">' + ''.join(cards) + '</div></body></html>')
    html_path.write_text(content, encoding="utf-8")



def create_scorecard(report_path: Path, output_path: Path) -> None:
    """Prepare a SHA-bound human scorecard without filling in fictional ratings."""
    root = report_path.resolve(strict=True).parent
    raw = report_path.read_bytes()
    report = json.loads(raw)
    if report.get("schema") != "maf.moss-comfy-live.v1" or report.get("status") != "awaiting_human_review":
        raise ValueError("only complete live runs are eligible for a scorecard")
    metrics = ("text_fidelity", "panel_order", "character_identity", "bbox_adherence", "artifact_control")
    samples = []
    for case in report["cases"]:
        if len(case["samples"]) != len(MODELS):
            raise ValueError("incomplete case")
        for sample in case["samples"]:
            path = local_path(root, sample["path"])
            if digest(path.read_bytes()) != sample["sha256"]:
                raise ValueError("scorecard image hash mismatch")
            samples.append({"case": case["id"], "model": sample["model"], "image_sha256": sample["sha256"],
                            "scores": {metric: None for metric in metrics}, "na_reasons": {},
                            "notes": ""})
    if output_path.exists():
        raise FileExistsError("scorecard already exists")
    scorecard = {"schema": "maf.moss-comfy-review.v1", "report_sha256": digest(raw),
                 "reviewer": "", "status": "unreviewed", "samples": samples,
                 "interpretation": "1=weak, 5=strong; use N/A only with na_reasons and never infer license"}
    output_path.write_text(json.dumps(scorecard, ensure_ascii=False, indent=2), encoding="utf-8")


def validate_scorecard(report_path: Path, scorecard_path: Path) -> dict[str, Any]:
    """Validate human entries and image integrity; this is NOT rights/release approval."""
    root = report_path.resolve(strict=True).parent
    report_raw = report_path.read_bytes()
    report = json.loads(report_raw)
    card = json.loads(scorecard_path.read_text(encoding="utf-8"))
    if report.get("status") != "awaiting_human_review" or card.get("schema") != "maf.moss-comfy-review.v1" or card.get("report_sha256") != digest(report_raw):
        raise ValueError("scorecard does not match completed live report")
    reviewer = card.get("reviewer")
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError("human reviewer name required")
    expected = {(case["id"], sample["model"]): sample["sha256"]
                for case in report["cases"] for sample in case["samples"]}
    seen = set()
    for sample in card.get("samples", []):
        key = (sample.get("case"), sample.get("model"))
        if key in seen or key not in expected or sample.get("image_sha256") != expected[key]:
            raise ValueError("duplicate/unmatched scorecard sample")
        seen.add(key)
        image = next(x for c in report["cases"] if c["id"] == key[0]
                     for x in c["samples"] if x["model"] == key[1])
        if digest(local_path(root, image["path"]).read_bytes()) != expected[key]:
            raise ValueError("reviewed image was modified")
        scores = sample.get("scores", {})
        if set(scores) != {"text_fidelity", "panel_order", "character_identity", "bbox_adherence", "artifact_control"}:
            raise ValueError("missing/unexpected scores")
        reasons = sample.get("na_reasons", {})
        if not isinstance(reasons, dict):
            raise ValueError("invalid N/A reasons")
        for metric, value in scores.items():
            if value == "N/A":
                if not isinstance(reasons.get(metric), str) or not reasons[metric].strip():
                    raise ValueError("N/A needs a written reason")
            elif type(value) is not int or not 1 <= value <= 5:
                raise ValueError("scores must be integers 1..5 or N/A with reason")
    if seen != set(expected):
        raise ValueError("missing human scores")
    return {"visual_review_recorded": True, "reviewer": reviewer,
            "scored_images": len(seen), "rights_approved": False,
            "release_approved": False, "quality_approved": False}

def main() -> None:
    parser = argparse.ArgumentParser(description="MAF-M1.7.2a real localhost ComfyUI bake-off")
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight")
    pre.add_argument("config", type=Path)
    live = sub.add_parser("run")
    live.add_argument("config", type=Path)
    live.add_argument("--output", type=Path, required=True)
    live.add_argument("--url", default="http://127.0.0.1:8188")
    live.add_argument("--timeout", type=int, default=900)
    live.add_argument("--live", action="store_true", help="explicitly allow trusted local workflows to execute")
    gallery = sub.add_parser("gallery")
    gallery.add_argument("report", type=Path)
    gallery.add_argument("--output", type=Path, required=True)
    scorecard = sub.add_parser("scorecard")
    scorecard.add_argument("report", type=Path)
    scorecard.add_argument("--output", type=Path, required=True)
    review = sub.add_parser("validate-review")
    review.add_argument("report", type=Path)
    review.add_argument("scorecard", type=Path)
    args = parser.parse_args()
    if args.command == "preflight":
        plan, workflows, hashes = load_plan(args.config)
        print(json.dumps({"valid": True, "cases": len(plan["cases"]), "arms": list(workflows),
                          "workflow_sha256": hashes}, indent=2))
    elif args.command == "run":
        if not args.live:
            parser.error("run requires --live (executes operator-supplied ComfyUI nodes)")
        result = run_plan(args.config, args.output, ComfyClient(args.url), args.timeout)
        print(json.dumps({"status": result["status"], "jobs": len(result["jobs"]),
                          "report": str(args.output / "report.json")}, ensure_ascii=False))
    elif args.command == "gallery":
        build_gallery(args.report, args.output)
        print(str(args.output))
    elif args.command == "scorecard":
        create_scorecard(args.report, args.output)
        print(str(args.output))
    else:
        print(json.dumps(validate_scorecard(args.report, args.scorecard), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
