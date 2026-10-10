"""MAF-M1.3: local-only ComfyUI native image-to-3D acquisition bridge.

The bridge uses an operator-exported API-format graph. It does not install
ComfyUI, fetch model weights, execute third-party Python, publish an asset, or
treat a GLB download as Godot/visual/license approval.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import shutil
import struct
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from PIL import Image, UnidentifiedImageError

from .io import write_json

MAX_GRAPH_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_GLB_BYTES = 100 * 1024 * 1024
MAX_JSON_BYTES = 8 * 1024 * 1024
NODE_ID = re.compile(r"[0-9]+")
SAFE_PART = re.compile(r"[A-Za-z0-9_.-]+")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _safe_filename(value: object) -> str:
    if (not isinstance(value, str) or not SAFE_PART.fullmatch(value)
            or value in {".", ".."}):
        raise ValueError("ComfyUI returned an unsafe filename")
    return value


def _safe_subfolder(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("ComfyUI returned an invalid subfolder")
    if not value:
        return ""
    parts = value.replace("\\", "/").split("/")
    if any(not SAFE_PART.fullmatch(x) or x in {".", ".."} for x in parts):
        raise ValueError("ComfyUI returned an unsafe subfolder")
    return "/".join(parts)


def _validate_image(path: Path) -> tuple[str, str]:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(f"Local input image unavailable or symlinked: {path}")
    if path.stat().st_size > MAX_IMAGE_BYTES or path.stat().st_size == 0:
        raise ValueError("Input image must be nonempty and at most 25 MiB")
    try:
        with Image.open(path) as image:
            fmt = image.format
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError("Input is not a valid image") from exc
    suffixes = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}
    if fmt not in suffixes:
        raise ValueError("Comfy3D accepts PNG, JPEG and WEBP only")
    return str(fmt), suffixes[str(fmt)]


def load_api_graph(
    workflow: str | Path,
    *,
    image_node: str | None = None,
    save_node: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate a ComfyUI API export, not the visual editor 'nodes/links' JSON."""
    source = Path(workflow)
    if source.is_symlink() or not source.is_file():
        raise FileNotFoundError(f"API workflow missing or symlinked: {source}")
    if source.stat().st_size > MAX_GRAPH_BYTES:
        raise ValueError("API workflow exceeds 4 MiB")
    try:
        graph = json.loads(source.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Workflow must be UTF-8 JSON") from exc
    if not isinstance(graph, dict) or "nodes" in graph:
        raise ValueError("Export the workflow with File > Export Workflow (API), not Save")
    if not 1 <= len(graph) <= 512:
        raise ValueError("API graph must contain 1 to 512 nodes")
    classes: set[str] = set()
    for node_id, node in graph.items():
        if (not isinstance(node_id, str) or not NODE_ID.fullmatch(node_id)
                or not isinstance(node, dict)
                or not isinstance(node.get("class_type"), str)
                or not isinstance(node.get("inputs"), dict)):
            raise ValueError(f"Invalid API graph node: {node_id}")
        classes.add(node["class_type"])
    if not any("Trellis2" in cls or "Pixal3D" in cls for cls in classes):
        raise ValueError("Expected native Trellis2 or Pixal3D nodes in the API graph")

    def choose(kind: str, selected: str | None) -> str:
        candidates = sorted(
            (key for key, node in graph.items() if node["class_type"] == kind),
            key=int,
        )
        if selected is not None:
            if selected not in candidates:
                raise ValueError(f"Node {selected!r} is not a {kind} node")
            return selected
        if len(candidates) != 1:
            raise ValueError(
                f"Expected exactly one {kind} node, found {len(candidates)}; "
                f"select one explicitly with --{'image-node' if kind == 'LoadImage' else 'save-node'}"
            )
        return candidates[0]

    input_id = choose("LoadImage", image_node)
    output_id = choose("SaveGLB", save_node)
    if not isinstance(graph[input_id]["inputs"].get("image"), str):
        raise ValueError("Selected LoadImage node needs an image filename input")
    mesh_link = graph[output_id]["inputs"].get("mesh")
    if (not isinstance(mesh_link, list) or len(mesh_link) != 2
            or str(mesh_link[0]) not in graph
            or not isinstance(mesh_link[1], int)):
        raise ValueError("Selected SaveGLB must have a connected mesh input")
    model = ("pixal3d+trellis2" if any("Pixal3D" in x for x in classes)
             and any("Trellis2" in x for x in classes)
             else "pixal3d" if any("Pixal3D" in x for x in classes)
             else "trellis2")
    return graph, {
        "schema_version": "1.3",
        "workflow_sha256": _file_digest(source),
        "image_node": input_id,
        "save_node": output_id,
        "model_family": model,
        "node_count": len(graph),
        "node_classes": sorted(classes),
        "validation": "api_graph_structural_only",
        "models_installed_verified": False,
        "runtime_compatible_verified": False,
    }


def inspect_glb(data: bytes) -> dict[str, int]:
    """Lightweight structural check. Not a mesh-topology or Godot QA pass."""
    if len(data) < 20 or len(data) > MAX_GLB_BYTES:
        raise ValueError("GLB is empty, truncated or above 100 MiB")
    magic, version, size = struct.unpack_from("<4sII", data)
    if magic != b"glTF" or version != 2 or size != len(data):
        raise ValueError("Invalid GLB 2.0 header or declared size")
    chunk_length, chunk_type = struct.unpack_from("<I4s", data, 12)
    if chunk_type != b"JSON" or chunk_length <= 0 or 20 + chunk_length > len(data):
        raise ValueError("GLB has no valid JSON chunk")
    try:
        document = json.loads(data[20:20 + chunk_length].decode("utf-8").rstrip(" \x00"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("GLB JSON is invalid") from exc
    if not isinstance(document, dict) or document.get("asset", {}).get("version") != "2.0":
        raise ValueError("GLB is missing glTF 2.0 asset metadata")
    meshes = document.get("meshes", [])
    if (not isinstance(meshes, list) or not meshes
            or not all(isinstance(m, dict) and isinstance(m.get("primitives"), list)
                       and m["primitives"] for m in meshes)):
        raise ValueError("GLB has no nonempty mesh primitives")
    return {
        "mesh_count": len(meshes),
        "material_count": len(document.get("materials", [])),
        "texture_count": len(document.get("textures", [])),
        "image_count": len(document.get("images", [])),
    }


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise ValueError("ComfyUI HTTP redirect refused")


class Comfy3DClient:
    """Small stdlib HTTP client. The server must be loopback, with no proxy."""
    def __init__(self, base_url: str = "http://127.0.0.1:8188") -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in
                {"localhost", "127.0.0.1", "::1"}
                or not parsed.port or parsed.username or parsed.password
                or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
            raise ValueError("ComfyUI URL must be plain HTTP at localhost/127.0.0.1/[::1] with a port")
        self.base_url = base_url.rstrip("/")
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), _NoRedirect()
        )

    def _request(self, method: str, path: str, *, payload: bytes | None = None,
                 content_type: str | None = None, limit: int = MAX_JSON_BYTES) -> bytes:
        if not path.startswith("/") or path.startswith("//"):
            raise ValueError("Invalid ComfyUI API path")
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.base_url + path, data=payload, headers=headers, method=method
        )
        try:
            with self._opener.open(request, timeout=30) as response:
                data = response.read(limit + 1)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"ComfyUI {method} {path.split('?')[0]} failed: {exc}") from exc
        if len(data) > limit:
            raise ValueError("ComfyUI response exceeds configured limit")
        return data

    def _json(self, method: str, path: str, *, payload: object | None = None) -> Any:
        raw = self._request(
            method, path,
            payload=(json.dumps(payload).encode("utf-8") if payload is not None else None),
            content_type=("application/json" if payload is not None else None),
        )
        try:
            return json.loads(raw)
        except (UnicodeError, ValueError) as exc:
            raise ValueError("ComfyUI returned invalid JSON") from exc

    def upload(self, path: Path, suffix: str) -> str:
        name = "maf-" + uuid.uuid4().hex + suffix
        boundary = "maf" + uuid.uuid4().hex
        image_bytes = path.read_bytes()
        body = (
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
            f"Content-Type: image/{'jpeg' if suffix == '.jpg' else suffix.lstrip('.')}\r\n\r\n"
        ).encode("ascii") + image_bytes + (
            f"\r\n--{boundary}\r\nContent-Disposition: form-data; name=\"overwrite\"\r\n\r\n"
            f"false\r\n--{boundary}--\r\n"
        ).encode("ascii")
        response = self._request(
            "POST", "/upload/image", payload=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        try:
            info = json.loads(response)
        except (ValueError, UnicodeError) as exc:
            raise ValueError("ComfyUI upload returned invalid JSON") from exc
        if not isinstance(info, dict) or info.get("type", "input") != "input":
            raise ValueError("ComfyUI upload did not return an input file")
        if _safe_subfolder(info.get("subfolder", "")):
            raise ValueError("ComfyUI input subfolders are not supported by M1.3")
        return _safe_filename(info.get("name"))

    def submit(self, graph: dict[str, Any]) -> str:
        reply = self._json("POST", "/prompt", payload={
            "prompt": graph, "client_id": str(uuid.uuid4())
        })
        if not isinstance(reply, dict) or not isinstance(reply.get("prompt_id"), str):
            raise ValueError(f"ComfyUI rejected the workflow: {str(reply)[:500]}")
        return reply["prompt_id"]

    def await_glb(self, prompt_id: str, save_node: str, *,
                  timeout_seconds: int = 900, poll_interval: float = 2.0,
                  clock: Callable[[], float] = time.monotonic,
                  sleep: Callable[[float], None] = time.sleep) -> tuple[dict, dict]:
        deadline = clock() + timeout_seconds
        while True:
            record = self._json("GET", "/history/" + urllib.parse.quote(prompt_id, safe=""))
            if not isinstance(record, dict):
                raise ValueError("Invalid ComfyUI history response")
            history = record.get(prompt_id)
            if history is not None:
                if not isinstance(history, dict):
                    raise ValueError("Malformed ComfyUI history entry")
                status = history.get("status") or {}
                if not isinstance(status, dict):
                    raise ValueError("Malformed ComfyUI status entry")
                if status.get("status_str") == "error":
                    raise RuntimeError("ComfyUI execution failed; inspect local ComfyUI logs")
                if status.get("completed") is True or status.get("status_str") == "success":
                    outputs = history.get("outputs") or {}
                    selected = outputs.get(save_node) if isinstance(outputs, dict) else None
                    models = selected.get("3d") if isinstance(selected, dict) else None
                    if not isinstance(models, list) or len(models) != 1:
                        raise ValueError("SaveGLB must return exactly one 3D output")
                    result = models[0]
                    if not isinstance(result, dict):
                        raise ValueError("Malformed SaveGLB output")
                    if result.get("type") != "output":
                        raise ValueError("SaveGLB result must be in ComfyUI output storage")
                    filename = _safe_filename(result.get("filename"))
                    if not filename.lower().endswith(".glb"):
                        raise ValueError("SaveGLB output is not a GLB file")
                    return {
                        "filename": filename, "subfolder": _safe_subfolder(result.get("subfolder", "")),
                        "type": "output",
                    }, {"status_str": status.get("status_str"), "completed": True}
            if clock() >= deadline:
                raise TimeoutError("Timed out waiting for ComfyUI; prompt may continue on local server")
            sleep(min(poll_interval, max(0, deadline - clock())))

    def download(self, result: dict) -> bytes:
        params = urllib.parse.urlencode(result)
        return self._request("GET", "/view?" + params, limit=MAX_GLB_BYTES)


def plan_comfy3d(image: str | Path, workflow: str | Path, *,
                 image_node: str | None = None,
                 save_node: str | None = None) -> dict[str, Any]:
    source = Path(image)
    image_format, _ = _validate_image(source)
    _, plan = load_api_graph(workflow, image_node=image_node, save_node=save_node)
    return {
        **plan,
        "input_sha256": _file_digest(source),
        "input_format": image_format,
        "input_bytes": source.stat().st_size,
        "execution": "not_started",
        "requires_explicit_live": True,
        "human_review_required": True,
        "license_review_required": True,
        "godot_qa_required": True,
        "publication_approved": False,
    }


def run_comfy3d(image: str | Path, workflow: str | Path, *,
                output_dir: str | Path,
                client: Comfy3DClient | None = None,
                image_node: str | None = None,
                save_node: str | None = None,
                timeout_seconds: int = 900,
                poll_interval: float = 2.0) -> tuple[dict[str, Any], Path]:
    """Perform one explicit live probe and persist evidence, even on remote failure."""
    if not 1 <= timeout_seconds <= 3600:
        raise ValueError("timeout_seconds must be between 1 and 3600")
    if not 0.1 <= poll_interval <= 30:
        raise ValueError("poll_interval must be between 0.1 and 30")
    source = Path(image).resolve(strict=True)
    workflow_source = Path(workflow).resolve(strict=True)
    # Check the original paths too, so symlinks are rejected before resolve().
    plan = plan_comfy3d(image, workflow, image_node=image_node, save_node=save_node)
    graph, _ = load_api_graph(workflow, image_node=image_node, save_node=save_node)
    _, suffix = _validate_image(Path(image))
    destination = Path(output_dir).absolute()
    if destination.exists():
        raise FileExistsError(f"Comfy3D run already exists: {destination}")
    if destination.parent.is_symlink():
        raise ValueError("Output directory parent must not be symlinked")
    destination.mkdir(parents=True)
    inputs = destination / "inputs"
    inputs.mkdir()
    image_copy = inputs / ("source" + suffix)
    workflow_copy = inputs / "workflow-api.json"
    report: dict[str, Any] = {
        **plan, "status": "running",
        "schema_version": "1.3", "prompt_id": None,
        "asset_paths": [], "failure": None,
        "structural_glb_valid": False, "runtime_qa_passed": False,
        "visual_qa_passed": False, "asset_pack_redistribution_approved": False,
    }
    evidence = destination / "evidence.json"
    try:
        shutil.copyfile(source, image_copy)
        shutil.copyfile(workflow_source, workflow_copy)
        if (_file_digest(image_copy) != plan["input_sha256"]
                or _file_digest(workflow_copy) != plan["workflow_sha256"]):
            raise ValueError("Snapshot changed while copying")
        session = client or Comfy3DClient()
        uploaded = session.upload(image_copy, suffix)
        graph = copy.deepcopy(graph)
        graph[plan["image_node"]]["inputs"]["image"] = uploaded
        # Scope files to one MAF probe. Do not overwrite ComfyUI's existing outputs.
        graph[plan["save_node"]]["inputs"]["filename_prefix"] = (
            "maf3d/maf-" + uuid.uuid4().hex
        )
        prompt_json = json.dumps(graph, sort_keys=True, separators=(",", ":")).encode("utf-8")
        (inputs / "submitted-prompt.json").write_bytes(prompt_json)
        report["submitted_prompt_sha256"] = _digest(prompt_json)
        prompt_id = session.submit(graph)
        report["prompt_id"] = prompt_id
        write_json(evidence, report)
        result, history_status = session.await_glb(
            prompt_id, plan["save_node"], timeout_seconds=timeout_seconds,
            poll_interval=poll_interval,
        )
        data = session.download(result)
        shape = inspect_glb(data)
        saved = destination / "asset.glb"
        saved.write_bytes(data)
        report.update({
            "status": "awaiting_3d_qa",
            "structural_glb_valid": True,
            "glb_sha256": _digest(data),
            "glb_bytes": len(data),
            "asset_paths": ["asset.glb"],
            "saveglb_result": result,
            "execution_status": history_status,
            "glb_structure": shape,
        })
    except Exception as exc:
        report.update({
            "status": "failed", "failure": f"{type(exc).__name__}: {exc}",
        })
    finally:
        write_json(evidence, report)
    return report, destination
