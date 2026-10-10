"""MAF-M1.0: local-only Cockpit API for the M0.9 production flow.

The browser never chooses executable paths or arbitrary local files. Existing
license, runtime, image-capture and human-review gates remain authoritative.
"""
from __future__ import annotations

import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .asset_flow import inspect_asset_flow, review_asset_flow, run_asset_flow
from .cockpit_review import VisualDecision, inspect_visual, record_visual
from .asset_sources import _sha256
from .attribution_bridge import _read_object
from .visual_gallery import GalleryReview

RUN_ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
RECIPE_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*\.ya?ml$")


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    recipe: str = Field(min_length=1, max_length=128)


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reviewer: str = Field(min_length=3, max_length=120)
    notes: str = Field(min_length=5, max_length=2000)
    visual_approved: StrictBool
    attribution_approved: StrictBool
    rights_approved_for_game_embedding: StrictBool

    @field_validator("reviewer", "notes")
    @classmethod
    def must_have_visible_content(cls, value: str, info) -> str:
        required = 3 if info.field_name == "reviewer" else 5
        if len(value.strip()) < required:
            raise ValueError("Review fields must contain meaningful text")
        return value.strip()


def _recipe_file(recipes_root: Path, value: str) -> Path:
    if not RECIPE_NAME.fullmatch(value) or ".." in value:
        raise HTTPException(400, "Invalid recipe name")
    path = recipes_root / value
    if path.is_symlink() or not path.is_file() or path.resolve().parent != recipes_root.resolve():
        raise HTTPException(404, "Recipe not found")
    return path


def _flow_dir(workspace: Path, flow_id: str) -> Path:
    if not RUN_ID.fullmatch(flow_id):
        raise HTTPException(400, "Invalid flow ID")
    folder = workspace / flow_id
    if folder.is_symlink() or folder.resolve().parent != workspace.resolve():
        raise HTTPException(400, "Invalid flow directory")
    if (folder / "summary.json").is_symlink():
        raise HTTPException(400, "Symlinked flow summary is not allowed")
    if not (folder / "summary.json").is_file():
        raise HTTPException(404, "Flow not found")
    return folder


def _artifact(folder: Path, *parts: str) -> Path:
    path = folder
    for part in parts:
        path = path / part
        if path.is_symlink():
            raise HTTPException(400, "Symlinked artifact is not allowed")
    if not path.is_file() or not path.resolve().is_relative_to(folder.resolve()):
        raise HTTPException(404, "Artifact not found")
    return path


