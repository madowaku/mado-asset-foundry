"""MAF-M1.7.1: ComfyUI output intake and conservative composition proxy QA.

No asset is automatically accepted, licensed, packaged, or released.
"""
from __future__ import annotations

from io import BytesIO
from html import escape
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import urllib.parse
import urllib.request

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .composition_style import _url, digest

MAX_JSON = 3_000_000
MAX_IMAGE = 20_000_000
MAX_OUTPUTS_PER_JOB = 8
MAX_EDGE = 8192


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _read_local(base: str, suffix: str, *, limit: int) -> bytes:
    """Fetch only loopback HTTP: no proxies or redirects to external hosts."""
    url = _url(base, suffix.split("?", 1)[0])
    if "?" in suffix:
        url += "?" + suffix.split("?", 1)[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    request = urllib.request.Request(url, headers={"Accept": "application/json, image/png"})
    with opener.open(request, timeout=20) as response:
        declared = response.headers.get("Content-Length")
        if declared is not None and int(declared) > limit:
            raise ValueError("ComfyUI response exceeds size limit")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("ComfyUI response exceeds size limit")
    return data


def _history(server: str, prompt_id: str) -> dict:
    if not isinstance(prompt_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", prompt_id):
        raise ValueError("Invalid ComfyUI prompt_id")
    payload = json.loads(_read_local(server, "/history/" + prompt_id, limit=MAX_JSON))
    if not isinstance(payload, dict):
        raise ValueError("Malformed ComfyUI history response")
    return payload


def _safe_descriptor(item: dict) -> dict:
    if not isinstance(item, dict):
        raise ValueError("Malformed image descriptor")
    filename = item.get("filename")
    subfolder = item.get("subfolder", "")
    if (not isinstance(filename, str) or len(filename) > 255
            or not re.fullmatch(r"[\w. -]+\.png", filename, flags=re.IGNORECASE)
            or filename.startswith(".") or "/" in filename or "\\" in filename):
        raise ValueError("Unsafe ComfyUI output filename")
    if not isinstance(subfolder, str) or len(subfolder) > 512 or "\\" in subfolder:
        raise ValueError("Unsafe ComfyUI output subfolder")
    path = PurePosixPath(subfolder)
    if path.is_absolute() or any(part in (".", "..") for part in subfolder.split("/")):
        raise ValueError("Unsafe ComfyUI output subfolder")
    if item.get("type") != "output":
        raise ValueError("Only persisted output files are accepted")
    return {"filename": filename, "subfolder": subfolder, "type": "output"}


def _download(server: str, item: dict) -> bytes:
    descriptor = _safe_descriptor(item)
    query = urllib.parse.urlencode(descriptor)
    return _read_local(server, "/view?" + query, limit=MAX_IMAGE)


def _png(data: bytes) -> Image.Image:
    if len(data) > MAX_IMAGE or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Output must be a PNG within size limit")
    with Image.open(BytesIO(data)) as image:
        image.verify()
    with Image.open(BytesIO(data)) as image:
        if image.format != "PNG" or max(image.size) > MAX_EDGE:
            raise ValueError("Unsupported PNG dimensions")
        return image.convert("RGBA")


def _similarity(source: Image.Image, candidate: Image.Image) -> dict:
    """Low-frequency visual similarity heuristic, not a semantic pose validator."""
    def features(image: Image.Image) -> tuple[list[float], list[float]]:
        gray = image.convert("RGB").convert("L").resize((32, 32), Image.Resampling.BILINEAR)
        blurred = gray.filter(ImageFilter.GaussianBlur(2)).resize((16, 16))
        values = [float(v) for v in blurred.getdata()]
        mean = sum(values) / len(values)
        contrast = max(18.0, (sum((v - mean) ** 2 for v in values) / len(values)) ** .5)
        gray_normalized = [max(-2.0, min(2.0, (v - mean) / contrast)) for v in values]
        edge = gray.filter(ImageFilter.FIND_EDGES).resize((8, 8))
        edge_values = [float(v) for v in edge.getdata()]
        edge_max = max(1., max(edge_values))
        return gray_normalized, [v / edge_max for v in edge_values]

    a, ae = features(source)
    b, be = features(candidate)
    coarse_error = sum(abs(x - y) for x, y in zip(a, b)) / (len(a) * 4.)
    edge_error = sum(abs(x - y) for x, y in zip(ae, be)) / len(ae)
    score = round(max(0., 1. - 0.7 * coarse_error - 0.3 * edge_error), 4)
    source_ratio = source.width / source.height
    target_ratio = candidate.width / candidate.height
    return {
        "composition_proxy_similarity": score,
        "aspect_ratio_delta": round(abs(source_ratio - target_ratio), 6),
        "same_dimensions": source.size == candidate.size,
        "flags": (["large_visual_change_review"] if score < .5 else [])
                 + (["aspect_ratio_changed"] if abs(source_ratio - target_ratio) > .01 else []),
        "meaning": "Uncalibrated luminance/edge proxy; cannot verify characters, poses or style.",
        "decision": "needs_human_review",
    }


def _compare(source: Image.Image, output: Image.Image) -> bytes:
    """Before / after / absolute difference panel, never auto-accept output."""
    width, height, header = 320, 320, 26
    base = Image.new("RGB", (width * 3, height + header), "white")
    before = ImageOps.contain(source.convert("RGB"), (width, height))
    after = ImageOps.contain(output.convert("RGB"), (width, height))
    def paste_center(image: Image.Image, index: int) -> None:
        base.paste(image, (index * width + (width - image.width) // 2,
                           header + (height - image.height) // 2))
    paste_center(before, 0)
    paste_center(after, 1)
    diff_source = Image.new("RGB", (width, height), "white")
    diff_output = Image.new("RGB", (width, height), "white")
    diff_source.paste(before, ((width - before.width)//2, (height - before.height)//2))
    diff_output.paste(after, ((width - after.width)//2, (height - after.height)//2))
    paste_center(ImageChops.difference(diff_source, diff_output), 2)
    draw = ImageDraw.Draw(base)
    for i, name in enumerate(("SOURCE", "CANDIDATE", "PIXEL DIFFERENCE")):
        draw.text((i * width + 8, 7), name, fill="black")
    output_stream = BytesIO()
    base.save(output_stream, format="PNG")
    return output_stream.getvalue()


def _save_json(path: Path, data: dict) -> None:
    # Keep a complete valid evidence document even if interrupted during writing.
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _write_gallery(root: Path, evidence: dict) -> Path:
    """A static, local-only candidate gallery; all text and paths are escaped."""
    panels = []
    for job in evidence["jobs"]:
        for asset in job.get("outputs", []):
            score = asset["qa"]["composition_proxy_similarity"]
            comparison = escape(asset["comparison"], quote=True)
            candidate = escape(asset["path"], quote=True)
            panels.append(
                "<article><h2>Seed " + escape(str(job["seed"])) + "</h2>"
                + '<img src="' + comparison + '" alt="Source, candidate and pixel diff">'
                + "<p>Composition proxy: " + escape(str(score)) + " (not a pass/fail verdict)</p>"
                + "<p>Candidate: <code>" + candidate + "</code></p>"
                + "<p><strong>Human visual review required.</strong></p></article>"
            )
    model_name = escape(str(evidence["model_id"]))
    html = (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        '<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; '
        'img-src \'self\'; style-src \'unsafe-inline\'">'
        "<title>MAF Composition QA</title>"
        "<style>body{font:16px system-ui;margin:24px;max-width:1000px}"
        "article{border:1px solid #aaa;border-radius:12px;margin:18px 0;padding:12px}"
        "img{width:100%;height:auto}code{overflow-wrap:anywhere}</style>"
        "</head><body><h1>MAF-M1.7.1 Composition Review</h1>"
        "<p>Model: " + model_name + "</p>"
        "<p>Grayscale/edge scores are uncalibrated visual-change indicators, "
        "not character, pose, style, or legal clearance. Publication approved: NO.</p>"
        + ("".join(panels) if panels else "<p>No rendered candidates yet.</p>")
        + "</body></html>"
    )
    target = root / "gallery.html"
    temporary = root / "gallery.html.tmp"
    temporary.write_text(html, encoding="utf-8")
    temporary.replace(target)
    return target


def _history_graph(record: dict) -> dict | None:
    prompt = record.get("prompt")
    if isinstance(prompt, list) and len(prompt) > 2 and isinstance(prompt[2], dict):
        return prompt[2]
    if isinstance(prompt, dict) and isinstance(prompt.get("prompt"), dict):
        return prompt["prompt"]
    return None


def _resolve_outputs(record: dict, graph: dict) -> list[dict]:
    output_nodes = {
        node_id for node_id, node in graph.items()
        if isinstance(node, dict) and node.get("class_type") == "SaveImage"
    }
    recorded = record.get("outputs")
    if not isinstance(recorded, dict):
        raise ValueError("History is missing output nodes")
    assets: list[dict] = []
    for node_id in sorted(output_nodes):
        found = recorded.get(node_id, {})
        if not isinstance(found, dict):
            raise ValueError("Invalid SaveImage result")
        images = found.get("images", [])
        if not isinstance(images, list):
            raise ValueError("Invalid SaveImage image list")
        for item in images:
            assets.append(_safe_descriptor(item))
    if not 1 <= len(assets) <= MAX_OUTPUTS_PER_JOB:
        raise ValueError("Expected 1-8 PNG outputs from SaveImage nodes")
    if len({(d["filename"], d["subfolder"]) for d in assets}) != len(assets):
        raise ValueError("Duplicate output references in history")
    return assets


def collect_run(run_dir: str | Path, *, server: str = "http://127.0.0.1:8188") -> dict:
    root = Path(run_dir)
    if root.is_symlink() or any((root / item).is_symlink() for item in ("workflows", "outputs", "comparisons")):
        raise ValueError("Symlinked run/output directories are not accepted")
    evidence_path = root / "evidence.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    if evidence.get("schema") != "maf.composition_style.v1" or evidence.get("runtime") != "comfyui":
        raise ValueError("Only live M1.7 runs can be collected")
    _url(server, "/history")
    for filename, expected in (
        ("source.png", evidence.get("source_sha256")),
        ("template.json", evidence.get("workflow_sha256")),
    ):
        if not isinstance(expected, str) or digest(root / filename) != expected:
            raise ValueError(f"Input evidence mismatch: {filename}")
    with Image.open(root / "source.png") as image:
        source = image.convert("RGBA")
    jobs = evidence.get("jobs")
    if not isinstance(jobs, list) or not jobs:
        raise ValueError("Missing queued jobs")
    (root / "outputs").mkdir(exist_ok=True)
    (root / "comparisons").mkdir(exist_ok=True)
    for job in jobs:
        graph_path = root / "workflows" / f"seed-{job['seed']}.json"
        if job.get("workflow") != str(graph_path.relative_to(root)) or digest(graph_path) != job.get("workflow_sha256"):
            raise ValueError("Submitted workflow evidence changed")
        if job.get("status") == "rendered":
            for asset in job.get("outputs", []):
                for label in ("path", "comparison"):
                    item = root / asset[label]
                    expected = asset["sha256"] if label == "path" else asset["comparison_sha256"]
                    if digest(item) != expected:
                        raise ValueError(f"Previously collected output changed: {item}")
            continue
        if job.get("status") not in ("queued", "pending", "error"):
            continue
        graph = json.loads(graph_path.read_text(encoding="utf-8"))
        pid = job.get("prompt_id")
        history = _history(server, pid)
        record = history.get(pid)
        if record is None:
            job["intake_state"] = "pending"
            continue
        if not isinstance(record, dict):
            raise ValueError("Malformed history record")
        status = record.get("status", {})
        if not isinstance(status, dict):
            raise ValueError("Malformed history status")
        if status.get("completed") is not True:
            job["intake_state"] = "pending"
            continue
        if status.get("status_str") != "success":
            job["intake_state"] = "execution_failed"
            job["status"] = "error"
            continue
        observed_graph = _history_graph(record)
        if observed_graph is not None and observed_graph != graph:
            raise ValueError("ComfyUI history workflow differs from queued workflow")
        descriptors = _resolve_outputs(record, graph)
        staging: list[tuple[Path, bytes]] = []
        qa: list[dict] = []
        for index, item in enumerate(descriptors):
            content = _download(server, item)
            candidate = _png(content)
            out = root / "outputs" / f"seed-{job['seed']}-{index:02d}.png"
            sheet = root / "comparisons" / f"seed-{job['seed']}-{index:02d}.png"
            if out.exists() or sheet.exists():
                raise FileExistsError(f"Refusing to overwrite existing candidate: {out}")
            comparison = _compare(source, candidate)
            result = {
                "path": str(out.relative_to(root)), "sha256": hashlib.sha256(content).hexdigest(),
                "comparison": str(sheet.relative_to(root)),
                "comparison_sha256": hashlib.sha256(comparison).hexdigest(),
                "size": list(candidate.size), "source": item,
                "qa": _similarity(source, candidate),
            }
            staging.extend(((out, content), (sheet, comparison)))
            qa.append(result)
        written: list[Path] = []
        try:
            for path, content in staging:
                path.write_bytes(content)
                written.append(path)
        except Exception:
            for path in written:
                path.unlink(missing_ok=True)
            raise
        job["outputs"] = qa
        job["status"] = "rendered"
        job["intake_state"] = "awaiting_human_review"
        job["history_graph_verified"] = observed_graph is not None
        _save_json(evidence_path, evidence)
    evidence["intake_stage"] = (
        "complete" if all(job.get("status") == "rendered" for job in jobs)
        else "incomplete"
    )
    evidence["publication_approved"] = False
    _save_json(evidence_path, evidence)
    _write_gallery(root, evidence)
    return evidence


def record_review(run_dir: str | Path, *, candidate: str,
                  decision: str, reviewer: str, note: str) -> Path:
    """Human visual verdict only. This does not satisfy MAF release/license gates."""
    root = Path(run_dir)
    if decision not in ("keep", "rework", "reject") or not reviewer.strip() or not note.strip():
        raise ValueError("Explicit human decision, reviewer and note required")
    if not re.fullmatch(r"outputs/seed-[0-9]+-[0-9]{2}\.png", candidate):
        raise ValueError("Invalid candidate path")
    evidence = json.loads((root / "evidence.json").read_text(encoding="utf-8"))
    assets = [asset for job in evidence.get("jobs", []) for asset in job.get("outputs", [])]
    match = next((a for a in assets if a["path"] == candidate), None)
    if match is None:
        raise ValueError("Candidate not present in intake evidence")
    if digest(root / candidate) != match["sha256"]:
        raise ValueError("Candidate content changed since collection")
    if digest(root / match["comparison"]) != match["comparison_sha256"]:
        raise ValueError("Comparison evidence changed since collection")
    reviews = root / "reviews"
    reviews.mkdir(exist_ok=True)
    output = reviews / (Path(candidate).stem + ".json")
    if output.exists() or output.is_symlink():
        raise FileExistsError("Review already recorded; no silent overwrite")
    review = {
        "schema": "maf.composition_style.review.v1",
        "candidate": candidate,
        "candidate_sha256": match["sha256"],
        "comparison_sha256": match["comparison_sha256"],
        "decision": decision, "reviewer": reviewer.strip(), "note": note.strip(),
        "publication_approved": False,
        "release_gate_satisfied": False,
    }
    output.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="MAF-M1.7.1 result intake + fidelity QA")
    sub = parser.add_subparsers(dest="command", required=True)
    intake = sub.add_parser("collect", help="Fetch completed outputs from local ComfyUI")
    intake.add_argument("run_dir")
    intake.add_argument("--server", default="http://127.0.0.1:8188")
    review = sub.add_parser("review", help="Hash-bound human review (no release)")
    review.add_argument("run_dir")
    review.add_argument("--candidate", required=True, help="e.g. outputs/seed-42-00.png")
    review.add_argument("--decision", choices=("keep", "rework", "reject"), required=True)
    review.add_argument("--reviewer", required=True)
    review.add_argument("--note", required=True)
    args = parser.parse_args()
    if args.command == "collect":
        result = collect_run(args.run_dir, server=args.server)
        print(json.dumps({"intake_stage": result["intake_stage"],
                          "jobs": [{"seed": j["seed"], "status": j["status"],
                                    "outputs": len(j.get("outputs", []))}
                                   for j in result["jobs"]]}, indent=2))
    else:
        print(record_review(args.run_dir, candidate=args.candidate,
                            decision=args.decision, reviewer=args.reviewer, note=args.note))


if __name__ == "__main__":
    main()
