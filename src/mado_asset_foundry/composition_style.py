"""MAF-M1.7: deterministic, license-aware ComfyUI img2img execution bridge.

The user supplies a ComfyUI API-format workflow and explicit node IDs. We do not
guess model-specific Anima nodes, download weights, or execute arbitrary plugins.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import urllib.error
import urllib.parse
import urllib.request
from uuid import uuid4

from PIL import Image


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _node(workflow: dict, node_id: str, field: str) -> dict:
    node = workflow.get(str(node_id))
    if not isinstance(node, dict) or not isinstance(node.get("inputs"), dict):
        raise ValueError(f"Missing ComfyUI node/inputs: {node_id}")
    if field not in node["inputs"]:
        raise ValueError(f"Missing node {node_id} input {field}")
    return node["inputs"]


def _url(base: str, suffix: str) -> str:
    parsed = urllib.parse.urlsplit(base)
    if (parsed.hostname not in ("localhost", "127.0.0.1", "::1")
            or parsed.scheme != "http" or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        raise ValueError("ComfyUI URL must be plain loopback HTTP, e.g. http://127.0.0.1:8188")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, suffix, "", ""))


def compile_workflow(template: dict, *, image_node: str, sampler_node: str,
                     input_name: str, denoise: float, seed: int) -> dict:
    if not isinstance(template, dict) or not template:
        raise ValueError("Expected non-empty API-format ComfyUI workflow JSON")
    if not (0.0 <= denoise <= 1.0):
        raise ValueError("denoise must be between 0 and 1")
    if not (0 <= seed < 2**64):
        raise ValueError("seed outside unsigned 64-bit range")
    result = copy.deepcopy(template)
    _node(result, image_node, "image")["image"] = input_name
    _node(result, sampler_node, "denoise")["denoise"] = denoise
    _node(result, sampler_node, "seed")["seed"] = seed
    if not any(isinstance(n, dict) and n.get("class_type") == "SaveImage" for n in result.values()):
        raise ValueError("Workflow must contain a SaveImage node to retain output")
    return result


def _http_json(url: str, data: dict | None = None, *, timeout: int = 20) -> dict:
    payload = None if data is None else json.dumps(data).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("ComfyUI returned non-object JSON")
    return result


def _upload(base: str, path: Path, *, timeout: int = 30) -> str:
    boundary = "maf" + uuid4().hex
    filename = "maf-" + uuid4().hex + ".png"
    content = path.read_bytes()
    data = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\n"
        "Content-Type: image/png\r\n\r\n"
    ).encode() + content + f"\r\n--{boundary}--\r\n".encode()
    request = urllib.request.Request(
        _url(base, "/upload/image"), data=data, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict) or not isinstance(result.get("name"), str):
        raise ValueError("Unexpected ComfyUI upload response")
    if result.get("subfolder") or result.get("type", "input") != "input":
        raise ValueError("Unexpected ComfyUI upload location")
    return result["name"]


def build_run(source: str | Path, template_path: str | Path, output: str | Path, *,
              image_node: str, sampler_node: str, denoise: float = 0.35,
              seeds: tuple[int, ...] = (42,), model_id: str,
              model_license_review: str, live: bool = False,
              server: str = "http://127.0.0.1:8188") -> Path:
    """Prepare immutable local evidence, optionally upload and queue explicit jobs.

    Enqueueing is NOT generation success. Inspect ComfyUI history/outputs separately.
    """
    src, workflow_src, dest = Path(source), Path(template_path), Path(output)
    if not src.is_file() or src.is_symlink() or not workflow_src.is_file() or workflow_src.is_symlink():
        raise ValueError("Source image and workflow must be existing regular files")
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"Run already exists: {dest}")
    if not model_id.strip() or not model_license_review.strip():
        raise ValueError("Explicit model provenance and license review notes are required")
    if not seeds or len(seeds) > 4 or len(set(seeds)) != len(seeds):
        raise ValueError("Provide 1-4 unique seeds for pilot generation")
    if src.stat().st_size > 30_000_000 or workflow_src.stat().st_size > 2_000_000:
        raise ValueError("Input exceeds safety limit")
    with Image.open(src) as im:
        im.verify()
    with Image.open(src) as im:
        if im.format != "PNG" or im.width > 8192 or im.height > 8192:
            raise ValueError("Requires PNG at most 8192 px per dimension")
    template = json.loads(workflow_src.read_text(encoding="utf-8"))
    compiled = [compile_workflow(template, image_node=image_node,
                sampler_node=sampler_node, input_name="maf-input.png",
                denoise=denoise, seed=seed) for seed in seeds]
    if live:
        _url(server, "/prompt")
    dest.mkdir(parents=True)
    (dest / "workflows").mkdir()
    shutil.copyfile(src, dest / "source.png")
    shutil.copyfile(workflow_src, dest / "template.json")
    evidence = {
        "schema": "maf.composition_style.v1", "stage": "prepared",
        "source_sha256": digest(dest / "source.png"),
        "workflow_sha256": digest(dest / "template.json"),
        "model_id": model_id, "model_license_review": model_license_review,
        "denoise": denoise, "seeds": list(seeds),
        "image_node": image_node, "sampler_node": sampler_node,
        "publication_approved": False, "human_visual_review": "pending",
        "runtime": "comfyui" if live else "offline", "jobs": [],
    }
    try:
        input_name = _upload(server, dest / "source.png") if live else "maf-input.png"
        for idx, (seed, wf) in enumerate(zip(seeds, compiled)):
            wf[image_node]["inputs"]["image"] = input_name
            file = dest / "workflows" / f"seed-{seed}.json"
            file.write_text(json.dumps(wf, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            job = {"seed": seed, "workflow": str(file.relative_to(dest)),
                   "workflow_sha256": digest(file), "status": "prepared"}
            if live:
                response = _http_json(_url(server, "/prompt"),
                    {"prompt": wf, "client_id": "maf-" + uuid4().hex})
                if not isinstance(response.get("prompt_id"), str):
                    raise ValueError("ComfyUI did not acknowledge prompt_id")
                job.update(prompt_id=response["prompt_id"], status="queued")
            evidence["jobs"].append(job)
        evidence["stage"] = "queued" if live else "prepared"
    except Exception as exc:
        evidence["stage"] = "failed"
        evidence["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        (dest / "evidence.json").write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return dest


def main() -> None:
    parser = argparse.ArgumentParser(description="MAF-M1.7 Anima/ComfyUI style bridge")
    parser.add_argument("source")
    parser.add_argument("workflow", help="Exported ComfyUI API-format workflow JSON")
    parser.add_argument("output", help="New evidence directory (no overwrite)")
    parser.add_argument("--image-node", required=True)
    parser.add_argument("--sampler-node", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--license-review", required=True)
    parser.add_argument("--denoise", type=float, default=0.35)
    parser.add_argument("--seeds", default="42", help="Comma-delimited, up to 4 unique seeds")
    parser.add_argument("--live", action="store_true", help="Upload and queue to local ComfyUI")
    parser.add_argument("--server", default="http://127.0.0.1:8188")
    args = parser.parse_args()
    seeds = tuple(int(x) for x in args.seeds.split(","))
    print(build_run(args.source, args.workflow, args.output, image_node=args.image_node,
          sampler_node=args.sampler_node, model_id=args.model_id,
          model_license_review=args.license_review, denoise=args.denoise,
          seeds=seeds, live=args.live, server=args.server))


if __name__ == "__main__":
    main()