def _flow_payload(folder: Path) -> dict:
    try:
        data = inspect_asset_flow(folder)
        flow_id = data["flow_id"]
        gallery_path = _artifact(folder, "gallery", flow_id, "report.json")
        gallery = _read_object(gallery_path)
        expected = [
            (_artifact(folder, "plan.json"), data.get("plan_sha256")),
            (_artifact(folder, "runtime", flow_id, "report.json"), data.get("runtime_report_sha256")),
            (gallery_path, data.get("gallery_report_sha256")),
            (_artifact(folder, "gallery", flow_id, "gallery.png"), data.get("screenshot_sha256")),
            (_artifact(folder, "gallery", flow_id, "CREDITS.md"), data.get("credits_sha256")),
            (_artifact(folder, "godot", flow_id, "asset_manifest.json"), data.get("manifest_sha256")),
        ]
        if any(not isinstance(digest, str) or _sha256(path) != digest for path, digest in expected):
            raise ValueError("Stored pipeline artifacts no longer match their evidence")
        if any(gallery.get(key) != data.get(key) for key in
               ("screenshot_sha256", "credits_sha256", "manifest_sha256")):
            raise ValueError("Gallery provenance disagrees with the run summary")
        for record in data.get("assets", []):
            asset_id = record.get("asset_id")
            if not isinstance(asset_id, str) or not RUN_ID.fullmatch(asset_id):
                raise ValueError("Invalid asset identity")
            if _sha256(_artifact(folder, "inputs", asset_id, "asset.png")) != record.get("original_sha256"):
                raise ValueError("Source asset snapshot has changed")
            if _sha256(_artifact(folder, "reports", asset_id, "report.json")) != record.get("intake_report_sha256"):
                raise ValueError("Intake report has changed")
            license_hash = record.get("original_license_sha256")
            if license_hash is not None and _sha256(_artifact(folder, "inputs", asset_id, "LICENSE.txt")) != license_hash:
                raise ValueError("License evidence snapshot has changed")
        assets = []
        for summary_asset in data.get("assets", []):
            asset_id = summary_asset.get("asset_id")
            if not isinstance(asset_id, str) or not RUN_ID.fullmatch(asset_id):
                raise ValueError("Invalid asset ID in saved flow")
            report = _read_object(_artifact(folder, "reports", asset_id, "report.json"))
            assets.append({
                "asset_id": asset_id,
                "title": report.get("title"),
                "creator": report.get("creator"),
                "source_id": report.get("source_id"),
                "asset_url": report.get("asset_url"),
                "license": report.get("license_spdx"),
                "license_status": report.get("status"),
                "attribution": report.get("attribution"),
                "license_evidence_url": report.get("license_evidence_url"),
                "license_evidence_sha256": report.get("license_evidence_sha256"),
                "sha256": report.get("sha256"),
                "reviewed_by_human": report.get("reviewed_by_human"),
            })
        return {
            "flow_id": flow_id,
            "status": data["status"],
            "review_status": data["review_status"],
            "publication_approved": False,
            "asset_count": data["source_count"],
            "godot_version": data["godot_version"],
            "runtime_status": data["godot_runtime"],
            "gallery_status": data["visual_gallery"],
            "screenshot_sha256": gallery["screenshot_sha256"],
            "credits_sha256": gallery["credits_sha256"],
            "manifest_sha256": gallery["manifest_sha256"],
            "assets": assets,
            "visual_review": inspect_visual(folder, {"flow_id": flow_id, "screenshot_sha256": gallery["screenshot_sha256"], "credits_sha256": gallery["credits_sha256"], "manifest_sha256": gallery["manifest_sha256"], "assets": assets}),
        }
    except (FileNotFoundError, KeyError, ValueError, TypeError, OSError) as exc:
        raise HTTPException(status_code=409, detail="Flow evidence invalid or incomplete") from exc


def _mutation_allowed(request: Request) -> None:
    # Custom header enforces preflight on cross-site browser requests. No CORS.
    if request.headers.get("X-MAF-Action") != "cockpit":
        raise HTTPException(403, "Missing local mutation header")
    origin = request.headers.get("origin")
    if origin:
        host = request.headers.get("host", "")
        if origin != f"{request.url.scheme}://{host}":
            raise HTTPException(403, "Cross-origin mutation refused")


def create_app(
    workspace: str | Path = "runs/asset-flows",
    *,
    recipes: str | Path = "recipes/asset-flows",
    godot_bin: str | None = None,
    virtual_display: bool = False,
    timeout: int = 120,
) -> FastAPI:
    if timeout < 1 or timeout > 600:
        raise ValueError("timeout must be between 1 and 600")
    workspace_path = Path(workspace).resolve()
    recipes_path = Path(recipes).resolve()
    static_dir = Path(__file__).with_name("ui") / "cockpit"
    app = FastAPI(title="MADO Asset Foundry Cockpit", version="1.1.0")
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "[::1]", "testserver"]
    )
    app.mount("/static", StaticFiles(directory=static_dir), name="cockpit-static")
    lock = Lock()
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="maf-cockpit")
    jobs: dict[str, dict] = {}
    stages = ("intake", "attribution", "runtime", "gallery", "evidence")
    active_job: list[str | None] = [None]

    @app.middleware("http")
    async def secure_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; font-src 'self'; "
            "base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        )
        return response

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(static_dir / "index.html")

    @app.get("/api/status")
    def status() -> dict:
        with lock:
            active = active_job[0]
        return {"version": "1.1.0", "can_start": godot_bin is not None,
                "active_job": active, "publication_enabled": False}

    @app.get("/api/recipes")
    def list_recipes() -> dict:
        available: list[dict] = []
        if recipes_path.is_dir():
            for path in sorted(recipes_path.iterdir()):
                if RECIPE_NAME.fullmatch(path.name) and ".." not in path.name and not path.is_symlink() and path.is_file():
                    available.append({"name": path.name})
        return {"recipes": available}

    @app.get("/api/flows")
    def list_flows() -> dict:
        flows = []
        if workspace_path.exists():
            for folder in workspace_path.iterdir():
                if not folder.is_dir() or folder.is_symlink() or not RUN_ID.fullmatch(folder.name):
                    continue
                if not (folder / "summary.json").is_file() or (folder / "summary.json").is_symlink():
                    continue
                try:
                    payload = inspect_asset_flow(folder)
                    flows.append({
                        "flow_id": payload["flow_id"],
                        "status": payload["status"],
                        "asset_count": payload["source_count"],
                        "review_status": payload["review_status"],
                        "publication_approved": False,
                    })
                except (FileNotFoundError, KeyError, ValueError, TypeError, OSError):
                    continue
        return {"flows": sorted(flows, key=lambda v: v["flow_id"])}

    @app.get("/api/flows/{flow_id}")
    def get_flow(flow_id: str) -> dict:
        folder = _flow_dir(workspace_path, flow_id)
        return _flow_payload(folder)

    @app.get("/api/flows/{flow_id}/gallery")
    def gallery_image(flow_id: str) -> FileResponse:
        folder = _flow_dir(workspace_path, flow_id)
        _flow_payload(folder)
        return FileResponse(_artifact(folder, "gallery", flow_id, "gallery.png"),
                            media_type="image/png")

    @app.get("/api/flows/{flow_id}/credits")
    def credits_file(flow_id: str) -> FileResponse:
        folder = _flow_dir(workspace_path, flow_id)
        _flow_payload(folder)
        return FileResponse(_artifact(folder, "gallery", flow_id, "CREDITS.md"),
                            media_type="text/plain; charset=utf-8")

    @app.get("/api/flows/{flow_id}/assets/{asset_id}/image")
    def asset_image(flow_id: str, asset_id: str) -> FileResponse:
        folder = _flow_dir(workspace_path, flow_id)
        _flow_payload(folder)
        if not RUN_ID.fullmatch(asset_id):
            raise HTTPException(400, "Invalid asset ID")
        _artifact(folder, "reports", asset_id, "report.json")
        return FileResponse(_artifact(folder, "godot", flow_id, "assets", f"{asset_id}.png"),
                            media_type="image/png")

    @app.post("/api/actions/run", status_code=202)
    def start_run(body: RunRequest, request: Request) -> dict:
        _mutation_allowed(request)
        if godot_bin is None:
            raise HTTPException(503, "Godot binary is not configured for the cockpit")
        recipe_file = _recipe_file(recipes_path, body.recipe)
        with lock:
            if active_job[0] is not None:
                raise HTTPException(409, "A flow is already running")
            job_id = uuid4().hex
            jobs[job_id] = {"job_id": job_id, "status": "running", "recipe": body.recipe,
                            "flow_id": None, "error": None, "current_stage": None,
                            "stages": [{"stage": step, "status": "pending"} for step in stages]}
            active_job[0] = job_id

        def on_progress(stage: str, status: str) -> None:
            if stage not in stages or status not in {"running", "completed", "failed"}:
                return
            with lock:
                job = jobs[job_id]
                for item in job["stages"]:
                    if item["stage"] == stage:
                        item["status"] = status
                job["current_stage"] = stage

        def worker() -> None:
            try:
                summary, _ = run_asset_flow(
                    recipe_file, godot_bin=godot_bin, workspace=workspace_path,
                    virtual_display=virtual_display, timeout=timeout,
                    force=False, progress=on_progress,
                )
                with lock:
                    jobs[job_id]["status"] = "completed"
                    jobs[job_id]["flow_id"] = summary["flow_id"]
            except Exception as exc:
                with lock:
                    jobs[job_id]["status"] = "failed"
                    jobs[job_id]["error"] = str(exc)[:500]
            finally:
                with lock:
                    if active_job[0] == job_id:
                        active_job[0] = None

        executor.submit(worker)
        return {"job_id": job_id, "status": "running"}

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str) -> dict:
        with lock:
            job = jobs.get(job_id)
            if job is None:
                raise HTTPException(404, "Job not found")
            return {**job, "stages": [dict(item) for item in job["stages"]]}

    @app.post("/api/flows/{flow_id}/assets/{asset_id}/visual")
    def save_visual(flow_id: str, asset_id: str, body: VisualDecision, request: Request) -> dict:
        _mutation_allowed(request)
        folder = _flow_dir(workspace_path, flow_id)
        with lock:
            if active_job[0] is not None:
                raise HTTPException(409, "Cannot assess visuals during an active job")
            data = _flow_payload(folder)
            try:
                result = record_visual(folder, data, asset_id, body)
            except KeyError:
                raise HTTPException(404, "Asset not found") from None
            except (ValueError, FileNotFoundError, OSError) as exc:
                raise HTTPException(409, "Visual evidence changed or review is locked") from exc
        return {"visual_review": result, "publication_approved": False}

    @app.post("/api/flows/{flow_id}/review")
    def approve_review(flow_id: str, body: ReviewRequest, request: Request) -> dict:
        _mutation_allowed(request)
        if not (body.visual_approved and body.attribution_approved and body.rights_approved_for_game_embedding):
            raise HTTPException(422, "All three human approvals are required")
        folder = _flow_dir(workspace_path, flow_id)
        with lock:
            if active_job[0] is not None:
                raise HTTPException(409, "Cannot review while a flow is running")
            if ((folder / "review" / "release-check.json").exists()
                    or (folder / "review" / "human-attestation.json").exists()
                    or (folder / "review" / "human-attestation.json").is_symlink()):
                raise HTTPException(409, "Review has already been recorded")
            flow = _flow_payload(folder)
            if not flow["visual_review"]["ready_for_final_review"]:
                raise HTTPException(409, "Review every asset as pass before final approval")
            gallery_report = _read_object(_artifact(folder, "gallery", flow_id, "report.json"))
            review = GalleryReview(
                project_id=flow_id,
                reviewer=body.reviewer.strip(),
                notes=body.notes.strip(),
                screenshot_sha256=gallery_report["screenshot_sha256"],
                credits_sha256=gallery_report["credits_sha256"],
                manifest_sha256=gallery_report["manifest_sha256"],
                visual_approved=True,
                attribution_approved=True,
                rights_approved_for_game_embedding=True,
            )
            # Ephemeral attestation is passed through the existing M0.9.3 gate.
            # The signed human decision is kept beside the gate result afterward.
            with tempfile.TemporaryDirectory(prefix="maf-attestation-") as tmp:
                temp = Path(tmp) / "review.json"
                temp.write_text(review.model_dump_json(indent=2), encoding="utf-8")
                try:
                    result, _ = review_asset_flow(folder, review_path=temp)
                except (FileNotFoundError, FileExistsError, ValueError, OSError) as exc:
                    raise HTTPException(409, "Review evidence changed or invalid") from exc
                if result["status"] != "human_release_review_passed":
                    raise HTTPException(409, "Review gate rejected the evidence")
                attestation = folder / "review" / "human-attestation.json"
                signed = review.model_dump(mode="json")
                signed["visual_review_sha256"] = _sha256(
                    _artifact(folder, "review", "visual-decisions.json")
                )
                with attestation.open("x", encoding="utf-8") as handle:
                    import json
                    json.dump(signed, handle, ensure_ascii=False, indent=2)
                    handle.write("\n")
        return {"status": result["status"], "reviewer": result["reviewer"],
                "publication_approved": False, "asset_pack_redistribution_approved": False}

    return app


def serve_cockpit(
    workspace: str | Path = "runs/asset-flows",
    *,
    recipes: str | Path = "recipes/asset-flows",
    godot_bin: str | None = None,
    virtual_display: bool = False,
    host: str = "127.0.0.1",
    port: int = 4174,
) -> None:
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("M1.0 Cockpit binds to loopback only")
    import uvicorn
    uvicorn.run(
        create_app(workspace, recipes=recipes, godot_bin=godot_bin,
                   virtual_display=virtual_display),
        host=host, port=port,
    )
